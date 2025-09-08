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

"""This module contains the behaviours for the Pett Agent ABCI skill."""

from abc import ABC
from typing import Generator, Set, Type, cast, Optional
import asyncio
import logging
import os

# Import from AEA framework base classes
from aea.skills.base import Behaviour as BaseBehaviour


# Create ABCI-specific base classes
class AbstractRound:
    """Abstract round class."""

    def __init__(self, synchronized_data, context=None):
        self.synchronized_data = synchronized_data
        self.context = context
        self.collection = {}
        self.threshold_reached = False
        self.most_voted_payload = None


class AbstractRoundBehaviour:
    """Abstract round behaviour class."""

    initial_behaviour_cls = None
    abci_app_cls = None
    behaviours = set()


# Import existing Pett functionality
from pett_agent.pett_websocket_client import PettWebSocketClient
from pett_agent.pett_tools import PettTools
from pett_agent.telegram_bot import PetTelegramBot
from pett_agent.TransactionExecutor import TransactionExecutor

from packages.pettai.skills.pett_agent_skill_abci.models import Params, SharedState
from packages.pettai.skills.pett_agent_skill_abci.rounds import (
    ConnectToPettRound,
    WaitForUserRequestRound,
    ProcessPetActionRound,
    ExecuteTransactionRound,
    HandleErrorRound,
    PettAgentAbciApp,
    SynchronizedData,
)
from packages.pettai.skills.pett_agent_skill_abci.payloads import (
    ConnectToPettPayload,
    UserRequestPayload,
    PetActionPayload,
    TransactionPayload,
    ErrorPayload,
)


