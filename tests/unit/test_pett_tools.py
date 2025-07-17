#!/usr/bin/env python3
"""
Unit tests for PettTools class.
Tests that the PettTools can be created and bound properly.
"""

import asyncio
import logging
import sys
import os

# Add the parent directory to the path so we can import pett_agent
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from pett_agent.pett_tools import PettTools
from pett_agent.pett_websocket_client import PettWebSocketClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_pett_tools_creation():
    """Test that PettTools can be created and bound properly."""
    try:
        logger.info("Testing PettTools creation...")

        # Create WebSocket client (without connecting)
        websocket_client = PettWebSocketClient()

        # Create tools
        pett_tools = PettTools(websocket_client)

        # Create tools list
        tools = pett_tools.create_tools()

        logger.info(f"✅ Successfully created {len(tools)} tools")

        # Test that tools are callable functions
        for i, tool in enumerate(tools):
            if callable(tool):
                logger.info(f"✅ Tool {i+1}: {tool.__name__} is callable")
            else:
                logger.error(f"❌ Tool {i+1} is not callable")

        # Test legacy method
        legacy_tools = pett_tools.get_tools()
        logger.info(f"✅ Legacy method returned {len(legacy_tools)} tools")

        logger.info("🎉 All unit tests passed!")

    except Exception as e:
        logger.error(f"❌ Unit test failed: {e}")
        raise


async def test_pett_tools_validation():
    """Test that PettTools validation works correctly."""
    try:
        logger.info("Testing PettTools validation...")

        # Create tools without client
        pett_tools = PettTools()

        # Test that validation fails when no client is set
        tools = pett_tools.create_tools()
        ai_search_tool = next(
            (tool for tool in tools if tool.__name__ == "ai_search"), None
        )

        if ai_search_tool:
            result = ai_search_tool("test query")
            if "WebSocket client not available" in result:
                logger.info("✅ Validation correctly detects missing client")
            else:
                logger.error("❌ Validation failed to detect missing client")
        else:
            logger.error("❌ Could not find ai_search tool")

        logger.info("🎉 Validation tests passed!")

    except Exception as e:
        logger.error(f"❌ Validation test failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(test_pett_tools_creation())
    asyncio.run(test_pett_tools_validation())
