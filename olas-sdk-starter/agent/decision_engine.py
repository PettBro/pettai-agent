import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Tuple, Callable

from langchain.chat_models import init_chat_model
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

from .pett_websocket_client import PettWebSocketClient
from .pett_tools import PettTools

logger = logging.getLogger(__name__)


class PetDecisionEngine:
    """Centralizes model, tools binding, and AI-driven decisions for the pet."""

    def __init__(self, websocket_client: PettWebSocketClient):
        self.websocket_client = websocket_client
        self.pett_tools = PettTools(self.websocket_client)
        # Optional prompt recorder: (kind, prompt, context)
        self._prompt_recorder: Optional[
            Callable[[str, str, Optional[Dict[str, Any]]], None]
        ] = None

        # Initialize model, memory, tools and agent once
        self.model = init_chat_model("gpt-4o", model_provider="openai")
        self.memory = MemorySaver()
        self.tools = self.pett_tools.create_tools()
        self.bound_model = self.model.bind_tools(self.tools)  # type: ignore

        self.system_message = (
            "You are PetDecisionEngine, an autonomous pet caretaker. "
            "Always decide the next best action given the pet's current "
            "stats and available tools. "
            "Prefer actions that improve low stats "
            "(hunger, hygiene, energy, happiness). "
            "When hunger is low, analyze provided mall JSON to determine "
            "which owned consumable increases hunger the most, then use it. "
            "Respond succinctly with the decided action(s) and parameters, "
            "and then execute using bound tools."
        )
        self.agent = create_react_agent(
            self.bound_model,
            self.tools,
            checkpointer=self.memory,
            prompt=self.system_message,
        )

    def set_prompt_recorder(
        self, recorder: Optional[Callable[[str, str, Optional[Dict[str, Any]]], None]]
    ) -> None:
        """Set a callback to record prompts sent to the LLM."""
        self._prompt_recorder = recorder

    async def choose_food_from_kitchen(self, kitchen_json: str) -> Optional[str]:
        """Ask the model to pick the owned consumable that best increases hunger.

        Returns an uppercase consumable id like "BURGER" if found, else None.
        """
        if not kitchen_json or kitchen_json.startswith("❌"):
            logger.warning(
                "[DecisionEngine] No valid mall data provided for food choice"
            )
            return None

        user_prompt = (
            "Given this mall payload (JSON), pick ONE owned food consumable "
            "that maximally increases hunger. "
            "Return ONLY the consumable id in UPPERCASE (e.g., BURGER). "
            "If none owned, return NONE.\n\n"
            f"KITCHEN_JSON:\n{kitchen_json}"
        )

        # Log prompt (trimmed to 200 chars)
        prompt_preview = (
            user_prompt[:200] + "..." if len(user_prompt) > 200 else user_prompt
        )
        logger.info(f"[DecisionEngine] 🧠 Prompt: {prompt_preview}")
        if self._prompt_recorder:
            try:
                self._prompt_recorder("food_choice", user_prompt, None)
            except Exception:
                pass

        messages = [
            {"role": "system", "content": self.system_message},
            {"role": "user", "content": user_prompt},
        ]

        config = {"configurable": {"thread_id": "pet_food_choice"}}
        result = await self.agent.ainvoke({"messages": messages}, config=config)
        text = ""
        if isinstance(result, dict) and "messages" in result and result["messages"]:
            last = result["messages"][-1]
            text = getattr(last, "content", "") or ""

        choice = (text or "").strip().upper()

        # Log the decision
        decision_text = choice if choice and choice != "NONE" else "No food selected"
        logger.info(f"[DecisionEngine] ✅ Food Decision: {decision_text}")

        if not choice or choice == "NONE":
            return None
        # Basic sanity: only allow simple token-like ids
        if not choice.isupper():
            logger.warning(f"[DecisionEngine] Invalid food choice format: {choice}")
            return None
        return choice

    async def decide_and_act(self, pet_data: Dict[str, Any]) -> None:
        """High-level decision: may call tools directly based on model output."""
        # Build a compact context for the agent
        context = {
            "pet": pet_data,
            "stats": pet_data.get("PetStats", {}),
        }

        user_prompt = (
            "Decide the next best action for the pet based on these stats. "
            "If hunger is low, you may request mall data by calling the "
            "appropriate tool, "
            "analyze it, then choose and use the best owned food. "
            "Keep responses short.\n\n"
            f"CONTEXT:\n{json.dumps(context)})"
        )

        # Log prompt (trimmed to 200 chars)
        prompt_preview = (
            user_prompt[:200] + "..." if len(user_prompt) > 200 else user_prompt
        )
        logger.info(f"[DecisionEngine] 🧠 Prompt: {prompt_preview}")
        if self._prompt_recorder:
            try:
                self._prompt_recorder("decide_and_act", user_prompt, context)
            except Exception:
                pass

        messages = [
            {"role": "system", "content": self.system_message},
            {"role": "user", "content": user_prompt},
        ]

        config = {"configurable": {"thread_id": "pet_decide_and_act"}}
        result = await self.agent.ainvoke({"messages": messages}, config=config)

        # Log the decision/action taken
        if isinstance(result, dict) and "messages" in result and result["messages"]:
            last = result["messages"][-1]
            response = getattr(last, "content", "") or ""
            response_preview = (
                response[:200] + "..." if len(response) > 200 else response
            )
            logger.info(f"[DecisionEngine] ✅ Decision: {response_preview}")
        else:
            logger.info("[DecisionEngine] ✅ Decision completed (no response content)")

    async def feed_best_owned_food(self) -> bool:
        """Fetch mall data and ask the model which owned food to use."""
        logger.info("[DecisionEngine] 🍔 Starting AI-driven food selection process")

        mall = await self.websocket_client.get_kitchen_data(timeout=10)
        choice = await self.choose_food_from_kitchen(mall)

        if not choice:
            logger.warning("[DecisionEngine] ❌ No suitable food found to feed pet")
            return False

        logger.info(f"[DecisionEngine] 🍖 Feeding pet: {choice}")
        success = await self.websocket_client.use_consumable(choice)

        if success:
            logger.info(f"[DecisionEngine] ✅ Successfully fed pet with {choice}")
        else:
            logger.warning(f"[DecisionEngine] ❌ Failed to feed pet with {choice}")

        return success
