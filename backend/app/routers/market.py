"""Dataset marketplace: search, detail/Proof Card, publish (on-chain or demo ledger),
dataset-level verification and license purchase."""
from __future__ import annotations

import base64
import json
import time

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import auth, crypto, ledger, provenance
from ..chain import client as chain
from ..config import CHAIN_ID, GWEI, UPLOAD_FEE
from ..db import Dataset, License, Sample, User, audit, get_db
from ..serialize import dataset_view

router = APIRouter(prefix="/api")


@router.get("/datasets")
def search(db: Session = Depends(get_db), q: str = "", category: str = "", sensor: str = "", location: str = "",
           min_quality: float = 0, verified: bool = False, max_price: int = 0, since: float = 0, until: float = 0,
           sort: str = "recent", limit: int = 60):
    rows = db.query(Dataset).filter(Dataset.status == "listed").all()
    out = []
    for d in rows:
        hay = f"{d.title} {d.description} {' '.join(d.tags or [])} {' '.join(d.categories or [])}".lower()
        if q and not all(w in hay for w in q.lower().split()):
            continue
        if category and category not in (d.categories or []):
            continue
        if sensor and not any(sensor.lower() in s.lower() for s in (d.sensor_types or [])):
            continue
        if location and location.lower() not in (d.location or "").lower():
            continue
        if d.quality_score < min_quality:
            continue
        if verified and d.mode != "onchain" and not d.content_root:
            continue
        if max_price and d.price > max_price:
            continue
        if since and d.capture_end and d.capture_end < since:
            continue
        if until and d.capture_start and d.capture_start > until:
            continue
        out.append(d)
    key = {"price": lambda d: d.price, "quality": lambda d: -d.quality_score, "samples": lambda d: -d.sample_count}.get(sort, lambda d: -d.created_at)
    out.sort(key=key)
    return [dataset_view(db, d) for d in out[:limit]]


@router.get("/datasets/{ds_id}")
def detail(ds_id: int, db: Session = Depends(get_db), user: User | None = Depends(auth.optional_user)):
    d = db.get(Dataset, ds_id)
    if not d:
        raise HTTPException(404, "dataset not found")
    v = dataset_view(db, d, detail=True)
    lic = db.query(License).filter(License.dataset_id == ds_id, License.buyer_id == user.id).first() if user else None
    v["licensed"] = bool(lic) or (user is not None and user.id == d.owner_id)
    v["license_record"] = {"tx_hash": lic.tx_hash, "mode": lic.mode, "via": lic.via, "tx_url": chain.explorer_tx(lic.tx_hash)} if lic else None
    v["buyers"] = db.query(License).filter(License.dataset_id == ds_id).count()
    return v


@router.get("/datasets/{ds_id}/manifests")
def manifests(ds_id: int, db: Session = Depends(get_db)):
    """Public, verifiable manifest bundle (hashes, sensor metadata, signatures — no media)."""
    rows = db.query(Sample).filter(Sample.dataset_id == ds_id).all()
    return [{"sample_id": s.id, "manifest": s.manifest, "manifest_hash": s.manifest_hash, "signature": s.signature,
             "media_sha256": s.media_sha256} for s in rows]


class PublishBody(BaseModel):
    title: str
    description: str = ""
    sample_ids: list[str]
    categories: list[str] = []
    tags: list[str] = []
    location: str = ""
    price: int  # gwei


