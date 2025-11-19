"""
Staking checkpoint management for the Pett agent.

This module encapsulates the interaction with the staking proxy contract in
order to call the `checkpoint` function whenever the liveness period has
elapsed since the last checkpoint execution.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_UP
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, cast

from eth_account.signers.local import LocalAccount
from web3 import Web3
from web3.contract import Contract
from web3.exceptions import ContractLogicError
from web3.middleware import ExtraDataToPOAMiddleware
from web3.types import TxParams

from .nonce_utils import get_shared_nonce_lock

DEFAULT_SAFE_ADDRESS = "0xdf5bae4216Dc278313712291c91D2DeAF2Cc9c1c"
DEFAULT_STATE_FILE = Path("data/staking_checkpoint_state.json")
DEFAULT_LIVENESS_PERIOD = 86_400  # 24 hours
SUBMISSION_COOLDOWN_SECONDS = 600  # 10 minutes to avoid duplicate submissions

# Gas strategy constants aligned with Safe.execTransaction tuning
DEFAULT_PRIORITY_FEE_PER_GAS = Web3.to_wei(5, "mwei")  # 0.005 gwei
MIN_PRIORITY_FEE_PER_GAS = Web3.to_wei(1, "mwei")  # 0.001 gwei floor
MAX_PRIORITY_FEE_PER_GAS = Web3.to_wei(50, "mwei")  # 0.05 gwei cap
MIN_FEE_BUFFER_PER_GAS = Web3.to_wei(5, "mwei")  # 0.005 gwei headroom
MAX_FEE_BUFFER_PER_GAS = Web3.to_wei(50, "mwei")  # 0.05 gwei cap
PRIORITY_FEE_OVERRIDE_ENV = "CHECKPOINT_PRIORITY_FEE_WEI"

# Minimal ABI fragment for the staking proxy contract.
STAKING_PROXY_ABI: list[Dict[str, Any]] = [
    {
        "inputs": [],
        "name": "checkpoint",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "tsCheckpoint",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "livenessPeriod",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

# Minimal ABI fragments required to compute staking KPIs.
STAKING_TOKEN_KPI_ABI: list[Dict[str, Any]] = [
    {
        "inputs": [],
        "name": "activityChecker",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "getNextRewardCheckpointTimestamp",
        "outputs": [
            {"internalType": "uint256", "name": "tsNext", "type": "uint256"}
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "serviceId", "type": "uint256"}
        ],
        "name": "getServiceInfo",
        "outputs": [
            {
                "components": [
                    {"internalType": "address", "name": "multisig", "type": "address"},
                    {"internalType": "address", "name": "owner", "type": "address"},
                    {
                        "internalType": "uint256[]",
                        "name": "nonces",
                        "type": "uint256[]",
                    },
                    {"internalType": "uint256", "name": "tsStart", "type": "uint256"},
                    {"internalType": "uint256", "name": "reward", "type": "uint256"},
                    {
                        "internalType": "uint256",
                        "name": "inactivity",
                        "type": "uint256",
                    },
                ],
                "internalType": "struct ServiceInfo",
                "name": "sInfo",
                "type": "tuple",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    },
]

ACTIVITY_CHECKER_KPI_ABI: list[Dict[str, Any]] = [
    {
        "inputs": [],
        "name": "livenessRatio",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "agent", "type": "address"}],
        "name": "getMultisigNonces",
        "outputs": [
            {"internalType": "uint256[]", "name": "nonces", "type": "uint256[]"}
        ],
        "stateMutability": "view",
        "type": "function",
    },
]


@dataclass
class StakingEpochKPIs:
    """Snapshot of staking KPI progress for the active epoch."""

    service_id: int
    multisig_address: str
    txs_in_epoch: int
    required_txs: int
    txs_remaining: int
    epoch_end_timestamp: Optional[int]
    seconds_to_epoch_end: Optional[int]
    liveness_ratio: Optional[int]
    liveness_period: Optional[int]
    current_multisig_nonce: Optional[int]
    last_checkpoint_nonce: Optional[int]
    threshold_met: bool
    updated_at: float = field(default_factory=lambda: time.time())

    def eta_text(self) -> str:
        """Return human-readable text for the remaining epoch time."""
        if self.seconds_to_epoch_end is None:
            return "unknown"
        seconds = self.seconds_to_epoch_end
        if seconds <= 0:
            return "due now"
        hours, rem = divmod(seconds, 3600)
        minutes, secs = divmod(rem, 60)
        parts: list[str] = []
        if hours:
            parts.append(f"{hours}h")
        if minutes or (hours and secs):
            parts.append(f"{minutes}m")
        if not parts:
            parts.append(f"{secs}s")
        return "in " + " ".join(parts)

    def status(self) -> str:
        """Return a concise status label."""
        if self.threshold_met:
            return "on_track"
        if self.txs_remaining <= max(1, self.required_txs // 4):
            return "close"
        return "behind"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize KPI snapshot for UI/telemetry."""
        return {
            "service_id": self.service_id,
            "multisig_address": self.multisig_address,
            "txs_in_epoch": self.txs_in_epoch,
            "required_txs": self.required_txs,
            "txs_remaining": self.txs_remaining,
            "epoch_end_timestamp": self.epoch_end_timestamp,
            "seconds_to_epoch_end": self.seconds_to_epoch_end,
            "liveness_ratio": self.liveness_ratio,
            "liveness_period": self.liveness_period,
            "current_multisig_nonce": self.current_multisig_nonce,
            "last_checkpoint_nonce": self.last_checkpoint_nonce,
            "threshold_met": self.threshold_met,
            "status": self.status(),
            "eta_text": self.eta_text(),
            "updated_at": self.updated_at,
        }


