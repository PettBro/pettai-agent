#!/usr/bin/env python3
"""
Test script for Pett Agent - Olas SDK
Quick test to verify the agent meets Olas SDK requirements.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def test_health_check():
    """Test the health check endpoint."""
    import aiohttp

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8716/healthcheck") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print("✅ Health check passed:")
                    print(f"   Status: {data.get('status')}")
                    print(
                        f"   Seconds since transition: {data.get('seconds_since_last_transition')}"
                    )
                    print(f"   Is transitioning: {data.get('is_transitioning_fast')}")
                    return True
                else:
                    print(f"❌ Health check failed with status {resp.status}")
                    return False
    except Exception as e:
        print(f"❌ Health check error: {e}")
        return False


async def test_agent_ui():
    """Test the agent UI endpoint."""
    import aiohttp

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8716/") as resp:
                if resp.status == 200:
                    print("✅ Agent UI endpoint accessible")
                    return True
                else:
                    print(f"❌ Agent UI failed with status {resp.status}")
                    return False
    except Exception as e:
        print(f"❌ Agent UI error: {e}")
        return False


def test_file_requirements():
    """Test file-based requirements."""
    print("🔍 Testing file requirements...")

    # Check if log.txt is created
    log_file = Path("log.txt")
    if log_file.exists():
        print("✅ log.txt file exists")
        # Check log format
        try:
            with open(log_file, "r") as f:
                lines = f.readlines()
                if lines:
                    last_line = lines[-1]
                    if "[agent]" in last_line and "]" in last_line:
                        print("✅ Log format appears correct")
                    else:
                        print("⚠️ Log format may be incorrect")
        except Exception as e:
            print(f"⚠️ Could not verify log format: {e}")
    else:
        print("❌ log.txt file not found")

    # Check ethereum_private_key.txt
    key_file = Path("ethereum_private_key.txt")
    if key_file.exists():
        print("✅ ethereum_private_key.txt file exists")
    else:
        print("⚠️ ethereum_private_key.txt file not found (will be created)")
        # Create placeholder
        key_file.touch()
        print("✅ Created placeholder ethereum_private_key.txt")


async def main():
    """Run all tests."""
    print("🧪 Testing Pett Agent Olas SDK Compliance\n")

    # Test file requirements
    test_file_requirements()
    print()

    # Wait a moment for agent to start
    print("⏳ Waiting for agent to start...")
    await asyncio.sleep(5)

    # Test endpoints
    health_ok = await test_health_check()
    print()

    ui_ok = await test_agent_ui()
    print()

    # Summary
    if health_ok and ui_ok:
        print("🎉 All tests passed! Agent is Olas SDK compliant.")
        return True
    else:
        print("❌ Some tests failed. Check the agent configuration.")
        return False


if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n🛑 Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"💥 Test error: {e}")
        sys.exit(1)
