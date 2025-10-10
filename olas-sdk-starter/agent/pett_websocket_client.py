import asyncio
import json
import logging
import os
from typing import Any, Callable, Dict, List, Optional

import websockets
from dotenv import load_dotenv

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
                else "ws://localhost:3005"
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
        if not self.privy_token:
            logger.warning(
                "Privy token not provided during initialization; authentication will be disabled until a token is set."
            )

    def set_telemetry_recorder(
        self, recorder: Optional[Callable[[Dict[str, Any], bool, Optional[str]], None]]
    ) -> None:
        """Set a callback to record outgoing messages and outcomes."""
        self._telemetry_recorder = recorder

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
            logger.error("Attempted to set an empty Privy token")
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
        if not self.privy_token:
            logger.error("No Privy token available for authentication")
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
            message_json = json.dumps(message)
            await self.websocket.send(message_json)
            logger.info(f"📤 Sent message type: {message['type']}")
            logger.debug(f"📤 Message content: {message_json}")
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
            self.pet_data = pet_data
            logger.info("Pet Status updated")
            logger.info(f"Updated pet data: {self.pet_data}")
        elif user_data:
            # If we got user data, extract pet from it
            pets = user_data.get("pets", [])
            if pets:
                self.pet_data = pets[0]
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
        return await self._send_message({"type": "RUB", "data": {}})

    async def shower_pet(self) -> bool:
        """Give the pet a shower."""
        return await self._send_message({"type": "SHOWER", "data": {}})

    async def sleep_pet(self) -> bool:
        """Put the pet to sleep."""
        return await self._send_message({"type": "SLEEP", "data": {}})

    async def throw_ball(self) -> bool:
        """Throw a ball for the pet."""
        return await self._send_message({"type": "THROWBALL", "data": {}})

    async def use_consumable(self, consumable_id: str) -> bool:
        """Use a consumable item."""
        if not consumable_id or not consumable_id.strip():
            logger.error("Invalid consumable ID provided")
            return False

        return await self._send_message(
            {
                "type": "CONSUMABLES_USE",
                "data": {"params": {"consumableId": consumable_id.strip()}},
            }
        )

    async def revive_pet(self, amount: int) -> bool:
        """Revive the pet.

        Args:
            amount: The amount of revive potions to buy.
        """
        if amount <= 0:
            logger.error("Amount must be greater than 0")
            return False

        await self._send_message(
            {
                "type": "CONSUMABLES_BUY",
                "data": {"params": {"consumableId": "REVIVE_POTION", "amount": amount}},
            }
        )

        await self._send_message(
            {
                "type": "CONSUMABLES_USE",
                "data": {
                    "params": {
                        "consumableId": "REVIVE_POTION",
                    }
                },
            }
        )

        return True

    async def buy_consumable(self, consumable_id: str, amount: int) -> bool:
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

        return await self._send_message(
            {
                "type": "CONSUMABLES_BUY",
                "data": {"params": {"foodId": consumable_id.strip(), "amount": amount}},
            }
        )

    async def get_consumables(self) -> bool:
        """Get available consumables."""
        logger.info("[TOOL] Getting consumables")
        return await self._send_message({"type": "CONSUMABLES_GET", "data": {}})

    async def get_kitchen(self) -> bool:
        """Get kitchen information."""
        return await self._send_message({"type": "KITCHEN_GET", "data": {}})

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
        return await self._send_message({"type": "MALL_GET", "data": {}})

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
        return await self._send_message({"type": "CLOSET_GET", "data": {}})

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

        return await self._send_message(
            {
                "type": "ACCESSORY_USE",
                "data": {"params": {"accessoryId": accessory_id.strip()}},
            }
        )

    async def buy_accessory(self, accessory_id: str) -> bool:
        """Buy an accessory."""
        if not accessory_id or not accessory_id.strip():
            logger.error("Invalid accessory ID provided")
            return False

        return await self._send_message(
            {
                "type": "ACCESSORY_BUY",
                "data": {"params": {"accessoryId": accessory_id.strip()}},
            }
        )

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
        return await self._send_message({"type": "HOTEL_CHECK_IN", "data": {}})

    async def hotel_check_out(self) -> bool:
        """Check pet out of hotel."""
        logger.info("[TOOL] Checking pet out of hotel")
        return await self._send_message({"type": "HOTEL_CHECK_OUT", "data": {}})

    async def buy_hotel(self, tier: str) -> bool:
        """Buy hotel tier."""
        if not tier or not tier.strip():
            logger.error("Invalid hotel tier provided")
            return False

        return await self._send_message(
            {"type": "HOTEL_BUY", "data": {"params": {"tier": tier.strip()}}}
        )

    async def get_office(self) -> bool:
        """Get office information."""
        return await self._send_message({"type": "OFFICE_GET", "data": {}})

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

💡 Tip: JWT tokens typically expire after 1-24 hours depending on your provider's settings.
        """
