"""Thin web3.py client for the single Veridata contract on Ethereum Sepolia.

Every transaction (register device, publish, purchase, fund request, release payouts, refund)
is signed in the user's browser wallet. The backend holds no private key: it only reads state
and verifies receipts and decoded events.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from .. import config

ABI = json.loads((Path(__file__).parent / "Veridata.abi.json").read_text())
_lock = threading.Lock()
_w3 = None
_contract = None


class ChainError(Exception):
    pass


def enabled() -> bool:
    return bool(config.CONTRACT_ADDRESS)


def _get():
    global _w3, _contract
    if not enabled():
        raise ChainError("chain not configured (VERIDATA_CONTRACT_ADDRESS empty)")
    if _w3 is None:
        from web3 import Web3
        _w3 = Web3(Web3.HTTPProvider(config.CHAIN_RPC_URL, request_kwargs={"timeout": 20}))
        _contract = _w3.eth.contract(address=Web3.to_checksum_address(config.CONTRACT_ADDRESS), abi=ABI)
    return _w3, _contract


def explorer_tx(h: str) -> str:
    return f"{config.EXPLORER_URL}/tx/{h}" if h and h.startswith("0x") else ""


def status() -> dict[str, Any]:
    out: dict[str, Any] = {
        "enabled": enabled(), "chainId": config.CHAIN_ID, "contract": config.CONTRACT_ADDRESS,
        "explorer": config.EXPLORER_URL, "rpc": config.CHAIN_RPC_URL,
    }
    if not enabled():
        return out
    try:
        w3, c = _get()
        out["block"] = w3.eth.block_number
        out["treasury"] = c.functions.treasury().call()
        out["uploadFeeWei"] = str(c.functions.uploadFee().call())
        out["platformFeeBps"] = c.functions.platformFeeBps().call()
        out["reachable"] = True
    except Exception as e:  # pragma: no cover - network dependent
        out["reachable"] = False
        out["error"] = str(e)[:200]
    return out


def verify_events(tx_hash: str, event: str, sender: str | None = None) -> list[dict[str, Any]]:
    """Wait for a receipt and return the decoded args of every `event` emitted by our contract."""
    w3, c = _get()
    try:
        rcpt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    except Exception as e:
        raise ChainError(f"receipt not found: {e}")
    if rcpt.status != 1:
        raise ChainError("transaction reverted")
    if sender:
        tx = w3.eth.get_transaction(tx_hash)
        if tx["from"].lower() != sender.lower():
            raise ChainError("transaction sent from a different wallet")
    logs = getattr(c.events, event)().process_receipt(rcpt, errors=__import__("web3").logs.DISCARD)
    if not logs:
        raise ChainError(f"no {event} event in transaction")
    out = []
    for l in logs:
        args = dict(l["args"])
        out.append({k: (v.hex() if isinstance(v, (bytes, bytearray)) else v) for k, v in args.items()} | {"blockNumber": rcpt.blockNumber})
    return out


def verify_event(tx_hash: str, event: str, sender: str | None = None) -> dict[str, Any]:
    return verify_events(tx_hash, event, sender)[0]


def read_dataset(dataset_id: int) -> dict[str, Any]:
    _, c = _get()
    owner, root, price, published, listed, ref = c.functions.datasets(dataset_id).call()
    return {"owner": owner, "contentRoot": root.hex(), "price": price, "publishedAt": published, "listed": listed, "storageRef": ref}


def read_device(device_id_hex: str) -> dict[str, Any]:
    _, c = _get()
    owner, pub, reg, active = c.functions.getDevice(bytes.fromhex(device_id_hex)).call()
    return {"owner": owner, "pubKey": pub.hex(), "registeredAt": reg, "active": active}


def has_license(dataset_id: int, addr: str) -> bool:
    from web3 import Web3
    _, c = _get()
    return c.functions.hasLicense(dataset_id, Web3.to_checksum_address(addr)).call()
