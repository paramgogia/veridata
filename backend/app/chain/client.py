"""Thin web3.py client for the single Veridata contract on Ethereum Sepolia.

User-initiated transactions (register device, publish, purchase, fund request) are signed in
the browser wallet; the backend only *verifies* their receipts and decoded events here.
The backend's own key (the contract's `verifier`) relays x402 purchases and releases
escrow payouts.
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


def relayer_enabled() -> bool:
    return enabled() and bool(config.VERIFIER_PRIVATE_KEY)


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
        "explorer": config.EXPLORER_URL, "relayer": relayer_enabled(), "rpc": config.CHAIN_RPC_URL,
    }
    if not enabled():
        return out
    try:
        w3, c = _get()
        out["block"] = w3.eth.block_number
        out["verifier"] = c.functions.verifier().call()
        out["uploadFeeWei"] = str(c.functions.uploadFee().call())
        out["platformFeeBps"] = c.functions.platformFeeBps().call()
        if relayer_enabled():
            acct = w3.eth.account.from_key(config.VERIFIER_PRIVATE_KEY)
            out["relayerAddress"] = acct.address
            out["relayerBalanceWei"] = str(w3.eth.get_balance(acct.address))
        out["reachable"] = True
    except Exception as e:  # pragma: no cover - network dependent
        out["reachable"] = False
        out["error"] = str(e)[:200]
    return out


def verify_event(tx_hash: str, event: str, sender: str | None = None) -> dict[str, Any]:
    """Wait for a receipt and return the decoded args of `event` emitted by our contract."""
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
    args = dict(logs[0]["args"])
    return {k: (v.hex() if isinstance(v, (bytes, bytearray)) else v) for k, v in args.items()} | {"blockNumber": rcpt.blockNumber}


def _send(fn) -> str:
    if not relayer_enabled():
        raise ChainError("relayer key not configured (VERIFIER_PRIVATE_KEY)")
    w3, _ = _get()
    acct = w3.eth.account.from_key(config.VERIFIER_PRIVATE_KEY)
    with _lock:  # serialize nonces
        tx = fn.build_transaction({
            "from": acct.address,
            "nonce": w3.eth.get_transaction_count(acct.address, "pending"),
            "chainId": config.CHAIN_ID,
        })
        signed = acct.sign_transaction(tx)
        h = w3.eth.send_raw_transaction(signed.raw_transaction)
    rcpt = w3.eth.wait_for_transaction_receipt(h, timeout=180)
    if rcpt.status != 1:
        raise ChainError("relayed transaction reverted")
    return "0x" + h.hex().removeprefix("0x")


def accept_sample(request_id: int, sample_hash_hex: str, contributor: str) -> str:
    from web3 import Web3
    _, c = _get()
    return _send(c.functions.acceptSample(request_id, bytes.fromhex(sample_hash_hex), Web3.to_checksum_address(contributor)))


def purchase_with_sig(dataset_id: int, buyer: str, amount_wei: int, deadline: int, sig_hex: str) -> str:
    from web3 import Web3
    _, c = _get()
    return _send(c.functions.purchaseLicenseWithSig(dataset_id, Web3.to_checksum_address(buyer), amount_wei, deadline,
                                                    bytes.fromhex(sig_hex.removeprefix("0x"))))


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


def credit_and_nonce(addr: str) -> tuple[int, int]:
    from web3 import Web3
    _, c = _get()
    a = Web3.to_checksum_address(addr)
    return c.functions.credit(a).call(), c.functions.nonces(a).call()


def payment_intent_typed_data(dataset_id: int, buyer: str, amount_wei: int, nonce: int, deadline: int) -> dict[str, Any]:
    return {
        "domain": {"name": "Veridata", "version": "1", "chainId": config.CHAIN_ID, "verifyingContract": config.CONTRACT_ADDRESS},
        "types": {"PaymentIntent": [
            {"name": "datasetId", "type": "uint256"}, {"name": "buyer", "type": "address"},
            {"name": "amount", "type": "uint256"}, {"name": "nonce", "type": "uint256"},
            {"name": "deadline", "type": "uint256"}]},
        "primaryType": "PaymentIntent",
        "message": {"datasetId": dataset_id, "buyer": buyer, "amount": str(amount_wei), "nonce": nonce, "deadline": deadline},
    }


def recover_intent_signer(typed: dict[str, Any], sig_hex: str) -> str:
    from eth_account import Account
    from eth_account.messages import encode_typed_data
    msg = dict(typed["message"])
    msg["amount"] = int(msg["amount"])
    full = {"types": {"EIP712Domain": [
        {"name": "name", "type": "string"}, {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"}, {"name": "verifyingContract", "type": "address"}], **typed["types"]},
        "domain": typed["domain"], "primaryType": typed["primaryType"], "message": msg}
    return Account.recover_message(encode_typed_data(full_message=full), signature=sig_hex)
