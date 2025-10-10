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

if TYPE_CHECKING:
    from .pett_agent import PettAgent


class OlasInterface:
    """Interface layer to handle all Olas SDK requirements."""

    def __init__(
        self,
        ethereum_private_key: Optional[str] = None,
        safe_contract_addresses: Optional[Dict[str, str]] = None,
        withdrawal_mode: bool = False,
        logger: Optional[logging.Logger] = None,
    ):
        """Initialize Olas interface."""
        self.ethereum_private_key: Optional[str] = ethereum_private_key
        self.safe_contract_addresses: Dict[str, str] = safe_contract_addresses or {}
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

        # Telemetry buffers (in-memory)
        self.sent_messages_history: Deque[Dict[str, Any]] = deque(maxlen=100)
        self.openai_prompts_history: Deque[Dict[str, Any]] = deque(maxlen=50)

        self.logger.info("🔧 Olas SDK Interface initialized")

    def _load_environment_variables(self) -> Dict[str, str]:
        """Load Olas SDK standard environment variables."""
        env_vars = {}

        # Standard Olas environment variables
        olas_env_vars = [
            "BASE_LEDGER_RPC",
            "CONTRACT_ADDRESS",
            "WITHDRAWAL_MODE",
            "OPENAI_API_KEY",
            "LANGSMITH_API_KEY",
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
        if pet_data:
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

            self.logger.debug(f"Pet data updated: {self.pet_name} (ID: {self.pet_id})")
        else:
            # Reset to defaults if no data
            self.pet_name = "Unknown"
            self.pet_id = "Unknown"
            self.pet_balance = "0.0000"
            self.pet_hotel_tier = 0
            self.pet_dead = False
            self.pet_sleeping = False

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
                else:
                    entry["data_preview"] = str(data)[:200]
            if error:
                entry["error"] = str(error)[:200]
            # Attach lightweight stats snapshot if available
            if self.pet_data and isinstance(self.pet_data.get("PetStats", {}), dict):
                stats = self.pet_data.get("PetStats", {})
                entry["pet_stats"] = {
                    "hunger": stats.get("hunger"),
                    "health": stats.get("health"),
                    "energy": stats.get("energy"),
                    "happiness": stats.get("happiness"),
                    "hygiene": stats.get("hygiene"),
                }
            self.sent_messages_history.append(entry)
        except Exception as e:
            self.logger.debug(f"Failed to record client send: {e}")

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

        health_data: Dict[str, Any] = {
            "status": self.health_status,
            "seconds_since_last_transition": seconds_since_transition,
            "is_transitioning_fast": (
                self.is_transitioning and seconds_since_transition < 30
            ),
            "agent_address": (
                self.ethereum_private_key[:10] + "..."
                if self.ethereum_private_key
                else "unknown"
            ),
            "safe_addresses": self.safe_contract_addresses,
            "withdrawal_mode": self.withdrawal_mode,
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

        self.logger.debug(f"Health check requested: {health_data}")
        return web.json_response(health_data)

    async def _agent_ui_handler(self, request: web.Request) -> web.Response:
        """Handle agent UI endpoint (Olas SDK optional requirement)."""
        if self.last_websocket_activity:
            seconds_since_websocket_activity = (
                datetime.now() - self.last_websocket_activity
            ).total_seconds()
            last_activity_display = f"{seconds_since_websocket_activity:.1f}s ago"
        else:
            last_activity_display = "Never"

        token_preview_display = self.privy_token_preview or "Not set"

        # Compute status class/icon for UI
        status_class = (
            "healthy"
            if self.health_status == "running"
            else ("transitioning" if self.is_transitioning else "error")
        )
        status_icon = (
            "🟢"
            if self.health_status == "running"
            else ("🟡" if self.is_transitioning else "🔴")
        )

        # Pre-render recent telemetry blocks for UI
        recent_messages: List[Dict[str, Any]] = list(self.sent_messages_history)[-10:][
            ::-1
        ]
        recent_actions: List[Dict[str, Any]] = [
            m
            for m in list(self.sent_messages_history)[-30:]
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
        ][-10:][::-1]
        recent_prompts: List[Dict[str, Any]] = list(self.openai_prompts_history)[-5:][
            ::-1
        ]

        # Get next-action timing from agent (optional)
        action_timing: Dict[str, Any] = {}
        if self.agent and hasattr(self.agent, "get_action_timing_info"):
            try:
                action_timing = self.agent.get_action_timing_info()
            except Exception:
                action_timing = {}

        def _fmt_success(s: bool) -> str:
            return "✅" if s else "❌"

        def _payload_preview(entry: Dict[str, Any]) -> str:
            keys = entry.get("data_keys")
            if keys:
                return ", ".join(keys)
            return entry.get("data_preview", "") or ""

        msgs_html = (
            "".join(
                (
                    "<tr>"
                    f"<td>{m.get('timestamp', '')}</td>"
                    f"<td><code>{m.get('type', '')}</code></td>"
                    f"<td>{_fmt_success(bool(m.get('success')))}</td>"
                    f"<td>{_payload_preview(m)}</td>"
                    "</tr>"
                )
                for m in recent_messages
            )
            or "<tr><td colspan=4>No recent messages</td></tr>"
        )

        actions_html = (
            "".join(
                (
                    "<li>"
                    f"[{m.get('timestamp', '')}] "
                    f"<strong>{m.get('type', '')}</strong> — "
                    f"{_fmt_success(bool(m.get('success')))}"
                    "</li>"
                )
                for m in recent_actions
            )
            or "<li>No recent actions</li>"
        )

        prompts_html = (
            "".join(
                (
                    "<li>"
                    f"<strong>{p.get('timestamp', '')}</strong> "
                    f"[{p.get('kind', 'prompt')}]<br/>"
                    f"<pre style=\"white-space:pre-wrap;word-break:break-word;\">{p.get('prompt', '')}</pre>"
                    "</li>"
                )
                for p in recent_prompts
            )
            or "<li>No recent prompts</li>"
        )

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Pett Agent - Olas SDK</title>
            <style>
                body {{
                  font-family: Arial, sans-serif;
                  margin: 40px;
                  background: #f5f5f5;
                  color: #222;
                }}
                .container {{
                  max-width: 1300px;
                  margin: 0 auto;
                  background: white;
                  padding: 36px;
                  border-radius: 10px;
                  box-shadow: 0 2px 10px rgba(0,0,0,0.08);
                }}
                .status {{
                  padding: 14px 18px;
                  border-radius: 6px;
                  margin: 10px 0 20px 0;
                  font-weight: 600;
                }}
                .status.healthy {{
                  background: #d4edda;
                  color: #155724;
                  border: 1px solid #c3e6cb;
                }}
                .status.transitioning {{
                  background: #fff3cd;
                  color: #856404;
                  border: 1px solid #ffeaa7;
                }}
                .status.error {{
                  background: #f8d7da;
                  color: #721c24;
                  border: 1px solid #f5c6cb;
                }}
                .info-grid {{
                  display: grid;
                  grid-template-columns: repeat(auto-fit,minmax(300px,1fr));
                  gap: 24px;
                  margin: 20px 0;
                }}
                .info-grid.large {{
                  grid-template-columns: repeat(auto-fit,minmax(440px,1fr));
                }}
                .info-card {{
                  background: #f8f9fa;
                  padding: 22px;
                  border-radius: 8px;
                  border-left: 6px solid #007bff;
                }}
                .info-card h3 {{ font-size: 1.15em; margin: 0 0 8px; }}
                .emoji {{ font-size: 1.2em; margin-right: 8px; }}
                .note {{ font-size: 0.85em; color: #555; margin-top: 8px; }}
                button {{
                  padding: 10px 16px;
                  border-radius: 4px;
                  border: none;
                  cursor: pointer;
                  background: #6c757d;
                  color: #fff;
                  font-size: 0.9em;
                  margin-right: 10px;
                }}
                button.secondary {{ background: #17a2b8; }}
                .controls {{ margin-top: 20px; }}
                table {{ width: 100%; border-collapse: collapse; font-size: 0.95em; }}
                th, td {{ border: 1px solid #e9ecef; padding: 10px 12px; text-align: left; }}
                th {{ background: #f1f3f5; }}
                ul {{ padding-left: 20px; }}
                .telemetry-table th:nth-child(1) {{ width: 200px; }}
                .telemetry-table th:nth-child(2) {{ width: 140px; }}
                .telemetry-table th:nth-child(3) {{ width: 100px; }}
                .info-card pre {{ max-height: 320px; overflow: auto; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🐾 Pett Agent Dashboard</h1>
                <p>Powered by Olas SDK | Virtual Pet Management Agent</p>
                <div class="status {status_class}">
                    <strong>Status:</strong> {self.health_status.upper()}
                    {status_icon}
                </div>
                <div class="info-grid">
                    <div class="info-card">
                        <h3><span class="emoji">⏱️</span>Runtime Info</h3>
                        <p><strong>Last Transition:</strong> {self.get_seconds_since_last_transition():.1f}s ago</p>
                        <p><strong>Transitioning:</strong> {'Yes' if self.is_transitioning else 'No'}</p>
                        <p><strong>Withdrawal Mode:</strong> {'Enabled' if self.withdrawal_mode else 'Disabled'}</p>
                        <p><strong>Next Action:</strong>
                            { (str(action_timing.get('minutes_until_next_action', '')) + 'm') if action_timing.get('next_action_scheduled') else 'Not scheduled' }
                        </p>
                    </div>
                    
                    <div class="info-card">
                        <h3><span class="emoji">🔗</span>Blockchain Info</h3>
                        <p><strong>Agent Address:</strong>
                        {self.ethereum_private_key[:10] + "..." if self.ethereum_private_key else "Not configured"}
                        </p>
                        <p><strong>Safe Contracts:</strong> {len(self.safe_contract_addresses)} configured</p>
                        <p><strong>Networks:</strong>
                        {", ".join(self.safe_contract_addresses.keys()) if self.safe_contract_addresses else "None"}
                        </p>
                    </div>
                </div>
                
                <div class="info-grid">
                    <div class="info-card">
                        <h3><span class="emoji">🔌</span>WebSocket Connection</h3>
                        <p><strong>URL:</strong> <code>{self.websocket_url}</code></p>
                        <p><strong>Status:</strong>
                        <span style="color: {'green' if self.websocket_connected else 'red'}">
                            {'🟢 Connected' if self.websocket_connected else '🔴 Disconnected'}
                        </span></p>
                        <p><strong>Authenticated:</strong>
                            <span style="color: {'green' if self.websocket_authenticated else 'orange'}">
                                {'✅ Yes' if self.websocket_authenticated else '❌ No'}
                            </span>
                        </p>
                        <p><strong>Last Activity:</strong> {last_activity_display}</p>
                    </div>

                    <div class="info-card">
                        <h3><span class="emoji">🐾</span>Pet Information</h3>
                        <p><strong>Name:</strong> {self.pet_name}</p>
                        <p><strong>ID:</strong> {self.pet_id}</p>
                        <p><strong>Balance:</strong> {self.pet_balance} $AIP</p>
                        <p><strong>Hotel Tier:</strong> {self.pet_hotel_tier}</p>
                        <p><strong>Status:</strong>
                            <span style="color: {'green' if self.pet_connected else 'red'}">
                                {'🟢 Connected' if self.pet_connected else '🔴 Disconnected'}
                            </span>
                        </p>
                        <p><strong>Condition:</strong>
                            {
                                (
                                    '💀 Dead' if self.pet_dead else (
                                        '😴 Sleeping' if self.pet_sleeping else '😊 Healthy'
                                    )
                                )
                            }
                        </p>
                        <p><strong>Health:</strong>
                            {'🟢 Healthy' if self.pet_connected and self.websocket_authenticated else
                             ('🟡 Limited' if self.websocket_connected else '🔴 Offline')}
                        </p>
                    </div>
                </div>

                <div class="info-grid">
                    <div class="info-card">
                        <h3><span class="emoji">🔐</span>Privy Authentication</h3>
                        <p><strong>Current token:</strong> {token_preview_display}</p>
                        <p class="note">
                            Set the <code>PRIVY_TOKEN</code> environment variable and
                            restart the agent to update this value.
                        </p>
                    </div>

                    <div class="info-card">
                        <h3><span class="emoji">🌐</span>Environment</h3>
                        <p><strong>Loaded Variables:</strong> {len(self.env_vars)}</p>
                        <p><strong>Key Variables:</strong>
                            {", ".join(list(self.env_vars.keys())[:5])}
                            {'...' if len(self.env_vars) > 5 else ''}
                        </p>
                    </div>
                </div>

                <div class="info-grid large">
                    <div class="info-card">
                        <h3><span class="emoji">⚙️</span>Recent Actions</h3>
                        <ul>
                            {actions_html}
                        </ul>
                    </div>

                    <div class="info-card">
                        <h3><span class="emoji">📤</span>Recent Messages Sent to Client</h3>
                        <table class="telemetry-table">
                            <thead>
                                <tr>
                                    <th>Time</th>
                                    <th>Type</th>
                                    <th>Result</th>
                                    <th>Payload</th>
                                </tr>
                            </thead>
                            <tbody>
                                {msgs_html}
                            </tbody>
                        </table>
                    </div>

                    <div class="info-card">
                        <h3><span class="emoji">🧠</span>Latest OpenAI Prompts</h3>
                        <ul>
                            {prompts_html}
                        </ul>
                    </div>
                </div>

                <div class="controls">
                    <button onclick="location.reload()">🔄 Refresh</button>
                    <button class="secondary"
                        onclick="fetch('/healthcheck')
                        .then(r => r.json())
                        .then(d => alert(JSON.stringify(d, null, 2)))
                        .catch(() => alert('Healthcheck failed'));">
                        🏥 Health Check
                    </button>
                </div>

                <footer style="margin-top: 30px; text-align: center; color: #666;">
                    <p>
                        Pett Agent running on Olas SDK |
                        {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                    </p>
                </footer>
            </div>
        </body>
        </html>
        """
        return web.Response(text=html_content, content_type="text/html")

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

    async def start_web_server(self, port: int = 8716) -> None:
        """Start web server for health checks and UI (Olas SDK requirement)."""
        try:
            self.app = web.Application()

            # Add routes
            self.app.router.add_get("/healthcheck", self._health_check_handler)
            self.app.router.add_get("/", self._agent_ui_handler)
            self.app.router.add_post("/", self._agent_api_handler)
            self.app.router.add_get("/exit", self._exit_handler)

            # Start server
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()

            self.site = web.TCPSite(self.runner, "localhost", port)
            await self.site.start()

            self.logger.info(f"🌐 Web server started on http://localhost:{port}")
            self.logger.info(f"🏥 Health check: http://localhost:{port}/healthcheck")
            self.logger.info(f"🎛️ Agent UI: http://localhost:{port}/")

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
