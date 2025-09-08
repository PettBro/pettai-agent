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

"""This module contains the payloads for the Pett Agent ABCI skill."""

from dataclasses import dataclass


# Create base payload class
class BaseTxPayload:
    """Base transaction payload."""

    def __init__(self, sender: str):
        self.sender = sender


@dataclass(frozen=True)
class ConnectToPettPayload(BaseTxPayload):
    """Payload for connecting to Pett.ai."""

    connection_status: str


@dataclass(frozen=True)
class UserRequestPayload(BaseTxPayload):
    """Payload for user requests."""

    user_request: str
    user_id: str


@dataclass(frozen=True)
class PetActionPayload(BaseTxPayload):
    """Payload for pet actions."""

    action_type: str
    action_result: str
    requires_transaction: bool


@dataclass(frozen=True)
class TransactionPayload(BaseTxPayload):
    """Payload for transaction execution."""

    transaction_hash: str
    transaction_status: str


@dataclass(frozen=True)
class ErrorPayload(BaseTxPayload):
    """Payload for error handling."""

    error_message: str
    recovery_action: str
