# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2025 pettai
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
# ------------------------------------------------------------------------------

"""External interface to bridge existing logic with ABCI agent."""

import asyncio
import logging
from typing import Dict, Any, Optional
from queue import Queue
import threading

logger = logging.getLogger(__name__)

# Import your existing logic (with error handling for optional components)
try:
    from pett_agent.telegram_bot import PetTelegramBot

    TELEGRAM_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Telegram bot not available: {e}")
    PetTelegramBot = None
    TELEGRAM_AVAILABLE = False

try:
    from pett_agent.pett_websocket_client import PettWebSocketClient

    WEBSOCKET_AVAILABLE = True
except ImportError as e:
    logger.warning(f"WebSocket client not available: {e}")
    PettWebSocketClient = None
    WEBSOCKET_AVAILABLE = False


class ABCIExternalInterface:
    """Interface to bridge external requests with ABCI agent."""

    def __init__(self):
        """Initialize the external interface."""
        self.request_queue = Queue()
        self.response_queue = Queue()
        self.telegram_bot: Optional[PetTelegramBot] = None
        self.websocket_client: Optional[PettWebSocketClient] = None
        self.running = False
        self._loop = None
        self._thread = None

    def start(self) -> None:
        """Start the external interface."""
        if self.running:
            return

        self.running = True
        self._thread = threading.Thread(target=self._run_interface, daemon=True)
        self._thread.start()
        logger.info("External interface started")

    def stop(self) -> None:
        """Stop the external interface."""
        self.running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("External interface stopped")

    def _run_interface(self) -> None:
        """Run the interface in a separate thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            self._loop.run_until_complete(self._interface_loop())
        except Exception as e:
            logger.error(f"Error in interface loop: {e}")
        finally:
            self._loop.close()

    async def _interface_loop(self) -> None:
        """Main interface loop."""
        while self.running:
            try:
                # Process any queued requests
                await self._process_requests()

                # Small delay to prevent busy waiting
                await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"Error in interface loop: {e}")
                await asyncio.sleep(1)

    async def _process_requests(self) -> None:
        """Process requests from the queue."""
        while not self.request_queue.empty():
            try:
                request = self.request_queue.get_nowait()
                response = await self._handle_request(request)
                self.response_queue.put(response)
            except Exception as e:
                logger.error(f"Error processing request: {e}")

    async def _handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a single request."""
        request_type = request.get("type")

        if request_type == "telegram_message":
            return await self._handle_telegram_message(request)
        elif request_type == "pet_action":
            return await self._handle_pet_action(request)
        elif request_type == "get_status":
            return await self._handle_get_status(request)
        else:
            return {"error": f"Unknown request type: {request_type}"}

    async def _handle_telegram_message(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle Telegram message through your existing bot logic."""
        try:
            user_id = request.get("user_id")
            message = request.get("message")

            # Your existing telegram bot can process this
            # For now, we'll just format it for the ABCI agent
            return {
                "success": True,
                "user_id": user_id,
                "processed_message": message,
                "action_type": "user_request",
            }

        except Exception as e:
            return {"error": f"Error handling telegram message: {e}"}

    async def _handle_pet_action(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle pet actions through your existing WebSocket client."""
        try:
            if not self.websocket_client:
                return {"error": "WebSocket client not available"}

            action = request.get("action")
            params = request.get("params", {})

            # Use your existing WebSocket client methods
            if action == "rub_pet":
                success = await self.websocket_client.rub_pet()
            elif action == "shower_pet":
                success = await self.websocket_client.shower_pet()
            elif action == "sleep_pet":
                success = await self.websocket_client.sleep_pet()
            elif action == "throw_ball":
                success = await self.websocket_client.throw_ball()
            elif action == "get_status":
                success = True  # Status is always available
            else:
                return {"error": f"Unknown pet action: {action}"}

            return {
                "success": success,
                "action": action,
                "pet_status": self.websocket_client.get_pet_status_summary(),
            }

        except Exception as e:
            return {"error": f"Error handling pet action: {e}"}

    async def _handle_get_status(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Get current status."""
        try:
            status = {
                "interface_running": self.running,
                "websocket_connected": False,
                "telegram_bot_active": self.telegram_bot is not None,
            }

            if self.websocket_client:
                status["websocket_connected"] = self.websocket_client.is_connected()
                status["pet_status"] = self.websocket_client.get_pet_status_summary()

            return {"success": True, "status": status}

        except Exception as e:
            return {"error": f"Error getting status: {e}"}

    def add_request(self, request: Dict[str, Any]) -> None:
        """Add a request to the queue."""
        self.request_queue.put(request)

    def get_response(self, timeout: float = 1.0) -> Optional[Dict[str, Any]]:
        """Get a response from the queue."""
        try:
            return self.response_queue.get(timeout=timeout)
        except:
            return None

    def set_websocket_client(self, client) -> None:
        """Set the WebSocket client."""
        if WEBSOCKET_AVAILABLE:
            self.websocket_client = client
        else:
            logger.warning("WebSocket client not available")

    def set_telegram_bot(self, bot) -> None:
        """Set the Telegram bot."""
        if TELEGRAM_AVAILABLE:
            self.telegram_bot = bot
        else:
            logger.warning("Telegram bot not available")


# Global instance for the ABCI agent to use
external_interface = ABCIExternalInterface()
