#!/usr/bin/env python3
"""
End-to-end tests for AI search functionality.
Tests the complete AI search flow from request to response.
"""

import asyncio
import logging
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


async def test_ai_search_basic():
    """Test basic AI search functionality."""

    # Check if PRIVY_TOKEN is set
    if not os.getenv("PRIVY_TOKEN"):
        logger.error("❌ PRIVY_TOKEN environment variable not set")
        logger.error("Please set your PRIVY_TOKEN before running this test")
        return False

    # Create WebSocket client
    client = PettWebSocketClient()

    try:
        # Connect and authenticate
        logger.info("🔌 Connecting to WebSocket...")
        if not await client.connect_and_authenticate():
            logger.error("❌ Failed to connect and authenticate")
            return False

        logger.info("✅ Connected and authenticated successfully!")

        # Test AI search
        search_prompt = "What is the latest news about artificial intelligence?"
        logger.info(f"🔍 Testing AI search with prompt: '{search_prompt}'")

        # Start listening for messages in the background
        listen_task = asyncio.create_task(client.listen_for_messages())

        # Perform the search
        result = await client.ai_search(search_prompt)

        logger.info("\n" + "=" * 50)
        logger.info("🔍 AI SEARCH RESULT:")
        logger.info("=" * 50)
        logger.info(result)
        logger.info("=" * 50)

        # Cancel the listen task
        listen_task.cancel()

        # Check if we got a valid result
        if result and not result.startswith("❌"):
            logger.info("✅ AI search test passed!")
            return True
        else:
            logger.error("❌ AI search test failed!")
            return False

    except Exception as e:
        logger.error(f"❌ Error during AI search test: {e}")
        return False
    finally:
        # Disconnect
        await client.disconnect()
        logger.info("🔌 Disconnected from WebSocket")


async def test_ai_search_timeout():
    """Test AI search timeout handling."""

    if not os.getenv("PRIVY_TOKEN"):
        logger.error("❌ PRIVY_TOKEN environment variable not set")
        return False

    client = PettWebSocketClient()

    try:
        if not await client.connect_and_authenticate():
            logger.error("❌ Failed to connect and authenticate")
            return False

        logger.info("✅ Connected and authenticated successfully!")

        # Test AI search with very short timeout
        search_prompt = "What is machine learning?"
        logger.info(f"🔍 Testing AI search timeout with prompt: '{search_prompt}'")

        # Start listening for messages in the background
        listen_task = asyncio.create_task(client.listen_for_messages())

        # Perform the search with 1 second timeout
        result = await client.ai_search(search_prompt, timeout=1)

        # Cancel the listen task
        listen_task.cancel()

        # Check if we got a timeout error
        if "timed out" in result:
            logger.info("✅ AI search timeout test passed!")
            return True
        else:
            logger.error("❌ AI search timeout test failed!")
            return False

    except Exception as e:
        logger.error(f"❌ Error during timeout test: {e}")
        return False
    finally:
        await client.disconnect()
        logger.info("🔌 Disconnected from WebSocket")


async def test_ai_search_invalid_input():
    """Test AI search with invalid input."""

    if not os.getenv("PRIVY_TOKEN"):
        logger.error("❌ PRIVY_TOKEN environment variable not set")
        return False

    client = PettWebSocketClient()

    try:
        if not await client.connect_and_authenticate():
            logger.error("❌ Failed to connect and authenticate")
            return False

        logger.info("✅ Connected and authenticated successfully!")

        # Test AI search with empty prompt
        logger.info("🔍 Testing AI search with empty prompt...")

        result = await client.ai_search("")

        if "Invalid search prompt" in result:
            logger.info("✅ Invalid input test passed!")
            return True
        else:
            logger.error("❌ Invalid input test failed!")
            return False

    except Exception as e:
        logger.error(f"❌ Error during invalid input test: {e}")
        return False
    finally:
        await client.disconnect()
        logger.info("🔌 Disconnected from WebSocket")


async def run_e2e_tests():
    """Run all end-to-end tests."""
    logger.info("🧪 Running End-to-End Tests")
    logger.info("=" * 50)

    tests = [
        ("Basic AI Search", test_ai_search_basic),
        ("AI Search Timeout", test_ai_search_timeout),
        ("Invalid Input Handling", test_ai_search_invalid_input),
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
    logger.info("📊 End-to-End Test Results:")
    logger.info("=" * 50)

    passed = 0
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"{test_name}: {status}")
        if result:
            passed += 1

    logger.info(f"\n🎯 {passed}/{len(results)} tests passed")

    if passed == len(results):
        logger.info("🎉 All end-to-end tests passed!")
    else:
        logger.error("❌ Some end-to-end tests failed!")

    return passed == len(results)


if __name__ == "__main__":
    asyncio.run(run_e2e_tests())
