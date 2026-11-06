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


def broker():
    import zerog_py_sdk as z
    bal = zerog.wallet_balance_0g()
    if bal < zerog.MIN_COMPUTE_LEDGER_0G * 10**18:
        raise SystemExit(f"wallet holds {bal / 1e18:.2f} 0G; the compute ledger needs >= {zerog.MIN_COMPUTE_LEDGER_0G} 0G")
    return z.create_broker(config.WALLET_PRIVATE_KEY, network="testnet", rpc_url=config.ZEROG_RPC_URL)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-id", default="", help="fine-tuning task id to deploy")
    ap.add_argument("--provider", default="", help="provider address (default: first listed)")
    ap.add_argument("--list", action="store_true", help="list deployed adapters and exit")
    ap.add_argument("--adapter", default="", help="adapter name for --status / --prompt")
    ap.add_argument("--status", action="store_true", help="show adapter serving status")
    ap.add_argument("--prompt", default="", help="chat message for --adapter")
    a = ap.parse_args()

    b = broker()
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
    print(f"deploying task {a.task_id} on {BASE_MODEL} via provider {provider}…")
    res = inf.deploy_adapter(provider, BASE_MODEL, a.task_id, wait=True, timeout_seconds=600)
    name = res.adapter_name
    print(f"deployed adapter: {name}")
    print("status:", json.dumps(inf.get_adapter_status(provider, name), default=str))
    print(f"\nChat with it: .venv/bin/python scripts/zerog_deploy_agent.py --provider {provider} --adapter {name} --prompt \"…\"")


if __name__ == "__main__":
    main()
