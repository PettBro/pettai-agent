"""
Action recorder utility for emitting transactions to the Pett action repository.

The recorder reads the agent EOA private key, connects to the target contract and
exposes an async interface that can be scheduled from the rest of the agent.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from typing import Dict, Optional, Set, Any

from eth_account.signers.local import LocalAccount
from web3 import Web3
from web3.contract import Contract
from web3.exceptions import ContractLogicError
from web3.middleware import ExtraDataToPOAMiddleware


# Contract address provided by the user.
DEFAULT_ACTION_REPO_ADDRESS = "0x6e9bBe84bC1751fb37F32BEACBc85bc32Af98321"


# ABI fragment for the recordAction interaction (provided by the user).
ACTION_REPO_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "agent", "type": "address"},
            {"internalType": "bytes32", "name": "actionType", "type": "bytes32"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "recordAction",
        "outputs": [
            {"internalType": "uint256", "name": "newActionCount", "type": "uint256"}
        ],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "agent", "type": "address"},
            {"internalType": "bytes32[]", "name": "actionTypes", "type": "bytes32[]"},
            {"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"},
        ],
        "name": "recordActionsBatch",
        "outputs": [
            {"internalType": "uint256", "name": "totalAdded", "type": "uint256"}
        ],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]


def _default_action_type_ids() -> Dict[str, int]:
    """Return the default mapping between Pett actions and numeric identifiers."""
    entries = [
        "CONSUMABLES_USE",
        "CONSUMABLES_BUY",
        "RUB",
        "SHOWER",
        "SLEEP",
        "THROWBALL",
        "ACCESSORY_USE",
        "ACCESSORY_BUY",
        "HOTEL_CHECK_IN",
        "HOTEL_CHECK_OUT",
        "HOTEL_BUY",
        "WITHDRAWAL_CREATE",
        "WITHDRAWAL_QUEUE",
        "WITHDRAWAL_JUMP",
        "WITHDRAWAL_USE",
        "TRANSFER",
        "DEPOSIT",
    ]
    # Enumerate sequential ids starting at 1.
    return {name: idx + 1 for idx, name in enumerate(entries)}


@dataclass
class RecorderConfig:
    """Runtime configuration for the recorder."""

    private_key: str
    rpc_url: str
    contract_address: str = DEFAULT_ACTION_REPO_ADDRESS


class ActionRecorder:
    """Encapsulates the on-chain interaction with the action repository contract."""

    def __init__(
        self,
        config: RecorderConfig,
        logger: Optional[logging.Logger] = None,
        action_type_ids: Optional[Dict[str, int]] = None,
    ) -> None:
        self._logger: logging.Logger = logger or logging.getLogger("action_recorder")
        self._config = config
        self._action_type_ids: Dict[str, int] = (
            action_type_ids or _default_action_type_ids()
        )
        self._w3: Optional[Web3] = None
        self._contract: Optional[Contract] = None
        self._account: Optional[LocalAccount] = None
        self._private_key: Optional[str] = None
        self._nonce_lock = threading.Lock()
        self._nonce_cache: Optional[int] = None
        self._unknown_actions: Set[str] = set()
        self._enabled: bool = False

        self._initialise()

    @property
    def contract_address(self) -> Optional[str]:
        """Return the configured contract address, if available."""
        try:
            if self._contract is not None:
                return self._contract.address  # type: ignore[attr-defined]
        except Exception:
            pass
        return getattr(self._config, "contract_address", None)

    @property
    def rpc_url(self) -> Optional[str]:
        """Return the configured RPC URL, if available."""
        return getattr(self._config, "rpc_url", None)

    @property
    def account_address(self) -> Optional[str]:
        """Return the agent account address, if available."""
        try:
            return self._account.address if self._account else None  # type: ignore[union-attr]
        except Exception:
            return None

    @property
    def is_enabled(self) -> bool:
        """Return True when the recorder is ready to emit transactions."""
        return self._enabled

    def _initialise(self) -> None:
        """Initialise Web3 provider, contract instance and signing account."""
        private_key = (self._config.private_key or "").strip()
        if not private_key:
            self._logger.warning(
                "ActionRecorder initialisation skipped: missing ethereum private key"
            )
            return
        if not private_key.startswith("0x"):
            private_key = f"0x{private_key}"

        rpc_url = (self._config.rpc_url or "").strip()
        if not rpc_url:
            self._logger.warning(
                "ActionRecorder initialisation skipped: missing RPC endpoint"
            )
            return

        try:
            w3 = Web3(Web3.HTTPProvider(rpc_url))
        except Exception as exc:
            self._logger.error(f"Failed to create Web3 provider: {exc}")
            return

        if not w3.is_connected():
            self._logger.warning(
                "Web3 provider could not connect to RPC endpoint; action recording disabled"
            )
            return

        # Inject POA middleware for chains such as Gnosis/Base.
        self._inject_poa_middleware(w3)

        try:
            account = w3.eth.account.from_key(private_key)
        except ValueError as exc:
            self._logger.error(f"Invalid ethereum private key supplied: {exc}")
            return

        try:
            checksum_address = Web3.to_checksum_address(self._config.contract_address)
            contract = w3.eth.contract(address=checksum_address, abi=ACTION_REPO_ABI)
        except Exception as exc:
            self._logger.error(f"Failed to instantiate action repo contract: {exc}")
            return

        self._w3 = w3
        self._contract = contract
        self._account = account
        self._private_key = private_key
        self._enabled = True

        address_preview = f"{account.address[:6]}...{account.address[-4:]}"
        self._logger.info(
            f"ActionRecorder initialised for agent address {address_preview}"
        )

    async def record_action(self, action_name: str, amount: int = 1) -> None:
        """Record a single Pett action on-chain."""
        if not self._enabled or not self._contract or not self._w3 or not self._account:
            return

        action_key = (action_name or "").upper()
        action_id = self._action_type_ids.get(action_key)
        self._logger.info(
            f"🧾 Scheduling on-chain recordAction: type={action_key} amount={int(amount)} account={self._account._address}"
        )
        if action_id is None:
            # Remember unknown actions to avoid repeating log spam.
            if action_key and action_key not in self._unknown_actions:
                self._unknown_actions.add(action_key)
                self._logger.debug(f"No action id mapping defined for '{action_key}'")
            return

        if amount <= 0:
            self._logger.debug(
                f"Ignoring recordAction for {action_key} with non-positive amount {amount}"
            )
            return

        # Log that we are enqueueing an on-chain recordAction
        try:
            addr_preview = "unknown"
            if self._account and getattr(self._account, "address", None):
                addr = self._account.address
                addr_preview = f"{addr[:6]}...{addr[-4:]}"
            self._logger.info(
                f"On-chain recordAction queued: action={action_key} amount={int(amount)} agent={addr_preview}"
            )
        except Exception:
            pass

        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(
                None, self._record_action_sync, action_key, action_id, int(amount)
            )
        except Exception as exc:
            self._logger.warning(
                f"Failed to submit recordAction for {action_key}: {exc}"
            )

    def _record_action_sync(self, action_key: str, action_id: int, amount: int) -> None:
        """Execute the synchronous portion of recordAction."""
        if (
            not self._enabled
            or self._contract is None
            or self._account is None
            or self._w3 is None
            or self._private_key is None
        ):
            return

        contract = self._contract
        w3 = self._w3
        account = self._account
        private_key = self._private_key

        action_bytes = action_id.to_bytes(32, "big")
        try:
            with self._nonce_lock:
                nonce = self._resolve_nonce()
                tx_params = {
                    "from": account.address,
                    "nonce": nonce,
                    "value": 0,
                }

                gas_limit = self._estimate_gas(
                    contract, account.address, action_bytes, amount, tx_params
                )
                if gas_limit:
                    tx_params["gas"] = gas_limit

                self._apply_fee_parameters(tx_params)
                tx_params["chainId"] = w3.eth.chain_id

                # Info-level pre-submit log
                self._logger.info(
                    f"Submitting recordAction: action={action_key} amount={amount} from={account.address} nonce={nonce}"
                )
                txn = contract.functions.recordAction(
                    account.address, action_bytes, amount
                ).build_transaction(
                    tx_params
                )  # type: ignore[arg-type]

                signed = w3.eth.account.sign_transaction(txn, private_key=private_key)
                tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
                self._nonce_cache = nonce + 1

                # Info-level confirmation with tx hash for operator visibility
                self._logger.info(
                    f"recordAction submitted: action={action_key} amount={amount} tx={tx_hash.hex()}"
                )
        except ValueError as exc:
            self._handle_value_error(exc)
            raise
        except ContractLogicError as exc:
            self._logger.warning(
                f"Contract rejected recordAction for {action_key}: {exc}"
            )
            # Reset cached nonce so the next attempt re-syncs.
            self._nonce_cache = None
        except Exception:
            # Reset cached nonce on unexpected failures.
            self._nonce_cache = None
            raise

    def _resolve_nonce(self) -> int:
        """Return the next transaction nonce, caching between submissions."""
        if self._w3 is None or self._account is None:
            raise RuntimeError("Nonce requested before recorder initialisation")
        if self._nonce_cache is None:
            self._nonce_cache = self._w3.eth.get_transaction_count(
                self._account.address, "pending"
            )
        return self._nonce_cache

    def _estimate_gas(
        self,
        contract: Contract,
        account_address: str,
        action_bytes: bytes,
        amount: int,
        tx_params: Dict[str, Any],
    ) -> Optional[int]:
        """Estimate gas usage with a conservative buffer."""
        try:
            gas_estimate = contract.functions.recordAction(
                account_address, action_bytes, amount
            ).estimate_gas(
                tx_params
            )  # type: ignore[arg-type]
        except Exception as exc:
            self._logger.debug(f"Gas estimation failed for recordAction: {exc}")
            return None

        # Add a 20% safety margin, minimum of 150k.
        buffered = int(gas_estimate * 1.2)
        return max(buffered, 150_000)

    def _apply_fee_parameters(self, tx_params: Dict[str, Any]) -> None:
        """Populate the fee parameters according to the network capabilities."""
        if self._w3 is None:
            raise RuntimeError(
                "Fee parameters requested before recorder initialisation"
            )
        try:
            latest_block = self._w3.eth.get_block("latest")
        except Exception as exc:
            self._logger.debug(f"Failed to fetch latest block for fee data: {exc}")
            tx_params["gasPrice"] = self._w3.eth.gas_price
            return

        base_fee = latest_block.get("baseFeePerGas")
        if base_fee is not None:
            priority_fee = Web3.to_wei(2, "gwei")
            tx_params["maxPriorityFeePerGas"] = priority_fee
            tx_params["maxFeePerGas"] = base_fee + priority_fee * 2
        else:
            tx_params["gasPrice"] = self._w3.eth.gas_price

    def _handle_value_error(self, error: ValueError) -> None:
        """Parse provider ValueErrors and adjust nonce cache when relevant."""
        message = str(error)
        lowered = message.lower()
        if "nonce too low" in lowered:
            self._logger.debug("RPC reported nonce too low; clearing local nonce cache")
            self._nonce_cache = None
        elif "replacement transaction underpriced" in lowered:
            self._logger.debug("Replacement transaction underpriced; bumping fee")
            self._nonce_cache = None
        else:
            self._logger.warning(f"RPC error during recordAction: {message}")

    def _inject_poa_middleware(self, w3: Web3) -> None:
        """Inject a POA-compatible middleware when available."""
        try:
            w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        except ValueError:
            pass
        except Exception as exc:
            self._logger.debug(
                f"Failed to inject extra-data POA middleware fallback: {exc}"
            )
