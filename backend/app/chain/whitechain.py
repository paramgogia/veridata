"""Whitechain Sepolia (chain 1874): gasless USDT checkout for dataset licenses.

The buyer, a person in the browser or an AI agent over HTTP 402, holds only USDT and signs
one EIP-3009 `ReceiveWithAuthorization` (an EIP-712 message, which costs no gas). Veridata's relayer
submits it to VeridataPay.purchase(), pays the WBT gas, and the contract splits the USDT
between seller and treasury in the same transaction.

Drain protection: the relayer only ever calls one function of one contract. It verifies the
signature off-chain, checks price, expiry, balance and nonce, simulates the call, caps the gas
price and gas limit, rate-limits per buyer and per day, and pauses below a minimum balance.
"""
from __future__ import annotations

import json
import secrets
import threading
import time
from pathlib import Path
from typing import Any

from .. import config

ABI = json.loads((Path(__file__).parent / "VeridataPay.abi.json").read_text())
USDT_ABI = [
    {"name": "balanceOf", "type": "function", "stateMutability": "view", "inputs": [{"name": "a", "type": "address"}], "outputs": [{"type": "uint256"}]},
    {"name": "authorizationState", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "a", "type": "address"}, {"name": "n", "type": "bytes32"}], "outputs": [{"type": "bool"}]},
]
NETWORK = "whitechain-sepolia"
_lock = threading.Lock()
_w3 = None


class PayError(Exception):
    def __init__(self, msg: str, status: int = 400):
        super().__init__(msg)
        self.status = status


def enabled() -> bool:
    return bool(config.WC_PAY_ADDRESS and config.WC_RELAYER_KEY)


def _web3():
    global _w3
    if _w3 is None:
        from web3 import Web3
        _w3 = Web3(Web3.HTTPProvider(config.WC_RPC_URL, request_kwargs={"timeout": 20}))
    return _w3


def _contracts():
    from web3 import Web3
    w3 = _web3()
    pay = w3.eth.contract(address=Web3.to_checksum_address(config.WC_PAY_ADDRESS), abi=ABI)
    usdt = w3.eth.contract(address=Web3.to_checksum_address(config.WC_USDT), abi=USDT_ABI)
    return w3, pay, usdt


def relayer_address() -> str:
    if not config.WC_RELAYER_KEY:
        return ""
    from eth_account import Account
    return Account.from_key(config.WC_RELAYER_KEY).address


def explorer_tx(h: str) -> str:
    return f"{config.WC_EXPLORER}/tx/{h}" if h and h.startswith("0x") else ""


def explorer_addr(a: str) -> str:
    return f"{config.WC_EXPLORER}/address/{a}" if a else ""


def usdt_price(price_gwei: int, price_usdt: int | None = None) -> int:
    """Dataset price in USDT base units (6 decimals)."""
    if price_usdt:
        return int(price_usdt)
    return max(1, round(price_gwei / 1e9 * config.WC_USDT_PER_ETH * 1e6))


def purchase_nonce(dataset_id: int, seller: str, salt: str) -> str:
    """Mirror of VeridataPay.purchaseNonce, computed locally."""
    from eth_abi import encode
    from web3 import Web3
    raw = encode(["uint256", "address", "uint256", "address", "bytes32"],
                 [config.WC_CHAIN_ID, Web3.to_checksum_address(config.WC_PAY_ADDRESS), dataset_id,
                  Web3.to_checksum_address(seller), bytes.fromhex(salt.removeprefix("0x"))])
    return "0x" + Web3.keccak(raw).hex().removeprefix("0x")


def typed_data(buyer: str, value: int, valid_after: int, valid_before: int, nonce: str) -> dict[str, Any]:
    from web3 import Web3
    return {
        "types": {
            "EIP712Domain": [{"name": "name", "type": "string"}, {"name": "version", "type": "string"},
                             {"name": "chainId", "type": "uint256"}, {"name": "verifyingContract", "type": "address"}],
            "ReceiveWithAuthorization": [{"name": "from", "type": "address"}, {"name": "to", "type": "address"},
                                         {"name": "value", "type": "uint256"}, {"name": "validAfter", "type": "uint256"},
                                         {"name": "validBefore", "type": "uint256"}, {"name": "nonce", "type": "bytes32"}],
        },
        "primaryType": "ReceiveWithAuthorization",
        "domain": {"name": config.WC_USDT_NAME, "version": config.WC_USDT_VERSION, "chainId": config.WC_CHAIN_ID,
                   "verifyingContract": Web3.to_checksum_address(config.WC_USDT)},
        "message": {"from": Web3.to_checksum_address(buyer) if buyer else "", "to": Web3.to_checksum_address(config.WC_PAY_ADDRESS),
                    "value": str(value), "validAfter": str(valid_after), "validBefore": str(valid_before), "nonce": nonce},
    }


