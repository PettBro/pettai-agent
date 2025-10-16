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

    async def choose_food_from_kitchen(
        self, kitchen_json: str, pet_stats: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Ask the model to pick the owned consumable that best increases hunger.

        Returns the consumable instance ID if found, else None.
        """
        if not kitchen_json or kitchen_json.startswith("❌"):
            logger.warning(
                "[DecisionEngine] No valid mall data provided for food choice"
            )
            return None

        # Parse and summarize kitchen payload to a compact list the model can reason about
        try:
            payload = (
                json.loads(kitchen_json)
                if isinstance(kitchen_json, str)
                else kitchen_json
            )
            raw_items: List[Dict[str, Any]] = payload.get("consumables", []) or []
            logger.info(
                f"[DecisionEngine] Found {len(raw_items)} consumables in kitchen"
            )
        except Exception as e:
            logger.warning(f"[DecisionEngine] Failed to parse kitchen JSON: {e}")
            return None

        def as_food_summary(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            bp = item.get("blueprint", {}) or {}
            if (bp.get("type") or "").upper() != "FOOD":
                return None
            # Use instance ID if available, otherwise fall back to blueprintID
            consumable_id = item.get("id") or str(item.get("blueprintID", "")).upper()
            if not consumable_id:
                return None
            return {
                "id": consumable_id,
                "blueprintID": str(item.get("blueprintID", "")).upper(),
                "name": bp.get("name", ""),
                "hunger": int(bp.get("hunger", 0) or 0),
                "happiness": int(bp.get("happiness", 0) or 0),
                "health": int(bp.get("health", 0) or 0),
            }

        food_items: List[Dict[str, Any]] = []
        for it in raw_items:
            summary = as_food_summary(it)
            if summary and summary.get("id"):
                food_items.append(summary)

        if not food_items:
            logger.info("[DecisionEngine] No FOOD items available in kitchen payload")
            return None

        logger.info(f"[DecisionEngine] Found {len(food_items)} food items in kitchen")

        # Deterministic fallback: best hunger, then happiness desc, then health desc
        def score_food(x: Dict[str, Any]) -> Tuple[int, int, int]:
            return (
                int(x.get("hunger", 0) or 0),
                int(x.get("happiness", 0) or 0),
                int(x.get("health", -999999) or -999999),
            )

        best_food = max(food_items, key=score_food)

        # Build stats context
        stats_context = ""
        if pet_stats:
            stats_json = json.dumps(pet_stats, ensure_ascii=False)
            stats_context = f"CURRENT_PET_STATS:\n{stats_json}\n\n"

        # Strengthened prompt: provide concise summary and clear instructions
        summary_json = json.dumps(food_items[:20], ensure_ascii=False)
        user_prompt = (
            "You are choosing ONE food blueprintID item to feed the pet.\n"
            f"{stats_context}"
            "Rules:\n"
            "- Only choose from FOOD items provided below (ignore potions/special).\n"
            "- Consider the pet's current stats when making the decision.\n"
            "- Maximize hunger increase as primary objective.\n"
            "- If there is a tie on hunger, prefer higher happiness.\n"
            "- If still tied, prefer higher (less negative) health.\n"
            "- Return ONLY the 'blueprintID' field value (the consumable blueprintID). No extra text.\n\n"
            f"FOOD_ITEMS (JSON array with fields id,blueprintID,name,hunger,happiness,health):\n{summary_json}\n"
        )

        # Log prompt (trimmed to 200 chars)
        prompt_preview = (
            user_prompt[:1000] + "..." if len(user_prompt) > 1000 else user_prompt
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
        result = await self.agent.ainvoke({"messages": messages}, config=config)  # type: ignore
        text = ""
        if isinstance(result, dict) and "messages" in result and result["messages"]:
            last = result["messages"][-1]
            text = getattr(last, "content", "") or ""

        choice = (text or "").strip()

        # Log the decision
        decision_text = choice if choice and choice != "NONE" else "No food selected"
        logger.info(f"[DecisionEngine] ✅ Food Decision: {decision_text}")

        # If model fails, use deterministic fallback
        if not choice or choice.upper() == "NONE":
            fallback_id = best_food.get("id")
            if fallback_id:
                logger.info(
                    f"[DecisionEngine] 🔁 Falling back to deterministic best FOOD (ID: {fallback_id})"
                )
                return fallback_id
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
        result = await self.agent.ainvoke({"messages": messages}, config=config)  # type: ignore

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

    async def feed_best_owned_food(
        self, pet_stats: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Fetch mall data and ask the model which owned food to use."""
        logger.info("[DecisionEngine] 🍔 Starting AI-driven food selection process")

        mall = await self.websocket_client.get_kitchen_data(timeout=10)
        choice = await self.choose_food_from_kitchen(mall, pet_stats)

        logger.info(f"[DecisionEngine] 🍔 Choice: {choice}")

        if not choice:
            logger.warning("[DecisionEngine] ❌ No suitable food found to feed pet")
            return False

        logger.info(
            f"[DecisionEngine] 🍖 Feeding pet with consumable ID: {choice} (type: {type(choice).__name__})"
        )
        success = await self.websocket_client.use_consumable(choice)

        if success:
            logger.info(f"[DecisionEngine] ✅ Feeding {choice} confirmed")
        else:
            logger.warning(f"[DecisionEngine] ❌ Feeding {choice} failed")

        return success
