"""Arkiv DB-chain integration: write marketplace entities to the decentralised database.

Reads go through the frontend (Next.js) using @arkiv-network/sdk publicClient.
Writes go through this module — the backend spawns the Node.js writer script
with the platform wallet to create/patch entities on Arkiv's Rabdi testnet.

If Arkiv is not configured (no ARKIV_ACCESS_KEY), all write calls degrade
gracefully — they log and return without blocking the request.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
from pathlib import Path
from typing import Any

from . import config

log = logging.getLogger("arkiv")
WRITER = Path(__file__).resolve().parent.parent / "arkiv" / "writer.mjs"
_installed = False
_install_lock = threading.Lock()


def enabled() -> bool:
    return bool(config.ARKIV_ACCESS_KEY and config.ARKIV_PRIVATE_KEY)


def _ensure_installed() -> None:
    global _installed
    if _installed:
        return
    with _install_lock:
        if _installed:
            return
        pkg_dir = WRITER.parent
        if not (pkg_dir / "node_modules").exists():
            log.info("arkiv: installing Node.js dependencies…")
            subprocess.run(["npm", "install"], cwd=str(pkg_dir),
                           capture_output=True, timeout=120, shell=True)
        _installed = True


def _call(payload: dict[str, Any]) -> dict[str, Any]:
    """Call the Node.js writer script and return the parsed result."""
    if not enabled():
        return {"ok": False, "error": "arkiv not configured"}
    _ensure_installed()
    env = {
        **os.environ,
        "ARKIV_ACCESS_KEY": config.ARKIV_ACCESS_KEY,
        "ARKIV_PRIVATE_KEY": config.ARKIV_PRIVATE_KEY,
    }
    try:
        proc = subprocess.run(
            ["node", str(WRITER)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
        if proc.returncode != 0:
            log.warning("arkiv writer error: %s", proc.stderr[:500])
            return {"ok": False, "error": proc.stderr[:500]}
        return json.loads(proc.stdout.strip())
    except Exception as e:
        log.warning("arkiv call failed: %s", e)
        return {"ok": False, "error": str(e)}


def background(fn, *args, **kwargs) -> None:
    """Fire-and-forget for API handlers: Arkiv latency or outages never delay a request.
    The local DB write has already been committed; Arkiv is a best-effort public index."""
    if not enabled():
        return

    def run() -> None:
        try:
            fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            log.warning("arkiv background write failed: %s", e)

    threading.Thread(target=run, daemon=True).start()


def create_entity(schema: str, data: dict[str, Any],
                   expiry_days: int | None = None,
                   expiry_date: float | None = None) -> dict[str, Any]:
    """Create a new entity on Arkiv. Non-blocking on failure."""
    return _call({
        "op": "create",
        "schema": schema,
        "data": data,
        "expiry_days": expiry_days,
        "expiry_date": expiry_date,
    })


def patch_entity(schema: str, entity_key: str,
                  data: dict[str, Any]) -> dict[str, Any]:
    """Update fields on an existing Arkiv entity. Non-blocking on failure."""
    return _call({
        "op": "patch",
        "schema": schema,
        "entity_key": entity_key,
        "data": data,
    })


def write_contributor(address: str, name: str, bio: str, roles: list[str],
                       reputation: float, sample_count: int, created_at: float) -> dict[str, Any]:
    return create_entity("contributor", {
        "wallet": address,
        "name": name[:120],
        "bio": bio[:500],
        "roles": ",".join(roles) if isinstance(roles, list) else str(roles),
        "reputation": round(reputation, 2),
        "sample_count": sample_count,
        "created_at": created_at,
    })


def write_device(device_id: str, owner_address: str, name: str, kind: str,
                  pubkey_hex: str, signing_mode: str, registration_tx: str,
                  registration_mode: str, status: str, created_at: float) -> dict[str, Any]:
    return create_entity("device", {
        "device_id": device_id,
        "owner_wallet": owner_address,
        "name": name[:120],
        "kind": kind,
        "pubkey_hex": pubkey_hex or "",
        "signing_mode": signing_mode or "",
        "registration_tx": registration_tx or "",
        "registration_mode": registration_mode,
        "status": status,
        "created_at": created_at,
    })


def write_request(request_id: int, buyer_address: str, title: str, category: str,
                   quantity: int, accepted: int, price_per_sample: int,
                   status: str, spec: dict, spec_hash: str, chain_request_id: int | None,
                   fund_tx: str, mode: str, deadline: float, created_at: float) -> dict[str, Any]:
    return create_entity("request", {
        "request_id": request_id,
        "buyer_wallet": buyer_address,
        "title": title[:200],
        "category": category,
        "quantity": quantity,
        "accepted": accepted,
        "price_per_sample": price_per_sample,
        "total_escrow": price_per_sample * quantity,
        "remaining_escrow": price_per_sample * quantity,
        "status": status,
        "require_device_sig": "true" if spec.get("require_device_signature", True) else "false",
        "min_quality": spec.get("min_quality", 0),
        "sensors": ",".join(spec.get("sensors", [])),
        "spec_hash": spec_hash or "",
        "chain_request_id": chain_request_id or 0,
        "fund_tx": fund_tx or "",
        "mode": mode,
        "created_at": created_at,
    }, expiry_date=deadline)


def write_sample(sample_id: str, contributor_address: str, device_id: str,
                  media_sha256: str, manifest_hash: str, storage_root_media: str,
                  storage_root_manifest: str, quality_score: float, status: str,
                  label: str, categories: list[str], sensors: dict,
                  sig_mode: str, captured_at: float, dataset_id: int | None) -> dict[str, Any]:
    return create_entity("sample", {
        "sample_id": sample_id,
        "contributor_wallet": contributor_address,
        "device_id": device_id or "",
        "media_sha256": media_sha256 or "",
        "manifest_hash": manifest_hash or "",
        "storage_root_media": storage_root_media or "",
        "storage_root_manifest": storage_root_manifest or "",
        "quality_score": round(quality_score, 1) if quality_score else 0,
        "status": status,
        "label": label or "",
        "categories": ",".join(categories) if isinstance(categories, list) else "",
        "sensors": ",".join(sorted(sensors.keys())) if isinstance(sensors, dict) else "",
        "sig_mode": sig_mode or "none",
        "captured_at": captured_at or 0,
        "dataset_id": dataset_id or 0,
    })


def write_dataset(dataset_id: int, owner_address: str, title: str, categories: list[str],
                   sensor_types: list[str], location: str, quality_score: float,
                   sample_count: int, price: int, content_root: str,
                   chain_dataset_id: int | None, publish_tx: str, mode: str,
                   status: str, created_at: float) -> dict[str, Any]:
    return create_entity("dataset", {
        "dataset_id": dataset_id,
        "owner_wallet": owner_address,
        "title": title[:200],
        "categories": ",".join(categories) if isinstance(categories, list) else "",
        "sensor_types": ",".join(sensor_types) if isinstance(sensor_types, list) else "",
        "location": location or "",
        "quality_score": round(quality_score, 1),
        "sample_count": sample_count,
        "price": price,
        "content_root": content_root or "",
        "chain_dataset_id": chain_dataset_id or 0,
        "publish_tx": publish_tx or "",
        "mode": mode,
        "status": status,
        "created_at": created_at,
    })


def write_submission(submission_id: int, request_id: int, sample_id: str,
                      contributor_address: str, status: str, payout: int,
                      mode: str, deadline: float, created_at: float) -> dict[str, Any]:
    return create_entity("submission", {
        "submission_id": submission_id,
        "request_id": request_id,
        "sample_id": sample_id,
        "contributor_wallet": contributor_address,
        "status": status,
        "payout": payout,
        "mode": mode,
        "created_at": created_at,
    }, expiry_date=deadline)


def write_audit(actor: str, action: str, target: str = "",
                 mode: str = "", created_at: float = 0) -> dict[str, Any]:
    import time
    return create_entity("audit_event", {
        "actor": actor if actor.startswith("0x") else "0x0000000000000000000000000000000000000000",
        "action": action,
        "target": target or "",
        "mode": mode,
        "created_at": created_at or time.time(),
    }, expiry_days=90)
