"""Deploy Veridata.sol to Ethereum Sepolia from the wallet in .env.

    cd backend && .venv/bin/python scripts/deploy_contract.py

Constructor: (treasury, uploadFeeWei, platformFeeBps). The wallet that pays
deployment gas is also the treasury. Prints the deployed address and tx link;
copy the address into VERIDATA_CONTRACT_ADDRESS in .env (the script does this
for you unless --no-update-env).
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from app import config

REPO = Path(__file__).resolve().parents[2]
ABI_PATH = REPO / "contracts" / "Veridata.abi.json"
BYTECODE_PATH = REPO / "contracts" / "Veridata.bin"
ENV_PATH = REPO / ".env"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--treasury", default="", help="treasury address (default: the wallet itself)")
    ap.add_argument("--upload-fee-gwei", type=int, default=config.UPLOAD_FEE, help="upload fee in gwei")
    ap.add_argument("--fee-bps", type=int, default=config.PLATFORM_FEE_BPS, help="platform fee in bps")
    ap.add_argument("--no-update-env", action="store_true", help="do not patch VERIDATA_CONTRACT_ADDRESS in .env")
    a = ap.parse_args()

    if not config.WALLET_PRIVATE_KEY:
        raise SystemExit("no wallet key: set WALLET_PRIVATE_KEY (or legacy VERIFIER_PRIVATE_KEY) in .env")
    if not BYTECODE_PATH.exists():
        raise SystemExit("contracts/Veridata.bin missing: compile Veridata.sol in Remix and export the bytecode")

    from eth_account import Account
    from web3 import Web3

    w3 = Web3(Web3.HTTPProvider(config.CHAIN_RPC_URL, request_kwargs={"timeout": 30}))
    if w3.eth.chain_id != config.CHAIN_ID:
        raise SystemExit(f"RPC chain id {w3.eth.chain_id} != expected {config.CHAIN_ID}")

    acct = Account.from_key(config.WALLET_PRIVATE_KEY)
    bal = w3.eth.get_balance(acct.address)
    print(f"wallet: {acct.address}  balance: {w3.from_wei(bal, 'ether')} ETH  (chain {w3.eth.chain_id})")
    if bal == 0:
        raise SystemExit("wallet has no Sepolia ETH for gas")

    abi = json.loads(ABI_PATH.read_text())
    bytecode = BYTECODE_PATH.read_text().strip()
    treasury = a.treasury or acct.address
    print(f"constructor: treasury={treasury} uploadFee={a.upload_fee_gwei * 10**9} wei feeBps={a.fee_bps}")

    c = w3.eth.contract(abi=abi, bytecode=bytecode)
    tx = c.constructor(treasury, a.upload_fee_gwei * 10**9, a.fee_bps).build_transaction({
        "from": acct.address,
        "nonce": w3.eth.get_transaction_count(acct.address),
        "chainId": config.CHAIN_ID,
    })
    signed = acct.sign_transaction(tx)
    h = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"deploy tx: {config.EXPLORER_URL}/tx/0x{h.hex()}")
    rcpt = w3.eth.wait_for_transaction_receipt(h, timeout=300)
    if rcpt.status != 1:
        raise SystemExit("deployment reverted")
    addr = rcpt.contractAddress
    print(f"deployed:  {addr}")
    if a.no_update_env:
        return
    text = ENV_PATH.read_text()
    text = re.sub(r"^VERIDATA_CONTRACT_ADDRESS=.*$", f"VERIDATA_CONTRACT_ADDRESS={addr}", text, flags=re.M)
    ENV_PATH.write_text(text)
    print("updated VERIDATA_CONTRACT_ADDRESS in .env — restart the backend")


if __name__ == "__main__":
    main()
