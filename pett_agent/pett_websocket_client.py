import asyncio
import websockets
import json
import logging
from typing import Dict, Any, Optional, Callable, List, Union
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PettWebSocketClient:
    def __init__(
        self,
        websocket_url: str = os.getenv(
            "WEBSOCKET_URL",
            (
                "ws://petbot-monorepo-websocket-333713154917.europe-west1.run.app"
                if os.getenv("NODE_ENV") == "production"
                else "ws://localhost:3005"
            ),
        ),
    ):
        self.websocket_url = websocket_url
        self.websocket: Optional[Any] = None
        self.authenticated = False
        self.pet_data: Optional[Dict[str, Any]] = None
        self.message_handlers: Dict[str, List[Callable]] = {}
        self.connection_established = False
        self.privy_token = os.getenv("PRIVY_TOKEN")
        self.data_message: Optional[Dict[str, Any]] = None
        self.ai_search_future: Optional[asyncio.Future[str]] = None
        self.kitchen_future: Optional[asyncio.Future[str]] = None
        self.mall_future: Optional[asyncio.Future[str]] = None
        self.closet_future: Optional[asyncio.Future[str]] = None
        if not self.privy_token:
            logger.error("PRIVY_TOKEN environment variable is not set")
            raise ValueError("Privy token is required")

    async def connect(self) -> bool:
        """Establish WebSocket connection to Pett.ai server."""
        try:
            self.websocket = await websockets.connect(self.websocket_url)
            self.connection_established = True
            logger.info("WebSocket connection established")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to WebSocket: {e}")
            return False

    async def disconnect(self) -> None:
        """Close WebSocket connection."""
        if self.websocket:
            await self.websocket.close()
            self.connection_established = False
            logger.info("WebSocket connection closed")

    async def authenticate(self) -> bool:
        """Default authentication using Privy token."""
        if not self.privy_token:
            logger.error("No Privy token available for authentication")
            return False

        return await self.authenticate_privy(self.privy_token)

    async def authenticate_privy(self, privy_auth_token: str) -> bool:
        """Authenticate using Privy credentials."""
        if not privy_auth_token or not privy_auth_token.strip():
            logger.error("Invalid Privy auth token provided")
            return False

        auth_message = {
            "type": "AUTH",
            "data": {
                "params": {
                    "authHash": {"hash": "Bearer " + privy_auth_token.strip()},
                    "authType": "privy",
                }
            },
        }

        return await self._send_message(auth_message)

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

    async def connect_and_authenticate(self) -> bool:
        """Connect to WebSocket and authenticate using Privy token."""
        if not await self.connect():
            return False

        if not await self.authenticate():
            return False

        return True

    async def _send_message(self, message: Dict[str, Any]) -> bool:
        """Send a message to the WebSocket server."""
        if not self.websocket or not self.connection_established:
            logger.error("WebSocket not connected")
            return False

        try:
            message_json = json.dumps(message)
            await self.websocket.send(message_json)
            logger.info(f"📤 Sent message type: {message['type']}")
            logger.debug(f"📤 Message content: {message_json}")
            return True
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return False

    async def listen_for_messages(self) -> None:
        """Listen for incoming messages from the server."""
        if not self.websocket or not self.connection_established:
            logger.error("WebSocket not connected")
            return

        try:
            async for message in self.websocket:
                await self._handle_message(json.loads(message))
        except websockets.exceptions.ConnectionClosed:
            logger.info("WebSocket connection closed")
            self.connection_established = False
        except Exception as e:
            logger.error(f"Error listening for messages: {e}")

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
                    logger.info(
                        f"💰 Balance: {pet.get('PetTokens', {}).get('tokens', '0')}"
                    )
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
            logger.info("Pet updated")
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
        """Get current pet balance."""
        if self.pet_data:
            return self.pet_data.get("balance", "0")
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
