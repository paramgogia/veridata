"""Reproduce the 0G fine-tune -> deploy chain and pinpoint the failing step.

    cd backend && .venv/bin/python scripts/zerog_health.py [--deploy]

Checks each link of the pipeline and prints PASS/FAIL with the exact
command to re-run a step manually. With --deploy it attempts the final
adapter deployment (currently blocked by the provider's serving hosts).

Known-good reference state (task from the live run):
    task     b2bc6dc1-cfa7-4769-ab73-1f57c3ed86ed
    dataset  0x9732301eb9a767d09063e45197dbb4be834fd6db915344aa805385bc536f0ca0
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/
from app import zerog  # noqa: E402

TASK = "b2bc6dc1-cfa7-4769-ab73-1f57c3ed86ed"
BASE_MODEL = "Qwen2.5-0.5B-Instruct"
GREEN, RED, DIM = "\033[32m", "\033[31m", "\033[2m"
END = "\033[0m"

ok = lambda m: print(f"  {GREEN}PASS{END} {m}")
bad = lambda m, hint="": print(f"  {RED}FAIL{END} {m}" + (f"\n    {DIM}fix: {hint}{END}" if hint else ""))
step = lambda n: print(f"\n[{n}]")


def host_up(url: str) -> bool:
    import httpx
    try:
        r = httpx.get(url, timeout=8)
        return True  # any HTTP response means the service is up
    except Exception:
        return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--deploy", action="store_true", help="attempt adapter deployment (step 8)")
    a = ap.parse_args()

    print(f"0G chain health for task {TASK}")

    step("1 wallet + RPC")
    try:
        bal = zerog.wallet_balance_0g("testnet")
        ok(f"wallet {bal / 1e18:.2f} 0G, RPC reachable")
    except Exception as e:
        bad(f"RPC/wallet: {type(e).__name__}", "retry — the public Galileo RPC flaps; run again")

    step("2 compute ledger + provider accounts")
    try:
        b = zerog.broker("testnet")
        det = b.ledger.get_ledger_with_detail()
        ok(f"ledger total {int(det.total_balance) / 1e18:.2f} 0G")
    except Exception as e:
        bad(f"ledger: {str(e)[:120]}", ".venv/bin/python -c \"from app import zerog; zerog.broker().ledger.add_ledger('3')\"")
    svcs = b.fine_tuning.list_service()
    provider = svcs[0].provider if svcs else ""
    if provider:
        for svc_type in ("fine-tuning", "inference"):
            try:
                acc = (b.fine_tuning if svc_type == "fine-tuning" else b.inference).get_account(provider)
                balp = int(getattr(getattr(acc, "account", acc) or acc, "balance", 0))
                ok(f"{svc_type} account funded {balp / 1e18:.2f} 0G" if balp else f"{svc_type} account exists (empty)")
            except Exception:
                bad(f"{svc_type} account missing",
                    f".venv/bin/python -c \"from app import zerog; zerog.fund_provider('{provider}', '{svc_type}', 10**18)\"")
    else:
        bad("no fine-tuning provider registered on-chain", "wait for the provider to re-register")

    step("3 fine-tuning provider host (TEE upload/task API)")
    ft_url = svcs[0].url if svcs else ""
    if ft_url:
        if host_up(ft_url):
            ok(f"{ft_url}")
        else:
            bad(f"{ft_url}", "provider host down — retry later; nothing we can do locally")

    step("4 task status")
    try:
        t = b.fine_tuning.get_task(provider, TASK)
        ok(f"progress: {t.progress}")
    except Exception as e:
        bad(f"get_task: {str(e)[:120]}", "provider host down (step 3) or RPC flap — retry")

    step("5 deliverable acknowledged on-chain")
    try:
        acc = b.fine_tuning.get_account_with_detail(provider)
        d = getattr(acc, "account", acc) or acc
        dl = list(getattr(d, "deliverables", []) or [])
        if dl and getattr(dl[0], "acknowledged", False):
            ok(f"deliverable acknowledged (root 0x{getattr(dl[0], 'model_root_hash', b'').hex()[:16]}…)")
        elif dl:
            bad("deliverable not acknowledged", ".venv/bin/python scripts/zerog_finetune.py 1")
        else:
            bad("no deliverable yet", ".venv/bin/python scripts/zerog_finetune.py 1")
    except Exception as e:
        bad(f"account read: {str(e)[:120]}", "retry — RPC flap")

    step("6 adapter file")
    zips = list(Path("data/0g_adapters").glob("*.zip"))
    if zips:
        ok(f"{zips[0].name} ({zips[0].stat().st_size} bytes)")
    else:
        bad("no adapter zip", ".venv/bin/python scripts/zerog_finetune.py 1  (re-downloads after acknowledge)")

    step("7 serving hosts (deploy target)")
    inf = b.inference.list_service()
    qwen = [s for s in inf if BASE_MODEL in (s.model or "")]
    if not qwen:
        bad("no inference provider serves Qwen2.5-0.5B-Instruct", "wait for the provider to re-register")
    up = [s for s in qwen if host_up(s.url)]
    for s in qwen:
        (ok if s in up else bad)(f"{s.provider[:10]}… {s.url}")
    if qwen and not up:
        print(f"  {RED}>>> FAILING STEP: adapter deployment cannot reach any serving host.{END}")

    step("8 deploy adapter + chat")
    if up:
        try:
            res = b.inference.deploy_adapter(up[0].provider, BASE_MODEL, TASK, wait=True, timeout_seconds=300)
            name = res.adapter_name
            ok(f"deployed adapter: {name}")
            reply = b.inference.chat_with_fine_tuned_model(up[0].provider, name, "Hello, agent!")
            print(f"  chat reply: {str(reply)[:300]}")
        except Exception as e:
            bad(f"deploy: {str(e)[:160]}", "retry later; also check provider sub-account funding (step 2)")
    else:
        bad("skipped — no reachable serving host",
            "the one command to re-run when the provider recovers:\n"
            f"    .venv/bin/python scripts/zerog_deploy_agent.py --task-id {TASK}")


if __name__ == "__main__":
    main()
