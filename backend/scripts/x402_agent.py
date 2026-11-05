"""Autonomous x402 buyer agent: discovers the price via HTTP 402, tops up prepaid credit if
needed, signs an EIP-712 PaymentIntent and retries with X-PAYMENT. No human approval.

    AGENT_PRIVATE_KEY=0x... python scripts/x402_agent.py <dataset_id> [--max-eth 0.01]

The agent wallet needs a little Sepolia ETH (for the one-time depositCredit tx).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path

import httpx
from eth_account import Account
from eth_account.messages import encode_typed_data
from web3 import Web3

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import config  # noqa: E402

API = os.environ.get("VERIDATA_API", "http://localhost:8000")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset_id", type=int)
    ap.add_argument("--max-eth", type=float, default=0.01, help="spend cap per purchase")
    a = ap.parse_args()
    acct = Account.from_key(os.environ["AGENT_PRIVATE_KEY"])
    url = f"{API}/api/x402/datasets/{a.dataset_id}/license"

    r = httpx.get(url, params={"buyer": acct.address}, timeout=30)
    if r.status_code != 402:
        sys.exit(f"expected 402, got {r.status_code}: {r.text}")
    req = r.json()["accepts"][0]
    amount = int(req["maxAmountRequired"])
    print(f"402 Payment Required: {amount / 1e18} ETH for {req['description']}")
    if amount > a.max_eth * 1e18:
        sys.exit(f"refusing: price exceeds spend cap of {a.max_eth} ETH")

    credit = int(req["extra"]["buyerCredit"])
    if credit < amount:
        w3 = Web3(Web3.HTTPProvider(config.CHAIN_RPC_URL))
        abi = json.loads((Path(config.__file__).parent / "chain" / "Veridata.abi.json").read_text())
        c = w3.eth.contract(address=Web3.to_checksum_address(req["payTo"]), abi=abi)
        tx = c.functions.depositCredit().build_transaction({"from": acct.address, "value": amount - credit,
                                                            "nonce": w3.eth.get_transaction_count(acct.address), "chainId": config.CHAIN_ID})
        h = w3.eth.send_raw_transaction(acct.sign_transaction(tx).raw_transaction)
        w3.eth.wait_for_transaction_receipt(h)
        print(f"deposited credit: {config.EXPLORER_URL}/tx/0x{h.hex().removeprefix('0x')}")
        r = httpx.get(url, params={"buyer": acct.address}, timeout=30)
        req = r.json()["accepts"][0]

    typed = req["extra"]["typedData"]
    msg = {**typed["message"], "amount": int(typed["message"]["amount"])}
    full = {"types": {"EIP712Domain": [{"name": "name", "type": "string"}, {"name": "version", "type": "string"},
                                       {"name": "chainId", "type": "uint256"}, {"name": "verifyingContract", "type": "address"}],
                      **typed["types"]}, "domain": typed["domain"], "primaryType": "PaymentIntent", "message": msg}
    sig = acct.sign_message(encode_typed_data(full_message=full)).signature.hex()
    payment = base64.b64encode(json.dumps({"x402Version": 1, "scheme": req["scheme"], "network": req["network"],
                                           "payload": {"typedData": typed, "signature": "0x" + sig.removeprefix("0x")}}).encode()).decode()
    r = httpx.get(url, headers={"X-PAYMENT": payment}, timeout=240)
    print(r.status_code, r.json())
    if "X-PAYMENT-RESPONSE" in r.headers:
        print("settlement:", json.loads(base64.b64decode(r.headers["X-PAYMENT-RESPONSE"])))


if __name__ == "__main__":
    main()
