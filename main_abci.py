#!/usr/bin/env python3
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

"""ABCI-compatible main entry point for Pett Agent."""

import os
import asyncio
import logging
import signal
import sys
from typing import Optional
from dotenv import load_dotenv

# Import your existing logic
from pett_agent.telegram_bot import PetTelegramBot
from pett_agent.pett_websocket_client import PettWebSocketClient

# Import ABCI interface
from packages.pettai.skills.pett_agent_skill_abci.external_interface import (
    external_interface,
)

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


class ABCIPettAgent:
    """ABCI-compatible Pett Agent that integrates existing logic."""

    def __init__(self):
        """Initialize the ABCI Pett Agent."""
        self.telegram_bot: Optional[PetTelegramBot] = None
        self.websocket_client: Optional[PettWebSocketClient] = None
        self.running = False

    async def initialize(self) -> bool:
        """Initialize the agent components."""
        try:
            logger.info("🚀 Initializing ABCI Pett Agent...")

            # Initialize WebSocket client
            self.websocket_client = PettWebSocketClient()
            external_interface.set_websocket_client(self.websocket_client)

            # Connect to Pett.ai WebSocket
            connected = await self.websocket_client.connect_and_authenticate()
            if not connected:
                logger.error("❌ Failed to connect to Pett.ai WebSocket")
                return False

            logger.info("✅ Connected to Pett.ai WebSocket")

            # Initialize Telegram bot if token is available
            telegram_token = os.environ.get(
                "CONNECTION_CONFIGS_CONFIG_TELEGRAM_BOT_TOKEN"
            )
            if telegram_token:
                logger.info("🤖 Initializing Telegram bot...")
                self.telegram_bot = PetTelegramBot()
                external_interface.set_telegram_bot(self.telegram_bot)

                # Start Telegram bot in background
                asyncio.create_task(self._run_telegram_bot())
                logger.info("✅ Telegram bot initialized")
            else:
                logger.info(
                    "ℹ️  No Telegram token found - running without Telegram interface"
                )

            # Start external interface
            external_interface.start()
            logger.info("✅ External interface started")

            return True

        except Exception as e:
            logger.error(f"❌ Error during initialization: {e}")
            return False

    async def _run_telegram_bot(self) -> None:
        """Run the Telegram bot in the background."""
        try:
            if self.telegram_bot:
                await self.telegram_bot.run()
        except Exception as e:
            logger.error(f"❌ Error in Telegram bot: {e}")

    async def run(self) -> None:
        """Run the ABCI agent."""
        if not await self.initialize():
            logger.error("❌ Failed to initialize agent")
            sys.exit(1)

        self.running = True
        logger.info("🎯 ABCI Pett Agent is running...")

        try:
            # Keep the agent running
            while self.running:
                # Process any external requests through the interface
                await self._process_external_interface()

                # Small delay to prevent busy waiting
                await asyncio.sleep(0.1)

        except KeyboardInterrupt:
            logger.info("🛑 Shutdown requested by user")
        except Exception as e:
            logger.error(f"❌ Error in main loop: {e}")
        finally:
            await self.shutdown()

    async def _process_external_interface(self) -> None:
        """Process requests from the external interface."""
        try:
            # Check for responses from the external interface
            response = external_interface.get_response(timeout=0.01)
            if response:
                logger.info(f"📨 Received response: {response}")

                # Here you could forward the response to the ABCI state machine
                # For now, we just log it

        except Exception as e:
            logger.error(f"❌ Error processing external interface: {e}")

    async def shutdown(self) -> None:
        """Shutdown the agent gracefully."""
        logger.info("🛑 Shutting down ABCI Pett Agent...")
        self.running = False

        try:
            # Stop external interface
            external_interface.stop()

            # Disconnect WebSocket
            if self.websocket_client:
                await self.websocket_client.disconnect()

            logger.info("✅ Shutdown complete")

        except Exception as e:
            logger.error(f"❌ Error during shutdown: {e}")

    def handle_signal(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"🔔 Received signal {signum}")
        self.running = False


async def main():
    """Main function to run the ABCI Pett Agent."""
    agent = ABCIPettAgent()

    # Set up signal handlers
    signal.signal(signal.SIGINT, agent.handle_signal)
    signal.signal(signal.SIGTERM, agent.handle_signal)

    try:
        await agent.run()
    except Exception as e:
        logger.critical(f"💥 Critical error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    try:
        logger.info("🌟 Starting ABCI Pett Agent application")
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Application shutdown requested by user")
    except Exception as e:
        logger.critical(f"💥 Critical error during startup: {e}", exc_info=True)
        sys.exit(1)
    finally:
        logger.info("👋 ABCI Pett Agent application terminated")
