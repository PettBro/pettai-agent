"""
Pytest configuration for pett_agent tests.
This file can be used for pytest fixtures and configuration.
"""

import pytest
import asyncio
import os
import sys

# Add the parent directory to the path so we can import pett_agent
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def privy_token():
    """Get the PRIVY_TOKEN from environment variables."""
    token = os.getenv("PRIVY_TOKEN")
    if not token:
        pytest.skip("PRIVY_TOKEN environment variable not set")
    return token


@pytest.fixture
def websocket_url(is_prod: bool = False):
    """Get the WebSocket URL for testing."""
    return os.getenv(
        "WEBSOCKET_URL",
        (
            "wss://petbot-monorepo-websocket-333713154917.europe-west1.run.app"
            if is_prod
            else "wss://localhost:3005"
        ),
    )


# Pytest configuration
def pytest_configure(config):
    """Configure pytest."""
    config.addinivalue_line("markers", "unit: mark test as a unit test")
    config.addinivalue_line("markers", "integration: mark test as an integration test")
    config.addinivalue_line("markers", "e2e: mark test as an end-to-end test")
    config.addinivalue_line("markers", "slow: mark test as slow running")


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers based on file location."""
    for item in items:
        # Add markers based on test file location
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        elif "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif "e2e" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)
            item.add_marker(pytest.mark.slow)
