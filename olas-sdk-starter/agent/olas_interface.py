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

from .react_server_manager import ReactServerManager


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
        self.websocket_url: str = (
            self.get_env_var("WEBSOCKET_URL", "ws://localhost:3005")
            or "ws://localhost:3005"
        )
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

        # React development server
        self.react_server: Optional[ReactServerManager] = None
        self.react_enabled: bool = False

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
        ]

        for var in olas_env_vars:
            value = os.environ.get(var)
            if value:
                env_vars[var] = value
                # Also check with CONNECTION_CONFIGS_CONFIG_ prefix
                prefixed_var = f"CONNECTION_CONFIGS_CONFIG_{var}"
                prefixed_value = os.environ.get(prefixed_var)
                if prefixed_value:
                    env_vars[prefixed_var] = prefixed_value

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
        value = os.environ.get(name, default)
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
        if self.react_server:
            await self.react_server.stop_dev_server()
        if self.app:
            await self.app.shutdown()
        if self.runner:
            await self.runner.cleanup()
        if self.site:
            await self.site.stop()
        # sys.exit(0)
        return web.json_response({"status": "ok"})

    async def _react_proxy_handler(self, request: web.Request) -> web.Response:
        """Proxy requests to React dev server."""
        if not self.react_server or not self.react_server.is_running:
            return web.json_response(
                {"error": "React dev server not running"}, status=503
            )

        try:
            # Build target URL
            target_url = f"http://localhost:{self.react_server.port}{request.path_qs}"
            # Normalize method and payload for proxying
            method = request.method.upper()
            forward_method = "GET" if method == "HEAD" else method
            payload = None
            if forward_method not in ("GET", "HEAD"):
                payload = await request.read()

            # Forward the request with timeout
            timeout = aiohttp.ClientTimeout(total=30)  # 30 second timeout
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(
                    method=forward_method,
                    url=target_url,
                    headers={
                        k: v for k, v in request.headers.items() if k.lower() != "host"
                    },
                    data=payload,
                ) as resp:
                    # Return the response
                    if method == "HEAD":
                        # For HEAD, return metadata only with empty body
                        return web.Response(
                            status=resp.status,
                            headers={
                                k: v
                                for k, v in resp.headers.items()
                                if k.lower() not in ["transfer-encoding", "connection"]
                            },
                        )
                    else:
                        body = await resp.read()
                        return web.Response(
                            body=body,
                            status=resp.status,
                            headers={
                                k: v
                                for k, v in resp.headers.items()
                                if k.lower() not in ["transfer-encoding", "connection"]
                            },
                        )
        except asyncio.TimeoutError:
            self.logger.error(f"⏱️ Proxy timeout after 30s for {request.path}")
            return web.json_response({"error": "React dev server timeout"}, status=504)
        except Exception as e:
            self.logger.error(f"❌ Error proxying to React: {e}")
            return web.json_response({"error": str(e)}, status=500)

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

    async def start_web_server(
        self, port: int = 8716, enable_react: bool = True
    ) -> None:
        """Start web server for health checks and UI (Olas SDK requirement)."""
        try:
            self.app = web.Application()

            # Try to start React dev server if enabled
            if enable_react:
                react_dir = Path(__file__).parent.parent / "frontend"
                if react_dir.exists():
                    self.logger.info("🎨 Starting React development server...")
                    self.react_server = ReactServerManager(
                        react_dir=str(react_dir), port=3000
                    )
                    react_started = await self.react_server.start_dev_server()
                    if react_started:
                        self.react_enabled = True
                        self.logger.info("✅ React dev server started successfully")
                    else:
                        self.logger.warning("⚠️ React dev server failed to start")
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
                f"🔄 Adding React proxy routes: {self.react_enabled} {self.react_server}"
            )
            # Add React proxy routes (if enabled)
            if self.react_enabled and self.react_server:
                # Proxy /login and other React routes
                self.app.router.add_get("/login", self._react_proxy_handler)
                self.app.router.add_get("/login/{tail:.*}", self._react_proxy_handler)

                # Proxy static files
                self.app.router.add_get("/static/{tail:.*}", self._react_proxy_handler)
                self.app.router.add_get("/assets/{tail:.*}", self._react_proxy_handler)

                # Proxy root to React
                self.app.router.add_get("/", self._react_proxy_handler)
            else:
                # Fallback to JSON health if React not available
                self.app.router.add_get("/", self._health_check_handler)

            # Start server (disable aiohttp access logs)
            self.runner = web.AppRunner(self.app, access_log=None)
            await self.runner.setup()

            self.site = web.TCPSite(self.runner, "localhost", port)
            await self.site.start()

            self.logger.info(f"🌐 Web server started on http://localhost:{port}")
            if self.react_enabled:
                self.logger.info(
                    f"🎨 React App proxy active at http://localhost:{port}/ (Dashboard at /dashboard)"
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
            # Stop React dev server first
            if self.react_server:
                await self.react_server.stop_dev_server()

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
            with open("log.txt", "a") as f:
                f.write(log_entry)
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
