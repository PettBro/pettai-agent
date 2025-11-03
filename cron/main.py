import os
import json
import asyncio
import logging
import time
from dataclasses import dataclass
import re
from pathlib import Path
from typing import Any, Dict, Optional, cast

import functions_framework  # type: ignore[import-not-found]
from web3 import Web3
from web3.contract import Contract
from web3.exceptions import ContractLogicError
from web3.types import TxParams, ChecksumAddress


logger = logging.getLogger("cron_checkpoint")
if not logger.handlers:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return str(val).strip().lower() in {"1", "true", "yes", "y", "on"}


AGENT_EOA_ADDRESS = "0xE43d9713a0999B965750fC94934D64CA7d5D2e15"
MASTER_SAFE_ADDRESS = "0x616E2bCFb3531AA407d91A02a0BE352Fd0960751"
SERVICE_REGISTRY_TOKEN_UTILITY = "0x34C895f302D0b5cf52ec0Edd3945321EB0f83dd5"
SERVICE_REGISTRY_ADDRESS = "0x3C1fF68f5aa342D296d4DEe4Bb1cACCA912D95fE"
ACTION_REPOSITORY_ADDRESS = "0x907afc85f3922cbdeb7b9ed806742b4ef998df31"
ACTIVITY_CHECKER_ADDRESS = "0x7ad8e6032849edd8bf742e459722ee8b10e2ccfc"
DEFAULT_STAKING_CONTRACT_ADDRESS = "0x31183503be52391844594b4B587F0e764eB3956E"

# Liveness ratio for Activity Checker (txs per second scaled by 1e18)
LIVENESS_RATIO = 92592592592592
# Target number of transactions required per liveness period (e.g., 8 per day)
TARGET_TXS_PER_LIVENESS_PERIOD = 8
# Derive liveness period (seconds) from liveness ratio: ratio = txs_per_sec * 1e18
# => liveness_period = TARGET_TXS_PER_LIVENESS_PERIOD * 1e18 / ratio
DERIVED_LIVENESS_PERIOD = max(
    1, int((TARGET_TXS_PER_LIVENESS_PERIOD * (10**18)) / LIVENESS_RATIO)
)

DEFAULT_SAFE_ADDRESS = MASTER_SAFE_ADDRESS
DEFAULT_STATE_FILE = Path("./staking_checkpoint_state.json")
DEFAULT_LIVENESS_PERIOD = DERIVED_LIVENESS_PERIOD
SUBMISSION_COOLDOWN_SECONDS = 600

# Minimal ABI for staking proxy
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


@dataclass
class CheckpointConfig:
    private_key: str
    rpc_url: str
    staking_contract_address: str
    safe_address: str = DEFAULT_SAFE_ADDRESS
    liveness_period: Optional[int] = None
    state_file: Optional[Path] = None
    dry_run: bool = True


def _load_config_from_env() -> CheckpointConfig:
    return CheckpointConfig(
        private_key=os.environ.get("ETH_PRIVATE_KEY", ""),
        rpc_url=os.environ.get("ETH_RPC_URL", ""),
        staking_contract_address=os.environ.get(
            "STAKING_CONTRACT_ADDRESS", DEFAULT_STAKING_CONTRACT_ADDRESS
        ),
        safe_address=os.environ.get("SAFE_ADDRESS", DEFAULT_SAFE_ADDRESS),
        liveness_period=DEFAULT_LIVENESS_PERIOD,
        state_file=DEFAULT_STATE_FILE,
        dry_run=_env_bool("DRY_RUN", False),
    )


