"""Deploy a fine-tuned LoRA adapter as a served 0G agent, then chat with it.

    cd backend && .venv/bin/python scripts/zerog_deploy_agent.py --task-id <id> [--provider ADDR]
                   .venv/bin/python scripts/zerog_deploy_agent.py --list
                   .venv/bin/python scripts/zerog_deploy_agent.py --adapter <name> --prompt "…"

The adapter (created by zerog_finetune.py) is deployed to the provider's TEE
(deploy_adapter, wait=True); the returned adapter_name is what the OpenAI-style
broker uses to serve the fine-tuned model. Requires the funded compute ledger.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/
from app import config, zerog  # noqa: E402

BASE_MODEL = "Qwen2.5-0.5B-Instruct"


def broker(network: str):
    bal = zerog.wallet_balance_0g(network)
    if bal < zerog.MIN_COMPUTE_LEDGER_0G * 10**18:
        raise SystemExit(f"wallet holds {bal / 1e18:.2f} 0G on {network}; the compute ledger needs >= {zerog.MIN_COMPUTE_LEDGER_0G} 0G")
    return zerog.broker(network)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-id", default="", help="fine-tuning task id to deploy")
    ap.add_argument("--provider", default="", help="provider address (default: first listed)")
    ap.add_argument("--list", action="store_true", help="list deployed adapters and exit")
    ap.add_argument("--adapter", default="", help="adapter name for --status / --prompt")
    ap.add_argument("--status", action="store_true", help="show adapter serving status")
    ap.add_argument("--prompt", default="", help="chat message for --adapter")
    ap.add_argument("--network", default="testnet", choices=["testnet", "mainnet"],
                    help="0G network (mainnet needs ~3.1 real 0G in the wallet for ledger + gas)")
    a = ap.parse_args()

    b = broker(a.network)
    inf = b.inference
    if a.list:
        for ad in inf.list_adapters(a.provider):
            print(json.dumps(ad if isinstance(ad, dict) else getattr(ad, "__dict__", str(ad)), default=str))
        return
    if a.adapter and a.status:
        print(json.dumps(inf.get_adapter_status(a.provider, a.adapter), default=str))
        return
    if a.adapter and a.prompt:
        reply = inf.chat_with_fine_tuned_model(a.provider, a.adapter, a.prompt)
        print(json.dumps(reply, default=str, indent=2))
        return

    if not a.task_id:
        raise SystemExit("need --task-id (or use --list / --adapter)")
    svcs = b.fine_tuning.list_service()
    provider = a.provider or (svcs[0].provider if svcs else "")
    if not provider:
        raise SystemExit("no fine-tuning provider registered")
    # The serving side needs its own funded sub-account (>= 1 0G).
    try:
        acc = b.inference.get_account(provider)
        funded = int(getattr(getattr(acc, "account", acc) or acc, "balance", 0)) > 0
    except Exception:
        funded = False
    if not funded:
        print("funding inference sub-account (1 0G)…")
        zerog.fund_provider(provider, "inference", int(1e18), a.network)
    print(f"deploying task {a.task_id} on {BASE_MODEL} via provider {provider}…")
    res = inf.deploy_adapter(provider, BASE_MODEL, a.task_id, wait=True, timeout_seconds=600)
    name = res.adapter_name
    print(f"deployed adapter: {name}")
    print("status:", json.dumps(inf.get_adapter_status(provider, name), default=str))
    print(f"\nChat with it: .venv/bin/python scripts/zerog_deploy_agent.py --provider {provider} --adapter {name} --prompt \"…\"")


if __name__ == "__main__":
    main()
