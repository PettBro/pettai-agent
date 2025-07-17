#!/usr/bin/env python3
"""
Integration tests for PettWebSocketClient.
Tests WebSocket connection, authentication, and basic functionality.
"""

import asyncio
import logging
import json
import sys
import os

# Add the parent directory to the path so we can import pett_agent
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from pett_agent.pett_websocket_client import PettWebSocketClient

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def test_websocket_connection():
    """Test WebSocket connection establishment."""
    try:
        logger.info("🔌 Testing WebSocket connection...")

        # Create client instance
        client = PettWebSocketClient()
        logger.info("✅ Client created successfully")

        # Test connection
        if await client.connect():
            logger.info("✅ WebSocket connection established")
            await client.disconnect()
            logger.info("✅ WebSocket connection closed")
            return True
        else:
            logger.error("❌ Failed to connect to WebSocket")
            return False

    except Exception as e:
        logger.error(f"❌ Connection test failed: {e}")
        return False


async def test_privy_authentication():
    """Test Privy authentication with the WebSocket client."""

    try:
        # Create client instance (will automatically load PRIVY_TOKEN from .env)
        client = PettWebSocketClient()
        logger.info("✅ Client created successfully")
    except ValueError as e:
        logger.error(f"❌ Failed to create client: {e}")
        logger.error("Make sure PRIVY_TOKEN is set in your .env file")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error creating client: {e}")
        return False

    try:
        # Connect first
        logger.info("🔌 Connecting to WebSocket...")
        if not await client.connect():
            logger.error("❌ Failed to connect to WebSocket")
            return False

        logger.info("✅ Connected to WebSocket successfully")

        # Authenticate
        logger.info("🔐 Authenticating with Privy token...")
        if not await client.authenticate():
            logger.error("❌ Failed to send authentication request")
            return False

        logger.info("✅ Authentication request sent successfully")
        logger.info("⏳ Waiting for authentication response...")

        # Listen for response with longer timeout
        try:
            await asyncio.wait_for(client.listen_for_messages(), timeout=30.0)
        except asyncio.TimeoutError:
            logger.error("⏰ Timeout waiting for authentication response")
            return False

        # Check authentication status
        if client.is_authenticated():
            logger.info("✅ Authentication successful!")

            # Get pet data using helper methods
            pet_name = client.get_pet_name()
            pet_id = client.get_pet_id()
            balance = client.get_pet_balance()
            hotel_tier = client.get_pet_hotel_tier()

            logger.info(f"🐾 Pet Name: {pet_name}")
            logger.info(f"🆔 Pet ID: {pet_id}")
            logger.info(f"💰 Balance: {balance}")
            logger.info(f"🏨 Hotel Tier: {hotel_tier}")

            # Get pet stats using helper methods
            hunger = client.get_pet_hunger()
            health = client.get_pet_health()
            energy = client.get_pet_energy()
            happiness = client.get_pet_happiness()
            hygiene = client.get_pet_hygiene()

            logger.info("📊 Pet Stats (using helper methods):")
            logger.info(f"   🍽️  Hunger: {hunger}")
            logger.info(f"   ❤️  Health: {health}")
            logger.info(f"   ⚡ Energy: {energy}")
            logger.info(f"   😊 Happiness: {happiness}")
            logger.info(f"   🧼 Hygiene: {hygiene}")

            # Get complete status summary
            status_summary = client.get_pet_status_summary()
            logger.info(f"📋 Status Summary: {json.dumps(status_summary, indent=2)}")

            return True

        else:
            logger.error("❌ Authentication failed - client is not authenticated")
            logger.error("Check the logs above for the specific error message")
            return False

    except Exception as e:
        logger.error(f"❌ Error during authentication test: {e}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        return False
    finally:
        # Disconnect
        if "client" in locals():
            await client.disconnect()
            logger.info("🔌 Disconnected from WebSocket")


async def test_pet_actions():
    """Test basic pet actions."""
    try:
        # Create and authenticate client
        client = PettWebSocketClient()

        if not await client.connect_and_authenticate():
            logger.error("❌ Failed to connect and authenticate for pet actions test")
            return False

        logger.info("✅ Connected and authenticated for pet actions test")

        # Test some pet actions
        logger.info("🎾 Testing pet actions...")

        # Rub pet
        if await client.rub_pet():
            logger.info("✅ Rub pet action sent")
        else:
            logger.error("❌ Failed to send rub pet action")

        # Get pet personality
        if await client.get_personality():
            logger.info("✅ Get personality action sent")
        else:
            logger.error("❌ Failed to send get personality action")

        # Listen for more responses
        logger.info("👂 Listening for more responses...")
        await asyncio.wait_for(client.listen_for_messages(), timeout=10.0)

        await client.disconnect()
        return True

    except Exception as e:
        logger.error(f"❌ Error during pet actions test: {e}")
        return False


async def run_integration_tests():
    """Run all integration tests."""
    logger.info("🧪 Running Integration Tests")
    logger.info("=" * 50)

    tests = [
        ("WebSocket Connection", test_websocket_connection),
        ("Privy Authentication", test_privy_authentication),
        ("Pet Actions", test_pet_actions),
    ]

    results = []

    for test_name, test_func in tests:
        logger.info(f"\n🔍 Running {test_name} test...")
        try:
            result = await test_func()
            results.append((test_name, result))
            if result:
                logger.info(f"✅ {test_name} test passed!")
            else:
                logger.error(f"❌ {test_name} test failed!")
        except Exception as e:
            logger.error(f"❌ {test_name} test failed with exception: {e}")
            results.append((test_name, False))

    # Summary
    logger.info("\n" + "=" * 50)
    logger.info("📊 Integration Test Results:")
    logger.info("=" * 50)

    passed = 0
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"{test_name}: {status}")
        if result:
            passed += 1

    logger.info(f"\n🎯 {passed}/{len(results)} tests passed")

    if passed == len(results):
        logger.info("🎉 All integration tests passed!")
    else:
        logger.error("❌ Some integration tests failed!")

    return passed == len(results)


if __name__ == "__main__":
    asyncio.run(run_integration_tests())
