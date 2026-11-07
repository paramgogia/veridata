"""JSON views of DB rows (never includes keys, storage secrets or plaintext media)."""
from __future__ import annotations

import time
from typing import Any

from sqlalchemy.orm import Session

from .chain.client import explorer_tx
from .db import DataRequest, Dataset, Device, Sample, User


def user_brief(u: User | None) -> dict[str, Any] | None:
    if not u:
        return None
    return {"id": u.id, "address": u.address, "name": u.name, "demo": bool(u.persona), "reputation": u.reputation}


def sample_view(s: Sample, full: bool = False) -> dict[str, Any]:
    d = {
        "id": s.id, "device_id": s.device_id, "captured_at": s.captured_at, "media_sha256": s.media_sha256,
        "media_bytes": s.media_bytes, "width": s.width, "height": s.height, "label": s.label,
        "description": s.description, "keywords": s.keywords, "categories": s.categories, "rfid": s.rfid,
        "sensors": s.sensors, "status": s.status, "dataset_id": s.dataset_id, "sig_mode": s.sig_mode,
        "signed": bool(s.signature), "manifest_hash": s.manifest_hash, "storage_ref": s.storage_ref,
        "storage_0g": {"root_media": s.storage_root_media, "root_manifest": s.storage_root_manifest,
                       "tx": s.storage_tx, "resolve_url": f"/api/zerog/manifest/{s.storage_root_manifest}" if s.storage_root_manifest else None},
        "preview_url": f"/api/previews/{s.preview_file}" if s.preview_file else None, "is_demo": s.is_demo,
        "quality": s.quality, "media_type": s.media_type or "image/jpeg", "duration_s": s.duration_s or 0,
    }
    if full:
        d["manifest"] = s.manifest
        d["signature"] = s.signature
    return d


def _usdt(ds: Dataset) -> float:
    from .chain.whitechain import usdt_price
    return usdt_price(ds.price or 0, ds.price_usdt) / 1e6


def dataset_view(db: Session, ds: Dataset, detail: bool = False) -> dict[str, Any]:
    owner = db.get(User, ds.owner_id)
    d = {
        "id": ds.id, "title": ds.title, "description": ds.description, "owner": user_brief(owner),
        "categories": ds.categories, "tags": ds.tags, "sensor_types": ds.sensor_types, "location": ds.location,
        "price": ds.price, "price_usdt": _usdt(ds), "license": ds.license, "format": ds.format, "content_root": ds.content_root,
        "sample_count": ds.sample_count, "quality_score": ds.quality_score, "chain_dataset_id": ds.chain_dataset_id,
        "publish_tx": ds.publish_tx, "publish_tx_url": explorer_tx(ds.publish_tx), "mode": ds.mode, "status": ds.status,
        "capture_start": ds.capture_start, "capture_end": ds.capture_end, "is_demo": ds.is_demo, "created_at": ds.created_at,
    }
    first = db.query(Sample).filter(Sample.dataset_id == ds.id).order_by(Sample.captured_at).first()
    d["cover_url"] = f"/api/previews/{first.preview_file}" if first and first.preview_file else None
    if detail:
        samples = db.query(Sample).filter(Sample.dataset_id == ds.id).order_by(Sample.captured_at).all()
        d["samples"] = [sample_view(s) for s in samples[:24]]
        devs = sorted({s.device_id for s in samples if s.device_id})
        d["devices"] = [device_view(db.get(Device, x)) for x in devs if db.get(Device, x)]
        labels: dict[str, int] = {}
        for s in samples:
            labels[s.label or "unlabelled"] = labels.get(s.label or "unlabelled", 0) + 1
        d["label_counts"] = labels
        d["signed_count"] = sum(1 for s in samples if s.signature)
        d["sig_modes"] = sorted({s.sig_mode for s in samples})
    return d


def device_view(dev: Device | None) -> dict[str, Any] | None:
    if not dev:
        return None
    from .crypto import key_fingerprint
    return {
        "id": dev.id, "owner_id": dev.owner_id, "name": dev.name, "kind": dev.kind, "sensors": dev.sensors,
        "pubkey": dev.pubkey_hex, "key_fp": key_fingerprint(dev.pubkey_hex), "signing_mode": dev.signing_mode,
        "simulated": dev.simulated, "status": dev.status, "registration_tx": dev.registration_tx,
        "registration_tx_url": explorer_tx(dev.registration_tx), "registration_mode": dev.registration_mode,
        "stream_url": dev.stream_url, "capture_url": dev.capture_url, "control_url": dev.control_url,
        "last_seen": dev.last_seen, "created_at": dev.created_at,
    }


def request_view(db: Session, r: DataRequest) -> dict[str, Any]:
    left = max(0, r.quantity - r.accepted)
    return {
        "id": r.id, "title": r.title, "description": r.description, "category": r.category, "buyer": user_brief(db.get(User, r.buyer_id)),
        "quantity": r.quantity, "accepted": r.accepted, "remaining": left, "price_per_sample": r.price_per_sample,
        "reward_pool": r.price_per_sample * r.quantity, "remaining_escrow": max(0, r.deposited - r.released - r.refunded),
        "deposited": r.deposited, "released": r.released, "refunded": r.refunded,
        "deadline": r.deadline, "days_left": max(0, round((r.deadline - time.time()) / 86400, 1)), "spec": r.spec,
        "spec_hash": r.spec_hash, "chain_request_id": r.chain_request_id, "fund_tx": r.fund_tx, "fund_tx_url": explorer_tx(r.fund_tx),
        "mode": r.mode, "status": r.status, "is_demo": r.is_demo, "created_at": r.created_at,
        "progress": round(r.accepted / r.quantity, 4) if r.quantity else 0,
    }
