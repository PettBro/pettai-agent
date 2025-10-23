import asyncio
import json
import logging
import os
import random
from typing import Any, Callable, Dict, List, Optional

import websockets
from dotenv import load_dotenv

from .action_recorder import ActionRecorder

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def format_wei_to_eth(wei_value: str | int, decimals: int = 4) -> str:
    """
    Convert wei value to ETH with specified decimal places.

    Args:
        wei_value: The wei value as string or int
        decimals: Number of decimal places to show (default: 4)

    Returns:
        Formatted ETH value as string
    """
    try:
        # Convert to int if it's a string
        if isinstance(wei_value, str):
            wei_value = int(wei_value)

        # Convert wei to ETH (1 ETH = 10^18 wei)
        eth_value = wei_value / (10**18)

        # Format with specified decimal places
        return f"{eth_value:.{decimals}f}"
    except (ValueError, TypeError, ZeroDivisionError):
        return "0.0000"


class PettWebSocketClient:
    def __init__(
        self,
        websocket_url: str | None = os.getenv(
            "WEBSOCKET_URL",
            (
                "wss://ws.pett.ai"
                if os.getenv("NODE_ENV") == "production"
                else "wss://ws.pett.ai"
            ),
        ),
        privy_token: Optional[str] = None,
    ):
        self.websocket_url = websocket_url
        self.websocket: Optional[Any] = None
        self.authenticated = False
        self.pet_data: Optional[Dict[str, Any]] = None
        self.message_handlers: Dict[str, List[Callable]] = {}
        self.connection_established = False
        self.privy_token = (privy_token or os.getenv("PRIVY_TOKEN") or "").strip()
        self.data_message: Optional[Dict[str, Any]] = None
        self.ai_search_future: Optional[asyncio.Future[str]] = None
        self.kitchen_future: Optional[asyncio.Future[str]] = None
        self.mall_future: Optional[asyncio.Future[str]] = None
        self.closet_future: Optional[asyncio.Future[str]] = None
        self.auth_future: Optional[asyncio.Future[bool]] = None
        self._last_auth_error: Optional[str] = None
        self._listener_task: Optional[asyncio.Task] = None
        self._jwt_expired: bool = False
        # Outgoing message telemetry recorder: (message, success, error)
        self._telemetry_recorder: Optional[
            Callable[[Dict[str, Any], bool, Optional[str]], None]
        ] = None
        # Pending nonce -> future mapping for correlating responses
        self._pending_nonces: Dict[str, asyncio.Future[Dict[str, Any]]] = {}
        if not self.privy_token:
            logger.warning(
                "Privy token not provided during initialization; authentication will be disabled until a token is set."
            )
        self._action_recorder: Optional[ActionRecorder] = None

    def set_telemetry_recorder(
        self, recorder: Optional[Callable[[Dict[str, Any], bool, Optional[str]], None]]
    ) -> None:
        """Set a callback to record outgoing messages and outcomes."""
        self._telemetry_recorder = recorder

    def set_action_recorder(self, recorder: Optional[ActionRecorder]) -> None:
        """Attach the action recorder used for on-chain reporting."""
        self._action_recorder = recorder

    def _schedule_record_action(self, action_type: str, amount: int = 1) -> None:
        """Schedule an asynchronous recordAction transaction if the recorder is available."""
        if not self._action_recorder or not self._action_recorder.is_enabled:
            return

        normalized_type = (action_type or "").upper()
        if not normalized_type:
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop (e.g., during tests); skip recording.
            return

        task = loop.create_task(
            self._action_recorder.record_action(normalized_type, amount)
        )

        def _handle_result(fut: asyncio.Future) -> None:
            if fut.cancelled():
                return
            exc = fut.exception()
            if exc:
                logger.debug("Action recorder task raised for %s: %s", action_type, exc)

        task.add_done_callback(_handle_result)

    def _generate_nonce(self) -> str:
        """Generate a simple random numeric nonce as a string."""
        return str(random.randint(10000, 99999))

    def _register_pending(self, nonce: str) -> asyncio.Future:
        """Create and register a pending future for the given nonce."""
        fut: asyncio.Future = asyncio.Future()
        self._pending_nonces[nonce] = fut  # type: ignore[assignment]
        return fut

    def _resolve_pending(self, nonce: Optional[str], message: Dict[str, Any]) -> None:
        """Resolve any pending future by nonce with the provided message."""
        if not nonce:
            return
        fut = self._pending_nonces.pop(nonce, None)
        if fut and not fut.done():
            try:
                fut.set_result(message)
            except Exception:
                # Ignore resolution errors to avoid cascading failures
                pass

    async def connect(self) -> bool:
        """Establish WebSocket connection to Pett.ai server."""
        try:
            if not self.websocket_url:
                logger.error("WebSocket URL is not set")
                return False

            logger.info(f"🔌 Connecting to WebSocket: {self.websocket_url}")
            self.websocket = await websockets.connect(
                self.websocket_url, ping_interval=20, ping_timeout=10, close_timeout=10
            )
            self.connection_established = True
            logger.info("✅ WebSocket connection established")
            return True
        except websockets.exceptions.InvalidURI as e:
            logger.error(f"❌ Invalid WebSocket URL: {e}")
            return False
        except websockets.exceptions.ConnectionClosed as e:
            logger.error(f"❌ WebSocket connection closed: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Failed to connect to WebSocket: {e}")
            return False

    async def disconnect(self) -> None:
        """Close WebSocket connection."""
        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        self._listener_task = None
        if self.websocket:
            await self.websocket.close()
        self.websocket = None
        self.connection_established = False
        self.authenticated = False
        logger.info("WebSocket connection closed")

    def set_privy_token(self, privy_token: str) -> None:
        """Update the stored Privy token without reconnecting."""
        token = (privy_token or "").strip()
        if not token:
            logger.warning(
                "⚠️ Attempted to set an empty Privy token - authentication will be disabled"
            )
            self.privy_token = ""
            return
        self.privy_token = token
        self._jwt_expired = False
        self._last_auth_error = None
        logger.info("Privy token updated on WebSocket client")

    async def refresh_token_and_reconnect(
        self, privy_token: str, max_retries: int = 3, auth_timeout: int = 10
    ) -> bool:
        """Update token, reset state, and reconnect/authenticate."""
        token = (privy_token or "").strip()
        if not token:
            logger.error("Cannot refresh connection with empty Privy token")
            return False

        self.set_privy_token(token)

        await self.disconnect()
        return await self.connect_and_authenticate(
            max_retries=max_retries, auth_timeout=auth_timeout
        )

    async def authenticate(self, timeout: int = 10) -> bool:
        """Default authentication using Privy token with timeout."""
        if not self.privy_token or not self.privy_token.strip():
            logger.warning("⚠️ No Privy token available for authentication")
            return False

        return await self.authenticate_privy(self.privy_token, timeout)

    async def authenticate_privy(
        self, privy_auth_token: str, timeout: int = 10
    ) -> bool:
        """Authenticate using Privy credentials with timeout and result waiting."""
        if not privy_auth_token or not privy_auth_token.strip():
            logger.error("Invalid Privy auth token provided")
            return False

        try:
            # Create a future to wait for the auth result
            auth_future: asyncio.Future[bool] = asyncio.Future()

            # Store the future so we can resolve it in the message handler
            self.auth_future = auth_future

            auth_message = {
                "type": "AUTH",
                "data": {
                    "params": {
                        "authHash": {"hash": "Bearer " + privy_auth_token.strip()},
                        "authType": "privy",
                    }
                },
            }

            # Send the auth message
            success = await self._send_message(auth_message)
            if not success:
                logger.error("Failed to send authentication message")
                return False

            logger.info("🔐 Authentication message sent, waiting for response...")

            # Wait for the auth result with timeout
            try:
                auth_result = await asyncio.wait_for(auth_future, timeout=timeout)
                logger.info(f"🔐 Authentication result: {auth_result}")
                return auth_result
            except asyncio.TimeoutError:
                logger.error(f"❌ Authentication timed out after {timeout} seconds")
                return False

        except Exception as e:
            logger.error(f"❌ Error during authentication: {e}")
            return False
        finally:
            # Clean up the future
            self.auth_future = None

    async def register_privy(self, pet_name: str, privy_auth_token: str) -> bool:
        """Register a new pet using Privy authentication."""
        if not pet_name or not pet_name.strip():
            logger.error("Invalid pet name provided")
            return False

        if not privy_auth_token or not privy_auth_token.strip():
            logger.error("Invalid Privy auth token provided")
            return False

        register_message = {
            "type": "REGISTER",
            "data": {
                "params": {
                    "registerHash": {
                        "name": pet_name.strip(),
                        "hash": "Bearer " + privy_auth_token.strip(),
                    },
                    "authType": "privy",
                }
            },
        }

        return await self._send_message(register_message)

    async def connect_and_authenticate(
        self, max_retries: int = 3, auth_timeout: int = 10
    ) -> bool:
        """Connect to WebSocket and authenticate using Privy token with retry logic."""
        # Skip authentication if no privy token or empty token
        if not self.privy_token or not self.privy_token.strip():
            logger.warning(
                "⚠️ No Privy token available - skipping authentication and retries"
            )
            return False

        for attempt in range(max_retries):
            try:
                logger.info(f"🔄 Connection attempt {attempt + 1}/{max_retries}")

                # Try to connect
                if not await self.connect():
                    logger.warning(f"❌ Connection attempt {attempt + 1} failed")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2**attempt)  # Exponential backoff
                        continue
                    return False

                logger.info("✅ WebSocket connected, starting message listener...")

                # Start listening for messages BEFORE authentication
                if self._listener_task and not self._listener_task.done():
                    self._listener_task.cancel()
                self._listener_task = asyncio.create_task(self.listen_for_messages())
                logger.info("👂 Started WebSocket message listener")

                logger.info("🔐 Attempting authentication...")
                # Try to authenticate
                auth_success = await self.authenticate(timeout=auth_timeout)
                if not auth_success:
                    logger.warning(f"❌ Authentication attempt {attempt + 1} failed")
                    await self.disconnect()

                    # Check if it's a JWT expiration error - don't retry in this case
                    if hasattr(self, "_last_auth_error") and self._last_auth_error:
                        if any(
                            keyword in str(self._last_auth_error).lower()
                            for keyword in [
                                "exp",
                                "jwt_expired",
                                "timestamp check failed",
                                "jwt",
                            ]
                        ):
                            self._jwt_expired = True
                            logger.critical(
                                "💀 JWT token expired - awaiting new token before reconnecting."
                            )
                            return False

                    if attempt < max_retries - 1:
                        await asyncio.sleep(2**attempt)  # Exponential backoff
                        continue
                    return False

                logger.info("✅ Connection and authentication successful!")
                return True

            except Exception as e:
                logger.error(f"❌ Error in connection attempt {attempt + 1}: {e}")
                await self.disconnect()
                if attempt < max_retries - 1:
                    await asyncio.sleep(2**attempt)  # Exponential backoff
                    continue
                return False

        return False

    async def _send_message(self, message: Dict[str, Any]) -> bool:
        """Send a message to the WebSocket server."""
        if not self.websocket or not self.connection_established:
            logger.error("WebSocket not connected")
            if self._telemetry_recorder:
                try:
                    self._telemetry_recorder(message, False, "WebSocket not connected")
                except Exception:
                    pass
            return False

        try:
            # Ensure a nonce is present on every outgoing message
            if "nonce" not in message:
                message["nonce"] = self._generate_nonce()
            message_json = json.dumps(message)
            await self.websocket.send(message_json)
            logger.info(f"📤 Sent message type: {message['type']}")
            logger.info(f"📤 Message content: {message_json}")
            if self._telemetry_recorder:
                try:
                    self._telemetry_recorder(message, True, None)
                except Exception:
                    pass
            return True
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            if self._telemetry_recorder:
                try:
                    self._telemetry_recorder(message, False, str(e))
                except Exception:
                    pass
            return False

    async def _send_and_wait(
        self,
        msg_type: str,
        data: Optional[Dict[str, Any]] = None,
        timeout: int = 10,
    ) -> tuple[bool, Optional[Dict[str, Any]]]:
        """Send a message with a nonce and wait for the correlated response.

        Returns a tuple of (success, response_message). Success is False if an error
        message is received or the wait times out or sending fails.
        """
        nonce = self._generate_nonce()
        future = self._register_pending(nonce)

        message: Dict[str, Any] = {
            "type": msg_type,
            "data": data or {},
            "nonce": nonce,
        }

        sent = await self._send_message(message)
        if not sent:
            # Clean up pending future
            try:
                if nonce in self._pending_nonces:
                    self._pending_nonces.pop(nonce, None)
            except Exception:
                pass
            return False, None

        try:
            response: Dict[str, Any] = await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            # No correlated error arrived within the window; assume success
            logger.info(
                f"⏱️ No error received within {timeout}s for {msg_type} (nonce {nonce}); assuming success"
            )
            return True, None
        except Exception as e:
            logger.error(
                f"❌ Error awaiting response for {msg_type} (nonce {nonce}): {e}"
            )
            return False, None

        # Treat explicit error type as failure
        if isinstance(response, dict) and (response.get("type") == "error"):
            return False, response

        return True, response

    async def listen_for_messages(self) -> None:
        """Listen for incoming messages from the server."""
        if not self.websocket or not self.connection_established:
            logger.error("❌ WebSocket not connected - cannot listen for messages")
            return

        logger.info("👂 Starting WebSocket message listener...")
        try:
            async for message in self.websocket:
                try:
                    message_data = json.loads(message)
                    await self._handle_message(message_data)
                except json.JSONDecodeError as e:
                    logger.error(f"❌ Failed to parse WebSocket message: {e}")
                    logger.error(f"❌ Raw message: {message}")
                except Exception as e:
                    logger.error(f"❌ Error handling WebSocket message: {e}")

        except websockets.exceptions.ConnectionClosed:
            logger.warning("⚠️ WebSocket connection closed during message listening")
            self.connection_established = False
        except Exception as e:
            logger.error(f"❌ Error in WebSocket message listener: {e}")
            self.connection_established = False

    async def _handle_message(self, message: Dict[str, Any]) -> None:
        """Handle incoming messages from the server."""
        message_type = message.get("type")
        # Resolve any waiting caller by nonce, if present
        try:
            self._resolve_pending(message.get("nonce"), message)
        except Exception:
            pass
        if message_type == "auth_result":
            await self._handle_auth_result(message)
        elif message_type == "pet_update":
            await self._handle_pet_update(message)
        elif message_type == "error":
            await self._handle_error(message)
        elif message_type == "data":
            await self._handle_data(message)

        # Call registered handlers
        if message_type in self.message_handlers:
            for handler in self.message_handlers[message_type]:
                try:
                    await handler(message)
                except Exception as e:
                    logger.error(f"Error in message handler: {e}")

    async def _handle_auth_result(self, message: Dict[str, Any]) -> None:
        """Handle authentication result message."""
        # Handle both message structures: with and without 'data' wrapper
        if "data" in message:
            data = message.get("data", {})
            success = data.get("success", False)
            error = data.get("error", "Unknown error")
            user_data = data.get("user", {})
            pet_data = data.get("pet", {})
        else:
            # Direct structure: {'type': 'auth_result', 'success': False, 'error': '...'}
            success = message.get("success", False)
            error = message.get("error", "Unknown error")
            user_data = message.get("user", {})
            pet_data = message.get("pet", {})

        if success:
            self.authenticated = True
            # Reset JWT expiration flag on successful auth
            self._jwt_expired = False
            self._last_auth_error = None  # Clear any previous errors

            # Extract pet data - now it's directly in the pet field
            if pet_data:
                # Use the pet data directly
                self.pet_data = pet_data
                logger.info("✅ Authentication successful!")
                logger.info(f"👤 User: {user_data.get('id', 'Unknown')}")
                logger.info(f"🔑 Privy ID: {user_data.get('privyID', 'Unknown')}")
                logger.info(f"📱 Telegram ID: {user_data.get('telegramID', 'Unknown')}")

                # Log pet information
                pet = self.pet_data
                if pet:
                    logger.info(f"🐾 Pet: {pet.get('name', 'Unknown')}")
                    logger.info(f"🆔 Pet ID: {pet.get('id', 'Unknown')}")
                    # Format balance from wei to ETH
                    raw_balance = pet.get("PetTokens", {}).get("tokens", "0")
                    formatted_balance = format_wei_to_eth(raw_balance)
                    logger.info(f"💰 Balance: {formatted_balance} $AIP")
                    logger.info(f"🏨 Hotel Tier: {pet.get('currentHotelTier', 0)}")
                    logger.info(f"💀 Dead: {pet.get('dead', False)}")
                    logger.info(f"😴 Sleeping: {pet.get('sleeping', False)}")

                    # Log pet stats
                    pet_stats = pet.get("PetStats", {})
                    if pet_stats:
                        logger.info("📊 Pet Stats:")
                        logger.info(f"   🍽️  Hunger: {pet_stats.get('hunger', 0)}")
                        logger.info(f"   ❤️  Health: {pet_stats.get('health', 0)}")
                        logger.info(f"   ⚡ Energy: {pet_stats.get('energy', 0)}")
                        logger.info(f"   😊 Happiness: {pet_stats.get('happiness', 0)}")
                        logger.info(f"   🧼 Hygiene: {pet_stats.get('hygiene', 0)}")
                        logger.info(
                            f"   🎯 XP: {pet_stats.get('xp', 0)}/"
                            f"{pet_stats.get('xpMax', 0)} (Level {pet_stats.get('level', 1)})"
                        )

            else:
                self.pet_data = {}
                logger.info("✅ Authentication successful but no pet found")
                logger.info(f"👤 User: {user_data.get('id', 'Unknown')}")
                logger.info(f"🔑 Privy ID: {user_data.get('privyID', 'Unknown')}")
                logger.info(f"📱 Telegram ID: {user_data.get('telegramID', 'Unknown')}")
        else:
            logger.error(f"❌ Authentication failed: {error}")
            self.authenticated = False

            # Store the error for retry logic
            self._last_auth_error = str(error)

            # Check if it's a JWT expiration error
            if (
                "exp" in str(error)
                or "JWT_EXPIRED" in str(error)
                or "timestamp check failed" in str(error)
            ):
                self._jwt_expired = True
                logger.error(
                    "🔑 JWT token has expired! Please get a new token from your authentication provider."
                )
                logger.error(
                    "💡 This usually means you need to refresh your Privy token or get a new one."
                )
                logger.error(self.get_token_refresh_instructions())
                logger.critical("💀 JWT token expired - waiting for refresh.")

        # Resolve the auth future if it exists
        if self.auth_future and not self.auth_future.done():
            self.auth_future.set_result(success)

    def _merge_pet_data(
        self, base: Dict[str, Any], new: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Merge new pet data into existing data, preserving nested fields when missing.

        - Only overwrite keys present in the new payload
        - For dict values (e.g., PetStats, PetTokens), perform a shallow merge
        - Preserve existing PetStats if the new payload lacks it or it is empty
        """
        if not isinstance(base, dict):
            base = {}

        merged: Dict[str, Any] = dict(base)

        for key, new_value in (new or {}).items():
            # Special handling for PetStats: ignore empty updates
            if key == "PetStats":
                if isinstance(new_value, dict) and new_value:
                    old_stats = merged.get("PetStats", {})
                    if isinstance(old_stats, dict):
                        # Shallow merge stats
                        updated_stats = dict(old_stats)
                        updated_stats.update(new_value)
                        merged["PetStats"] = updated_stats
                    else:
                        merged["PetStats"] = new_value
                else:
                    # Skip overwriting existing stats with empty/none
                    continue
                continue

            # Generic shallow merge for nested dicts
            if isinstance(new_value, dict) and isinstance(merged.get(key), dict):
                updated_dict = dict(merged.get(key) or {})
                updated_dict.update(new_value)
                merged[key] = updated_dict
            else:
                merged[key] = new_value

        return merged

    async def _handle_pet_update(self, message: Dict[str, Any]) -> None:
        """Handle pet update message."""
        # Handle both message structures: with and without 'data' wrapper
        if "data" in message:
            data = message.get("data", {})
            user_data = data.get("user", {})
            pet_data = data.get("pet", {})
        else:
            # Direct structure
            user_data = message.get("user", {})
            pet_data = message.get("pet", {})

        # Update pet data
        if pet_data:
            # Merge with existing data to avoid losing fields on partial updates
            if self.pet_data and isinstance(self.pet_data, dict):
                merged = self._merge_pet_data(self.pet_data, pet_data)
                # If pet id changes, prefer new payload entirely
                old_id = self.pet_data.get("id")
                new_id = pet_data.get("id")
                self.pet_data = merged if not old_id or old_id == new_id else pet_data
                logger.info("Pet Status updated (merged partial update)")
            else:
                self.pet_data = pet_data
                logger.info("Pet Status updated")
            logger.info(f"Updated pet data: {self.pet_data}")
        elif user_data:
            # If we got user data, extract pet from it
            pets = user_data.get("pets", [])
            if pets:
                pet_from_user = pets[0]
                if self.pet_data and isinstance(self.pet_data, dict):
                    self.pet_data = self._merge_pet_data(self.pet_data, pet_from_user)
                    logger.info("Pet updated from user data (merged)")
                else:
                    self.pet_data = pet_from_user
                    logger.info("Pet updated from user data")
                logger.info(f"Updated pet data: {self.pet_data}")

    async def _handle_error(self, message: Dict[str, Any]) -> None:
        """Handle error message."""
        error = message.get("error")
        logger.error(f"Server error: {error}")

    async def _handle_data(self, message: Dict[str, Any]) -> None:
        """Handle data message."""
        self.data_message = message
        logger.info("📊 Received data message")
        logger.info(f"Data message: {message}")

        # Handle AI search results
        if self.ai_search_future and not self.ai_search_future.done():
            try:
                # Extract AI search result from the message
                ai_result = message.get("data", {}).get("result", "")
                if ai_result:
                    self.ai_search_future.set_result(ai_result)
                else:
                    self.ai_search_future.set_result("No search results found")
            except Exception as e:
                logger.error(f"Error handling AI search result: {e}")
                if not self.ai_search_future.done():
                    self.ai_search_future.set_result(
                        f"Error processing search result: {str(e)}"
                    )

        # Handle kitchen data
        if self.kitchen_future and not self.kitchen_future.done():
            try:
                kitchen_data = message.get("data", {})
                if kitchen_data:
                    self.kitchen_future.set_result(json.dumps(kitchen_data, indent=2))
                else:
                    self.kitchen_future.set_result("No kitchen data found")
            except Exception as e:
                logger.error(f"Error handling kitchen data: {e}")
                if not self.kitchen_future.done():
                    self.kitchen_future.set_result(
                        f"Error processing kitchen data: {str(e)}"
                    )

        # Handle mall data
        if self.mall_future and not self.mall_future.done():
            try:
                mall_data = message.get("data", {})
                if mall_data:
                    self.mall_future.set_result(json.dumps(mall_data, indent=2))
                else:
                    self.mall_future.set_result("No mall data found")
            except Exception as e:
                logger.error(f"Error handling mall data: {e}")
                if not self.mall_future.done():
                    self.mall_future.set_result(f"Error processing mall data: {str(e)}")

        # Handle closet data
        if self.closet_future and not self.closet_future.done():
            try:
                closet_data = message.get("data", {})
                if closet_data:
                    self.closet_future.set_result(json.dumps(closet_data, indent=2))
                else:
                    self.closet_future.set_result("No closet data found")
            except Exception as e:
                logger.error(f"Error handling closet data: {e}")
                if not self.closet_future.done():
                    self.closet_future.set_result(
                        f"Error processing closet data: {str(e)}"
                    )

    def register_message_handler(self, message_type: str, handler: Callable) -> None:
        """Register a handler for a specific message type."""
        if message_type not in self.message_handlers:
            self.message_handlers[message_type] = []
        self.message_handlers[message_type].append(handler)

    # Pet action methods
    async def rub_pet(self) -> bool:
        """Rub the pet."""
        success, _ = await self._send_and_wait("RUB", {}, timeout=10)
        if success:
            logger.info("✅ RUB action confirmed by server; recording on-chain")
            self._schedule_record_action("RUB")
        return bool(success)

    async def shower_pet(self) -> bool:
        """Give the pet a shower."""
        success, _ = await self._send_and_wait("SHOWER", {}, timeout=10)
        if success:
            logger.info("✅ SHOWER action confirmed by server; recording on-chain")
            self._schedule_record_action("SHOWER")
        return bool(success)

    async def sleep_pet(self, record_on_chain: bool = True) -> bool:
        """Put the pet to sleep."""
        success, _ = await self._send_and_wait("SLEEP", {}, timeout=10)
        if success:
            logger.info("✅ SLEEP action confirmed by server")
            if record_on_chain:
                logger.info("📗 Recording SLEEP action on-chain")
                self._schedule_record_action("SLEEP")
        return bool(success)

    async def throw_ball(self) -> bool:
        """Throw a ball for the pet."""
        success, _ = await self._send_and_wait("THROWBALL", {}, timeout=10)
        if success:
            logger.info("✅ THROWBALL action confirmed by server; recording on-chain")
            self._schedule_record_action("THROWBALL")
        return bool(success)

    async def use_consumable(self, consumable_id: str) -> bool:
        """Use a consumable item."""
        if not consumable_id or not consumable_id.strip():
            logger.error(f"Invalid consumable ID provided: {consumable_id!r}")
            return False

        consumable_id = consumable_id.strip()
        logger.info(f"🍴 Using consumable: {consumable_id}")

        success, response = await self._send_and_wait(
            "CONSUMABLES_USE",
            {"params": {"foodId": consumable_id}},
            timeout=15,
        )

        if success:
            self._schedule_record_action("CONSUMABLES_USE")
            return True

        # Attempt auto-buy on "not found" error then retry once
        error_text = ""
        if isinstance(response, dict):
            error_text = str(response.get("error", ""))

        if error_text and ("not found" in error_text.lower()):
            logger.info(
                f"🛒 Consumable {consumable_id} not owned. Attempting to buy one and retry."
            )
            buy_success, _ = await self._send_and_wait(
                "CONSUMABLES_BUY",
                {"params": {"foodId": consumable_id, "amount": 1}},
                timeout=15,
            )
            if not buy_success:
                logger.warning(
                    f"❌ Failed to buy missing consumable {consumable_id}; will not retry use."
                )
                return False

            # Retry once after successful buy
            logger.info(f"🔁 Retrying use of {consumable_id} after purchase")
            retry_success, _ = await self._send_and_wait(
                "CONSUMABLES_USE",
                {"params": {"foodId": consumable_id}},
                timeout=15,
            )
            if retry_success:
                self._schedule_record_action("CONSUMABLES_USE")
            return bool(retry_success)

        return False

    async def buy_consumable(
        self, consumable_id: str, amount: int, *, record_on_chain: bool = True
    ) -> bool:
        """Buy a consumable item for the pet.

        Args:
            consumable_id: The ID of the consumable to buy. Allowed values:
                "BURGER", "SALAD", "STEAK", "COOKIE", "PIZZA", "SUSHI",
                "ENERGIZER", "POTION", "XP_POTION", "SUPER_XP_POTION",
                "SMALL_POTION", "LARGE_POTION", "REVIVE_POTION",
                "POISONOUS_ARROW", "REINFORCED_SHIELD", "BATTLE_SWORD",
                "ACCOUNTANT"
            amount: The number of consumables to buy (default: 1).
        """
        if not consumable_id or not consumable_id.strip():
            logger.error("Invalid consumable ID provided")
            return False

        if amount <= 0:
            logger.error("Amount must be greater than 0")
            return False

        success, _ = await self._send_and_wait(
            "CONSUMABLES_BUY",
            {"params": {"foodId": consumable_id.strip(), "amount": amount}},
            timeout=15,
        )
        if success and record_on_chain:
            self._schedule_record_action("CONSUMABLES_BUY", amount)
        return bool(success)

    async def get_consumables(self) -> bool:
        """Get available consumables."""
        logger.info("[TOOL] Getting consumables")
        success, _ = await self._send_and_wait("CONSUMABLES_GET", {}, timeout=10)
        return bool(success)

    async def get_kitchen(self) -> bool:
        """Get kitchen information."""
        success, _ = await self._send_and_wait("KITCHEN_GET", {}, timeout=10)
        return bool(success)

    async def get_kitchen_data(self, timeout: int = 10) -> str:
        """Get kitchen information and wait for the result.

        Args:
            timeout: Maximum time to wait for response in seconds (default: 10)

        Returns:
            The kitchen data as a JSON string, or error message if failed
        """
        try:
            # Create a future to wait for the kitchen data
            self.kitchen_future = asyncio.Future()

            # Send the kitchen request
            success = await self._send_message({"type": "KITCHEN_GET", "data": {}})

            if not success:
                return "❌ Failed to send kitchen request"

            logger.info("[TOOL] Sent kitchen request")
            logger.info(f"[TOOL] Waiting up to {timeout} seconds for response...")

            # Wait for the result with timeout
            try:
                result: str = await asyncio.wait_for(
                    self.kitchen_future, timeout=timeout
                )
                return result

            except asyncio.TimeoutError:
                logger.warning(
                    f"[TOOL] Kitchen request timed out after {timeout} seconds"
                )
                return f"❌ Kitchen request timed out after {timeout} seconds. Please try again."

        except Exception as e:
            logger.error(f"[TOOL] Error during kitchen request: {e}")
            return f"❌ Error during kitchen request: {str(e)}"
        finally:
            # Clean up the future
            self.kitchen_future = None

    async def get_mall(self) -> bool:
        """Get mall information."""
        success, _ = await self._send_and_wait("MALL_GET", {}, timeout=10)
        return bool(success)

    async def get_mall_data(self, timeout: int = 10) -> str:
        """Get mall information and wait for the result.

        Args:
            timeout: Maximum time to wait for response in seconds (default: 10)

        Returns:
            The mall data as a JSON string, or error message if failed
        """
        try:
            # Create a future to wait for the mall data
            self.mall_future = asyncio.Future()

            # Send the mall request
            success = await self._send_message({"type": "MALL_GET", "data": {}})

            if not success:
                return "❌ Failed to send mall request"

            logger.info("[TOOL] Sent mall request")
            logger.info(f"[TOOL] Waiting up to {timeout} seconds for response...")

            # Wait for the result with timeout
            try:
                result: str = await asyncio.wait_for(self.mall_future, timeout=timeout)
                return result

            except asyncio.TimeoutError:
                logger.warning(f"[TOOL] Mall request timed out after {timeout} seconds")
                return f"❌ Mall request timed out after {timeout} seconds. Please try again."

        except Exception as e:
            logger.error(f"[TOOL] Error during mall request: {e}")
            return f"❌ Error during mall request: {str(e)}"
        finally:
            # Clean up the future
            self.mall_future = None

    async def get_closet(self) -> bool:
        """Get closet information."""
        success, _ = await self._send_and_wait("CLOSET_GET", {}, timeout=10)
        return bool(success)

    async def get_closet_data(self, timeout: int = 10) -> str:
        """Get closet information and wait for the result.

        Args:
            timeout: Maximum time to wait for response in seconds (default: 10)

        Returns:
            The closet data as a JSON string, or error message if failed
        """
        try:
            # Create a future to wait for the closet data
            self.closet_future = asyncio.Future()

            # Send the closet request
            success = await self._send_message({"type": "CLOSET_GET", "data": {}})

            if not success:
                return "❌ Failed to send closet request"

            logger.info("[TOOL] Sent closet request")
            logger.info(f"[TOOL] Waiting up to {timeout} seconds for response...")

            # Wait for the result with timeout
            try:
                result: str = await asyncio.wait_for(
                    self.closet_future, timeout=timeout
                )
                return result

            except asyncio.TimeoutError:
                logger.warning(
                    f"[TOOL] Closet request timed out after {timeout} seconds"
                )
                return f"❌ Closet request timed out after {timeout} seconds. Please try again."

        except Exception as e:
            logger.error(f"[TOOL] Error during closet request: {e}")
            return f"❌ Error during closet request: {str(e)}"
        finally:
            # Clean up the future
            self.closet_future = None

    async def use_accessory(self, accessory_id: str) -> bool:
        """Use an accessory."""
        if not accessory_id or not accessory_id.strip():
            logger.error("Invalid accessory ID provided")
            return False

        success, _ = await self._send_and_wait(
            "ACCESSORY_USE",
            {"params": {"accessoryId": accessory_id.strip()}},
            timeout=10,
        )
        if success:
            self._schedule_record_action("ACCESSORY_USE")
        return bool(success)

    async def buy_accessory(self, accessory_id: str) -> bool:
        """Buy an accessory."""
        if not accessory_id or not accessory_id.strip():
            logger.error("Invalid accessory ID provided")
            return False

        success, _ = await self._send_and_wait(
            "ACCESSORY_BUY",
            {"params": {"accessoryId": accessory_id.strip()}},
            timeout=10,
        )
        if success:
            self._schedule_record_action("ACCESSORY_BUY")
        return bool(success)

    async def ai_search(self, prompt: str, timeout: int = 30) -> str:
        """Perform AI search and wait for the result.

        Args:
            prompt: The search prompt to send
            timeout: Maximum time to wait for response in seconds (default: 30)

        Returns:
            The search result as a string, or error message if failed
        """
        if not prompt or not prompt.strip():
            logger.error("Invalid search prompt provided")
            return "❌ Invalid search prompt provided"

        try:
            # Create a future to wait for the AI search result
            self.ai_search_future = asyncio.Future()

            # Send the AI search request
            success = await self._send_message(
                {
                    "type": "AI_SEARCH",
                    "data": {"params": {"prompt": prompt.strip(), "type": "web"}},
                }
            )

            if not success:
                return "❌ Failed to send AI search request"

            logger.info(f"[TOOL] Sent AI search request: {prompt}")
            logger.info(f"[TOOL] Waiting up to {timeout} seconds for response...")

            # Wait for the result with timeout
            try:
                result: str = await asyncio.wait_for(
                    self.ai_search_future, timeout=timeout
                )
                return result

            except asyncio.TimeoutError:
                logger.warning(f"[TOOL] AI search timed out after {timeout} seconds")
                return (
                    f"❌ AI search timed out after {timeout} seconds. Please try again."
                )

        except Exception as e:
            logger.error(f"[TOOL] Error during AI search: {e}")
            return f"❌ Error during AI search: {str(e)}"
        finally:
            # Clean up the future
            self.ai_search_future = None

    async def get_personality(self) -> bool:
        """Get pet personality information."""
        logger.info("[TOOL] Getting pet personality information")
        return await self._send_message({"type": "PERSONALITY_GET", "data": {}})

    async def generate_image(self, prompt: str) -> bool:
        """Generate an image."""
        if not prompt or not prompt.strip():
            logger.error("Invalid image prompt provided")
            return False

        return await self._send_message(
            {"type": "GEN_IMAGE", "data": {"params": {"prompt": prompt.strip()}}}
        )

    async def hotel_check_in(self) -> bool:
        """Check pet into hotel."""
        logger.info("[TOOL] Checking pet into hotel")
        success, _ = await self._send_and_wait("HOTEL_CHECK_IN", {}, timeout=10)
        if success:
            self._schedule_record_action("HOTEL_CHECK_IN")
        return bool(success)

    async def hotel_check_out(self) -> bool:
        """Check pet out of hotel."""
        logger.info("[TOOL] Checking pet out of hotel")
        success, _ = await self._send_and_wait("HOTEL_CHECK_OUT", {}, timeout=10)
        if success:
            self._schedule_record_action("HOTEL_CHECK_OUT")
        return bool(success)

    async def buy_hotel(self, tier: str) -> bool:
        """Buy hotel tier."""
        if not tier or not tier.strip():
            logger.error("Invalid hotel tier provided")
            return False

        success, _ = await self._send_and_wait(
            "HOTEL_BUY", {"params": {"tier": tier.strip()}}, timeout=10
        )
        if success:
            self._schedule_record_action("HOTEL_BUY")
        return bool(success)

    async def get_office(self) -> bool:
        """Get office information."""
        success, _ = await self._send_and_wait("OFFICE_GET", {}, timeout=10)
        return bool(success)

    def get_pet_data(self) -> Optional[Dict[str, Any]]:
        """Get current pet data."""
        return self.pet_data

    def get_pet_stats(self) -> Optional[Dict[str, Any]]:
        """Get current pet stats."""
        if self.pet_data:
            return self.pet_data.get("PetStats", {})
        return None

    def get_pet_name(self) -> Optional[str]:
        """Get current pet name."""
        if self.pet_data:
            return self.pet_data.get("name")
        return None

    def get_pet_id(self) -> Optional[str]:
        """Get current pet ID."""
        if self.pet_data:
            return self.pet_data.get("id")
        return None

    def get_pet_balance(self) -> Optional[str]:
        """Get current pet balance formatted as ETH."""
        if self.pet_data:
            # Try to get balance from PetTokens first, then fallback to balance field
            raw_balance = self.pet_data.get("PetTokens", {}).get(
                "tokens", self.pet_data.get("balance", "0")
            )
            return format_wei_to_eth(raw_balance)
        return None

    def get_pet_hotel_tier(self) -> int:
        """Get current pet hotel tier."""
        if self.pet_data:
            return self.pet_data.get("currentHotelTier", 0)
        return 0

    def get_pet_hunger(self) -> int:
        """Get current pet hunger level."""
        stats = self.get_pet_stats()
        return stats.get("hunger", 0) if stats else 0

    def get_pet_health(self) -> int:
        """Get current pet health level."""
        stats = self.get_pet_stats()
        return stats.get("health", 0) if stats else 0

    def get_pet_energy(self) -> int:
        """Get current pet energy level."""
        stats = self.get_pet_stats()
        return stats.get("energy", 0) if stats else 0

    def get_pet_happiness(self) -> int:
        """Get current pet happiness level."""
        stats = self.get_pet_stats()
        return stats.get("happiness", 0) if stats else 0

    def get_pet_hygiene(self) -> int:
        """Get current pet hygiene level."""
        stats = self.get_pet_stats()
        return stats.get("hygiene", 0) if stats else 0

    def get_pet_status_summary(self) -> Dict[str, Any]:
        """Get a summary of current pet status."""
        if not self.pet_data:
            return {}

        return {
            "name": self.get_pet_name(),
            "id": self.get_pet_id(),
            "balance": self.get_pet_balance(),
            "hotel_tier": self.get_pet_hotel_tier(),
            "stats": {
                "hunger": self.get_pet_hunger(),
                "health": self.get_pet_health(),
                "energy": self.get_pet_energy(),
                "happiness": self.get_pet_happiness(),
                "hygiene": self.get_pet_hygiene(),
            },
        }

    def is_authenticated(self) -> bool:
        """Check if client is authenticated."""
        return self.authenticated

    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self.connection_established

    def is_jwt_expired(self) -> bool:
        """Check if JWT token has expired."""
        return self._jwt_expired

    def get_token_refresh_instructions(self) -> str:
        """Get instructions for refreshing the JWT token."""
        return """
🔑 JWT Token Refresh Instructions:

1. **For Privy Authentication:**
   - Go to your Privy dashboard or authentication flow
   - Generate a new access token
   - Update your PRIVY_TOKEN environment variable

2. **Common Token Sources:**
   - Privy Dashboard → Access Tokens
   - Your authentication provider's token endpoint
   - Mobile app authentication flow

3. **Environment Variable:**
   - Update PRIVY_TOKEN in your .env file
   - Restart the agent after updating the token

4. **Token Format:**
   - Ensure the token is valid and not expired
   - Remove any "Bearer " prefix if present
   - The token should be the raw JWT string
"""