def requirements(dataset_id: int, seller: str, value: int, resource: str, title: str) -> dict[str, Any]:
    """x402 `accepts` entry: everything a payer needs to build the signature."""
    if not enabled():
        raise PayError("Whitechain checkout not configured (WHITECHAIN_PAY_ADDRESS / relayer key)", 503)
    salt = "0x" + secrets.token_hex(32)
    now = int(time.time())
    return {
        "scheme": "exact", "network": NETWORK, "chainId": config.WC_CHAIN_ID,
        "maxAmountRequired": str(value), "asset": config.WC_USDT, "payTo": config.WC_PAY_ADDRESS,
        "resource": resource, "description": f"Training license: {title}"[:200], "mimeType": "application/json",
        "maxTimeoutSeconds": 600,
        "extra": {
            "name": config.WC_USDT_NAME, "version": config.WC_USDT_VERSION, "decimals": 6, "symbol": "USDT",
            "primaryType": "ReceiveWithAuthorization", "datasetId": dataset_id, "seller": seller, "salt": salt,
            "nonce": purchase_nonce(dataset_id, seller, salt), "validAfter": "0", "validBefore": str(now + 600),
            "gas": "paid by Veridata relayer (WBT)",
        },
    }


def _split_sig(sig: str) -> tuple[int, bytes, bytes]:
    b = bytes.fromhex(sig.removeprefix("0x"))
    if len(b) != 65:
        raise PayError("signature must be 65 bytes")
    v = b[64] if b[64] >= 27 else b[64] + 27
    return v, b[:32], b[32:64]


def _guards(db, buyer: str) -> None:
    from ..db import WcPayment
    now = time.time()
    if db.query(WcPayment).filter(WcPayment.created_at > now - 86400).count() >= config.WC_DAILY_TX_CAP:
        raise PayError("relayer daily budget reached; try again tomorrow", 429)
    if db.query(WcPayment).filter(WcPayment.buyer == buyer.lower(), WcPayment.created_at > now - 3600).count() >= config.WC_PER_BUYER_HOURLY:
        raise PayError("too many purchases from this wallet in the last hour", 429)


