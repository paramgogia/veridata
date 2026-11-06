"""Software pays software: an AI training agent buys a Veridata dataset license over HTTP 402.

The agent holds only USDT on Whitechain Sepolia: no WBT, no gas, no wallet popup.
It requests the resource, gets 402 + payment requirements, signs one EIP-3009
ReceiveWithAuthorization, retries with X-PAYMENT, and receives the license plus an
access token it uses to pull the signed manifests it just paid for.

    set AGENT_PRIVATE_KEY=0x...   (a wallet that holds test USDT; never commit it)
    python scripts/x402_agent.py 6 --max-usdt 1 --api http://localhost:8000
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys

import httpx
from eth_account import Account
from eth_account.messages import encode_typed_data


def sign_authorization(key: str, accepts: dict) -> dict:
    """Build the x402 `exact` payload for a VeridataPay requirement."""
    acct = Account.from_key(key)
    ex = accepts["extra"]
    auth = {"from": acct.address, "to": accepts["payTo"], "value": int(accepts["maxAmountRequired"]),
            "validAfter": int(ex["validAfter"]), "validBefore": int(ex["validBefore"]), "nonce": ex["nonce"]}
    typed = {
        "types": {
            "EIP712Domain": [{"name": "name", "type": "string"}, {"name": "version", "type": "string"},
                             {"name": "chainId", "type": "uint256"}, {"name": "verifyingContract", "type": "address"}],
            "ReceiveWithAuthorization": [{"name": "from", "type": "address"}, {"name": "to", "type": "address"},
                                         {"name": "value", "type": "uint256"}, {"name": "validAfter", "type": "uint256"},
                                         {"name": "validBefore", "type": "uint256"}, {"name": "nonce", "type": "bytes32"}],
        },
        "primaryType": "ReceiveWithAuthorization",
        "domain": {"name": ex["name"], "version": ex["version"], "chainId": int(accepts["chainId"]), "verifyingContract": accepts["asset"]},
        "message": {**auth, "nonce": bytes.fromhex(auth["nonce"].removeprefix("0x"))},
    }
    sig = acct.sign_message(encode_typed_data(full_message=typed)).signature.hex()
    return {"signature": "0x" + sig.removeprefix("0x"), "salt": ex["salt"],
            "authorization": {k: str(v) for k, v in auth.items()}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset_id", type=int)
    ap.add_argument("--api", default=os.environ.get("VERIDATA_API", "http://localhost:8000"))
    ap.add_argument("--max-usdt", type=float, default=1.0, help="spending cap: refuse to pay more than this")
    a = ap.parse_args()
    key = os.environ.get("AGENT_PRIVATE_KEY")
    if not key:
        print("set AGENT_PRIVATE_KEY to a wallet holding Whitechain test USDT", file=sys.stderr)
        return 2
    url = f"{a.api}/api/x402/datasets/{a.dataset_id}/license"
    print(f"agent {Account.from_key(key).address}\n-> GET {url}")
    with httpx.Client(timeout=180) as http:
        r = http.get(url)
        if r.status_code != 402:
            print(f"expected 402, got {r.status_code}: {r.text[:300]}")
            return 1
        req = r.json()["accepts"][0]
        usdt = int(req["maxAmountRequired"]) / 1e6
        print(f"<- 402 Payment Required: {usdt} USDT on {req['network']} (chain {req['chainId']}) for “{req['description']}”")
        if usdt > a.max_usdt:
            print(f"price {usdt} exceeds the agent's cap {a.max_usdt}; not paying")
            return 1
        payment = {"x402Version": 1, "scheme": "exact", "network": req["network"], "payload": sign_authorization(key, req)}
        print("   signed EIP-3009 ReceiveWithAuthorization (off-chain, 0 gas); retrying with X-PAYMENT …")
        r = http.get(url, headers={"X-PAYMENT": base64.b64encode(json.dumps(payment).encode()).decode()})
        if r.status_code != 200:
            print(f"payment failed {r.status_code}: {r.text[:300]}")
            return 1
        body = r.json()
        p = body["payment"]
        print(f"<- 200 OK: license granted for dataset {body['license']['dataset_id']}")
        print(f"   paid {p['usdt']} USDT  (seller {(p['value'] - p['fee']) / 1e6}, platform fee {p['fee'] / 1e6})")
        print(f"   gas paid by Veridata relayer {p['gas_paid_by']}: {p['gas_cost_wei'] / 1e18:.8f} WBT")
        print(f"   tx {p['explorer']}")
        m = http.get(f"{a.api}{body['manifests_url']}", headers={"Authorization": f"Bearer {body['access_token']}"}).json()
        print(f"   fetched {len(m)} signed capture manifests; first manifest hash {m[0]['manifest_hash'][:16]}…" if m else "   no manifests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
