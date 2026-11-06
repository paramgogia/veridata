"""Fine-tune inside 0G's TEE and deploy the resulting model as an inference agent.

    cd backend && .venv/bin/python scripts/zerog_finetune.py <dataset_id> [--provider ADDR]

The 0G compute ledger requires >= 3 0G in the wallet (see zerog.py). This script:
  1. exports the licensed dataset as JSONL (description -> label) for the base LLM,
  2. uploads it to the fine-tuning provider's TEE (upload_dataset_to_tee),
  3. creates a fine-tuning task (create_task) and waits for the deliverable,
  4. acknowledges the model (acknowledge_model) and downloads the LoRA adapter,
  5. deploys the adapter as a served agent (inference.deploy_adapter) so the
     fine-tuned model is callable through the same OpenAI-compatible broker.

Only the weights come out — the dataset never leaves the TEE unencrypted.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/
from app import config, zerog  # noqa: E402
from app.db import Dataset, Sample, SessionLocal  # noqa: E402

BASE_MODEL = "Qwen2.5-0.5B-Instruct"


def export_jsonl(dataset_id: int) -> Path:
    db = SessionLocal()
    samples = db.query(Sample).filter(Sample.dataset_id == dataset_id, Sample.label != "").all()
    db.close()
    if not samples:
        raise SystemExit(f"dataset {dataset_id} has no labelled samples")
    out = Path(zerog.__file__).resolve().parent.parent / "data" / f"ft_dataset_{dataset_id}.jsonl"
    with out.open("w") as f:
        for s in samples:
            f.write(json.dumps({"prompt": f"Describe this captured scene for a data marketplace: {s.description}",
                                "completion": s.label}) + "\n")
    print(f"exported {len(samples)} samples -> {out}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset_id", type=int)
    ap.add_argument("--provider", default="", help="fine-tuning provider address (default: first listed)")
    ap.add_argument("--no-deploy", action="store_true", help="stop after downloading the adapter")
    a = ap.parse_args()

    bal = zerog.wallet_balance_0g()
    if bal < zerog.MIN_COMPUTE_LEDGER_0G * 10**18:
        raise SystemExit(f"wallet holds {bal / 1e18:.2f} 0G; the compute ledger needs >= {zerog.MIN_COMPUTE_LEDGER_0G} 0G")

    import zerog_py_sdk as z
    broker = z.create_broker(config.WALLET_PRIVATE_KEY, network="testnet", rpc_url=config.ZEROG_RPC_URL)
    detail = broker.ledger.get_ledger_with_detail()
    if int(detail.total_balance) == 0:
        broker.ledger.add_ledger(str(zerog.MIN_COMPUTE_LEDGER_0G))
        print("ledger created")
    ft = broker.fine_tuning
    svcs = ft.list_service()
    if not svcs:
        raise SystemExit("no fine-tuning providers registered on 0G testnet")
    provider = a.provider or svcs[0].provider
    print(f"fine-tuning provider: {provider} ({[s.model for s in svcs if s.provider == provider] or svcs[0].model})")

    data = export_jsonl(a.dataset_id)
    task = ft.upload_dataset_to_tee(provider, str(data), data.name, len(data.read_text().splitlines()))
    print("dataset in TEE:", task)

    print("creating fine-tuning task (this may take several minutes to settle)…")
    t = ft.create_task(provider, BASE_MODEL, data.name, int(1e18), task)
    print("task id:", t.id)
    while True:
        st = ft.get_task(t.id)
        print(f"  progress: {st.progress or 'queued'} · deliver_index: {st.deliver_index or '-'}")
        if st.deliver_index:
            break
        time.sleep(30)

    ft.acknowledge_model(provider, t.id)
    print("model acknowledged; downloading LoRA adapter…")
    adapter = ft.download_lora_from_tee(provider, t.id)
    print("adapter saved:", adapter)

    if not a.no_deploy:
        out = broker.inference.deploy_adapter(provider, t.id, BASE_MODEL)
        print("adapter deployed:", out)


if __name__ == "__main__":
    main()
