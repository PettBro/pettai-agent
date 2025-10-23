"""
Pett Agent - Olas SDK Integration
Main agent class that integrates your existing Pett Agent logic with Olas SDK requirements.
"""

import os
import asyncio
import logging
import random
from typing import Optional, TypedDict, Dict, Any, Union, List
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Import your existing logic
from .pett_websocket_client import PettWebSocketClient
from .pett_tools import PettTools
from .telegram_bot import PetTelegramBot
from .olas_interface import OlasInterface
from .decision_engine import PetDecisionEngine

# Load environment variables
load_dotenv()


class PettAgent:
    """Main Pett Agent class with Olas SDK integration."""

    LOW_THRESHOLD = 30.0
    LOW_ENERGY_THRESHOLD = 20.0

    def __init__(
        self,
        olas_interface: OlasInterface,
        logger: logging.Logger,
        is_production: bool = True,
    ):
        """Initialize the Pett Agent."""
        self.olas = olas_interface
        self.logger = logger
        self.is_production = is_production
        self.running = False
        self.olas.register_agent(self)

        # Your existing components
        self.websocket_client: Optional[PettWebSocketClient] = None
        self.telegram_bot: Optional[PetTelegramBot] = None
        self.pett_tools: Optional[PettTools] = None
        self.decision_engine: Optional[PetDecisionEngine] = None

        # Configuration
        self.telegram_token = (
            self.olas.get_env_var("TELEGRAM_BOT_TOKEN") or ""
        ).strip()
        self.privy_token = (self.olas.get_env_var("PRIVY_TOKEN") or "").strip()
        self.websocket_url = self.olas.get_env_var("WEBSOCKET_URL", "wss://ws.pett.ai")

        self.logger.info("🐾 Pett Agent initialized")
        # Action scheduler configuration
        self.action_interval_minutes: float = (
            30 if is_production else 1
        )  # should be 30 minutes in prod
        self.next_action_at: Optional[datetime] = None
        self.last_action_at: Optional[datetime] = None

        # Flag to indicate we're waiting for React login
        self.waiting_for_react_login: bool = False
        self._low_health_recovery_in_progress: bool = False

    # TypedDicts for pet data shape
    class PetTokensDict(TypedDict, total=False):
        petID: str
        tokens: str
        ethTokens: str
        solanaTokens: str
        useSolana: bool
        depositedTokens: str

    class PetStatsDict(TypedDict, total=False):
        petID: str
        hunger: Union[str, int, float]
        health: Union[str, int, float]
        hygiene: Union[str, int, float]
        energy: Union[str, int, float]
        happiness: Union[str, int, float]
        xp: Union[str, int, float]
        level: int
        xpMax: Union[str, int, float]
        xpMin: Union[str, int, float]

    class PetDataDict(TypedDict, total=False):
        id: str
        name: str
        userID: str
        sleeping: bool
        dead: bool
        god: bool
        active: bool
        currentHotelTier: int
        deadTime: Union[str, None]
        inRiskOfDeathTime: Union[str, None]
        PetTokens: "PettAgent.PetTokensDict"
        PetStats: "PettAgent.PetStatsDict"

    async def initialize(self) -> bool:
        """Initialize all agent components."""
        try:
            self.logger.info("🚀 Initializing Pett Agent components...")
            self.olas.update_health_status("initializing", is_transitioning=True)

            # Start Olas web server for health checks
            await self.olas.start_web_server()

            # Initialize WebSocket client (but don't fail if token is expired)
            if self.privy_token:
                self.logger.info("🔌 Initializing WebSocket client...")
                self.websocket_client = PettWebSocketClient(
                    websocket_url=self.websocket_url
                )
                try:
                    self.websocket_client.set_action_recorder(
                        self.olas.get_action_recorder()
                    )
                    try:
                        recorder = self.olas.get_action_recorder()
                        if recorder and recorder.is_enabled:
                            addr_preview = "unknown"
                            if recorder.account_address:
                                aa = recorder.account_address
                                addr_preview = f"{aa[:6]}...{aa[-4:]}"
                            self.logger.info(
                                "🧾 On-chain action recorder ENABLED: contract=%s rpc=%s agent=%s",
                                recorder.contract_address,
                                recorder.rpc_url,
                                addr_preview,
                            )
                        else:
                            self.logger.info(
                                "🧾 On-chain action recorder DISABLED (missing key or RPC)"
                            )
                    except Exception as e:
                        self.logger.error("❌ Failed to set action recorder: %s", e)
                        pass
                except Exception as e:
                    self.logger.error("❌ Failed to set action recorder: %s", e)
                    pass
                # Wire outgoing message telemetry to Olas
                try:

                    def _recorder_msg(
                        m: Dict[str, Any], success: bool, err: Optional[str]
                    ) -> None:
                        self.olas.record_client_send(m, success=success, error=err)

                    self.websocket_client.set_telemetry_recorder(_recorder_msg)
                except Exception:
                    pass

                # Try to connect and authenticate (but don't fail if token expired)
                self.logger.info(
                    "🔐 Attempting authentication with environment token..."
                )
                connected = await self.websocket_client.connect_and_authenticate()
                if connected:
                    self.logger.info("✅ WebSocket connected and authenticated")

                    # Update Olas interface with WebSocket status
                    self.olas.update_websocket_status(
                        connected=True, authenticated=True
                    )

                    # Set OpenAI API key for decision engine
                    openai_key = self.olas.get_env_var("OPENAI_API_KEY")
                    if openai_key:
                        os.environ["OPENAI_API_KEY"] = openai_key
                        self.logger.info(
                            f"🔑 OpenAI API key configured: {openai_key[:5]}...{openai_key[-5:]}"
                        )
                    else:
                        self.logger.warning(
                            "⚠️ No OpenAI API key found - AI features will be limited"
                        )

                    # Initialize Decision Engine and Pett Tools
                    self.decision_engine = PetDecisionEngine(self.websocket_client)
                    # Wire prompt recorder to Olas
                    try:

                        def _recorder_prompt(
                            kind: str, prompt: str, ctx: Optional[Dict[str, Any]]
                        ) -> None:
                            self.olas.record_openai_prompt(kind, prompt, context=ctx)

                        self.decision_engine.set_prompt_recorder(_recorder_prompt)
                    except Exception:
                        pass
                    self.pett_tools = self.decision_engine.pett_tools
                    self.logger.info("🛠️ Decision Engine and Pett Tools initialized")

                    # React to server-side errors (e.g., low health) with recovery actions
                    try:
                        if self.websocket_client:
                            self.websocket_client.register_message_handler(
                                "error", self._on_client_error_message
                            )
                        # Keep Olas pet data in sync on live updates
                        self.websocket_client.register_message_handler(
                            "pet_update", self._on_client_pet_update_message
                        )
                    except Exception:
                        pass

                    # Try to get pet status
                    try:
                        pet_status_result = self.pett_tools.get_pet_status()
                        if "❌" not in pet_status_result:
                            pet_connected = True
                            # Extract a summary from the pet status
                            if "Pet Status:" in pet_status_result:
                                pet_status = "Active"
                            else:
                                pet_status = "Connected"

                            # Also get and update the actual pet data
                            if (
                                self.websocket_client
                                and self.websocket_client.is_connected()
                            ):
                                pet_data = self.websocket_client.get_pet_data()
                                if pet_data:
                                    self.olas.update_pet_data(pet_data)
                                    self.logger.debug(
                                        f"Initial pet data updated: {pet_data.get('name', 'Unknown')}"
                                    )
                        else:
                            pet_connected = False
                            pet_status = "Error"
                            # Clear pet data on error
                            self.olas.update_pet_data(None)

                        self.olas.update_pet_status(pet_connected, pet_status)
                    except Exception as e:
                        self.logger.debug(f"Could not get pet status: {e}")
                        self.olas.update_pet_status(False, "Unknown")
                        self.olas.update_pet_data(None)
                else:
                    self.logger.info(
                        "⏸️  Environment token authentication failed (expired or invalid)"
                    )
                    self.logger.info(
                        "✨ Waiting for user to login via React app at http://localhost:8716/"
                    )
                    self.olas.update_websocket_status(
                        connected=False, authenticated=False
                    )
                    # Keep websocket_client initialized for later use
                    self.waiting_for_react_login = True
            else:
                self.logger.info("ℹ️  No PRIVY_TOKEN in environment")
                self.logger.info(
                    "✨ Waiting for user to login via React app at http://localhost:8716/"
                )
                # Initialize WebSocket client for later use
                self.websocket_client = PettWebSocketClient(
                    websocket_url=self.websocket_url
                )
                try:
                    self.websocket_client.set_action_recorder(
                        self.olas.get_action_recorder()
                    )
                    try:
                        recorder2 = self.olas.get_action_recorder()
                        if recorder2 and recorder2.is_enabled:
                            addr_preview2 = "unknown"
                            if recorder2.account_address:
                                aa2 = recorder2.account_address
                                addr_preview2 = f"{aa2[:6]}...{aa2[-4:]}"
                            self.logger.info(
                                "🧾 On-chain action recorder ENABLED: contract=%s rpc=%s agent=%s",
                                recorder2.contract_address,
                                recorder2.rpc_url,
                                addr_preview2,
                            )
                        else:
                            self.logger.info(
                                "🧾 On-chain action recorder DISABLED (missing key or RPC)"
                            )
                    except Exception:
                        pass
                except Exception:
                    pass
                try:

                    def _recorder_msg(
                        m: Dict[str, Any], success: bool, err: Optional[str]
                    ) -> None:
                        self.olas.record_client_send(m, success=success, error=err)

                    self.websocket_client.set_telemetry_recorder(_recorder_msg)
                except Exception:
                    pass
                self.waiting_for_react_login = True

            # Initialize Telegram bot if token is available
            if self.telegram_token:
                self.logger.info("🤖 Initializing Telegram bot...")
                try:
                    # Share WebSocket client and decision engine to avoid duplicates
                    self.telegram_bot = PetTelegramBot(
                        websocket_client=self.websocket_client,
                        decision_engine=self.decision_engine,
                    )
                    # Start Telegram bot in background
                    asyncio.create_task(self._run_telegram_bot())
                    self.logger.info(
                        "✅ Telegram bot initialized with shared components"
                    )
                except Exception as e:
                    self.logger.error(f"❌ Failed to initialize Telegram bot: {e}")
            else:
                self.logger.info("ℹ️ No TELEGRAM_BOT_TOKEN found - Telegram disabled")

            self.olas.update_health_status("running", is_transitioning=False)
            self.logger.info("✅ Pett Agent initialization complete")
            return True

        except Exception as e:
            self.logger.error(f"❌ Failed to initialize Pett Agent: {e}")
            self.olas.update_health_status("error", is_transitioning=False)
            return False

    async def _run_telegram_bot(self):
        """Run Telegram bot in background."""
        try:
            if self.telegram_bot:
                self.logger.info("🤖 Starting Telegram bot...")
                await self.telegram_bot.run()
        except Exception as e:
            self.logger.error(f"❌ Error in Telegram bot: {e}")

    async def _check_withdrawal_mode(self):
        """Check and handle withdrawal mode."""
        if self.olas.withdrawal_mode:
            self.logger.info("💰 Withdrawal mode detected")
            if self.olas.handle_withdrawal():
                self.logger.info("💰 Withdrawal completed, shutting down...")
                self.running = False

    async def _health_monitor(self):
        """Monitor agent health and update status."""
        while self.running:
            try:
                # Check WebSocket connection
                if self.websocket_client:
                    if not self.websocket_client.is_connected():
                        # Skip reconnection if waiting for React login
                        if self.waiting_for_react_login:
                            self.logger.debug(
                                "⏸️  Waiting for user to login via React - skipping reconnection"
                            )
                            await asyncio.sleep(30)
                            continue

                        self.logger.warning(
                            "⚠️ WebSocket disconnected, attempting reconnection..."
                        )
                        self.olas.update_health_status(
                            "reconnecting", is_transitioning=True
                        )
                        self.olas.update_websocket_status(
                            connected=False, authenticated=False
                        )

                        # Try to reconnect
                        connected = (
                            await self.websocket_client.connect_and_authenticate()
                        )
                        if connected:
                            self.logger.info("✅ WebSocket reconnected")

                            self.olas.update_health_status(
                                "running", is_transitioning=False
                            )
                            self.olas.update_websocket_status(
                                connected=True, authenticated=True
                            )

                            # Try to get updated pet status
                            try:
                                pet_status_result = self.pett_tools.get_pet_status()
                                if "❌" not in pet_status_result:
                                    pet_connected = True
                                    if "Pet Status:" in pet_status_result:
                                        pet_status = "Active"
                                    else:
                                        pet_status = "Connected"
                                else:
                                    pet_connected = False
                                    pet_status = "Error"
                                self.olas.update_pet_status(pet_connected, pet_status)
                            except Exception as e:
                                self.logger.debug(
                                    f"Could not get pet status after reconnect: {e}"
                                )
                                self.olas.update_pet_status(False, "Unknown")
                        else:
                            self.logger.error("❌ WebSocket reconnection failed")
                            self.olas.update_health_status(
                                "error", is_transitioning=False
                            )
                            self.olas.update_websocket_status(
                                connected=False, authenticated=False
                            )
                            self.olas.update_pet_status(False, "Disconnected")

                # Check for withdrawal mode
                await self._check_withdrawal_mode()

                # Sleep for health check interval
                await asyncio.sleep(30)  # Check every 30 seconds

            except Exception as e:
                self.logger.error(f"❌ Error in health monitor: {e}")
                await asyncio.sleep(10)  # Shorter sleep on error

    async def update_privy_token(
        self, privy_token: str, *, max_retries: int = 3, auth_timeout: int = 10
    ) -> bool:
        """Update the Privy token at runtime and refresh WebSocket state."""
        token = (privy_token or "").strip()
        if not token:
            self.logger.error("❌ Received empty Privy token from UI")
            return False

        self.logger.info("🔐 Updating Privy token and refreshing WebSocket connection")

        # Clear waiting flag since we have a new token
        self.waiting_for_react_login = False

        # Persist the token for other components
        self.privy_token = token
        os.environ["PRIVY_TOKEN"] = token

        token_preview = f"{token[:6]}...{token[-4:]}" if len(token) > 12 else token
        self.olas.env_vars["PRIVY_TOKEN"] = token_preview

        if not self.websocket_client:
            self.logger.info("🔌 Creating WebSocket client with new Privy token")
            self.websocket_client = PettWebSocketClient(
                websocket_url=self.websocket_url, privy_token=token
            )
            try:
                self.websocket_client.set_action_recorder(
                    self.olas.get_action_recorder()
                )
                try:
                    recorder3 = self.olas.get_action_recorder()
                    if recorder3 and recorder3.is_enabled:
                        addr_preview3 = "unknown"
                        if recorder3.account_address:
                            aa3 = recorder3.account_address
                            addr_preview3 = f"{aa3[:6]}...{aa3[-4:]}"
                        self.logger.info(
                            "🧾 On-chain action recorder ENABLED: contract=%s rpc=%s agent=%s",
                            recorder3.contract_address,
                            recorder3.rpc_url,
                            addr_preview3,
                        )
                    else:
                        self.logger.info(
                            "🧾 On-chain action recorder DISABLED (missing key or RPC)"
                        )
                except Exception:
                    pass
            except Exception:
                pass
            try:

                def _recorder_msg2(
                    m: Dict[str, Any], success: bool, err: Optional[str]
                ) -> None:
                    self.olas.record_client_send(m, success=success, error=err)

                self.websocket_client.set_telemetry_recorder(_recorder_msg2)
            except Exception:
                pass
        else:
            self.websocket_client.set_privy_token(token)
            try:
                self.websocket_client.set_action_recorder(
                    self.olas.get_action_recorder()
                )
            except Exception:
                pass

        connected = await self.websocket_client.refresh_token_and_reconnect(
            token, max_retries=max_retries, auth_timeout=auth_timeout
        )
        if not connected:
            self.logger.error(
                "❌ Failed to authenticate WebSocket with new Privy token"
            )
            self.olas.update_websocket_status(
                connected=self.websocket_client.is_connected(), authenticated=False
            )
            return False

        self.logger.info("✅ WebSocket re-authenticated with updated Privy token")
        self.olas.update_websocket_status(connected=True, authenticated=True)
        self.olas.update_health_status("running", is_transitioning=False)

        # Ensure OpenAI API key is set
        openai_key = self.olas.get_env_var("OPENAI_API_KEY")
        if openai_key:
            os.environ["OPENAI_API_KEY"] = openai_key

        if self.decision_engine:
            self.decision_engine.websocket_client = self.websocket_client
            self.decision_engine.pett_tools.set_client(self.websocket_client)
            # Ensure recorder remains wired
            try:

                def _recorder_prompt2(
                    kind: str, prompt: str, ctx: Optional[Dict[str, Any]]
                ) -> None:
                    self.olas.record_openai_prompt(kind, prompt, context=ctx)

                self.decision_engine.set_prompt_recorder(_recorder_prompt2)
            except Exception:
                pass
            self.pett_tools = self.decision_engine.pett_tools
        else:
            self.decision_engine = PetDecisionEngine(self.websocket_client)
            try:

                def _recorder_prompt3(
                    kind: str, prompt: str, ctx: Optional[Dict[str, Any]]
                ) -> None:
                    self.olas.record_openai_prompt(kind, prompt, context=ctx)

                self.decision_engine.set_prompt_recorder(_recorder_prompt3)
            except Exception:
                pass
            self.pett_tools = self.decision_engine.pett_tools

        try:
            pet_status_result = self.pett_tools.get_pet_status()
            if "❌" not in pet_status_result:
                pet_connected = True
                pet_status = (
                    "Active" if "Pet Status:" in pet_status_result else "Connected"
                )
                pet_data = self.websocket_client.get_pet_data()
                if pet_data:
                    self.olas.update_pet_data(pet_data)
            else:
                pet_connected = False
                pet_status = "Error"
                self.olas.update_pet_data(None)
            self.olas.update_pet_status(pet_connected, pet_status)
        except Exception as e:
            self.logger.debug(f"Could not refresh pet status after Privy login: {e}")
            self.olas.update_pet_status(True, "Connected")

        return True

    async def logout_privy(self) -> bool:
        """Clear Privy token, disconnect, and return to pre-login state."""
        try:
            self.logger.info("🔓 Logging out: clearing Privy token and disconnecting")

            # Enter waiting state for next React login
            self.waiting_for_react_login = True

            # Clear stored token and environment
            self.privy_token = ""
            try:
                if "PRIVY_TOKEN" in os.environ:
                    del os.environ["PRIVY_TOKEN"]
            except Exception:
                pass

            # Update Olas visible env snapshot
            try:
                if "PRIVY_TOKEN" in self.olas.env_vars:
                    self.olas.env_vars.pop("PRIVY_TOKEN", None)
            except Exception:
                pass

            # Tear down websocket auth and disconnect
            if self.websocket_client:
                try:
                    self.websocket_client.set_privy_token("")
                except Exception:
                    pass
                try:
                    await self.websocket_client.disconnect()
                except Exception:
                    pass

            # Reset runtime status
            self.olas.update_websocket_status(connected=False, authenticated=False)
            self.olas.update_pet_status(False, "Disconnected")
            self.olas.update_pet_data(None)
            self.olas.update_health_status("running", is_transitioning=False)

            self.logger.info("✅ Logout complete; awaiting React login")
            return True
        except Exception as e:
            self.logger.error(f"❌ Logout failed: {e}")
            return False

    async def _pet_action_loop(self):
        """Main pet action loop - your existing logic."""
        while self.running:
            try:
                # Initialize next_action_at lazily
                if self.next_action_at is None:
                    self.next_action_at = datetime.now()

                if self.websocket_client and self.websocket_client.is_authenticated():
                    # Your existing pet management logic can go here

                    # Get pet status periodically
                    if self.pett_tools:
                        try:
                            # If it's not yet time, sleep just until the next action
                            now = datetime.now()
                            if self.next_action_at and now < self.next_action_at:
                                sleep_seconds = max(
                                    (self.next_action_at - now).total_seconds(), 1
                                )
                                await asyncio.sleep(min(sleep_seconds, 30))
                                continue

                            pet_status_result = self.pett_tools.get_pet_status()
                            if "❌" not in pet_status_result:
                                self.logger.debug("🐾 Pet agent running action...")

                                pet_connected = True
                                if "Pet Status:" in pet_status_result:
                                    pet_status = "Active"
                                else:
                                    pet_status = "Connected"

                                # Also get and update the actual pet data
                                if (
                                    self.websocket_client
                                    and self.websocket_client.is_connected()
                                ):
                                    pet_data = self.websocket_client.get_pet_data()
                                    if pet_data:
                                        self.olas.update_pet_data(pet_data)
                                        self.logger.debug(
                                            f"Pet data updated: {pet_data}"
                                        )

                                        # Decide and perform actions based on current state
                                        try:
                                            await self._decide_and_perform_actions(pet_data)  # type: ignore[arg-type]
                                            # Update scheduler timestamps
                                            self.last_action_at = datetime.now()
                                            self.next_action_at = (
                                                self.last_action_at
                                                + timedelta(
                                                    minutes=self.action_interval_minutes
                                                )
                                            )
                                        except Exception as e:
                                            self.logger.debug(
                                                f"Action decision error: {e}"
                                            )
                            else:
                                pet_connected = False
                                pet_status = "Error"
                                # Clear pet data on error
                                self.olas.update_pet_data(None)

                            self.olas.update_pet_status(pet_connected, pet_status)
                            self.logger.debug(f"Pet status updated: {pet_status}")
                        except Exception as e:
                            self.logger.debug(f"Pet tools error: {e}")
                            self.olas.update_pet_status(False, "Error")
                            self.olas.update_pet_data(None)
                    else:
                        self.logger.error("❌ No WebSocket client or PettTools found")
                        self.olas.update_pet_status(False, "Disconnected")
                        self.olas.update_pet_data(None)

                # Idle sleep; keep modest to allow shutdown responsiveness
                await asyncio.sleep(5)

            except Exception as e:
                self.logger.error(f"❌ Error in pet action loop: {e}")
                await asyncio.sleep(30)  # Sleep on error

    def _to_float(self, value: Union[str, int, float, None]) -> float:
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(str(value))
        except Exception:
            return 0.0

    async def _recover_low_health(self) -> bool:
        """Attempt to recover health using SMALL_POTION or SALAD.

        Preference:
        1) Use SMALL_POTION via CONSUMABLES_USE (blueprintID: SMALL_POTION)
        2) Fallback to eat SALAD (blueprintID: SALAD) via use_consumable
        """
        if self._low_health_recovery_in_progress:
            return False
        self._low_health_recovery_in_progress = True
        try:
            if not self.websocket_client:
                return False

            client = self.websocket_client

            # Try small health potion first
            self.logger.info("🧪 Trying SMALL_POTION to restore health")
            # The API path for potion use is via buy/use or direct consumable use when owned.
            # We try direct consumable use by blueprint id.
            try:
                success = await client.use_consumable("SMALL_POTION")
                if success:
                    self.logger.info("✅ SMALL_POTION use confirmed")
                    await asyncio.sleep(0.5)
                    return True
                # If use failed, try to buy one then use again
                self.logger.info("🛒 SMALL_POTION not available; attempting to buy 1")
                bought = await client.buy_consumable(
                    "SMALL_POTION", 1, record_on_chain=False
                )
                if bought:
                    await asyncio.sleep(0.5)
                    self.logger.info("🔁 Using SMALL_POTION after purchase")
                    success = await client.use_consumable("SMALL_POTION")
                    if success:
                        self.logger.info("✅ SMALL_POTION use confirmed after purchase")
                        await asyncio.sleep(0.5)
                        return True
            except Exception as e:
                self.logger.debug(f"Small potion use/buy failed: {e}")

            # Fallback to SALAD (improves health and hunger)
            self.logger.info("🥗 Falling back to SALAD to recover health")
            try:
                success = await client.use_consumable("SALAD")
                if success:
                    self.logger.info("✅ SALAD consumption confirmed")
                    await asyncio.sleep(0.5)
                    return True
                # If use failed, try to buy one then use again
                self.logger.info("🛒 SALAD not available; attempting to buy 1")
                bought = await client.buy_consumable("SALAD", 1, record_on_chain=False)
                if bought:
                    await asyncio.sleep(0.5)
                    self.logger.info("🔁 Using SALAD after purchase")
                    success = await client.use_consumable("SALAD")
                    if success:
                        self.logger.info(
                            "✅ SALAD consumption confirmed after purchase"
                        )
                        await asyncio.sleep(0.5)
                        return True
            except Exception as e:
                self.logger.debug(f"Salad use/buy failed: {e}")

            return False
        finally:
            self._low_health_recovery_in_progress = False

    async def _on_client_error_message(self, message: Dict[str, Any]) -> None:
        """Handle server error messages to auto-recover from low health errors."""
        try:
            error = None
            if "data" in message:
                error = message.get("data", {}).get("error")
            if not error:
                error = message.get("error")

            if not error:
                return

            error_str = str(error).lower()
            if (
                "not have enough health" in error_str
                or "not enough health" in error_str
            ):
                self.logger.info(
                    "🩹 Detected 'not enough health' error; attempting recovery"
                )
                await self._recover_low_health()
        except Exception as e:
            self.logger.debug(f"Error handler encountered exception: {e}")

    async def _on_client_pet_update_message(self, message: Dict[str, Any]) -> None:
        """Update Olas pet data immediately when live pet_update arrives."""
        try:
            if not self.websocket_client:
                return
            pet_data = self.websocket_client.get_pet_data()
            if pet_data:
                self.olas.update_pet_data(pet_data)
                # Attach post-action stats to the latest recorded action
                self.olas.update_last_action_stats()
        except Exception as e:
            self.logger.debug(f"Pet update handler encountered exception: {e}")

    async def _random_action(self, client: PettWebSocketClient) -> None:
        actions = [
            (client.rub_pet, "rub"),
            (client.shower_pet, "shower"),
            (client.throw_ball, "throw_ball"),
        ]
        action_func, action_name = random.choice(actions)
        self.logger.info(f"🎲 Performing random action: {action_name}")
        await action_func()

    async def _decide_and_perform_actions(
        self, pet_data: "PettAgent.PetDataDict"
    ) -> None:
        if not self.websocket_client or not self.pett_tools:
            self.logger.error("❌ No WebSocket client or PettTools found")
            self.olas.update_pet_status(False, "Error")
            self.olas.update_pet_data(None)
            return

        client = self.websocket_client
        stats: Dict[str, Any] = pet_data.get("PetStats", {})  # type: ignore[assignment]
        sleeping: bool = bool(pet_data.get("sleeping", False))

        hygiene = self._to_float(stats.get("hygiene", 0))
        happiness = self._to_float(stats.get("happiness", 0))
        energy = self._to_float(stats.get("energy", 0))
        hunger = self._to_float(stats.get("hunger", 0))
        health = self._to_float(stats.get("health", 0))

        # Top-priority: low energy -> sleep
        if energy < self.LOW_ENERGY_THRESHOLD and not sleeping:
            self.logger.info("😴 Low energy detected; initiating sleep")
            await client.sleep_pet()
            return

        if energy > 100 - self.LOW_ENERGY_THRESHOLD and sleeping:
            self.logger.info("🔥 High energy detected; initiating wake")
            await client.sleep_pet(record_on_chain=False)
            sleeping = False

        # If pet is sleeping and we are about to perform non-sleep actions, nudge to wake
        if sleeping:
            self.logger.info("🛌 Pet is sleeping; waking up to perform actions")
            await client.sleep_pet(record_on_chain=False)
            await asyncio.sleep(0.5)
            sleeping = False

        # Priority 0: low health -> attempt recovery
        if health < self.LOW_THRESHOLD:
            self.logger.info("🩹 Low health detected; attempting recovery")
            recovered = await self._recover_low_health()
            if not recovered:
                self.logger.warning("⚠️ Health recovery failed")
            return

        if random.random() < 0.15:
            self.logger.info(
                "🎲 Random variance: performing random_action instead of shower"
            )
            await self._random_action(client)
            return

        # Priority 1: low hygiene -> shower
        if hygiene < self.LOW_THRESHOLD:
            # Small randomness to occasionally do a different engaging action
            self.logger.info("🚿 Low hygiene detected; showering pet")
            await client.shower_pet()
            return

        # Priority 2: low hunger -> use AI decision engine to pick best food
        if hunger < self.LOW_THRESHOLD:
            self.logger.info("🍔 Low hunger detected; using AI to select best food")
            if self.decision_engine:
                success = await self.decision_engine.feed_best_owned_food(stats)
                if not success:
                    self.logger.warning(
                        "⚠️ AI food selection failed; skipping fallback use"
                    )
            else:
                self.logger.warning(
                    "⚠️ No decision engine available; skipping food selection"
                )
            return

        # Priority 3: low happiness -> throw ball 3 times with delays
        if happiness < self.LOW_THRESHOLD:
            self.logger.info("🎾 Low happiness detected; throwing ball 3 times")
            for _ in range(3):
                await client.throw_ball()
                await asyncio.sleep(0.5)
            return

        # Fallback: random action
        self.logger.info("🎲 No priority actions; performing random_action")
        await self._random_action(client)

    async def run(self):
        """Run the Pett Agent."""
        if not await self.initialize():
            self.logger.error("❌ Failed to initialize agent")
            return

        self.running = True
        self.logger.info("🎯 Pett Agent is now running...")

        try:
            # Start background tasks
            tasks = [
                asyncio.create_task(self._health_monitor()),
                asyncio.create_task(self._pet_action_loop()),
            ]

            # Run until shutdown
            await asyncio.gather(*tasks)

        except KeyboardInterrupt:
            self.logger.info("🛑 Shutdown requested by user")
        except Exception as e:
            self.logger.error(f"❌ Error in main loop: {e}")
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Shutdown the agent gracefully."""
        self.logger.info("🛑 Shutting down Pett Agent...")
        self.running = False

        try:
            # Update health status
            self.olas.update_health_status("shutting_down", is_transitioning=True)

            # Disconnect WebSocket
            if self.websocket_client:
                await self.websocket_client.disconnect()
                self.logger.info("🔌 WebSocket disconnected")

            # Stop web server
            await self.olas.stop_web_server()

            # Final health status
            self.olas.update_health_status("stopped", is_transitioning=False)
            self.logger.info("✅ Pett Agent shutdown complete")

        except Exception as e:
            self.logger.error(f"❌ Error during shutdown: {e}")

    def get_action_timing_info(self) -> Dict[str, Any]:
        """Expose action scheduling info for UI/health."""
        now = datetime.now()
        next_at = self.next_action_at or now
        minutes_until = max(int((next_at - now).total_seconds() // 60), 0)
        return {
            "action_interval_minutes": self.action_interval_minutes,
            "next_action_at": next_at.isoformat(),
            "minutes_until_next_action": minutes_until,
            "next_action_scheduled": True,
        }
