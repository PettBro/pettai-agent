"""
Olas SDK Interface Layer
Handles all Olas SDK requirements and provides a clean interface for the Pett Agent.
"""

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING, Deque, List

from aiohttp import web
from collections import deque
import aiohttp

if TYPE_CHECKING:
    from .pett_agent import PettAgent

from .action_recorder import (
    ActionRecorder,
    RecorderConfig,
    DEFAULT_ACTION_REPO_ADDRESS,
)
from .staking_checkpoint import (
    CheckpointConfig,
    StakingCheckpointClient,
    DEFAULT_SAFE_ADDRESS,
    DEFAULT_STATE_FILE,
)
import subprocess
import mimetypes


class OlasInterface:
    """Interface layer to handle all Olas SDK requirements."""

    def __init__(
        self,
        ethereum_private_key: Optional[str] = None,
        withdrawal_mode: bool = False,
        logger: Optional[logging.Logger] = None,
    ):
        """Initialize Olas interface."""
        self.ethereum_private_key: Optional[str] = ethereum_private_key
        self.withdrawal_mode: bool = withdrawal_mode
        self.logger: logging.Logger = logger or logging.getLogger("olas_interface")
        self.agent: Optional["PettAgent"] = None

        # Health check state
        self.last_transition_time: datetime = datetime.now()
        self.is_transitioning: bool = False
        self.health_status: str = "starting"

        # Web server for health checks and UI
        self.app: Optional[web.Application] = None
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None

        # Environment variables (Olas SDK requirement)
        self.env_vars: Dict[str, str] = self._load_environment_variables()
        self.privy_token_preview: Optional[str] = self._token_preview(
            self.env_vars.get("PRIVY_TOKEN")
        )
        if "PRIVY_TOKEN" in self.env_vars and self.privy_token_preview:
            self.env_vars["PRIVY_TOKEN"] = self.privy_token_preview

        # WebSocket and Pet connection status
        self.websocket_url: str = self.env_vars.get("WEBSOCKET_URL", "wss://ws.pett.ai")
        self.websocket_connected: bool = False
        self.websocket_authenticated: bool = False
        self.pet_connected: bool = False
        self.pet_status: str = "Unknown"
        self.last_websocket_activity: Optional[datetime] = None

        # Pet data storage
        self.pet_data: Optional[Dict[str, Any]] = None
        self.pet_name: str = "Unknown"
        self.pet_id: str = "Unknown"
        self.pet_balance: str = "0.0000"
        self.pet_hotel_tier: int = 0
        self.pet_dead: bool = False
        self.pet_sleeping: bool = False
        # Pet stats storage
        self.pet_hunger: float = 0.0
        self.pet_health: float = 0.0
        self.pet_energy: float = 0.0
        self.pet_happiness: float = 0.0
        self.pet_hygiene: float = 0.0
        self.pet_xp: float = 0.0
        self.pet_level: int = 1

        # Telemetry buffers (in-memory)
        self.sent_messages_history: Deque[Dict[str, Any]] = deque(maxlen=100)
        self.openai_prompts_history: Deque[Dict[str, Any]] = deque(maxlen=50)

        # React static build directory
        self.react_build_dir: Optional[Path] = None
        self.react_enabled: bool = False

        # Optional on-chain components
        self.action_recorder: Optional[ActionRecorder] = None
        self.staking_checkpoint_client: Optional[StakingCheckpointClient] = None
        self._initialise_action_recorder()
        self._initialise_staking_checkpoint()

        self.logger.info("🔧 Olas SDK Interface initialized")

    def _get_current_stats_snapshot(self) -> Dict[str, Any]:
        """Build a snapshot dict of the currently stored pet stats."""
        return {
            "hunger": self.pet_hunger,
            "health": self.pet_health,
            "energy": self.pet_energy,
            "happiness": self.pet_happiness,
            "hygiene": self.pet_hygiene,
            "xp": self.pet_xp,
            "level": self.pet_level,
        }

    def _load_environment_variables(self) -> Dict[str, str]:
        """Load Olas SDK standard environment variables."""
        env_vars = {}

        # Standard Olas environment variables
        olas_env_vars = [
            "OPENAI_API_KEY",
            "TELEGRAM_BOT_TOKEN",
            "PRIVY_TOKEN",
            "WEBSOCKET_URL",
            "SAFE_CONTRACT_ADDRESSES",
        ]

        for var in olas_env_vars:
            prefixed_var = f"CONNECTION_CONFIGS_CONFIG_{var}"
            prefixed_value = os.environ.get(prefixed_var)
            if prefixed_value:
                env_vars[var] = prefixed_value

        self.logger.info(f"📋 Loaded {len(env_vars)} environment variables")
        return env_vars

    @staticmethod
    def _token_preview(token: Optional[str]) -> Optional[str]:
        """Create a short preview of sensitive tokens for UI display."""
        if not token:
            return None
        token = token.strip()
        if len(token) <= 12:
            return token
        return f"{token[:6]}...{token[-4:]}"

    def register_agent(self, agent: "PettAgent") -> None:
        """Store a reference to the running PettAgent instance."""
        self.agent = agent
        self.logger.debug("Registered PettAgent with Olas interface")

    def get_env_var(self, name: str, default: Optional[str] = None) -> Optional[str]:
        """Get environment variable with Olas SDK prefix handling."""
        # Try direct name first
        value = self.env_vars.get(name, default)
        if value:
            return value

        # Try with CONNECTION_CONFIGS_CONFIG_ prefix
        prefixed_name = f"CONNECTION_CONFIGS_CONFIG_{name}"
        return os.environ.get(prefixed_name, default)

    def update_health_status(self, status: str, is_transitioning: bool = False) -> None:
        """Update health check status."""
        self.health_status = status
        self.is_transitioning = is_transitioning
        if not is_transitioning:
            self.last_transition_time = datetime.now()

        self.logger.debug(
            f"Health status updated: {status} (transitioning: {is_transitioning})"
        )

    def update_websocket_status(
        self,
        connected: bool,
        authenticated: bool = False,
        activity_time: Optional[datetime] = None,
    ) -> None:
        """Update WebSocket connection status."""
        self.websocket_connected = connected
        self.websocket_authenticated = authenticated
        if activity_time is not None:
            self.last_websocket_activity = activity_time
        elif connected:
            self.last_websocket_activity = datetime.now()

        self.logger.debug(
            f"WebSocket status updated: connected={connected}, authenticated={authenticated}"
        )

    def update_pet_status(self, connected: bool, status: str = "Unknown") -> None:
        """Update pet connection status."""
        self.pet_connected = connected
        self.pet_status = status
        self.logger.debug(f"Pet status updated: connected={connected}, status={status}")

    def update_pet_data(self, pet_data: Optional[Dict[str, Any]]) -> None:
        """Update pet data with detailed information."""
        self.pet_data = pet_data
        print("pet_data", pet_data)
        if pet_data and pet_data.get("name"):
            self.pet_name = pet_data.get("name", "Unknown")
            self.pet_id = pet_data.get("id", "Unknown")

            # Format balance from wei to ETH (using the same logic as websocket client)
            raw_balance = pet_data.get("PetTokens", {}).get(
                "tokens", pet_data.get("balance", "0")
            )
            try:
                if isinstance(raw_balance, str):
                    raw_balance = int(raw_balance)
                eth_value = raw_balance / (10**18)
                self.pet_balance = f"{eth_value:.4f}"
            except (ValueError, TypeError, ZeroDivisionError):
                self.pet_balance = "0.0000"

            self.pet_hotel_tier = pet_data.get("currentHotelTier", 0)
            self.pet_dead = pet_data.get("dead", False)
            self.pet_sleeping = pet_data.get("sleeping", False)

            # Extract and normalize PetStats
            stats = pet_data.get("PetStats", {}) if isinstance(pet_data, dict) else {}
            if isinstance(stats, dict):

                def to_float(v):
                    try:
                        if v is None:
                            return 0.0
                        if isinstance(v, (int, float)):
                            return float(v)
                        return float(str(v))
                    except Exception:
                        return 0.0

                self.pet_hunger = to_float(stats.get("hunger"))
                self.pet_health = to_float(stats.get("health"))
                self.pet_energy = to_float(stats.get("energy"))
                self.pet_happiness = to_float(stats.get("happiness"))
                self.pet_hygiene = to_float(stats.get("hygiene"))
                self.pet_xp = to_float(stats.get("xp"))
                try:
                    self.pet_level = int(
                        stats.get("level", self.pet_level) or self.pet_level
                    )
                except Exception:
                    pass

            self.logger.debug(f"Pet data updated: {self.pet_name} (ID: {self.pet_id})")
        else:
            # Reset to defaults if no data
            self.pet_name = "Unknown"
            self.pet_id = "Unknown"
            self.pet_balance = "0.0000"
            self.pet_hotel_tier = 0
            self.pet_dead = False
            self.pet_sleeping = False
            self.pet_hunger = 0.0
            self.pet_health = 0.0
            self.pet_energy = 0.0
            self.pet_happiness = 0.0
            self.pet_hygiene = 0.0
            self.pet_xp = 0.0
            self.pet_level = 1

    def record_client_send(
        self, message: Dict[str, Any], success: bool, error: Optional[str] = None
    ) -> None:
        try:
            entry: Dict[str, Any] = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "type": message.get("type"),
                "success": bool(success),
            }
            data = message.get("data")
            if data is not None:
                if isinstance(data, dict):
                    entry["data_keys"] = list(data.keys())[:10]
                    # Store actual data for preview (truncated)
                    entry["data_values"] = str(data)[:300] + "..."
                else:
                    entry["data_preview"] = str(data)[:200] + "..."
            if error:
                entry["error"] = str(error)[:200]
            # Do not attach stats here; we will update with post-action stats after pet_update
            self.sent_messages_history.append(entry)
        except Exception as e:
            self.logger.debug(f"Failed to record client send: {e}")

    def update_last_action_stats(self) -> None:
        """Update the most recent action entry with the latest stored pet stats (post-action)."""
        try:
            if not self.sent_messages_history:
                return
            # Action types we display in health recent actions
            actionable_types = {
                "RUB",
                "SHOWER",
                "SLEEP",
                "THROWBALL",
                "CONSUMABLES_USE",
                "CONSUMABLES_BUY",
                "HOTEL_CHECK_IN",
                "HOTEL_CHECK_OUT",
                "HOTEL_BUY",
                "ACCESSORY_USE",
                "ACCESSORY_BUY",
            }

            # Find the most recent actionable entry from the end
            for idx in range(len(self.sent_messages_history) - 1, -1, -1):
                entry = self.sent_messages_history[idx]
                if str(entry.get("type")) in actionable_types:
                    entry["pet_stats"] = self._get_current_stats_snapshot()
                    break
        except Exception as e:
            self.logger.debug(f"Failed to update last action stats: {e}")

    def record_openai_prompt(
        self, kind: str, prompt: str, context: Optional[Dict[str, Any]] = None
    ) -> None:
        try:
            entry: Dict[str, Any] = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "kind": kind,
                "prompt": (prompt or "")[:2000],
            }
            if context:
                entry["context_keys"] = list(context.keys())[:10]
            self.openai_prompts_history.append(entry)
        except Exception as e:
            self.logger.debug(f"Failed to record OpenAI prompt: {e}")

    def get_seconds_since_last_transition(self) -> float:
        """Get seconds since last transition for health check."""
        return (datetime.now() - self.last_transition_time).total_seconds()

    @property
    def is_healthy(self) -> bool:
        """Compute overall health boolean for quick checks.

        Criteria (conservative):
        - Not in an error or stopped state
        - WebSocket connected
        - If transitioning, allow a short grace period (< 60s)
        """
        if self.health_status in {"error", "stopped"}:
            return False
        if not self.websocket_connected:
            return False
        if self.is_transitioning and self.get_seconds_since_last_transition() > 60:
            return False
        return True

    def _resolve_rpc_url(self) -> Optional[str]:
        """Attempt to resolve the RPC URL for action recording."""

        def _lookup_env(name: str, include_prefixed: bool) -> Optional[str]:
            candidates = [name]
            if include_prefixed:
                candidates.append(f"CONNECTION_CONFIGS_CONFIG_{name}")
            for candidate in candidates:
                value = os.environ.get(candidate)
                if value and value.strip():
                    return value.strip()
            return None

        candidate_env_vars = [
            ("ACTION_REPO_RPC_URL", True),
            ("BASE_LEDGER_RPC", True),
            ("CONNECTION_LEDGER_CONFIG_LEDGER_APIS_GNOSIS_ADDRESS", False),
            ("CONNECTION_LEDGER_CONFIG_LEDGER_APIS_ETHEREUM_ADDRESS", False),
            ("CONNECTION_LEDGER_CONFIG_LEDGER_APIS_BASE_ADDRESS", False),
            ("ETH_RPC_URL", True),
            ("RPC_URL", True),
        ]

        for env_name in candidate_env_vars:
            value = _lookup_env(env_name[0], include_prefixed=env_name[1])
            if value:
                return value
        return None

    def _initialise_action_recorder(self) -> None:
        """Initialise the optional action recorder using the agent's credentials."""
        private_key = (self.ethereum_private_key or "").strip()
        if not private_key:
            self.logger.info(
                "Skipping action recorder initialisation: ethereum private key not available"
            )
            return

        rpc_url = self._resolve_rpc_url()
        if not rpc_url:
            self.logger.info(
                "Skipping action recorder initialisation: RPC endpoint not configured"
            )
            return

        contract_address_env = os.environ.get("ACTION_REPO_CONTRACT_ADDRESS")
        contract_address = (contract_address_env or DEFAULT_ACTION_REPO_ADDRESS).strip()
        # The ActionRecorder resolves the Safe from CONNECTION_CONFIGS_CONFIG_SAFE_CONTRACT_ADDRESSES

        try:
            config = RecorderConfig(
                private_key=private_key,
                rpc_url=rpc_url,
                contract_address=contract_address or DEFAULT_ACTION_REPO_ADDRESS,
            )
            self.action_recorder = ActionRecorder(config=config, logger=self.logger)
        except Exception as exc:
            self.logger.error(f"Failed to initialise action recorder: {exc}")
            self.action_recorder = None

    def get_action_recorder(self) -> Optional[ActionRecorder]:
        """Return the configured action recorder, if available."""
        return self.action_recorder

    def get_staking_checkpoint_client(self) -> Optional[StakingCheckpointClient]:
        """Return the staking checkpoint client, if available."""
        return self.staking_checkpoint_client

    def _initialise_staking_checkpoint(self) -> None:
        """Initialise the staking checkpoint helper when configuration is provided."""
        feature_flag = os.environ.get("ENABLE_STAKING_CHECKPOINTS", "1").strip().lower()
        if feature_flag in {"0", "false", "no"}:
            self.logger.info("Staking checkpoint helper disabled via environment flag")
            return

        private_key = (self.ethereum_private_key or "").strip()
        if not private_key:
            self.logger.info(
                "Skipping staking checkpoint initialisation: ethereum private key not available"
            )
            return

        rpc_url = self._resolve_rpc_url()
        if not rpc_url:
            self.logger.info(
                "Skipping staking checkpoint initialisation: RPC endpoint not configured"
            )
            return

        staking_address: Optional[str] = None
        staking_env_candidates = (
            "STAKING_CONTRACT_ADDRESS",
            "STAKING_PROXY_ADDRESS",
            "SERVICE_STAKING_CONTRACT_ADDRESS",
            "CONNECTION_CONFIGS_CONFIG_STAKING_CONTRACT_ADDRESS",
        )
        for env_name in staking_env_candidates:
            value = os.environ.get(env_name)
            if value and value.strip():
                staking_address = value.strip()
                break

        if not staking_address:
            self.logger.info(
                "Skipping staking checkpoint initialisation: staking contract address not configured"
            )
            return

        safe_address: Optional[str] = None
        safe_env_candidates = (
            "STAKING_SAFE_ADDRESS",
            "SERVICE_SAFE_ADDRESS",
            "SAFE_CONTRACT_ADDRESS",
        )
        for env_name in safe_env_candidates:
            value = os.environ.get(env_name)
            if value and value.strip():
                safe_address = value.strip()
                break
        safe_address = safe_address or DEFAULT_SAFE_ADDRESS

        liveness_env = os.environ.get(
            "STAKING_LIVENESS_PERIOD_SECONDS"
        ) or os.environ.get("STAKING_LIVENESS_PERIOD")
        liveness_period: Optional[int] = None
        if liveness_env:
            try:
                liveness_period = int(liveness_env.strip())
            except ValueError:
                self.logger.warning(
                    "Invalid staking liveness period provided (%s); ignoring and falling back to contract value",
                    liveness_env,
                )

        state_file_env = os.environ.get("STAKING_CHECKPOINT_STATE_FILE")
        state_file_path = (
            Path(state_file_env).expanduser()
            if state_file_env and state_file_env.strip()
            else DEFAULT_STATE_FILE
        )

        try:
            config = CheckpointConfig(
                private_key=private_key,
                rpc_url=rpc_url,
                staking_contract_address=staking_address,
                safe_address=safe_address,
                liveness_period=liveness_period,
                state_file=state_file_path,
            )
            self.staking_checkpoint_client = StakingCheckpointClient(
                config=config, logger=self.logger
            )
        except Exception as exc:
            self.logger.error(f"Failed to initialise staking checkpoint helper: {exc}")
            self.staking_checkpoint_client = None

    async def _health_check_handler(self, request: web.Request) -> web.Response:
        """Handle health check endpoint (Olas SDK requirement)."""
        seconds_since_transition = self.get_seconds_since_last_transition()
        seconds_since_websocket_activity = None
        if self.last_websocket_activity:
            seconds_since_websocket_activity = (
                datetime.now() - self.last_websocket_activity
            ).total_seconds()

        # Get next-action timing from agent (optional)
        action_timing: Dict[str, Any] = {}
        if self.agent and hasattr(self.agent, "get_action_timing_info"):
            try:
                action_timing = self.agent.get_action_timing_info()
            except Exception:
                action_timing = {}

        # Compute environment variable status against expected Olas variables
        expected_env_vars: List[str] = [
            "OPENAI_API_KEY",
            "TELEGRAM_BOT_TOKEN",
            "PRIVY_TOKEN",
            "WEBSOCKET_URL",
        ]
        env_var_messages: Dict[str, str] = {}
        for var in expected_env_vars:
            direct = os.environ.get(var)
            prefixed = os.environ.get(f"CONNECTION_CONFIGS_CONFIG_{var}")
            if not direct and not prefixed:
                env_var_messages[var] = (
                    "Missing; set either the direct variable or its CONNECTION_CONFIGS_CONFIG_ prefixed variant."
                )
        needs_env_update = bool(env_var_messages)

        # Compute agent health placeholders (conservative defaults)
        # Note: These can be enhanced if PettAgent exposes richer telemetry
        agent_health: Dict[str, Any] = {
            "is_making_on_chain_transactions": False,
            "is_staking_kpi_met": False,
            "has_required_funds": False,
            "staking_status": "unknown",
        }

        # Derive has_required_funds from known pet balance when available
        try:
            agent_health["has_required_funds"] = float(self.pet_balance) > 0.0
        except Exception:
            pass

        health_data: Dict[str, Any] = {
            # New required schema (Pearl-compatible)
            "is_healthy": self.is_healthy,
            "seconds_since_last_transition": seconds_since_transition,
            "is_tm_healthy": True,  # Not applicable for Olas SDK agents; report healthy
            "period": 0,
            "reset_pause_duration": 0,
            "rounds": [],  # Not applicable for this agent; ABCI rounds not used
            "is_transitioning_fast": (
                self.is_transitioning and seconds_since_transition < 30
            ),
            "agent_health": agent_health,
            "rounds_info": {},
            "env_var_status": {
                "needs_update": needs_env_update,
                "env_vars": env_var_messages,
            },
            # Existing detailed data preserved for our UI and debugging
            "status": self.health_status,
            "agent_address": (
                self.ethereum_private_key[:10] + "..."
                if self.ethereum_private_key
                else "unknown"
            ),
            "withdrawal_mode": False,
            "websocket": {
                "url": self.websocket_url,
                "connected": self.websocket_connected,
                "authenticated": self.websocket_authenticated,
                "last_activity_seconds_ago": seconds_since_websocket_activity,
            },
            "pet": {
                "connected": self.pet_connected,
                "status": self.pet_status,
                "name": self.pet_name,
                "id": self.pet_id,
                "balance": self.pet_balance,
                "hotel_tier": self.pet_hotel_tier,
                "dead": self.pet_dead,
                "sleeping": self.pet_sleeping,
                "stats": {
                    "hunger": self.pet_hunger,
                    "health": self.pet_health,
                    "energy": self.pet_energy,
                    "happiness": self.pet_happiness,
                    "hygiene": self.pet_hygiene,
                    "xp": self.pet_xp,
                    "level": self.pet_level,
                },
            },
            "action_scheduling": action_timing,
            "timestamp": datetime.now().isoformat(),
            "recent": {
                "sent_messages": list(self.sent_messages_history)[-20:],
                "openai_prompts": list(self.openai_prompts_history)[-10:],
                "actions": [
                    m
                    for m in list(self.sent_messages_history)[-50:]
                    if str(m.get("type"))
                    in {
                        "RUB",
                        "SHOWER",
                        "SLEEP",
                        "THROWBALL",
                        "CONSUMABLES_USE",
                        "CONSUMABLES_BUY",
                        "HOTEL_CHECK_IN",
                        "HOTEL_CHECK_OUT",
                        "HOTEL_BUY",
                        "ACCESSORY_USE",
                        "ACCESSORY_BUY",
                    }
                ][-20:],
            },
        }

        return web.json_response(health_data)

    async def _agent_ui_handler(self, request: web.Request) -> web.Response:
        """Deprecated: HTML dashboard is replaced by React UI."""
        self.logger.info("HTML dashboard endpoint deprecated; use React UI at /")
        return web.json_response(
            {"error": "deprecated", "use": "/dashboard"}, status=410
        )

    async def _agent_api_handler(self, request: web.Request) -> web.Response:
        """Handle POST requests for agent communication."""
        if request.method == "POST":
            try:
                data = await request.json()
                self.logger.info(f"📨 Received API request: {data}")

                # Handle different API commands
                command = data.get("command")
                if command == "status":
                    return web.json_response(
                        {
                            "status": self.health_status,
                            "is_healthy": self.is_healthy,
                            "timestamp": datetime.now().isoformat(),
                        }
                    )
                elif command == "ping":
                    return web.json_response({"response": "pong"})
                else:
                    return web.json_response(
                        {"error": f"Unknown command: {command}"}, status=400
                    )

            except Exception as e:
                self.logger.error(f"Error handling API request: {e}")
                return web.json_response({"error": str(e)}, status=500)

        return web.json_response({"error": "Method not allowed"}, status=405)

    async def _exit_handler(self, request: web.Request) -> web.Response:
        """Handle exit requests."""
        self.logger.info("🛑 Exiting agent")
        if self.agent:
            await self.agent.shutdown()
        if self.app:
            await self.app.shutdown()
        if self.runner:
            await self.runner.cleanup()
        if self.site:
            await self.site.stop()
        # sys.exit(0)
        return web.json_response({"status": "ok"})

    async def _serve_static_file(self, request: web.Request) -> web.Response:
        """Serve static files from React build directory."""
        if not self.react_build_dir or not self.react_build_dir.exists():
            return web.json_response({"error": "React build not available"}, status=503)

        try:
            # Get the file path from the URL
            file_path = self.react_build_dir / request.path.lstrip("/")

            # Security check: ensure the path is within build directory
            try:
                file_path = file_path.resolve()
                self.react_build_dir.resolve()
                if not str(file_path).startswith(str(self.react_build_dir.resolve())):
                    return web.Response(status=403, text="Forbidden")
            except Exception:
                return web.Response(status=403, text="Forbidden")

            # Check if file exists
            if not file_path.is_file():
                return web.Response(status=404, text="Not Found")

            # Determine content type
            content_type, _ = mimetypes.guess_type(str(file_path))
            if not content_type:
                content_type = "application/octet-stream"

            # Read and return file
            with open(file_path, "rb") as f:
                content = f.read()

            return web.Response(body=content, content_type=content_type)

        except Exception as e:
            self.logger.error(f"❌ Error serving static file {request.path}: {e}")
            return web.Response(status=500, text="Internal Server Error")

    async def _serve_react_app(self, request: web.Request) -> web.Response:
        """Serve React app index.html for SPA routing."""
        if not self.react_build_dir or not self.react_build_dir.exists():
            return web.json_response({"error": "React build not available"}, status=503)

        try:
            index_path = self.react_build_dir / "index.html"

            if not index_path.is_file():
                return web.Response(status=404, text="index.html not found")

            # Read and return index.html
            with open(index_path, "rb") as f:
                content = f.read()

            return web.Response(body=content, content_type="text/html")

        except Exception as e:
            self.logger.error(f"❌ Error serving React app: {e}")
            return web.Response(status=500, text="Internal Server Error")

    async def _login_api_handler(self, request: web.Request) -> web.Response:
        """Handle login API requests from React frontend."""
        if request.method == "POST":
            try:
                data = await request.json()
                privy_token = data.get("privy_token")

                if not privy_token:
                    return web.json_response(
                        {"error": "privy_token is required"}, status=400
                    )

                self.logger.info("🔐 Received login request from React frontend")

                # Update privy token in agent
                if self.agent and hasattr(self.agent, "update_privy_token"):
                    success = await self.agent.update_privy_token(privy_token)

                    return web.json_response(
                        {
                            "success": success,
                            "authenticated": self.websocket_authenticated,
                            "pet_connected": self.pet_connected,
                            "pet_name": self.pet_name,
                        }
                    )
                else:
                    return web.json_response(
                        {"error": "Agent not initialized"}, status=500
                    )

            except Exception as e:
                self.logger.error(f"❌ Error handling login: {e}")
                return web.json_response({"error": str(e)}, status=500)

        return web.json_response({"error": "Method not allowed"}, status=405)

    async def _logout_api_handler(self, request: web.Request) -> web.Response:
        """Handle logout requests from React frontend."""
        if request.method == "POST":
            try:
                self.logger.info("🔓 Received logout request from React frontend")

                if self.agent and hasattr(self.agent, "logout_privy"):
                    success = await self.agent.logout_privy()
                    if success:
                        self.privy_token_preview = None
                    return web.json_response({"success": success})
                else:
                    return web.json_response(
                        {"error": "Agent not initialized"}, status=500
                    )

            except Exception as e:
                self.logger.error(f"❌ Error handling logout: {e}")
                return web.json_response({"error": str(e)}, status=500)

        return web.json_response({"error": "Method not allowed"}, status=405)

    def _command_exists(self, command: str) -> bool:
        """Check if a command exists in PATH."""
        try:
            subprocess.run(
                ["which", command],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    async def _ensure_npm_dependencies(self, react_dir: Path) -> bool:
        """Install npm/yarn dependencies if needed."""
        try:
            node_modules = react_dir / "node_modules"
            package_json = react_dir / "package.json"

            if not package_json.exists():
                self.logger.error(f"❌ No package.json found in {react_dir}")
                return False

            # Check if node_modules exists
            if node_modules.exists():
                self.logger.info("✅ node_modules already exists, skipping install")
                return True

            self.logger.info("📦 Installing npm dependencies...")

            # Check for yarn.lock or package-lock.json to determine package manager
            use_yarn = (react_dir / "yarn.lock").exists()

            # Determine which package manager to use
            install_cmd = None
            if use_yarn and self._command_exists("yarn"):
                install_cmd = ["yarn", "install"]
                self.logger.info("Using yarn for installation")
            elif self._command_exists("npm"):
                install_cmd = ["npm", "install"]
                self.logger.info("Using npm for installation")
            else:
                self.logger.error("❌ Neither yarn nor npm found in PATH")
                return False

            # Run installation
            process = await asyncio.create_subprocess_exec(
                *install_cmd,
                cwd=str(react_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                self.logger.info("✅ Dependencies installed successfully")
                return True
            else:
                self.logger.error(
                    f"❌ Dependency installation failed: {stderr.decode()}"
                )
                return False

        except Exception as e:
            self.logger.error(f"❌ Error installing dependencies: {e}")
            return False

    async def build_react_app(self, react_dir: Path) -> bool:
        """Build React app to static files."""
        try:
            if not react_dir.exists():
                self.logger.warning(f"⚠️ React directory not found: {react_dir}")
                return False

            package_json = react_dir / "package.json"
            if not package_json.exists():
                self.logger.error(f"❌ No package.json found in {react_dir}")
                return False

            build_dir = react_dir / "build"

            # Check if build already exists and is recent
            if build_dir.exists() and (build_dir / "index.html").exists():
                self.logger.info("✅ React build already exists, skipping build")
                return True

            # Ensure dependencies are installed
            if not await self._ensure_npm_dependencies(react_dir):
                return False

            self.logger.info("📦 Building React app...")

            # Check for yarn.lock or package-lock.json to determine package manager
            use_yarn = (react_dir / "yarn.lock").exists()
            build_cmd = (
                ["yarn", "build"]
                if use_yarn and self._command_exists("yarn")
                else ["npm", "run", "build"]
            )

            # Run build command
            process = await asyncio.create_subprocess_exec(
                *build_cmd,
                cwd=str(react_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                self.logger.info("✅ React app built successfully")
                return True
            else:
                self.logger.error(f"❌ React build failed: {stderr.decode()}")
                return False

        except Exception as e:
            self.logger.error(f"❌ Error building React app: {e}")
            return False

    async def start_web_server(
        self, port: int = 8716, enable_react: bool = True
    ) -> None:
        """Start web server for health checks and UI (Olas SDK requirement)."""
        try:
            self.app = web.Application()

            # Try to build and serve React static files if enabled
            if enable_react:
                react_dir = Path(__file__).parent.parent / "frontend"
                if react_dir.exists():
                    self.logger.info("🎨 Building React frontend...")
                    react_built = await self.build_react_app(react_dir)
                    if react_built:
                        self.react_build_dir = react_dir / "build"
                        self.react_enabled = True
                        self.logger.info("✅ React build available for serving")
                    else:
                        self.logger.warning("⚠️ React build failed")
                else:
                    self.logger.info(f"ℹ️ No React frontend found at {react_dir}")

            # Deprecated HTML dashboard removed in favor of React UI
            self.app.router.add_get(
                "/api/health", self._health_check_handler
            )  # JSON health
            self.app.router.add_get("/api/status", self._health_check_handler)
            self.app.router.add_get("/healthcheck", self._health_check_handler)
            self.app.router.add_post("/api/login", self._login_api_handler)
            self.app.router.add_post("/api/logout", self._logout_api_handler)
            self.app.router.add_post("/", self._agent_api_handler)
            self.app.router.add_get("/exit", self._exit_handler)

            self.logger.debug(
                f"🔄 Adding React static file routes: {self.react_enabled}"
            )
            # Add React static file routes (if enabled)
            if self.react_enabled and self.react_build_dir:
                # Serve static files
                self.app.router.add_get("/static/{tail:.*}", self._serve_static_file)
                self.app.router.add_get("/assets/{tail:.*}", self._serve_static_file)

                # Serve React routes (SPA fallback to index.html)
                self.app.router.add_get("/login", self._serve_react_app)
                self.app.router.add_get("/login/{tail:.*}", self._serve_react_app)
                self.app.router.add_get("/dashboard", self._serve_react_app)
                self.app.router.add_get("/dashboard/{tail:.*}", self._serve_react_app)

                # Root serves React
                self.app.router.add_get("/", self._serve_react_app)
            else:
                # Fallback to JSON health if React not available
                self.app.router.add_get("/", self._health_check_handler)

            # Start server (disable aiohttp access logs)
            self.runner = web.AppRunner(self.app, access_log=None)
            await self.runner.setup()

            # Bind to 0.0.0.0 to allow access from outside Docker container
            self.site = web.TCPSite(self.runner, "0.0.0.0", port)
            await self.site.start()

            self.logger.info(
                f"🌐 Web server started on http://0.0.0.0:{port} (access via http://localhost:{port})"
            )
            if self.react_enabled:
                self.logger.info(
                    f"🎨 React App available at http://localhost:{port}/ (Dashboard at /dashboard)"
                )
                self.logger.info(f"🏥 Health API: http://localhost:{port}/api/health")
            else:
                self.logger.info(f"🏥 Health API: http://localhost:{port}/api/health")

        except Exception as e:
            self.logger.error(f"Failed to start web server: {e}")
            raise

    async def stop_web_server(self) -> None:
        """Stop the web server."""
        try:
            if self.site:
                await self.site.stop()
            if self.runner:
                await self.runner.cleanup()
            self.logger.info("🛑 Web server stopped")
        except Exception as e:
            self.logger.error(f"Error stopping web server: {e}")

    def log_to_file(self, message: str, level: str = "INFO") -> None:
        """Log message to log.txt file (Olas SDK requirement)."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
        log_entry = f"[{timestamp}] [{level}] [agent] {message}\n"

        try:
            print(log_entry)
        except Exception as e:
            self.logger.error(f"Failed to write to log.txt: {e}")

    def handle_withdrawal(self) -> bool:
        """Handle withdrawal mode (Olas SDK optional requirement)."""
        if not self.withdrawal_mode:
            return False

        self.logger.info("💰 Withdrawal mode activated")
        # TODO: Implement actual withdrawal logic
        # This would typically:
        # 1. Stop normal operations
        # 2. Withdraw funds from Safe to Agent EOA
        # 3. Prepare for shutdown

        return True
