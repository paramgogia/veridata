"""Fine-tune inside a 0G TEE provider and download the LoRA adapter.

    cd backend && .venv/bin/python scripts/zerog_finetune.py <dataset_id> [--provider ADDR] [--config path]

Flow (all through the zerog_py_sdk broker):
  1. export the licensed dataset as JSONL (description -> label),
  2. upload it to the provider's TEE (upload_dataset_to_tee) -> dataset hash,
  3. create a fine-tuning task (create_task) with a JSON training-params file,
  4. poll until the provider reports a deliverable, then acknowledge the model
     (acknowledge_model) and download the LoRA adapter (download_lora_from_tee),
  5. deployment: scripts/zerog_deploy_agent.py turns the task into a served agent.

Requires the 0G compute ledger: >= 3 0G in the wallet (see app/zerog.py).
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
# Schema learned from the Galileo testnet provider's validator:
# only these keys are allowed and neftune_noise_alpha is required.
DEFAULT_TRAINING_PARAMS = {"neftune_noise_alpha": 5.0, "num_train_epochs": 3,
                           "per_device_train_batch_size": 4, "learning_rate": 0.0001, "max_steps": 20}
POLL_SECONDS = 30


def export_jsonl(dataset_id: int) -> Path:
    db = SessionLocal()
    samples = db.query(Sample).filter(Sample.dataset_id == dataset_id, Sample.label != "").all()
    db.close()
    if not samples:
        raise SystemExit(f"dataset {dataset_id} has no labelled samples")
    out = Path(__file__).resolve().parents[1] / "data" / f"ft_dataset_{dataset_id}.jsonl"
    with out.open("w") as f:
        for s in samples:
            f.write(json.dumps({"prompt": f"Describe this captured scene for a data marketplace: {s.description}",
                                "completion": s.label}) + "\n")
    print(f"exported {len(samples)} samples -> {out}")
    return out


def require_funding(broker, network: str, provider: str) -> None:
    bal = zerog.wallet_balance_0g(network)
    if bal < zerog.MIN_COMPUTE_LEDGER_0G * 10**18:
        raise SystemExit(f"wallet holds {bal / 1e18:.2f} 0G on {network}; the compute ledger needs >= {zerog.MIN_COMPUTE_LEDGER_0G} 0G")
    try:
        detail = broker.ledger.get_ledger_with_detail()
    except Exception:
        detail = None
    if detail is None or int(detail.total_balance) == 0:
        print("creating compute ledger (locks 3 0G)…")
        broker.ledger.add_ledger(str(zerog.MIN_COMPUTE_LEDGER_0G))
        detail = broker.ledger.get_ledger_with_detail()
    print(f"ledger total {int(detail.total_balance) / 1e18:.2f} 0G")
    # Fund the provider's fine-tuning sub-account (1 0G; the provider requires
    # >= 1 0G and the account must exist before create_task).
    try:
        acc = broker.fine_tuning.get_account(provider)
        bal_prov = int(getattr(getattr(acc, "account", acc) or acc, "balance", 0))
    except Exception:
        bal_prov = 0
    if bal_prov == 0:
        print("funding provider sub-account (1 0G)…")
        zerog.fund_provider(provider, "fine-tuning", int(1e18), network)
        print("provider funded")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset_id", type=int)
    ap.add_argument("--provider", default="", help="fine-tuning provider address (default: first listed)")
    ap.add_argument("--config", default="", help="JSON training-params file (default: built-in)")
    ap.add_argument("--network", default="testnet", choices=["testnet", "mainnet"],
                    help="0G network (mainnet needs ~3.1 real 0G in the wallet for ledger + gas)")
    a = ap.parse_args()

    broker = zerog.broker(a.network)

    ft = broker.fine_tuning
    svcs = ft.list_service()
    if not svcs:
        raise SystemExit(f"no fine-tuning providers registered on 0G {a.network}")
    provider = a.provider or svcs[0].provider
    print(f"fine-tuning provider: {provider}")
    require_funding(broker, a.network, provider)

    data = export_jsonl(a.dataset_id)

    if a.config:
        training_path = Path(a.config)
    else:
        training_path = data.with_suffix(".params.json")
        training_path.write_text(json.dumps(DEFAULT_TRAINING_PARAMS))
    print(f"training params: {training_path.read_text().strip()}")

    print("uploading dataset to the provider's TEE…")
    up = ft.upload_dataset_to_tee(provider, str(data))
    print("upload response:", json.dumps(up)[:300])
    dataset_hash = up.get("datasetHash") or up.get("dataset_hash") or up.get("hash") or up.get("root") or up.get("id")
    if not dataset_hash:
        raise SystemExit(f"could not find the dataset hash in the provider response: {list(up)}")

    print(f"creating task: model={BASE_MODEL} dataset_hash={str(dataset_hash)[:20]}…")
    task_id = ft.create_task(provider, BASE_MODEL, str(dataset_hash), str(training_path))
    print("task id:", task_id)

    while True:
        st = ft.get_task(provider, task_id)
        print(f"  progress: {getattr(st, 'progress', None) or 'queued'} · deliver_index: {getattr(st, 'deliver_index', None) or '-'}")
        if getattr(st, "deliver_index", None) or getattr(st, "progress", "") == "Delivered":
            break
        time.sleep(POLL_SECONDS)

    out_dir = Path(__file__).resolve().parents[1] / "data" / "0g_adapters"
    out_dir.mkdir(exist_ok=True)
    print("acknowledging model (downloads the ENCRYPTED artifact)…")
    ft.acknowledge_model(provider, task_id, str(out_dir))
    # Per the official docs: acknowledge-model downloads the model encrypted;
    # once the task shows "Finished" the provider has settled fees and uploaded
    # the decryption key to the contract — decrypt-model unwraps the LoRA zip.
    while True:
        st = ft.get_task(provider, task_id)
        if getattr(st, "progress", "") == "Finished":
            break
        print(f"  waiting for settlement… ({st.progress})")
        time.sleep(POLL_SECONDS)
    enc = out_dir / f"lora_model_{task_id}.zip"
    dec = out_dir / f"adapter_{task_id}_decrypted.zip"
    ft.decrypt_model(provider, task_id, str(enc), str(dec))
    print("adapter decrypted:", dec)
    print(f"\nNext: .venv/bin/python scripts/zerog_deploy_agent.py --task-id {task_id} [--provider {provider}]")


if __name__ == "__main__":
    main()