@router.post("/datasets")
def prepare_publish(body: PublishBody, request: Request, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    if not body.sample_ids:
        raise HTTPException(400, "select at least one sample")
    if body.price < 0:
        raise HTTPException(400, "bad price")
    samples = db.query(Sample).filter(Sample.id.in_(body.sample_ids)).all()
    if len(samples) != len(set(body.sample_ids)):
        raise HTTPException(404, "some samples not found")
    for s in samples:
        if s.owner_id != user.id:
            raise HTTPException(403, "you can only publish your own samples")
        if s.dataset_id:
            raise HTTPException(409, f"sample {s.id[:8]} already published")
        if s.status != "verified":
            raise HTTPException(409, f"sample {s.id[:8]} has not passed quality & privacy verification")
    leaves = [s.manifest_hash or s.media_sha256 for s in samples]
    root = crypto.merkle_root(leaves)
    scores = [s.quality["quality_score"] for s in samples if s.quality]
    d = Dataset(title=body.title[:200], description=body.description[:4000], owner_id=user.id, categories=body.categories,
                tags=body.tags[:20], location=body.location[:120], price=body.price, content_root=root, sample_count=len(samples),
                quality_score=round(sum(scores) / len(scores), 1) if scores else 0, status="pending",
                sensor_types=sorted({k for s in samples for k in (s.sensors or {}).keys()} | ({"rfid"} if any(s.rfid for s in samples) else set()) | {"camera"}),
                capture_start=min(s.captured_at for s in samples), capture_end=max(s.captured_at for s in samples))
    db.add(d)
    db.flush()
    for s in samples:
        s.dataset_id = d.id
    audit(db, user.address, "dataset.prepare", str(d.id), {"root": root}, auth.client_ip(request))
    db.commit()
    storage_ref = f"veridata://datasets/{d.id}/manifests#root={root[:16]}"
    return {"dataset_id": d.id, "content_root": "0x" + root, "storage_ref": storage_ref, "upload_fee": UPLOAD_FEE,
            "price_wei": str(body.price * GWEI)}


class ConfirmBody(BaseModel):
    tx_hash: str = ""


@router.post("/datasets/{ds_id}/confirm")
def confirm_publish(ds_id: int, body: ConfirmBody, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    d = db.get(Dataset, ds_id)
    if not d or d.owner_id != user.id:
        raise HTTPException(404, "dataset not found")
    if d.status != "pending":
        raise HTTPException(409, "already published")
    if body.tx_hash:
        try:
            ev = chain.verify_event(body.tx_hash, "DatasetPublished", sender=user.address)
        except chain.ChainError as e:
            raise HTTPException(400, str(e))
        if ev["contentRoot"].removeprefix("0x") != d.content_root:
            raise HTTPException(400, "on-chain contentRoot does not match dataset")
        d.chain_dataset_id, d.publish_tx, d.mode = int(ev["datasetId"]), body.tx_hash, "onchain"
        ledger.record(db, "upload_fee", UPLOAD_FEE, frm=user.id, mode="onchain", tx_hash=body.tx_hash, ref=f"dataset:{d.id}", chain_id=CHAIN_ID)
    else:
        ledger.require_local_funds(db, user.id, UPLOAD_FEE)
        ledger.record(db, "upload_fee", UPLOAD_FEE, frm=user.id, ref=f"dataset:{d.id}", memo="demo ledger")
        d.mode = "local"
    d.status = "listed"
    for s in db.query(Sample).filter(Sample.dataset_id == d.id).all():
        s.status = "published"
    audit(db, user.address, "dataset.publish", str(d.id), {"mode": d.mode, "tx": body.tx_hash})
    db.commit()
    from .. import arkiv
    arkiv.write_dataset(d.id, user.address, d.title, d.categories or [],
                        d.sensor_types or [], d.location or "", d.quality_score,
                        d.sample_count, d.price, d.content_root,
                        d.chain_dataset_id, d.publish_tx, d.mode, d.status, d.created_at)
    return dataset_view(db, d)


@router.post("/datasets/{ds_id}/verify")
def verify_dataset(ds_id: int, db: Session = Depends(get_db)):
    d = db.get(Dataset, ds_id)
    if not d:
        raise HTTPException(404, "dataset not found")
    samples = db.query(Sample).filter(Sample.dataset_id == ds_id).all()
    results = []
    for s in samples[:40]:
        v = provenance.verify_sample(db, s)
        results.append({"sample_id": s.id, "valid": v["valid"], "failed": [x["name"] for x in v["steps"] if x["ok"] is False]})
    root, n = provenance.dataset_root(db, d)
    steps = [{"name": "merkle_root", "ok": root == d.content_root, "detail": f"recomputed {root[:20]}… over {n} manifests"}]
    from .. import zerog
    if zerog.enabled():
        # Independent of the platform DB: resolve each manifest from 0G storage by
        # its root and re-derive the Merkle root from the resolved bytes.
        leaves_0g: list[str] = []
        missing = 0
        for s in samples[:40]:
            if not s.storage_root_manifest:
                missing += 1
                continue
            try:
                data = zerog.download_bytes(s.storage_root_manifest)
                m2 = json.loads(data)
                if crypto.sha256_hex(crypto.canonical(m2)) == s.manifest_hash:
                    leaves_0g.append(s.manifest_hash)
                else:
                    missing += 1
            except Exception:
                missing += 1
        if leaves_0g and missing == 0:
            root_0g = crypto.merkle_root(leaves_0g)
            steps.append({"name": "zerog_root", "ok": root_0g == d.content_root,
                          "detail": f"Merkle root re-derived from {len(leaves_0g)} manifests resolved from 0G storage: {root_0g[:20]}…"})
        elif leaves_0g:
            steps.append({"name": "zerog_root", "ok": None,
                          "detail": f"{missing}/{len(samples[:40])} manifests have no 0G root (seed/older samples); resolved {len(leaves_0g)}"})
        else:
            steps.append({"name": "zerog_root", "ok": None, "detail": "no 0G-stored manifests in this dataset"})
    if d.mode == "onchain" and d.chain_dataset_id:
        try:
            onc = chain.read_dataset(d.chain_dataset_id)
            steps.append({"name": "onchain_root", "ok": onc["contentRoot"].removeprefix("0x") == root,
                          "detail": f"Veridata.datasets({d.chain_dataset_id}).contentRoot on chain {CHAIN_ID}"})
        except Exception as e:
            steps.append({"name": "onchain_root", "ok": None, "detail": f"chain unreachable: {type(e).__name__}"})
    else:
        steps.append({"name": "onchain_root", "ok": None, "detail": f"not anchored on-chain (mode: {d.mode})"})
    valid_n = sum(1 for r in results if r["valid"])
    steps.append({"name": "samples", "ok": valid_n == len(results), "detail": f"{valid_n}/{len(results)} samples pass integrity + signature checks"})
    return {"valid": all(s["ok"] is not False for s in steps), "steps": steps, "samples": results, "checked_at": time.time()}


class PurchaseBody(BaseModel):
    tx_hash: str = ""


def _grant(db: Session, d: Dataset, buyer: User, mode: str, tx_hash: str = "", via: str = "direct") -> License:
    fee = ledger.fee(d.price)
    lic = License(dataset_id=d.id, buyer_id=buyer.id, price=d.price, tx_hash=tx_hash, mode=mode, via=via)
    db.add(lic)
    ledger.record(db, "purchase", d.price - fee, frm=buyer.id, to=d.owner_id, mode=mode, tx_hash=tx_hash, ref=f"dataset:{d.id}",
                  chain_id=CHAIN_ID if mode == "onchain" else None)
    ledger.record(db, "platform_fee", fee, frm=buyer.id, mode=mode, tx_hash=tx_hash, ref=f"dataset:{d.id}")
    audit(db, buyer.address, "license.purchase", str(d.id), {"mode": mode, "via": via, "tx": tx_hash})
    return lic


@router.post("/datasets/{ds_id}/purchase")
def purchase(ds_id: int, body: PurchaseBody, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    d = db.get(Dataset, ds_id)
    if not d or d.status != "listed":
        raise HTTPException(404, "dataset not available")
    if d.owner_id == user.id:
        raise HTTPException(409, "you own this dataset")
    if db.query(License).filter(License.dataset_id == ds_id, License.buyer_id == user.id).first():
        raise HTTPException(409, "already licensed")
    if body.tx_hash:
        if d.mode != "onchain":
            raise HTTPException(400, "dataset is not listed on-chain")
        try:
            ev = chain.verify_event(body.tx_hash, "LicensePurchased")
        except chain.ChainError as e:
            raise HTTPException(400, str(e))
        if int(ev["datasetId"]) != d.chain_dataset_id or ev["buyer"].lower() != user.address:
            raise HTTPException(400, "transaction is not a license purchase for this dataset by your wallet")
        _grant(db, d, user, "onchain", body.tx_hash)
    else:
        if d.mode == "onchain" and not user.persona:
            raise HTTPException(400, "this dataset is listed on-chain; pay with your wallet")
        ledger.require_local_funds(db, user.id, d.price)
        _grant(db, d, user, "local")
    db.commit()
    return {"ok": True, "dataset_id": ds_id}