def settle(db, *, dataset_id: int, seller: str, expected_value: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Verify an x402 `exact` payload and relay it on-chain. Returns the decoded receipt."""
    from eth_account import Account
    from eth_account.messages import encode_typed_data
    from web3 import Web3

    if not enabled():
        raise PayError("Whitechain checkout not configured", 503)
    try:
        auth = payload["authorization"]
        sig, salt = payload["signature"], payload["salt"]
        buyer = Web3.to_checksum_address(auth["from"])
        value, va, vb = int(auth["value"]), int(auth["validAfter"]), int(auth["validBefore"])
        nonce = auth["nonce"].lower()
    except (KeyError, ValueError, TypeError) as e:
        raise PayError(f"malformed payment payload: {e}")

    # 1. The authorization must be exactly this purchase.
    if auth.get("to", "").lower() != config.WC_PAY_ADDRESS.lower():
        raise PayError("authorization must pay the VeridataPay contract")
    if value != expected_value:
        raise PayError(f"amount must equal the price ({expected_value} USDT units)")
    if nonce != purchase_nonce(dataset_id, seller, salt).lower():
        raise PayError("nonce does not commit to this dataset and seller")
    now = int(time.time())
    if vb < now + 30 or vb > now + 3600 or va > now:
        raise PayError("authorization expired or outside the allowed window")
    if buyer.lower() == seller.lower():
        raise PayError("seller cannot buy their own dataset")

    # 2. Signature check off-chain: never spend gas on a forged or mistyped signature.
    td = typed_data(buyer, value, va, vb, nonce)
    msg = {**td, "message": {**td["message"], "value": value, "validAfter": va, "validBefore": vb,
                             "nonce": bytes.fromhex(nonce.removeprefix("0x"))}}
    try:
        signer = Account.recover_message(encode_typed_data(full_message=msg), signature=sig)
    except Exception:
        raise PayError("invalid signature")
    if signer.lower() != buyer.lower():
        raise PayError("signature was not made by the paying wallet")
    v, r, s = _split_sig(sig)

    _guards(db, buyer)
    w3, pay, usdt = _contracts()
    relayer = Account.from_key(config.WC_RELAYER_KEY)

    # 3. On-chain preconditions.
    if pay.functions.hasLicense(dataset_id, buyer).call():
        raise PayError("this wallet already holds a license for the dataset", 409)
    if usdt.functions.balanceOf(buyer).call() < value:
        raise PayError("insufficient USDT balance", 402)
    try:
        if usdt.functions.authorizationState(buyer, bytes.fromhex(nonce[2:])).call():
            raise PayError("authorization already used", 409)
    except PayError:
        raise
    except Exception:
        pass  # older tokens may lack authorizationState; simulation below still catches reuse
    bal = w3.eth.get_balance(relayer.address)
    if bal < config.WC_MIN_RELAYER_WBT * 10**18:
        raise PayError("relayer paused: gas balance below the safety floor", 503)
    gas_price = w3.eth.gas_price
    if gas_price > config.WC_MAX_GAS_GWEI * 10**9:
        raise PayError("network gas price above the relayer cap; retry shortly", 503)

    fn = pay.functions.purchase(dataset_id, Web3.to_checksum_address(seller), buyer, value, va, vb,
                                bytes.fromhex(salt.removeprefix("0x")), v, r, s)
    # 4. Simulate; a revert here costs nothing.
    try:
        fn.call({"from": relayer.address})
        est = fn.estimate_gas({"from": relayer.address})
    except Exception as e:
        raise PayError(f"payment would revert: {str(e)[:160]}")
    gas = min(int(est * 1.25), config.WC_GAS_LIMIT)
    if est > config.WC_GAS_LIMIT:
        raise PayError("gas estimate above the relayer cap", 503)

    # 5. Send (serialised so relayer nonces never collide).
    with _lock:
        tx = fn.build_transaction({"from": relayer.address, "nonce": w3.eth.get_transaction_count(relayer.address, "pending"),
                                   "gas": gas, "gasPrice": gas_price, "chainId": config.WC_CHAIN_ID})
        signed = relayer.sign_transaction(tx)
        h = w3.eth.send_raw_transaction(signed.raw_transaction)
    rcpt = w3.eth.wait_for_transaction_receipt(h, timeout=120)
    tx_hash = "0x" + h.hex().removeprefix("0x")
    if rcpt.status != 1:
        raise PayError(f"transaction reverted: {tx_hash}", 502)
    from web3.logs import DISCARD
    ev = pay.events.LicensePurchased().process_receipt(rcpt, errors=DISCARD)
    fee = int(ev[0]["args"]["platformFee"]) if ev else 0
    gas_cost = int(rcpt.gasUsed) * int(rcpt.get("effectiveGasPrice", gas_price))
    return {"tx_hash": tx_hash, "buyer": buyer.lower(), "seller": seller.lower(), "value": value, "fee": fee,
            "gas_used": int(rcpt.gasUsed), "gas_cost_wei": gas_cost, "block": int(rcpt.blockNumber),
            "explorer": explorer_tx(tx_hash)}


def status() -> dict[str, Any]:
    out: dict[str, Any] = {
        "enabled": enabled(), "chainId": config.WC_CHAIN_ID, "network": NETWORK, "rpc": config.WC_RPC_URL,
        "explorer": config.WC_EXPLORER, "contract": config.WC_PAY_ADDRESS, "usdt": config.WC_USDT,
        "relayer": relayer_address(), "usdtPerEth": config.WC_USDT_PER_ETH,
        "guards": {"maxGasGwei": config.WC_MAX_GAS_GWEI, "gasLimit": config.WC_GAS_LIMIT, "dailyTxCap": config.WC_DAILY_TX_CAP,
                   "perBuyerHourly": config.WC_PER_BUYER_HOURLY, "minRelayerWbt": config.WC_MIN_RELAYER_WBT},
    }
    if not config.WC_PAY_ADDRESS:
        return out
    try:
        w3, pay, usdt = _contracts()
        out["relayerWbt"] = w3.eth.get_balance(out["relayer"]) / 1e18 if out["relayer"] else 0
        out["treasury"] = pay.functions.treasury().call()
        out["feeBps"] = pay.functions.feeBps().call()
        out["treasuryUsdt"] = usdt.functions.balanceOf(out["treasury"]).call()
        out["gasPriceGwei"] = w3.eth.gas_price / 1e9
        out["reachable"] = True
    except Exception as e:  # network dependent
        out["reachable"] = False
        out["error"] = str(e)[:200]
    return out
