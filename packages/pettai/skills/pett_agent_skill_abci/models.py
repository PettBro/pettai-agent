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

"""This module contains the models for the Pett Agent ABCI skill."""

from typing import Optional

# Import from AEA framework base classes
from aea.skills.base import Model


# Create base classes using AEA framework
class BaseParams(Model):
    """Base parameters class."""

    pass


class BaseBenchmarkTool(Model):
    """Base benchmark tool."""

    def measure(self, behaviour_id):
        return self

    def local(self):
        return self

    def consensus(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class BaseRequests(Model):
    """Base requests class."""

    pass


class BaseSharedState(Model):
    """Base shared state class."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.synchronized_data = None


class BaseAbciDialogues(Model):
    """Base dialogues class."""

    pass


# Import Pett types for type annotations
from pett_agent.pett_websocket_client import PettWebSocketClient


class SharedState(BaseSharedState):
    """Keep the current shared state of the skill."""

    def __init__(self, *args, **kwargs):
        """Initialize shared state."""
        super().__init__(*args, **kwargs)
        self.websocket_client: Optional[PettWebSocketClient] = None

        # Additional state for ABCI integration
        self.pending_http_messages = []
        self.user_sessions = {}  # Track user sessions from external interfaces
        self.pet_action_queue = []  # Queue of pending pet actions
        self.current_round = None
        self.last_user_request = None
        self.transaction_history = []

        # Integration with your existing telegram bot logic
        self.telegram_bot_active = False
        self.external_requests = []  # For handling external API requests

    @property
    def abci_app_cls(self):
        """Get the ABCI app class."""
        # Import here to avoid circular imports
        from packages.pettai.skills.pett_agent_skill_abci.rounds import PettAgentAbciApp

        return PettAgentAbciApp

    def add_user_request(self, user_id: str, request: str) -> None:
        """Add a user request to be processed."""
        self.external_requests.append(
            {
                "user_id": user_id,
                "request": request,
                "timestamp": (
                    self.synchronized_data.get("timestamp", 0)
                    if self.synchronized_data
                    else 0
                ),
            }
        )

    def get_websocket_client(self) -> Optional[PettWebSocketClient]:
        """Get the WebSocket client, creating if needed."""
        if not self.websocket_client:
            try:
                self.websocket_client = PettWebSocketClient()
            except Exception as e:
                # Log error but don't fail
                pass
        return self.websocket_client

    def is_websocket_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return (
            self.websocket_client
            and self.websocket_client.is_connected()
            and self.websocket_client.is_authenticated()
        )

    def get_pet_status(self) -> dict:
        """Get current pet status from WebSocket client."""
        if self.websocket_client:
            return self.websocket_client.get_pet_status_summary()
        return {}


class Params(BaseParams):
    """Pett Agent parameters."""


class BenchmarkTool(BaseBenchmarkTool):
    """Benchmarking tool for the Pett Agent."""


class Requests(BaseRequests):
    """Keep the current pending requests."""


class AbciDialogues(BaseAbciDialogues):
    """The dialogues class keeps track of all dialogues."""