class ConnectToPettBehaviour(BaseBehaviour, ABC):
    """Behaviour to connect to Pett.ai WebSocket."""

    matching_round: Type[AbstractRound] = ConnectToPettRound

    def async_act(self) -> Generator:
        """Async act method."""
        # Integrate PettWebSocketClient connection logic
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            connection_status = "failed"

            try:
                # Create WebSocket client
                websocket_client = PettWebSocketClient()

                # Attempt to connect and authenticate
                connected = yield from self._async_connect_websocket(websocket_client)

                if connected:
                    # Store the client in synchronized data for later use
                    self.context.logger.info(
                        "✅ Successfully connected to Pett.ai WebSocket"
                    )
                    connection_status = "connected"

                    # Store websocket client in the shared state
                    shared_state = cast("SharedState", self.context.state)
                    shared_state.websocket_client = websocket_client
                else:
                    self.context.logger.error(
                        "❌ Failed to connect to Pett.ai WebSocket"
                    )
                    connection_status = "failed"

            except Exception as e:
                self.context.logger.error(
                    f"❌ Exception during WebSocket connection: {e}"
                )
                connection_status = "failed"

            payload = ConnectToPettPayload(
                sender=self.context.agent_address, connection_status=connection_status
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def _async_connect_websocket(self, client: PettWebSocketClient) -> Generator:
        """Helper method to connect WebSocket asynchronously in the ABCI context."""
        # Create a future for the connection
        connection_future = asyncio.ensure_future(client.connect_and_authenticate())

        # Wait for the connection to complete
        while not connection_future.done():
            yield

        try:
            result = connection_future.result()
            return result
        except Exception as e:
            self.context.logger.error(f"WebSocket connection error: {e}")
            return False


class WaitForUserRequestBehaviour(BaseBehaviour, ABC):
    """Behaviour to wait for user requests via Telegram bot."""

    matching_round: Type[AbstractRound] = WaitForUserRequestRound

    def async_act(self) -> Generator:
        """Async act method."""
        # Integrate user request handling logic
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            # Get shared state to access stored data
            shared_state = cast("SharedState", self.context.state)

            user_request = "no_request"
            user_id = "unknown"

            try:
                # Check if we have a WebSocket client
                if (
                    hasattr(shared_state, "websocket_client")
                    and shared_state.websocket_client
                ):
                    websocket_client = shared_state.websocket_client

                    # Check for pet data and simulate a user request
                    pet_data = websocket_client.get_pet_data()
                    if pet_data:
                        # Simulate checking for pending user requests
                        # In a real implementation, this could be integrated with Telegram bot
                        # or a message queue system
                        user_request = self._check_for_user_requests(pet_data)
                        user_id = pet_data.get("id", "unknown")

                        self.context.logger.info(
                            f"🔍 Checking for user requests for pet: {pet_data.get('name', 'Unknown')}"
                        )
                    else:
                        self.context.logger.warning("⚠️ No pet data available")
                        user_request = "no_pet_data"
                else:
                    self.context.logger.warning("⚠️ No WebSocket client available")
                    user_request = "no_websocket"

            except Exception as e:
                self.context.logger.error(f"❌ Error checking for user requests: {e}")
                user_request = f"error: {str(e)}"

            payload = UserRequestPayload(
                sender=self.context.agent_address,
                user_request=user_request,
                user_id=user_id,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def _check_for_user_requests(self, pet_data: dict) -> str:
        """Check for pending user requests based on pet state."""
        # This is a simplified implementation
        # In practice, this could integrate with Telegram bot or message queues

        pet_stats = pet_data.get("PetStats", {})

        # Check if pet needs care based on stats
        if pet_stats.get("hunger", 0) < 30:
            return "feed_pet_request"
        elif pet_stats.get("hygiene", 0) < 30:
            return "shower_pet_request"
        elif pet_stats.get("energy", 0) < 30:
            return "sleep_pet_request"
        elif pet_stats.get("happiness", 0) < 30:
            return "play_pet_request"
        else:
            return "pet_status_request"


class ProcessPetActionBehaviour(BaseBehaviour, ABC):
    """Behaviour to process pet actions using PettTools."""

    matching_round: Type[AbstractRound] = ProcessPetActionRound

    def async_act(self) -> Generator:
        """Async act method."""
        # Integrate PettTools action processing logic
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            # Get shared state to access stored data
            shared_state = cast("SharedState", self.context.state)

            action_type = "no_action"
            action_result = "failed"
            requires_transaction = False

            try:
                # Get the user request from synchronized data
                user_request = shared_state.synchronized_data.user_request

                if (
                    hasattr(shared_state, "websocket_client")
                    and shared_state.websocket_client
                ):
                    websocket_client = shared_state.websocket_client

                    # Create PettTools instance
                    pett_tools = PettTools(websocket_client)

                    # Process the user request
                    action_type, action_result, requires_transaction = (
                        yield from self._process_pet_action(
                            user_request, websocket_client, pett_tools
                        )
                    )

                    self.context.logger.info(
                        f"🐾 Processed action: {action_type} with result: {action_result}"
                    )
                else:
                    self.context.logger.warning(
                        "⚠️ No WebSocket client available for pet actions"
                    )
                    action_result = "no_websocket"

            except Exception as e:
                self.context.logger.error(f"❌ Error processing pet action: {e}")
                action_result = f"error: {str(e)}"

            payload = PetActionPayload(
                sender=self.context.agent_address,
                action_type=action_type,
                action_result=action_result,
                requires_transaction=requires_transaction,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def _process_pet_action(
        self,
        user_request: str,
        websocket_client: PettWebSocketClient,
        pett_tools: PettTools,
    ) -> Generator:
        """Process the pet action based on user request."""
        action_type = user_request
        requires_transaction = False

        try:
            if user_request == "feed_pet_request":
                # Feed the pet (buy and use consumable)
                action_future = asyncio.ensure_future(
                    websocket_client.buy_consumable("BURGER", 1)
                )
                yield from self._wait_for_future(action_future)

                if action_future.result():
                    use_future = asyncio.ensure_future(
                        websocket_client.use_consumable("BURGER")
                    )
                    yield from self._wait_for_future(use_future)
                    result = (
                        "fed_pet_burger" if use_future.result() else "failed_to_feed"
                    )
                else:
                    result = "failed_to_buy_food"

            elif user_request == "shower_pet_request":
                # Give pet a shower
                action_future = asyncio.ensure_future(websocket_client.shower_pet())
                yield from self._wait_for_future(action_future)
                result = (
                    "showered_pet" if action_future.result() else "failed_to_shower"
                )

            elif user_request == "sleep_pet_request":
                # Put pet to sleep
                action_future = asyncio.ensure_future(websocket_client.sleep_pet())
                yield from self._wait_for_future(action_future)
                result = "pet_sleeping" if action_future.result() else "failed_to_sleep"

            elif user_request == "play_pet_request":
                # Play with pet (throw ball)
                action_future = asyncio.ensure_future(websocket_client.throw_ball())
                yield from self._wait_for_future(action_future)
                result = (
                    "played_with_pet" if action_future.result() else "failed_to_play"
                )

            elif user_request == "pet_status_request":
                # Get pet status
                pet_data = websocket_client.get_pet_data()
                if pet_data:
                    result = f"pet_status_retrieved: {pet_data.get('name', 'Unknown')}"
                else:
                    result = "no_pet_data"

            else:
                result = f"unknown_request: {user_request}"

            return action_type, result, requires_transaction

        except Exception as e:
            return action_type, f"error: {str(e)}", requires_transaction

    def _wait_for_future(self, future) -> Generator:
        """Wait for an asyncio future to complete."""
        while not future.done():
            yield


class ExecuteTransactionBehaviour(BaseBehaviour, ABC):
    """Behaviour to execute blockchain transactions."""

    matching_round: Type[AbstractRound] = ExecuteTransactionRound

    def async_act(self) -> Generator:
        """Async act method."""
        # Integrate TransactionExecutor logic
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            # Get shared state to access stored data
            shared_state = cast("SharedState", self.context.state)

            transaction_hash = "0x000..."
            transaction_status = "failed"

            try:
                # Get the action result from synchronized data to determine if transaction is needed
                action_result = shared_state.synchronized_data.pet_action_result

                if action_result and "requires_transaction" in action_result:
                    # Initialize TransactionExecutor
                    tx_executor = TransactionExecutor()

                    # Execute transaction based on the action result
                    transaction_hash, transaction_status = (
                        yield from self._execute_transaction(tx_executor, action_result)
                    )

                    self.context.logger.info(
                        f"💰 Transaction executed: {transaction_hash} with status: {transaction_status}"
                    )
                else:
                    # No transaction needed
                    transaction_status = "not_required"
                    transaction_hash = "0x000..."
                    self.context.logger.info(
                        "ℹ️ No transaction required for this action"
                    )

            except Exception as e:
                self.context.logger.error(f"❌ Error executing transaction: {e}")
                transaction_status = f"error: {str(e)}"
                transaction_hash = "0x000..."

            payload = TransactionPayload(
                sender=self.context.agent_address,
                transaction_hash=transaction_hash,
                transaction_status=transaction_status,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def _execute_transaction(
        self, tx_executor: TransactionExecutor, action_result: str
    ) -> Generator:
        """Execute blockchain transaction based on action result."""
        transaction_hash = "0x000..."
        transaction_status = "failed"

        try:
            # This is a simplified example of transaction execution
            # In practice, this would depend on the specific action and requirements

            if "token_transfer" in action_result:
                # Example: Execute token transfer transaction
                transaction_future = asyncio.ensure_future(
                    tx_executor.execute_safe_transaction(
                        {
                            "to": "0x...",  # destination address
                            "value": "0",  # ETH value
                            "data": "0x...",  # transaction data
                        }
                    )
                )
                yield from self._wait_for_future(transaction_future)

                if transaction_future.result():
                    transaction_hash = transaction_future.result().get(
                        "hash", "0x000..."
                    )
                    transaction_status = "success"
                else:
                    transaction_status = "failed"

            else:
                # No specific transaction required
                transaction_status = "not_applicable"

            return transaction_hash, transaction_status

        except Exception as e:
            return "0x000...", f"error: {str(e)}"

    def _wait_for_future(self, future) -> Generator:
        """Wait for an asyncio future to complete."""
        while not future.done():
            yield


class HandleErrorBehaviour(BaseBehaviour, ABC):
    """Behaviour to handle errors and recover."""

    matching_round: Type[AbstractRound] = HandleErrorRound

    def async_act(self) -> Generator:
        """Async act method."""
        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            # Get shared state to access stored data
            shared_state = cast("SharedState", self.context.state)

            error_message = "unknown_error"
            recovery_action = "reset"

            try:
                # Check for error conditions and determine recovery action
                error_message, recovery_action = self._analyze_error_conditions(
                    shared_state
                )

                # Attempt recovery actions
                if recovery_action == "reconnect_websocket":
                    yield from self._attempt_websocket_reconnection(shared_state)
                elif recovery_action == "restart_services":
                    yield from self._restart_services(shared_state)
                elif recovery_action == "reset":
                    yield from self._reset_agent_state(shared_state)

                self.context.logger.info(
                    f"🔧 Error handled: {error_message}, Action: {recovery_action}"
                )

            except Exception as e:
                self.context.logger.error(f"❌ Error in error handling: {e}")
                error_message = f"error_handler_failed: {str(e)}"
                recovery_action = "reset"

            payload = ErrorPayload(
                sender=self.context.agent_address,
                error_message=error_message,
                recovery_action=recovery_action,
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def _analyze_error_conditions(self, shared_state) -> tuple:
        """Analyze current error conditions and determine recovery action."""
        # Check synchronized data for error indicators
        synchronized_data = shared_state.synchronized_data

        # Check connection status
        connection_status = synchronized_data.connection_status
        if connection_status and "failed" in connection_status:
            return "websocket_connection_failed", "reconnect_websocket"

        # Check for transaction errors
        transaction_hash = synchronized_data.transaction_hash
        if transaction_hash and "error" in str(transaction_hash):
            return "transaction_execution_failed", "restart_services"

        # Check for pet action errors
        pet_action_result = synchronized_data.pet_action_result
        if pet_action_result and "error" in pet_action_result:
            return "pet_action_failed", "reconnect_websocket"

        # Default error handling
        return "general_error", "reset"

    def _attempt_websocket_reconnection(self, shared_state) -> Generator:
        """Attempt to reconnect WebSocket client."""
        try:
            self.context.logger.info("🔄 Attempting WebSocket reconnection...")

            # Clean up existing connection
            if hasattr(shared_state, "websocket_client"):
                if shared_state.websocket_client:
                    disconnect_future = asyncio.ensure_future(
                        shared_state.websocket_client.disconnect()
                    )
                    yield from self._wait_for_future(disconnect_future)

                # Create new WebSocket client
                shared_state.websocket_client = PettWebSocketClient()

                # Attempt reconnection
                connect_future = asyncio.ensure_future(
                    shared_state.websocket_client.connect_and_authenticate()
                )
                yield from self._wait_for_future(connect_future)

                if connect_future.result():
                    self.context.logger.info("✅ WebSocket reconnection successful")
                else:
                    self.context.logger.error("❌ WebSocket reconnection failed")

        except Exception as e:
            self.context.logger.error(f"❌ Error during WebSocket reconnection: {e}")

    def _restart_services(self, shared_state) -> Generator:
        """Restart related services."""
        try:
            self.context.logger.info("🔄 Restarting services...")

            # Reset WebSocket connection
            yield from self._attempt_websocket_reconnection(shared_state)

            # Additional service restart logic could go here

        except Exception as e:
            self.context.logger.error(f"❌ Error during service restart: {e}")

    def _reset_agent_state(self, shared_state) -> Generator:
        """Reset agent state to initial conditions."""
        try:
            self.context.logger.info("🔄 Resetting agent state...")

            # Clean up WebSocket connection
            if (
                hasattr(shared_state, "websocket_client")
                and shared_state.websocket_client
            ):
                disconnect_future = asyncio.ensure_future(
                    shared_state.websocket_client.disconnect()
                )
                yield from self._wait_for_future(disconnect_future)
                shared_state.websocket_client = None

            # Reset other state variables as needed

        except Exception as e:
            self.context.logger.error(f"❌ Error during state reset: {e}")

    def _wait_for_future(self, future) -> Generator:
        """Wait for an asyncio future to complete."""
        while not future.done():
            yield


class PettAgentRoundBehaviour(AbstractRoundBehaviour):
    """Pett Agent round behaviour."""

    initial_behaviour_cls = ConnectToPettBehaviour
    abci_app_cls = PettAgentAbciApp
    behaviours: Set[Type[BaseBehaviour]] = {
        ConnectToPettBehaviour,
        WaitForUserRequestBehaviour,
        ProcessPetActionBehaviour,
        ExecuteTransactionBehaviour,
        HandleErrorBehaviour,
    }
