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

"""This module contains the handlers for the Pett Agent ABCI skill."""

# Import from AEA framework base classes
from aea.skills.base import Handler as BaseHandler


class BaseABCIRoundHandler(BaseHandler):
    """Base ABCI round handler."""

    pass


class BaseContractApiHandler(BaseHandler):
    """Base contract API handler."""

    pass


class BaseHttpHandler(BaseHandler):
    """Base HTTP handler."""

    pass


class BaseIpfsHandler(BaseHandler):
    """Base IPFS handler."""

    pass


class BaseLedgerApiHandler(BaseHandler):
    """Base ledger API handler."""

    pass


class BaseSigningHandler(BaseHandler):
    """Base signing handler."""

    pass


class BaseTendermintHandler(BaseHandler):
    """Base tendermint handler."""

    pass


class ABCIRoundHandler(BaseABCIRoundHandler):
    """ABCI round handler for Pett Agent."""

    def setup(self) -> None:
        """Set up the handler."""
        super().setup()

    def handle(self, message) -> None:
        """Handle ABCI messages."""
        # ABCI framework will handle round progression
        super().handle(message)

    def teardown(self) -> None:
        """Tear down the handler."""
        super().teardown()


class ContractApiHandler(BaseContractApiHandler):
    """Contract API handler for Pett Agent."""

    def setup(self) -> None:
        """Set up the handler."""
        super().setup()

    def handle(self, message) -> None:
        """Handle contract API messages."""
        # Handle blockchain interactions if needed
        super().handle(message)

    def teardown(self) -> None:
        """Tear down the handler."""
        super().teardown()


class HttpHandler(BaseHttpHandler):
    """HTTP handler for Pett Agent."""

    def setup(self) -> None:
        """Set up the handler."""
        super().setup()

    def handle(self, message) -> None:
        """Handle HTTP messages."""
        # Handle external HTTP requests (e.g., webhooks, API calls)
        self.context.logger.info(f"Received HTTP message: {message}")

        # Extract relevant data and forward to behaviours via shared state
        if hasattr(message, "body"):
            # Store message for processing by behaviours
            shared_state = self.context.state
            shared_state.pending_http_messages = getattr(
                shared_state, "pending_http_messages", []
            )
            shared_state.pending_http_messages.append(message)

    def teardown(self) -> None:
        """Tear down the handler."""
        super().teardown()


class IpfsHandler(BaseIpfsHandler):
    """IPFS handler for Pett Agent."""

    def setup(self) -> None:
        """Set up the handler."""
        super().setup()

    def handle(self, message) -> None:
        """Handle IPFS messages."""
        super().handle(message)

    def teardown(self) -> None:
        """Tear down the handler."""
        super().teardown()


class LedgerApiHandler(BaseLedgerApiHandler):
    """Ledger API handler for Pett Agent."""

    def setup(self) -> None:
        """Set up the handler."""
        super().setup()

    def handle(self, message) -> None:
        """Handle ledger API messages."""
        # Handle blockchain transactions
        super().handle(message)

    def teardown(self) -> None:
        """Tear down the handler."""
        super().teardown()


class SigningHandler(BaseSigningHandler):
    """Signing handler for Pett Agent."""

    def setup(self) -> None:
        """Set up the handler."""
        super().setup()

    def handle(self, message) -> None:
        """Handle signing messages."""
        # Handle message signing requests
        super().handle(message)

    def teardown(self) -> None:
        """Tear down the handler."""
        super().teardown()


class TendermintHandler(BaseTendermintHandler):
    """Tendermint handler for Pett Agent."""

    def setup(self) -> None:
        """Set up the handler."""
        super().setup()

    def handle(self, message) -> None:
        """Handle Tendermint messages."""
        # Handle consensus-related messages
        super().handle(message)

    def teardown(self) -> None:
        """Tear down the handler."""
        super().teardown()