class StakingCheckpointClient:
    def __init__(
        self, config: CheckpointConfig, logger: Optional[logging.Logger] = None
    ) -> None:
        self._logger = logger or logging.getLogger("staking_checkpoint")
        self._config = config
        self._w3: Optional[Web3] = None
        self._staking_contract: Optional[Contract] = None
        self._account_address: Optional[ChecksumAddress] = None
        self._private_key: Optional[str] = None
        self._safe_address = self._normalise_address(config.safe_address)
        self._state_file = config.state_file or DEFAULT_STATE_FILE
        self._cached_liveness_period: Optional[int] = config.liveness_period
        self._warned_missing_liveness = False
        self._nonce_cache: Optional[int] = None
        self._last_known_checkpoint_ts: Optional[int] = None
        self._last_checked_at: Optional[int] = None
        self._last_submitted_at: Optional[int] = None
        self._last_tx_hash: Optional[str] = None
        self._dry_run: bool = bool(config.dry_run)
        self._last_attempted_nonce: Optional[int] = None
        self._next_nonce: Optional[int] = None

        self._load_state()
        self._initialise()

    @property
    def is_enabled(self) -> bool:
        return bool(self._w3 and self._staking_contract and self._account_address)

    async def call_checkpoint_if_needed(self, force: bool = False) -> Optional[str]:
        if not self.is_enabled:
            return None
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._call_checkpoint_if_needed_sync, force
        )

    def _call_checkpoint_if_needed_sync(self, force: bool = False) -> Optional[str]:
        if not self.is_enabled:
            return None

        assert self._staking_contract is not None
        assert self._w3 is not None

        last_onchain = self._get_last_checkpoint_on_chain()
        current_ts = self._get_current_block_timestamp()
        liveness = self._get_liveness_period()
        should_execute = force

        if not should_execute:
            if self._recent_submission_in_progress(current_ts):
                self._logger.debug("Skipping checkpoint: recent submission pending")
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
                        "Checkpoint liveness not reached (remaining %ss)", remaining
                    )

        self._record_state(last_onchain, current_ts, self._last_tx_hash)

        if not should_execute:
            return None

        return self._submit_checkpoint_transaction(current_ts)

    def _recent_submission_in_progress(self, current_ts: int) -> bool:
        if self._last_submitted_at is None:
            return False
        cooldown = SUBMISSION_COOLDOWN_SECONDS
        liveness = self._get_liveness_period()
        if liveness is not None and liveness > 0:
            cooldown = min(SUBMISSION_COOLDOWN_SECONDS, max(liveness // 2, 30))
        return (current_ts - self._last_submitted_at) < cooldown

    def _get_last_checkpoint_on_chain(self) -> int:
        assert self._staking_contract is not None
        try:
            value = self._staking_contract.functions.tsCheckpoint().call()
            last_ts = int(value or 0)
            self._last_known_checkpoint_ts = last_ts
            return last_ts
        except Exception as exc:
            self._logger.error("Failed to fetch on-chain checkpoint timestamp: %s", exc)
            if self._last_known_checkpoint_ts is not None:
                return self._last_known_checkpoint_ts
            raise

    def _get_current_block_timestamp(self) -> int:
        assert self._w3 is not None
        try:
            latest_block = self._w3.eth.get_block("latest")
            timestamp = latest_block.get("timestamp")
            if timestamp is None:
                raise KeyError("timestamp")
            return int(timestamp)
        except Exception as exc:
            self._logger.debug("Falling back to system time for timestamp: %s", exc)
            return int(time.time())

    def _get_liveness_period(self) -> Optional[int]:
        if self._cached_liveness_period is not None:
            return self._cached_liveness_period
        contract_value: Optional[int] = None
        if self._staking_contract is not None:
            try:
                value = self._staking_contract.functions.livenessPeriod().call()
                contract_value = int(value)
            except Exception as exc:
                self._logger.debug("Failed to fetch livenessPeriod: %s", exc)
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
        if any(
            x is None
            for x in (
                self._staking_contract,
                self._w3,
                self._private_key,
                self._account_address,
            )
        ):
            return None

        assert self._staking_contract is not None
        assert self._w3 is not None
        assert self._private_key is not None
        assert self._account_address is not None

        contract: Contract = self._staking_contract
        w3: Web3 = self._w3
        account_address: ChecksumAddress = self._account_address
        private_key: str = self._private_key

        try:
            nonce = self._resolve_nonce()
            tx_params: Dict[str, Any] = {
                "from": account_address,
                "nonce": nonce,
            }

            gas_limit = self._estimate_gas(tx_params)
            if gas_limit:
                tx_params["gas"] = gas_limit

            self._apply_fee_parameters(tx_params)
            tx_params["chainId"] = w3.eth.chain_id

            self._logger.info(
                "Submitting staking checkpoint (safe %s, nonce=%s, ts=%s)",
                self._safe_address,
                nonce,
                current_ts,
            )

            txn = contract.functions.checkpoint().build_transaction(
                cast(TxParams, tx_params)
            )

            if self._dry_run:
                try:
                    self._logger.info(
                        "[DRY RUN] Would submit checkpoint tx: %s",
                        {
                            "to": contract.address,
                            "from": account_address,
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

            signed = w3.eth.account.sign_transaction(txn, private_key=private_key)
            raw_tx = getattr(signed, "rawTransaction", None) or getattr(
                signed, "raw_transaction", None
            )
            if raw_tx is None:
                raise AttributeError(
                    "Signed transaction missing raw payload for checkpoint call"
                )
            tx_hash = w3.eth.send_raw_transaction(raw_tx)
            self._last_attempted_nonce = nonce
            self._next_nonce = int(nonce) + 1
            self._nonce_cache = self._next_nonce
            self._last_submitted_at = current_ts
            self._last_tx_hash = tx_hash.hex()
            self._persist_state_file()
            return self._last_tx_hash
        except ValueError as exc:
            self._handle_value_error(exc)
            lowered = str(exc).lower()
            if "nonce too low" in lowered:
                next_nonce = None
                try:
                    msg = str(exc)
                    m = re.search(r"next nonce\s*(\d+)", msg, re.IGNORECASE)
                    if m:
                        next_nonce = int(m.group(1))
                except Exception:
                    next_nonce = None
                if next_nonce is None:
                    try:
                        next_nonce = w3.eth.get_transaction_count(
                            account_address, "pending"
                        )
                    except Exception:
                        next_nonce = None
                if next_nonce is not None:
                    suggested = int(next_nonce)
                    if self._last_attempted_nonce is not None:
                        suggested = max(suggested, self._last_attempted_nonce + 1)
                    self._next_nonce = suggested
                    self._nonce_cache = suggested
                    self._persist_state_file()
                self._logger.info(
                    "Updated persisted nonce due to 'nonce too low'; will try on next invocation"
                )
                return None
            if "already known" in lowered or "known transaction" in lowered:
                self._logger.info(
                    "Provider indicates known transaction; treating as submitted"
                )
                return self._last_tx_hash
            raise
        except ContractLogicError as exc:
            self._logger.warning(
                "Staking contract rejected checkpoint transaction: %s", exc
            )
            return None
        except Exception:
            raise

    def _estimate_gas(self, tx_params: Dict[str, Any]) -> Optional[int]:
        if self._staking_contract is None:
            return None
        try:
            gas_estimate = self._staking_contract.functions.checkpoint().estimate_gas(
                cast(TxParams, tx_params)
            )
            buffered = int(gas_estimate * 1.2)
            return max(buffered, 200_000)
        except Exception as exc:
            self._logger.debug("Gas estimation failed for checkpoint: %s", exc)
            return None

    def _apply_fee_parameters(self, tx_params: Dict[str, Any]) -> None:
        if self._w3 is None:
            raise RuntimeError("Web3 not initialised")
        try:
            latest_block = self._w3.eth.get_block("latest")
        except Exception as exc:
            self._logger.debug("Failed to fetch latest block for fees: %s", exc)
            tx_params["gasPrice"] = self._w3.eth.gas_price
            return
        base_fee = latest_block.get("baseFeePerGas")
        if base_fee is not None:
            priority_fee = Web3.to_wei(2, "gwei")
            tx_params["maxPriorityFeePerGas"] = priority_fee
            tx_params["maxFeePerGas"] = base_fee + priority_fee * 2
        else:
            tx_params["gasPrice"] = self._w3.eth.gas_price

    def _resolve_nonce(self) -> int:
        if self._w3 is None or self._account_address is None:
            raise RuntimeError("Nonce requested before initialisation")
        if self._next_nonce is not None:
            return int(self._next_nonce)
        pending_nonce_raw = self._w3.eth.get_transaction_count(
            self._account_address, "pending"
        )
        pending_nonce: int = int(pending_nonce_raw)
        self._next_nonce = pending_nonce
        self._nonce_cache = pending_nonce
        self._persist_state_file()
        return pending_nonce

    def _handle_value_error(self, error: ValueError) -> None:
        message = str(error)
        lowered = message.lower()
        if (
            "nonce too low" in lowered
            or "replacement transaction underpriced" in lowered
        ):
            self._logger.debug("RPC indicated nonce/price issue; clearing cached nonce")
            self._nonce_cache = None
        else:
            self._logger.warning("RPC error during checkpoint submission: %s", message)

    def _initialise(self) -> None:
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
            self._logger.error(f"Failed to create Web3 provider: {exc}")
            return

        if not w3.is_connected():
            self._logger.warning("Web3 provider could not connect; checkpoint disabled")
            return

        # Try to inject POA middleware for chains like Base/Polygon if needed
        try:
            from web3.middleware import geth_poa_middleware  # type: ignore

            w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        except Exception:
            try:
                from web3.middleware import ExtraDataToPOAMiddleware  # type: ignore

                w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
            except Exception:
                pass

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
        self._account_address = Web3.to_checksum_address(account.address)
        self._private_key = private_key

        addr_preview = f"{account.address[:6]}...{account.address[-4:]}"
        self._logger.info(
            "Staking checkpoint client initialised for agent %s (safe %s, contract %s)",
            addr_preview,
            self._safe_address,
            staking_contract.address,
        )

    def _record_state(
        self,
        last_checkpoint_ts: int,
        checked_at: int,
        tx_hash: Optional[str],
        submission_ts: Optional[int] = None,
    ) -> None:
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
            "next_nonce": (
                int(self._next_nonce) if self._next_nonce is not None else None
            ),
        }
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            with self._state_file.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
        except Exception as exc:
            self._logger.debug(
                "Failed to persist checkpoint state to %s: %s", self._state_file, exc
            )

    def _persist_state_file(self) -> None:
        if self._state_file is None:
            return
        payload = {
            "last_checkpoint_ts": (
                int(self._last_known_checkpoint_ts)
                if self._last_known_checkpoint_ts is not None
                else None
            ),
            "last_checked_at": (
                int(self._last_checked_at)
                if self._last_checked_at is not None
                else None
            ),
            "last_submitted_at": (
                int(self._last_submitted_at)
                if self._last_submitted_at is not None
                else None
            ),
            "last_tx_hash": self._last_tx_hash,
            "next_nonce": (
                int(self._next_nonce) if self._next_nonce is not None else None
            ),
        }
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            with self._state_file.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
        except Exception as exc:
            self._logger.debug(
                "Failed to persist checkpoint state (light) to %s: %s",
                self._state_file,
                exc,
            )

    def _load_state(self) -> None:
        if self._state_file is None or not self._state_file.exists():
            return
        try:
            with self._state_file.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception as exc:
            self._logger.debug(
                "Failed to load checkpoint state from %s: %s", self._state_file, exc
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
            # Load persisted next nonce when available
            try:
                next_nonce_val = payload.get("next_nonce")
                if next_nonce_val is not None:
                    self._next_nonce = int(next_nonce_val)
            except Exception:
                self._next_nonce = None
        except (TypeError, ValueError) as exc:
            self._logger.debug("Malformed checkpoint state payload ignored: %s", exc)

    def _normalise_address(self, address: Optional[str]) -> str:
        addr = (address or DEFAULT_SAFE_ADDRESS).strip()
        if not addr:
            return DEFAULT_SAFE_ADDRESS
        try:
            return Web3.to_checksum_address(addr)
        except Exception:
            return addr

    def get_from_address(self) -> Optional[str]:
        try:
            return str(self._account_address) if self._account_address else None
        except Exception:
            return None


def _json_response(body: dict, status: int = 200):
    return (json.dumps(body), status, {"Content-Type": "application/json"})


@functions_framework.http
def checkpoint_http(request):
    """HTTP entrypoint to trigger the staking checkpoint.

    Does not rely on query or body args; uses env configuration only.
    """
    try:
        config = _load_config_from_env()
        client = StakingCheckpointClient(config, logger=logger)

        if not client.is_enabled:
            return _json_response(
                {
                    "status": "disabled",
                    "reason": "missing or invalid config (private key / rpc / contract)",
                },
                status=503,
            )

        tx_hash = asyncio.run(client.call_checkpoint_if_needed(force=False))
        from_address = client.get_from_address()

        return _json_response(
            {
                "status": "submitted" if tx_hash else "skipped",
                "tx_hash": tx_hash,
                "dry_run": bool(config.dry_run),
                "force": False,
                "from_address": from_address,
            }
        )
    except Exception as exc:
        logger.exception("checkpoint invocation failed: %s", exc)
        try:
            from_address = client.get_from_address()  # type: ignore[name-defined]
        except Exception:
            from_address = None
        return _json_response(
            {"status": "error", "error": str(exc), "from_address": from_address},
            status=500,
        )
