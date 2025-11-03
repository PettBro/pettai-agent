from __future__ import annotations

import threading
from typing import Dict

from web3 import Web3


_address_locks: Dict[str, threading.Lock] = {}
_global_lock = threading.Lock()


def get_shared_nonce_lock(address: str) -> threading.Lock:
    """Return a process-wide lock shared by all users of the same address.

    This helps serialize raw-transaction submissions across different components
    that sign and send with the same EOA to avoid nonce races.
    """
    try:
        addr = str(Web3.to_checksum_address(address))
    except Exception:
        addr = (address or "").strip()

    with _global_lock:
        lock = _address_locks.get(addr)
        if lock is None:
            lock = threading.Lock()
            _address_locks[addr] = lock
        return lock
