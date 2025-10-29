"""
Action recorder utility for emitting transactions to the Pett action repository.

The recorder reads the agent EOA private key, connects to the target contract and
exposes an async interface that can be scheduled from the rest of the agent.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional, Set, Any, cast

from eth_account.signers.local import LocalAccount
from web3 import Web3
from web3.contract import Contract
from web3.exceptions import ContractLogicError
from web3.middleware import ExtraDataToPOAMiddleware
from web3.types import TxParams


# Contract address provided by the user.
DEFAULT_ACTION_REPO_ADDRESS = "0x907afc85f3922cbdeb7b9ed806742b4ef998df31"


# ABI fragment for the recordAction interaction (provided by the user).
ACTION_REPO_ABI = [
    {
        "inputs": [
            {"internalType": "uint8", "name": "actionId", "type": "uint8"},
            {"internalType": "bytes32", "name": "nonce", "type": "bytes32"},
            {"internalType": "uint256", "name": "timestamp", "type": "uint256"},
            {"internalType": "uint8", "name": "v", "type": "uint8"},
            {"internalType": "bytes32", "name": "r", "type": "bytes32"},
            {"internalType": "bytes32", "name": "s", "type": "bytes32"},
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
            {"internalType": "uint8[]", "name": "actionIds", "type": "uint8[]"},
            {"internalType": "bytes32[]", "name": "nonces", "type": "bytes32[]"},
            {"internalType": "uint256[]", "name": "timestamps", "type": "uint256[]"},
            {"internalType": "uint8[]", "name": "vs", "type": "uint8[]"},
            {"internalType": "bytes32[]", "name": "rs", "type": "bytes32[]"},
            {"internalType": "bytes32[]", "name": "ss", "type": "bytes32[]"},
        ],
        "name": "recordActionsBatch",
        "outputs": [
            {"internalType": "uint256", "name": "totalAdded", "type": "uint256"}
        ],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

# Minimal ABI for Gnosis Safe we interact with
SAFE_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "value", "type": "uint256"},
            {"internalType": "bytes", "name": "data", "type": "bytes"},
            {"internalType": "uint8", "name": "operation", "type": "uint8"},
            {"internalType": "uint256", "name": "safeTxGas", "type": "uint256"},
            {"internalType": "uint256", "name": "baseGas", "type": "uint256"},
            {"internalType": "uint256", "name": "gasPrice", "type": "uint256"},
            {"internalType": "address", "name": "gasToken", "type": "address"},
            {
                "internalType": "address payable",
                "name": "refundReceiver",
                "type": "address",
            },
            {"internalType": "bytes", "name": "signatures", "type": "bytes"},
        ],
        "name": "execTransaction",
        "outputs": [{"internalType": "bool", "name": "success", "type": "bool"}],
        "stateMutability": "payable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "value", "type": "uint256"},
            {"internalType": "bytes", "name": "data", "type": "bytes"},
            {"internalType": "uint8", "name": "operation", "type": "uint8"},
            {"internalType": "uint256", "name": "safeTxGas", "type": "uint256"},
            {"internalType": "uint256", "name": "baseGas", "type": "uint256"},
            {"internalType": "uint256", "name": "gasPrice", "type": "uint256"},
            {"internalType": "address", "name": "gasToken", "type": "address"},
            {"internalType": "address", "name": "refundReceiver", "type": "address"},
            {"internalType": "uint256", "name": "_nonce", "type": "uint256"},
        ],
        "name": "getTransactionHash",
        "outputs": [{"internalType": "bytes32", "name": "", "type": "bytes32"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "nonce",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
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
    multisig_address: Optional[str] = None


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
        self._safe_contract: Optional[Contract] = None
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

        # Optional: instantiate Gnosis Safe
        safe_contract: Optional[Contract] = None
        safe_addr = (getattr(self._config, "multisig_address", None) or "").strip()
        if safe_addr:
            try:
                safe_checksum = Web3.to_checksum_address(safe_addr)
                safe_contract = w3.eth.contract(address=safe_checksum, abi=SAFE_ABI)
            except Exception as exc:
                self._logger.error(f"Failed to instantiate Gnosis Safe contract: {exc}")
                safe_contract = None
        else:
            self._logger.warning(
                "No multisig configured; will not be able to submit via Safe"
            )

        self._w3 = w3
        self._contract = contract
        self._safe_contract = safe_contract
        self._account = account
        self._private_key = private_key
        self._enabled = True

        address_preview = f"{account.address[:6]}...{account.address[-4:]}"
        self._logger.info(
            f"ActionRecorder initialised for agent address {address_preview}"
        )

    async def record_action_verified(
        self, action_name: str, verification: Dict[str, Any]
    ) -> None:
        """Record a Pett action on-chain using server-provided signature verification.

        The verification dict is expected to have the following structure:
        {
          "hash": "0x...",  # optional informational
          "signature": {"v": 27|28, "r": "0x..", "s": "0x.."},
          "message": {
            "action": 3,                   # uint8 action id
            "actionName": "RUB",           # optional, informational
            "timestamp": "1761755842",     # string or int seconds
            "nonce": "0x..."               # bytes32 hex
          }
        }
        """
        if not self._enabled or not self._contract or not self._w3 or not self._account:
            return

        action_key = (action_name or "").upper()
        # Prefer local mapping for robustness; fall back to server-provided id if unknown
        action_id = self._action_type_ids.get(action_key)
        try:
            _msg_action = (verification.get("message", {}) or {}).get("action")
            server_action_id = int(_msg_action) if _msg_action is not None else None
        except Exception:
            server_action_id = None  # type: ignore[assignment]
        if action_id is None and server_action_id is not None:
            action_id = server_action_id

        if action_id is None:
            # Unknown action mapping; log and abort
            if action_key and action_key not in self._unknown_actions:
                self._unknown_actions.add(action_key)
                self._logger.debug(
                    f"No action id mapping defined for '{action_key}' (and no server id)"
                )
            return

        message = verification.get("message", {}) or {}
        signature = verification.get("signature", {}) or {}

        nonce_hex = str(message.get("nonce", "")).strip()
        timestamp_raw = message.get("timestamp")
        try:
            timestamp = int(timestamp_raw) if timestamp_raw is not None else 0
        except Exception:
            timestamp = 0
        v = int(signature.get("v", 0) or 0)
        r = str(signature.get("r", "")).strip()
        s = str(signature.get("s", "")).strip()

        if not (
            nonce_hex
            and timestamp > 0
            and v in (27, 28)
            and r.startswith("0x")
            and s.startswith("0x")
        ):
            self._logger.debug(
                f"Incomplete verification payload for {action_key}: nonce={bool(nonce_hex)} ts={timestamp} v={v}"
            )
            return

        # Log scheduling
        try:
            addr_preview = "unknown"
            if self._account and getattr(self._account, "address", None):
                addr = self._account.address
                addr_preview = f"{addr[:6]}...{addr[-4:]}"
            self._logger.info(
                f"On-chain recordAction (verified) queued: action={action_key} id={action_id} agent={addr_preview}"
            )
        except Exception:
            pass

        loop = asyncio.get_running_loop()
        try:
            assert action_id is not None
            await loop.run_in_executor(
                None,
                self._record_action_verified_sync,
                action_key,
                int(action_id),
                nonce_hex,
                int(timestamp),
                int(v),
                r,
                s,
            )
        except Exception as exc:
            self._logger.warning(
                f"Failed to submit verified recordAction for {action_key}: {exc}"
            )

    def _record_action_verified_sync(
        self,
        action_key: str,
        action_id: int,
        nonce_hex: str,
        timestamp: int,
        v: int,
        r: str,
        s: str,
    ) -> None:
        """Execute the synchronous portion of verified recordAction."""
        if not self._enabled:
            return
        if self._contract is None:
            return
        if self._account is None:
            return
        if self._w3 is None:
            return
        if self._private_key is None:
            return

        contract = self._contract
        safe = self._safe_contract
        w3 = self._w3
        account = self._account
        private_key = self._private_key

        if safe is None:
            self._logger.warning(
                "Multisig not configured; cannot submit verified action"
            )
            return

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                with self._nonce_lock:
                    nonce = self._resolve_nonce()
                    tx_params: Dict[str, Any] = {
                        "from": account.address,
                        "nonce": nonce,
                        "value": 0,
                    }

                    # Build inner calldata for ActionRepo.recordAction
                    try:
                        inner_txn = contract.functions.recordAction(
                            int(action_id), nonce_hex, int(timestamp), int(v), r, s
                        ).build_transaction({"from": account.address})
                        inner_data = inner_txn.get("data")
                        if not inner_data:
                            raise ValueError(
                                "Failed to build inner calldata for recordAction"
                            )
                        inner_data_bytes = self._to_bytes(inner_data)
                    except Exception as exc:
                        self._logger.warning(f"Failed to encode inner calldata: {exc}")
                        return

                    # Safe params
                    to_addr = contract.address
                    value = 0
                    operation = 0
                    safe_tx_gas = 0
                    base_gas = 0
                    gas_price = 0
                    gas_token = "0x0000000000000000000000000000000000000000"
                    refund_receiver = "0x0000000000000000000000000000000000000000"

                    # Fetch Safe nonce
                    try:
                        safe_nonce = int(safe.functions.nonce().call())
                    except Exception as exc:
                        self._logger.warning(f"Failed to fetch Safe nonce: {exc}")
                        return

                    # Compute Safe tx hash
                    try:
                        tx_hash_bytes = safe.functions.getTransactionHash(
                            to_addr,
                            value,
                            inner_data_bytes,
                            operation,
                            safe_tx_gas,
                            base_gas,
                            gas_price,
                            gas_token,
                            refund_receiver,
                            safe_nonce,
                        ).call()
                    except Exception as exc:
                        self._logger.warning(f"Failed to compute Safe tx hash: {exc}")
                        return

                    # Sign for eth_sign flow (v -> v+4)
                    try:
                        from eth_account.messages import encode_defunct

                        msg = encode_defunct(primitive=tx_hash_bytes)
                        signed_msg = w3.eth.account.sign_message(
                            msg, private_key=private_key
                        )
                        sig_r = getattr(signed_msg, "r")
                        sig_s = getattr(signed_msg, "s")
                        sig_v = int(getattr(signed_msg, "v")) + 4
                        signatures = (
                            sig_r.to_bytes(32, "big")
                            + sig_s.to_bytes(32, "big")
                            + bytes([sig_v])
                        )
                    except Exception as exc:
                        self._logger.warning(f"Failed to sign Safe transaction: {exc}")
                        return

                    # Estimate outer gas
                    gas_limit = self._estimate_gas_safe_exec(
                        safe,
                        to_addr,
                        value,
                        inner_data_bytes,
                        operation,
                        safe_tx_gas,
                        base_gas,
                        gas_price,
                        gas_token,
                        refund_receiver,
                        signatures,
                        tx_params,
                    )
                    if gas_limit:
                        tx_params["gas"] = gas_limit

                    self._apply_fee_parameters(tx_params)
                    tx_params["chainId"] = w3.eth.chain_id

                    self._logger.info(
                        "Submitting Safe.execTransaction for verified recordAction: "
                        f"action={action_key} id={action_id} from={account.address} nonce={nonce}"
                    )
                    self._logger.info(
                        (
                            f"Inner recordAction params: actionId={int(action_id)}, nonce={nonce_hex}, "
                            f"timestamp={int(timestamp)}, v={int(v)}, r={r}, s={s}"
                        )
                    )

                    txn = safe.functions.execTransaction(
                        to_addr,
                        value,
                        inner_data_bytes,
                        operation,
                        safe_tx_gas,
                        base_gas,
                        gas_price,
                        gas_token,
                        refund_receiver,
                        signatures,
                    ).build_transaction(cast(TxParams, tx_params))

                    signed = w3.eth.account.sign_transaction(
                        txn, private_key=private_key
                    )
                    raw_tx = getattr(signed, "rawTransaction", None) or getattr(
                        signed, "raw_transaction", None
                    )
                    if raw_tx is None:
                        raise AttributeError(
                            "SignedTransaction missing raw transaction payload"
                        )
                    sent_hash = w3.eth.send_raw_transaction(raw_tx)
                    self._nonce_cache = nonce + 1

                    self._logger.info(
                        f"Safe.execTransaction submitted: action={action_key} id={action_id} tx={sent_hash.hex()}"
                    )
                    return
            except ValueError as exc:
                self._handle_value_error(exc)
                lowered = str(exc).lower()
                if "nonce too low" in lowered and attempt < max_attempts - 1:
                    time.sleep(0.25)
                    continue
                raise
            except ContractLogicError as exc:
                self._logger.warning(
                    f"Contract rejected verified recordAction for {action_key}: {exc}"
                )
                self._nonce_cache = None
                return
            except Exception:
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

    def _estimate_gas_safe_exec(
        self,
        safe: Contract,
        to_addr: str,
        value: int,
        inner_data: bytes,
        operation: int,
        safe_tx_gas: int,
        base_gas: int,
        gas_price: int,
        gas_token: str,
        refund_receiver: str,
        signatures: bytes,
        tx_params: Dict[str, Any],
    ) -> Optional[int]:
        """Estimate gas for Safe.execTransaction with a conservative buffer."""
        try:
            gas_estimate = safe.functions.execTransaction(
                to_addr,
                value,
                inner_data,
                operation,
                safe_tx_gas,
                base_gas,
                gas_price,
                gas_token,
                refund_receiver,
                signatures,
            ).estimate_gas(cast(TxParams, tx_params))
        except Exception as exc:
            self._logger.debug(f"Gas estimation failed for Safe.execTransaction: {exc}")
            return None

        buffered = int(gas_estimate * 1.2)
        return max(buffered, 300_000)

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

    def _to_bytes(self, data: Any) -> bytes:
        """Normalize hex string or HexBytes to raw bytes."""
        if isinstance(data, (bytes, bytearray)):
            return bytes(data)
        try:
            s = str(data)
            if s.startswith("0x"):
                return bytes.fromhex(s[2:])
            return bytes.fromhex(s)
        except Exception:
            return b""
