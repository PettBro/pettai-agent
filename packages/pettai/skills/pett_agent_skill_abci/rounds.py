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

"""This module contains the rounds for the Pett Agent ABCI skill."""

import enum
from typing import Dict, FrozenSet, Optional, Set, Tuple


# Create ABCI-specific base classes
class AbciApp:
    """Base ABCI application."""

    initial_round_cls = None
    initial_states = set()
    transition_function = {}
    final_states = set()
    event_to_timeout = {}
    cross_period_persisted_keys = frozenset()
    db_pre_conditions = {}
    db_post_conditions = {}


class AbstractRound:
    """Abstract round class."""

    def __init__(self, synchronized_data, context=None):
        self.synchronized_data = synchronized_data
        self.context = context
        self.collection = {}
        self.threshold_reached = False
        self.most_voted_payload = None


class BaseSynchronizedData:
    """Base synchronized data."""

    def __init__(self, db=None):
        self.db = db or {}

    def update(self, synchronized_data_class=None, **kwargs):
        """Update synchronized data."""
        new_db = self.db.copy()
        new_db.update(kwargs)
        return synchronized_data_class(db=new_db) if synchronized_data_class else self


from packages.pettai.skills.pett_agent_skill_abci.payloads import (
    ConnectToPettPayload,
    UserRequestPayload,
    PetActionPayload,
    TransactionPayload,
    ErrorPayload,
)


class Event(enum.Enum):
    """Pett Agent events."""

    CONNECT_TO_PETT = "connect_to_pett"
    USER_REQUEST = "user_request"
    PET_ACTION_NEEDED = "pet_action_needed"
    TRANSACTION_NEEDED = "transaction_needed"
    ERROR_OCCURRED = "error_occurred"
    RESET = "reset"
    DONE = "done"
    NO_MAJORITY = "no_majority"
    ROUND_TIMEOUT = "round_timeout"


class SynchronizedData(BaseSynchronizedData):
    """Synchronized data for the Pett Agent."""

    @property
    def connection_status(self) -> Optional[str]:
        """Get the connection status."""
        return self.db.get("connection_status", None)

    @property
    def user_request(self) -> Optional[str]:
        """Get the current user request."""
        return self.db.get("user_request", None)

    @property
    def pet_action_result(self) -> Optional[str]:
        """Get the pet action result."""
        return self.db.get("pet_action_result", None)

    @property
    def transaction_hash(self) -> Optional[str]:
        """Get the transaction hash."""
        return self.db.get("transaction_hash", None)

    @property
    def error_message(self) -> Optional[str]:
        """Get the error message."""
        return self.db.get("error_message", None)


class ConnectToPettRound(AbstractRound):
    """ConnectToPettRound"""

    payload_class = ConnectToPettPayload
    synchronized_data_class = SynchronizedData

    def end_block(self) -> Optional[Tuple[SynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            payload = self.most_voted_payload
            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                **{
                    "connection_status": payload.connection_status,
                }
            )
            return synchronized_data, Event.CONNECT_TO_PETT

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY

        return None


class WaitForUserRequestRound(AbstractRound):
    """WaitForUserRequestRound"""

    payload_class = UserRequestPayload
    synchronized_data_class = SynchronizedData

    def end_block(self) -> Optional[Tuple[SynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            payload = self.most_voted_payload
            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                user_request=payload.user_request,
            )
            return synchronized_data, Event.USER_REQUEST

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY

        return None


class ProcessPetActionRound(AbstractRound):
    """ProcessPetActionRound"""

    payload_class = PetActionPayload
    synchronized_data_class = SynchronizedData

    def end_block(self) -> Optional[Tuple[SynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            payload = self.most_voted_payload
            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                pet_action_result=payload.action_result,
            )

            if payload.requires_transaction:
                return synchronized_data, Event.TRANSACTION_NEEDED
            else:
                return synchronized_data, Event.USER_REQUEST

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY

        return None


class ExecuteTransactionRound(AbstractRound):
    """ExecuteTransactionRound"""

    payload_class = TransactionPayload
    synchronized_data_class = SynchronizedData

    def end_block(self) -> Optional[Tuple[SynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            payload = self.most_voted_payload
            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                transaction_hash=payload.transaction_hash,
            )
            return synchronized_data, Event.USER_REQUEST

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY

        return None


class HandleErrorRound(AbstractRound):
    """HandleErrorRound"""

    payload_class = ErrorPayload
    synchronized_data_class = SynchronizedData

    def end_block(self) -> Optional[Tuple[SynchronizedData, Event]]:
        """Process the end of the block."""
        if self.threshold_reached:
            payload = self.most_voted_payload
            synchronized_data = self.synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                error_message=payload.error_message,
            )

            if payload.recovery_action == "reset":
                return synchronized_data, Event.RESET
            else:
                return synchronized_data, Event.ERROR_OCCURRED

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY

        return None


class FinishedPettAgentRound(AbstractRound):
    """FinishedPettAgentRound"""

    def end_block(self):
        """Process the end of the block."""
        return None


class PettAgentAbciApp(AbciApp):
    """PettAgentAbciApp"""

    initial_round_cls = ConnectToPettRound
    initial_states = {ConnectToPettRound}
    transition_function = {
        ConnectToPettRound: {
            Event.CONNECT_TO_PETT: WaitForUserRequestRound,
            Event.ERROR_OCCURRED: HandleErrorRound,
            Event.NO_MAJORITY: ConnectToPettRound,
            Event.ROUND_TIMEOUT: ConnectToPettRound,
        },
        WaitForUserRequestRound: {
            Event.USER_REQUEST: ProcessPetActionRound,
            Event.ERROR_OCCURRED: HandleErrorRound,
            Event.RESET: ConnectToPettRound,
            Event.NO_MAJORITY: WaitForUserRequestRound,
            Event.ROUND_TIMEOUT: WaitForUserRequestRound,
        },
        ProcessPetActionRound: {
            Event.PET_ACTION_NEEDED: ProcessPetActionRound,
            Event.TRANSACTION_NEEDED: ExecuteTransactionRound,
            Event.USER_REQUEST: WaitForUserRequestRound,
            Event.ERROR_OCCURRED: HandleErrorRound,
            Event.RESET: ConnectToPettRound,
            Event.NO_MAJORITY: ProcessPetActionRound,
            Event.ROUND_TIMEOUT: ProcessPetActionRound,
        },
        ExecuteTransactionRound: {
            Event.USER_REQUEST: WaitForUserRequestRound,
            Event.ERROR_OCCURRED: HandleErrorRound,
            Event.RESET: ConnectToPettRound,
            Event.NO_MAJORITY: ExecuteTransactionRound,
            Event.ROUND_TIMEOUT: ExecuteTransactionRound,
        },
        HandleErrorRound: {
            Event.RESET: ConnectToPettRound,
            Event.ERROR_OCCURRED: FinishedPettAgentRound,
            Event.NO_MAJORITY: HandleErrorRound,
            Event.ROUND_TIMEOUT: HandleErrorRound,
        },
        FinishedPettAgentRound: {},
    }
    final_states = {FinishedPettAgentRound}
    event_to_timeout = {}
    cross_period_persisted_keys = frozenset()
    db_pre_conditions = {
        ConnectToPettRound: set(),
    }
    db_post_conditions = {
        FinishedPettAgentRound: set(),
    }