@dataclass
class CheckpointConfig:
    """Configuration required to interact with the staking contract."""

    private_key: str
    rpc_url: str
    staking_contract_address: str
    safe_address: str = DEFAULT_SAFE_ADDRESS
    liveness_period: Optional[int] = None
    state_file: Optional[Path] = None
    # When True, do not broadcast checkpoint txs; only log what would be sent
    dry_run: bool = True
    staking_token_address: Optional[str] = None
    service_id: Optional[int] = None


class StakingCheckpointClient:
    """Encapsulates the staking checkpoint interaction logic."""

    def __init__(
        self,
        config: CheckpointConfig,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._logger = logger or logging.getLogger("staking_checkpoint")
        self._config = config
        self._w3: Optional[Web3] = None
        self._staking_contract: Optional[Contract] = None
        self._account: Optional[LocalAccount] = None
        self._private_key: Optional[str] = None
        self._safe_address = self._normalise_address(config.safe_address)
        self._state_file = self._resolve_state_file(config.state_file)
        self._cached_liveness_period: Optional[int] = config.liveness_period
        self._warned_missing_liveness = False
        self._nonce_lock = threading.Lock()
        self._nonce_cache: Optional[int] = None
        self._call_lock = threading.Lock()
        self._last_known_checkpoint_ts: Optional[int] = None
        self._last_checked_at: Optional[int] = None
        self._last_submitted_at: Optional[int] = None
        self._last_tx_hash: Optional[str] = None
        self._dry_run: bool = bool(config.dry_run)
        self._service_id: Optional[int] = config.service_id
        self._staking_token_address: Optional[str] = self._resolve_token_address(
            config
        )
        self._kpi_cache: Optional[Tuple[StakingEpochKPIs, float]] = None
        self._kpi_cache_ttl: float = 60.0
        self._warned_missing_service_id = False
        self._warned_metrics_failure = False

        self._load_state()
        self._initialise()

    @property
    def is_enabled(self) -> bool:
        """Return True when the client is ready to submit transactions."""
        return bool(self._w3 and self._staking_contract and self._account)

    async def call_checkpoint_if_needed(self, force: bool = False) -> Optional[str]:
        """
        Call checkpoint when liveness period elapsed.

        Returns the transaction hash (hex string) when a checkpoint transaction
        was submitted, None otherwise.
        """
        if not self.is_enabled:
            return None

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._call_checkpoint_if_needed_sync, force
        )

    async def get_epoch_kpis(
        self, force_refresh: bool = False
    ) -> Optional[StakingEpochKPIs]:
        """Return staking KPI snapshot for the current epoch."""
        if not self.is_enabled:
            return None
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._get_epoch_kpis_sync, force_refresh
        )

    def _call_checkpoint_if_needed_sync(self, force: bool = False) -> Optional[str]:
        """Synchronous implementation invoked from the executor."""
        if not self.is_enabled:
            return None

        if not self._call_lock.acquire(blocking=False):
            return None

        try:
            assert self._staking_contract is not None
            assert self._w3 is not None

            last_onchain = self._get_last_checkpoint_on_chain()
            current_ts = self._get_current_block_timestamp()
            liveness = self._get_liveness_period()
            should_execute = force

            if not should_execute:
                if self._recent_submission_in_progress(current_ts):
                    self._logger.debug(
                        "Skipping staking checkpoint: recent submission pending"
                    )
                    self._record_state(last_onchain, current_ts, self._last_tx_hash)
                    return None

                if liveness is None:
                    should_execute = True
                else:
                    elapsed = current_ts - last_onchain
                    should_execute = elapsed > liveness
                    if not should_execute:
                        remaining = max(liveness - elapsed, 0)
                        self._logger.debug(
                            "Checkpoint liveness not reached yet (remaining %ss)",
                            remaining,
                        )

            self._record_state(last_onchain, current_ts, self._last_tx_hash)

            if not should_execute:
                return None

            tx_hash = self._submit_checkpoint_transaction(current_ts)
            if tx_hash:
                self._logger.info(
                    "Staking checkpoint transaction submitted: %s", tx_hash
                )
                self._record_state(
                    last_onchain, current_ts, tx_hash, submission_ts=current_ts
                )
            return tx_hash
        finally:
            self._call_lock.release()

    def _get_epoch_kpis_sync(
        self, force_refresh: bool = False
    ) -> Optional[StakingEpochKPIs]:
        """Blocking implementation of KPI retrieval."""
        if not self.is_enabled:
            return None

        now = time.time()
        if (
            not force_refresh
            and self._kpi_cache is not None
            and (now - self._kpi_cache[1]) < self._kpi_cache_ttl
        ):
            return self._kpi_cache[0]

        cached_entry = self._kpi_cache

        if self._service_id is None:
            if not self._warned_missing_service_id:
                self._logger.debug(
                    "Staking KPIs unavailable: configure SERVICE_ID / STAKING_SERVICE_ID"
                )
                self._warned_missing_service_id = True
            return cached_entry[0] if cached_entry and not force_refresh else None

        staking_token_address = self._staking_token_address
        if staking_token_address is None and self._staking_contract is not None:
            try:
                staking_token_address = Web3.to_checksum_address(
                    self._staking_contract.address  # type: ignore[attr-defined]
                )
            except Exception:
                staking_token_address = cast(str, self._staking_contract.address)
            self._staking_token_address = staking_token_address

        if staking_token_address is None:
            if not self._warned_metrics_failure:
                self._logger.debug(
                    "Staking KPIs unavailable: staking token address not resolved"
                )
                self._warned_metrics_failure = True
            return cached_entry[0] if cached_entry and not force_refresh else None

        assert self._w3 is not None
        try:
            staking_contract = self._w3.eth.contract(
                address=staking_token_address, abi=STAKING_TOKEN_KPI_ABI
            )
            service_info = staking_contract.functions.getServiceInfo(
                int(self._service_id)
            ).call()
        except Exception as exc:
            if not self._warned_metrics_failure:
                self._logger.debug(
                    "Failed to fetch staking KPIs for service %s: %s",
                    self._service_id,
                    exc,
                )
                self._warned_metrics_failure = True
            return cached_entry[0] if cached_entry and not force_refresh else None

        try:
            multisig_address = str(service_info[0])
        except Exception:
            multisig_address = ""
        try:
            multisig_address = Web3.to_checksum_address(multisig_address)
        except Exception:
            pass
        if not multisig_address:
            multisig_address = self._safe_address

        last_checkpoint_nonce: Optional[int] = None
        try:
            nonce_snapshot = service_info[2]
            if isinstance(nonce_snapshot, (list, tuple)) and nonce_snapshot:
                last_checkpoint_nonce = int(nonce_snapshot[0])
        except Exception:
            last_checkpoint_nonce = None

        try:
            epoch_end_ts = int(
                staking_contract.functions.getNextRewardCheckpointTimestamp().call()
            )
        except Exception:
            epoch_end_ts = None

        seconds_to_epoch_end: Optional[int] = None
        if epoch_end_ts is not None:
            seconds_to_epoch_end = max(int(epoch_end_ts - int(now)), 0)

        activity_checker_address: Optional[str]
        try:
            activity_checker_address = staking_contract.functions.activityChecker().call()
            activity_checker_address = Web3.to_checksum_address(
                str(activity_checker_address)
            )
        except Exception:
            activity_checker_address = None

        liveness_ratio: Optional[int] = None
        current_multisig_nonce: Optional[int] = None
        required_txs = 0

        if activity_checker_address:
            try:
                activity_checker = self._w3.eth.contract(
                    address=activity_checker_address, abi=ACTIVITY_CHECKER_KPI_ABI
                )
                liveness_ratio = int(
                    activity_checker.functions.livenessRatio().call()
                )

                multisig_nonces_raw = activity_checker.functions.getMultisigNonces(
                    multisig_address
                ).call()
                if isinstance(multisig_nonces_raw, (list, tuple)):
                    if len(multisig_nonces_raw) > 0:
                        current_multisig_nonce = int(multisig_nonces_raw[0])
                else:
                    current_multisig_nonce = int(multisig_nonces_raw)
            except Exception as exc:
                if not self._warned_metrics_failure:
                    self._logger.debug(
                        "Failed to query activity checker KPIs: %s", exc
                    )
                    self._warned_metrics_failure = True

        liveness_period = self._get_liveness_period()
        if liveness_period and liveness_ratio:
            try:
                ratio_dec = Decimal(liveness_ratio)
                period_dec = Decimal(liveness_period)
                required_dec = (ratio_dec * period_dec) / Decimal(10**18)
                required_txs = int(required_dec.to_integral_value(rounding=ROUND_UP))
            except Exception:
                required_txs = 0

        if required_txs <= 0:
            # Fallback to the commonly used daily threshold of 8 txs.
            required_txs = 8

        if current_multisig_nonce is None or last_checkpoint_nonce is None:
            txs_in_epoch = 0
        else:
            txs_in_epoch = max(current_multisig_nonce - last_checkpoint_nonce, 0)

        txs_remaining = max(required_txs - txs_in_epoch, 0)
        threshold_met = required_txs > 0 and txs_in_epoch >= required_txs

        metrics = StakingEpochKPIs(
            service_id=int(self._service_id),
            multisig_address=multisig_address,
            txs_in_epoch=txs_in_epoch,
            required_txs=required_txs,
            txs_remaining=txs_remaining,
            epoch_end_timestamp=epoch_end_ts,
            seconds_to_epoch_end=seconds_to_epoch_end,
            liveness_ratio=liveness_ratio,
            liveness_period=liveness_period,
            current_multisig_nonce=current_multisig_nonce,
            last_checkpoint_nonce=last_checkpoint_nonce,
            threshold_met=threshold_met,
        )

        self._kpi_cache = (metrics, now)
        self._warned_missing_service_id = False
        self._warned_metrics_failure = False
        return metrics

    def _recent_submission_in_progress(self, current_ts: int) -> bool:
        """Return True if a recent submission is still within cooldown."""
        if self._last_submitted_at is None:
            return False
        cooldown = SUBMISSION_COOLDOWN_SECONDS
        liveness = self._get_liveness_period()
        if liveness is not None and liveness > 0:
            cooldown = min(SUBMISSION_COOLDOWN_SECONDS, max(liveness // 2, 30))
        return (current_ts - self._last_submitted_at) < cooldown

    def _get_last_checkpoint_on_chain(self) -> int:
        """Fetch the last checkpoint timestamp from the contract."""
        assert self._staking_contract is not None
        try:
            value = self._staking_contract.functions.tsCheckpoint().call()
            last_ts = int(value or 0)
            self._last_known_checkpoint_ts = last_ts
            return last_ts
        except Exception as exc:
            self._logger.error("Failed to fetch on-chain checkpoint timestamp: %s", exc)
            # Fallback to cached value when available.
            if self._last_known_checkpoint_ts is not None:
                return self._last_known_checkpoint_ts
            raise

    def _get_current_block_timestamp(self) -> int:
        """Return the timestamp of the latest block."""
        assert self._w3 is not None
        try:
            latest_block = self._w3.eth.get_block("latest")
            timestamp = latest_block.get("timestamp")
            if timestamp is None:
                raise KeyError("timestamp")
            return int(timestamp)
        except Exception as exc:
            self._logger.debug(
                "Failed to fetch latest block timestamp; falling back to system time: %s",
                exc,
            )
            return int(time.time())

    def _get_liveness_period(self) -> Optional[int]:
        """Resolve the liveness period from config or contract."""
        if self._cached_liveness_period is not None:
            return self._cached_liveness_period

        contract_value: Optional[int] = None
        if self._staking_contract is not None:
            try:
                value = self._staking_contract.functions.livenessPeriod().call()
                contract_value = int(value)
            except Exception as exc:
                self._logger.debug(
                    "Failed to fetch livenessPeriod from staking contract: %s", exc
                )

        if contract_value is not None and contract_value > 0:
            self._cached_liveness_period = contract_value
            return self._cached_liveness_period

        if self._config.liveness_period is not None:
            self._cached_liveness_period = int(self._config.liveness_period)
            return self._cached_liveness_period

        if not self._warned_missing_liveness:
            self._logger.warning(
                "Liveness period unavailable; defaulting to %s seconds",
                DEFAULT_LIVENESS_PERIOD,
            )
            self._warned_missing_liveness = True

        self._cached_liveness_period = DEFAULT_LIVENESS_PERIOD
        return self._cached_liveness_period

    def _submit_checkpoint_transaction(self, current_ts: int) -> Optional[str]:
        """Build, sign, and submit the checkpoint transaction."""
        if (
            self._staking_contract is None
            or self._account is None
            or self._w3 is None
            or self._private_key is None
        ):
            return None

        contract = self._staking_contract
        w3 = self._w3

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                with self._nonce_lock:
                    nonce = self._resolve_nonce()
                    tx_params: Dict[str, Any] = {
                        "from": self._account.address,
                        "nonce": nonce,
                    }

                    gas_limit = self._estimate_gas(tx_params)
                    if gas_limit:
                        tx_params["gas"] = gas_limit

                    self._apply_fee_parameters(tx_params)
                    tx_params["chainId"] = w3.eth.chain_id

                    self._logger.info(
                        "Submitting staking checkpoint transaction via safe %s "
                        "(nonce=%s, timestamp=%s)",
                        self._safe_address,
                        nonce,
                        current_ts,
                    )

                    txn = contract.functions.checkpoint().build_transaction(
                        cast(TxParams, tx_params)
                    )

                    if self._dry_run:
                        # Do not sign/send; just print what would be submitted
                        try:
                            self._logger.info(
                                "[DRY RUN] Would submit staking checkpoint tx: %s",
                                {
                                    "to": contract.address,
                                    "from": self._account.address,
                                    "nonce": tx_params.get("nonce"),
                                    "gas": tx_params.get("gas"),
                                    "chainId": tx_params.get("chainId"),
                                    "maxPriorityFeePerGas": tx_params.get(
                                        "maxPriorityFeePerGas"
                                    ),
                                    "maxFeePerGas": tx_params.get("maxFeePerGas"),
                                    "gasPrice": tx_params.get("gasPrice"),
                                },
                            )
                        except Exception:
                            pass
                        return None
                    signed = w3.eth.account.sign_transaction(
                        txn, private_key=self._private_key
                    )
                    raw_tx = getattr(signed, "rawTransaction", None) or getattr(
                        signed, "raw_transaction", None
                    )
                    if raw_tx is None:
                        raise AttributeError(
                            "Signed transaction missing raw payload for checkpoint call"
                        )
                    tx_hash = w3.eth.send_raw_transaction(raw_tx)
                    self._nonce_cache = nonce + 1
                    self._last_submitted_at = current_ts
                    self._last_tx_hash = tx_hash.hex()
                    return self._last_tx_hash
            except ValueError as exc:
                self._handle_value_error(exc)
                lowered = str(exc).lower()
                if "nonce too low" in lowered and attempt < max_attempts - 1:
                    time.sleep(0.25)
                    continue
                raise
            except ContractLogicError as exc:
                self._logger.warning(
                    "Staking contract rejected checkpoint transaction: %s", exc
                )
                self._nonce_cache = None
                return None
            except Exception:
                self._nonce_cache = None
                raise

        return None

    def _estimate_gas(self, tx_params: Dict[str, Any]) -> Optional[int]:
        """Estimate gas usage for the checkpoint transaction."""
        if self._staking_contract is None:
            return None
        try:
            gas_estimate = self._staking_contract.functions.checkpoint().estimate_gas(
                cast(TxParams, tx_params)
            )
            buffered = int(gas_estimate * 1.2)
            return max(buffered, 200_000)
        except Exception as exc:
            self._logger.debug("Gas estimation failed for staking checkpoint: %s", exc)
            return None

    def _apply_fee_parameters(self, tx_params: Dict[str, Any]) -> None:
        """Populate gas price / fee parameters depending on network support."""
        if self._w3 is None:
            raise RuntimeError("Web3 not initialised for checkpoint client")

        try:
            latest_block = self._w3.eth.get_block("latest")
        except Exception as exc:
            self._logger.debug(
                "Failed to fetch latest block for fee parameters: %s", exc
            )
            tx_params["gasPrice"] = self._w3.eth.gas_price
            return

        base_fee = latest_block.get("baseFeePerGas")
        if base_fee is None:
            tx_params["gasPrice"] = self._w3.eth.gas_price
            return

        base_fee_int = int(base_fee)
        priority_fee = int(self._suggest_priority_fee())
        min_buffer = int(MIN_FEE_BUFFER_PER_GAS)
        max_buffer = int(MAX_FEE_BUFFER_PER_GAS)

        if priority_fee <= 0:
            buffer = min_buffer
        else:
            buffer = max(min_buffer, min(priority_fee, max_buffer))

        max_fee = base_fee_int + priority_fee + buffer

        tx_params["maxPriorityFeePerGas"] = priority_fee
        tx_params["maxFeePerGas"] = max_fee

        self._logger.debug(
            "Checkpoint fee params: base=%s priority=%s buffer=%s max=%s",
            base_fee_int,
            priority_fee,
            buffer,
            max_fee,
        )

    def _suggest_priority_fee(self) -> int:
        """Return a conservative priority fee similar to Safe.execTransaction."""
        if self._w3 is None:
            return int(DEFAULT_PRIORITY_FEE_PER_GAS)

        priority_fee: Optional[int] = None

        override_raw = os.environ.get(PRIORITY_FEE_OVERRIDE_ENV)
        if override_raw:
            try:
                priority_fee = max(0, int(override_raw))
                self._logger.debug(
                    "Using checkpoint priority fee override (%s=%s)",
                    PRIORITY_FEE_OVERRIDE_ENV,
                    priority_fee,
                )
            except ValueError:
                self._logger.warning(
                    "Invalid %s value '%s'; ignoring",
                    PRIORITY_FEE_OVERRIDE_ENV,
                    override_raw,
                )

        if priority_fee is None:
            try:
                suggested = getattr(self._w3.eth, "max_priority_fee", None)
                if callable(suggested):
                    suggested = suggested()
                if suggested is not None:
                    priority_fee = int(suggested)
            except Exception as exc:
                self._logger.debug(
                    "Failed to obtain RPC priority fee suggestion: %s", exc
                )

        if priority_fee is None or priority_fee <= 0:
            priority_fee = int(DEFAULT_PRIORITY_FEE_PER_GAS)

        if 0 < priority_fee < int(MIN_PRIORITY_FEE_PER_GAS):
            priority_fee = int(MIN_PRIORITY_FEE_PER_GAS)
        elif priority_fee > int(MAX_PRIORITY_FEE_PER_GAS):
            priority_fee = int(MAX_PRIORITY_FEE_PER_GAS)

        return priority_fee

    def _resolve_nonce(self) -> int:
        """Return the next transaction nonce, caching between submissions."""
        if self._w3 is None or self._account is None:
            raise RuntimeError(
                "Nonce requested before checkpoint client initialisation"
            )
        if self._nonce_cache is None:
            self._nonce_cache = self._w3.eth.get_transaction_count(
                self._account.address, "pending"
            )
        return self._nonce_cache

    def _handle_value_error(self, error: ValueError) -> None:
        """Interpret provider errors to adjust nonce cache when relevant."""
        message = str(error)
        lowered = message.lower()
        if "nonce too low" in lowered:
            self._logger.debug("RPC reported nonce too low; clearing cached nonce")
            self._nonce_cache = None
        elif "replacement transaction underpriced" in lowered:
            self._logger.debug(
                "Replacement transaction underpriced; clearing cached nonce"
            )
            self._nonce_cache = None
        else:
            self._logger.warning("RPC error during checkpoint submission: %s", message)

    def _initialise(self) -> None:
        """Initialise web3 provider, account and staking contract."""
        private_key = (self._config.private_key or "").strip()
        if not private_key:
            self._logger.info(
                "Staking checkpoint disabled: ethereum private key unavailable"
            )
            return
        if not private_key.startswith("0x"):
            private_key = f"0x{private_key}"

        rpc_url = (self._config.rpc_url or "").strip()
        if not rpc_url:
            self._logger.info(
                "Staking checkpoint disabled: RPC endpoint not configured"
            )
            return

        try:
            w3 = Web3(Web3.HTTPProvider(rpc_url))
        except Exception as exc:
            self._logger.error(f"Failed to create Web3 provider for checkpoint: {exc}")
            return

        if not w3.is_connected():
            self._logger.warning(
                "Web3 provider could not connect; staking checkpoint disabled"
            )
            return

        self._inject_poa_middleware(w3)

        try:
            account = w3.eth.account.from_key(private_key)
        except ValueError as exc:
            self._logger.error(f"Invalid ethereum private key supplied: {exc}")
            return

        try:
            staking_contract = w3.eth.contract(
                address=Web3.to_checksum_address(self._config.staking_contract_address),
                abi=STAKING_PROXY_ABI,
            )
        except Exception as exc:
            self._logger.error(f"Failed to instantiate staking contract: {exc}")
            return

        self._w3 = w3
        self._staking_contract = staking_contract
        self._account = account
        self._private_key = private_key

        # Use a process-wide shared lock for this address to prevent nonce races
        try:
            self._nonce_lock = get_shared_nonce_lock(account.address)
        except Exception:
            pass

        addr_preview = f"{account.address[:6]}...{account.address[-4:]}"
        self._logger.info(
            "Staking checkpoint client initialised for agent %s (safe %s, contract %s)",
            addr_preview,
            self._safe_address,
            staking_contract.address,
        )

    def _inject_poa_middleware(self, w3: Web3) -> None:
        """Inject POA middleware when required (e.g., Base network)."""
        try:
            w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        except ValueError:
            pass
        except Exception as exc:
            self._logger.debug(
                f"Failed to inject POA middleware fallback for checkpoint client: {exc}"
            )

    def _record_state(
        self,
        last_checkpoint_ts: int,
        checked_at: int,
        tx_hash: Optional[str],
        submission_ts: Optional[int] = None,
    ) -> None:
        """Persist last checkpoint information for reuse across restarts."""
        self._last_known_checkpoint_ts = last_checkpoint_ts
        self._last_checked_at = checked_at
        if submission_ts is not None:
            self._last_submitted_at = submission_ts
        if tx_hash:
            self._last_tx_hash = tx_hash

        if self._state_file is None:
            return

        payload = {
            "last_checkpoint_ts": int(last_checkpoint_ts),
            "last_checked_at": int(checked_at),
            "last_submitted_at": (
                int(self._last_submitted_at)
                if self._last_submitted_at is not None
                else None
            ),
            "last_tx_hash": tx_hash,
        }

        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            with self._state_file.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
        except Exception as exc:
            self._logger.debug(
                "Failed to persist staking checkpoint state to %s: %s",
                self._state_file,
                exc,
            )

    def _load_state(self) -> None:
        """Load previously persisted state if available."""
        if self._state_file is None:
            return
        if not self._state_file.exists():
            return
        try:
            with self._state_file.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception as exc:
            self._logger.debug(
                "Failed to load staking checkpoint state from %s: %s",
                self._state_file,
                exc,
            )
            return

        try:
            self._last_known_checkpoint_ts = (
                int(payload.get("last_checkpoint_ts"))
                if payload.get("last_checkpoint_ts") is not None
                else None
            )
            self._last_checked_at = (
                int(payload.get("last_checked_at"))
                if payload.get("last_checked_at") is not None
                else None
            )
            self._last_submitted_at = (
                int(payload.get("last_submitted_at"))
                if payload.get("last_submitted_at") is not None
                else None
            )
            tx_hash = payload.get("last_tx_hash")
            self._last_tx_hash = str(tx_hash) if tx_hash else None
        except (TypeError, ValueError) as exc:
            self._logger.debug(
                "Malformed staking checkpoint state payload ignored: %s", exc
            )

    def _resolve_state_file(self, state_file: Optional[Path]) -> Path:
        """Return the path to the state file, defaulting to ./data."""
        if state_file is None:
            return DEFAULT_STATE_FILE
        if isinstance(state_file, Path):
            return state_file
        return Path(state_file)

    def _resolve_token_address(self, config: CheckpointConfig) -> Optional[str]:
        """Determine the staking token address used for KPI queries."""
        candidate = config.staking_token_address or config.staking_contract_address
        if not candidate:
            return None
        try:
            return Web3.to_checksum_address(candidate)
        except Exception:
            return candidate

    def _normalise_address(self, address: Optional[str]) -> str:
        """Return a checksum-safe address when possible."""
        addr = (address or DEFAULT_SAFE_ADDRESS).strip()
        if not addr:
            return DEFAULT_SAFE_ADDRESS
        try:
            return Web3.to_checksum_address(addr)
        except Exception:
            return addr
