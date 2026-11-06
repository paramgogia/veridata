"""Buyer-funded data requests: create + escrow, submissions, verification-gated payouts, refunds.

Demo-ledger requests pay out immediately when a sample passes the checks. On-chain requests
mark passing samples as `verified`; the buyer then releases the payouts from their own wallet
(Veridata.releasePayouts), so the platform never holds a private key.

Accepted samples are delivered into a private 'delivery' dataset owned by the buyer
(contributors keep attribution per sample), which the buyer can use in the Training Room."""
from __future__ import annotations

import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import auth, crypto, ledger, provenance
from ..chain import client as chain
from ..config import CHAIN_ID, GWEI
from ..db import DataRequest, Dataset, Sample, Submission, User, audit, get_db
from ..serialize import request_view, sample_view, user_brief

router = APIRouter(prefix="/api")
_submit_lock = threading.Lock()  # serializes acceptance → no double-counting / double payouts


@router.get("/requests")
def list_requests(db: Session = Depends(get_db), status: str = "open", category: str = "", sort: str = "value", mine: bool = False,
                  user: User | None = Depends(auth.optional_user)):
    q = db.query(DataRequest)
    if status != "all":
        q = q.filter(DataRequest.status == status)
    if category:
        q = q.filter(DataRequest.category == category)
    if mine and user:
        q = q.filter(DataRequest.buyer_id == user.id)
    rows = [request_view(db, r) for r in q.all()]
    keys = {"value": lambda r: -r["remaining_escrow"], "deadline": lambda r: r["deadline"], "recent": lambda r: -r["created_at"],
            "progress": lambda r: -r["progress"], "price": lambda r: -r["price_per_sample"]}
    rows.sort(key=keys.get(sort, keys["value"]))
    return rows


@router.get("/requests/recent-fulfilled")
def recent_fulfilled(db: Session = Depends(get_db)):
    subs = db.query(Submission).filter(Submission.status == "accepted").order_by(Submission.id.desc()).limit(8).all()
    out = []
    for s in subs:
        r = db.get(DataRequest, s.request_id)
        out.append({"request_id": r.id, "title": r.title, "contributor": user_brief(db.get(User, s.contributor_id)), "payout": s.payout,
                    "mode": s.mode, "tx_hash": s.tx_hash, "tx_url": chain.explorer_tx(s.tx_hash), "created_at": s.created_at})
    return out


class RequestBody(BaseModel):
    title: str = Field(min_length=4, max_length=200)
    description: str = ""
    category: str
    quantity: int = Field(gt=0, le=100000)
    price_per_sample: int = Field(gt=0)  # gwei
    deadline_days: float = Field(gt=0, le=365)
    media_format: str = "image/jpeg"
    min_resolution: str = "640x480"
    sensors: list[str] = []
    location: str = ""
    conditions: str = ""
    required_metadata: list[str] = []
    require_device_signature: bool = True
    min_quality: float = 50
    labels: list[str] = []


@router.post("/requests")
def create_request(body: RequestBody, request: Request, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    spec = body.model_dump(exclude={"title", "description", "category", "quantity", "price_per_sample", "deadline_days"})
    spec_hash = crypto.sha256_hex(crypto.canonical({"title": body.title, "description": body.description, "category": body.category,
                                                    "quantity": body.quantity, "price_per_sample": body.price_per_sample, **spec}))
    r = DataRequest(buyer_id=user.id, title=body.title, description=body.description[:4000], category=body.category,
                    quantity=body.quantity, price_per_sample=body.price_per_sample, deadline=time.time() + body.deadline_days * 86400,
                    spec=spec, spec_hash=spec_hash, status="pending")
    db.add(r)
    audit(db, user.address, "request.create", "", {"spec_hash": spec_hash}, auth.client_ip(request))
    db.commit()
    return request_view(db, r) | {"price_wei": str(body.price_per_sample * GWEI), "deposit_wei": str(body.price_per_sample * body.quantity * GWEI),
                                  "deadline_unix": int(r.deadline)}


class ConfirmBody(BaseModel):
    tx_hash: str = ""


@router.post("/requests/{rid}/confirm")
def confirm_request(rid: int, body: ConfirmBody, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    r = db.get(DataRequest, rid)
    if not r or r.buyer_id != user.id:
        raise HTTPException(404, "request not found")
    if r.status != "pending":
        raise HTTPException(409, "already funded")
    total = r.price_per_sample * r.quantity
    if body.tx_hash:
        try:
            ev = chain.verify_event(body.tx_hash, "RequestFunded", sender=user.address)
        except chain.ChainError as e:
            raise HTTPException(400, str(e))
        if ev["specHash"].removeprefix("0x") != r.spec_hash or int(ev["deposited"]) != total * GWEI:
            raise HTTPException(400, "on-chain request does not match specification/deposit")
        r.chain_request_id, r.fund_tx, r.mode = int(ev["requestId"]), body.tx_hash, "onchain"
        ledger.record(db, "escrow_deposit", total, frm=user.id, mode="onchain", tx_hash=body.tx_hash, ref=f"request:{r.id}", chain_id=CHAIN_ID)
    else:
        ledger.require_local_funds(db, user.id, total)
        ledger.record(db, "escrow_deposit", total, frm=user.id, ref=f"request:{r.id}", memo="demo ledger escrow")
        r.mode = "local"
    r.deposited = total
    r.status = "open"
    audit(db, user.address, "request.fund", str(r.id), {"mode": r.mode, "tx": body.tx_hash, "amount": total})
    db.commit()
    from .. import arkiv
    arkiv.background(arkiv.write_request, r.id, user.address, r.title, r.category, r.quantity, r.accepted,
                        r.price_per_sample, r.status, r.spec or {}, r.spec_hash,
                        r.chain_request_id, r.fund_tx, r.mode, r.deadline, r.created_at)
    return request_view(db, r)


@router.get("/requests/{rid}")
def get_request(rid: int, db: Session = Depends(get_db)):
    r = db.get(DataRequest, rid)
    if not r:
        raise HTTPException(404, "request not found")
    subs = db.query(Submission).filter(Submission.request_id == rid).order_by(Submission.id.desc()).limit(50).all()
    out = []
    for s in subs:
        smp = db.get(Sample, s.sample_id)
        out.append({"id": s.id, "status": s.status, "reasons": s.reasons, "payout": s.payout, "mode": s.mode, "tx_hash": s.tx_hash,
                    "tx_url": chain.explorer_tx(s.tx_hash), "created_at": s.created_at, "contributor": user_brief(db.get(User, s.contributor_id)),
                    "sample": sample_view(smp) if smp else None})
    delivery = db.query(Dataset).filter(Dataset.status == "delivery", Dataset.title == f"Delivery · request #{rid}").first()
    return request_view(db, r) | {"submissions": out, "delivery_dataset_id": delivery.id if delivery else None}


class SubmitBody(BaseModel):
    sample_ids: list[str]


def _check(db: Session, r: DataRequest, s: Sample, user: User) -> list[str]:
    reasons = []
    spec = r.spec or {}
    if s.owner_id != user.id:
        return ["not your sample"]
    if db.query(Submission).filter(Submission.sample_id == s.id, Submission.status.in_(["accepted", "verified"])).first():
        return ["sample already accepted for a request (duplicate reward claim)"]
    dup = (db.query(Sample).filter(Sample.media_sha256 == s.media_sha256, Sample.id != s.id).all())
    if any(db.query(Submission).filter(Submission.sample_id == d.id, Submission.status.in_(["accepted", "verified"])).first() for d in dup):
        return ["identical media already rewarded (duplicate content hash)"]
    ver = provenance.verify_sample(db, s)
    if spec.get("require_device_signature", True) and not ver["valid"]:
        failed = [x["name"] for x in ver["steps"] if x["ok"] is False]
        reasons.append(f"provenance check failed: {', '.join(failed) or 'unsigned'}")
    if not s.quality:
        reasons.append("run quality & privacy assessment first")
    else:
        if not s.quality.get("approved"):
            reasons += s.quality.get("rejection_reasons", ["rejected by quality checks"])
        if s.quality.get("quality_score", 0) < float(spec.get("min_quality", 0)):
            reasons.append(f"quality {s.quality.get('quality_score')} below required {spec.get('min_quality')}")
    labels = spec.get("labels") or []
    if labels and s.label not in labels:
        reasons.append(f"label must be one of {labels}")
    if s.captured_at < r.created_at - 60:
        reasons.append("captured before the request was created")
    for f in spec.get("required_metadata", []):
        if f == "rfid" and not s.rfid:
            reasons.append("RFID tag association required")
        elif f in ("ir", "temp_c", "humidity_pct") and f not in (s.sensors or {}):
            reasons.append(f"sensor reading '{f}' required")
        elif f == "description" and not s.description:
            reasons.append("description required")
    return reasons


def _delivery_dataset(db: Session, r: DataRequest) -> Dataset:
    title = f"Delivery · request #{r.id}"
    d = db.query(Dataset).filter(Dataset.status == "delivery", Dataset.title == title).first()
    if not d:
        d = Dataset(title=title, description=f"Samples accepted for: {r.title}", owner_id=r.buyer_id, categories=[r.category],
                    status="delivery", mode=r.mode, license="Commissioned data — buyer training rights; contributor attribution retained")
        db.add(d)
        db.flush()
    return d


def _pending(db: Session, r: DataRequest) -> int:
    return db.query(Submission).filter(Submission.request_id == r.id, Submission.status == "verified").count()


def _sample_hash(s: Sample) -> str:
    return s.manifest_hash or s.media_sha256


def _accept(db: Session, r: DataRequest, s: Sample, sub: Submission, contributor: User, tx: str = "") -> int:
    """Bookkeeping for a paid sample: ledger, delivery dataset, counters."""
    fee = ledger.fee(r.price_per_sample)
    payout = r.price_per_sample - fee
    sub.status, sub.payout, sub.tx_hash = "accepted", payout, tx
    r.accepted += 1
    r.released += r.price_per_sample
    ledger.record(db, "payout", payout, to=contributor.id, mode=r.mode, tx_hash=tx, ref=f"request:{r.id}",
                  memo=f"buyer:{r.buyer_id}", chain_id=CHAIN_ID if r.mode == "onchain" else None)
    ledger.record(db, "platform_fee", fee, mode=r.mode, tx_hash=tx, ref=f"request:{r.id}")
    d = _delivery_dataset(db, r)
    s.dataset_id = d.id
    s.status = "published"
    db.flush()
    root, n = provenance.dataset_root(db, d)
    d.content_root, d.sample_count = root, n
    contributor.reputation = round(min(5.0, (contributor.reputation or 0) + 0.02), 2)
    if r.accepted >= r.quantity:
        r.status = "filled"
    return payout


@router.post("/requests/{rid}/submit")
def submit(rid: int, body: SubmitBody, request: Request, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    with _submit_lock:
        r = db.get(DataRequest, rid)
        if not r or r.status != "open":
            raise HTTPException(409, "request is not open")
        if r.buyer_id == user.id:
            raise HTTPException(403, "buyers cannot fulfil their own requests")
        if time.time() > r.deadline:
            raise HTTPException(409, "request has expired")
        results = []
        for sid in body.sample_ids[:50]:
            s = db.get(Sample, sid)
            if not s:
                results.append({"sample_id": sid, "status": "rejected", "reasons": ["not found"]})
                continue
            reasons = _check(db, r, s, user)
            if not reasons and r.accepted + (_pending(db, r) if r.mode == "onchain" else 0) >= r.quantity:
                reasons = ["request already fully filled"]
            sub = Submission(request_id=r.id, sample_id=s.id, contributor_id=user.id, mode=r.mode)
            db.add(sub)
            if reasons:
                sub.status, sub.reasons = "rejected", reasons
                results.append({"sample_id": sid, "status": "rejected", "reasons": reasons})
                continue
            if r.mode == "onchain":
                # passed every check; the buyer releases the ETH from their own wallet
                sub.status, sub.payout = "verified", r.price_per_sample - ledger.fee(r.price_per_sample)
                db.flush()
                results.append({"sample_id": sid, "status": "verified", "payout": sub.payout, "mode": r.mode,
                                "note": "verified; waiting for the buyer to release the payout on-chain"})
                continue
            payout = _accept(db, r, s, sub, user)
            results.append({"sample_id": sid, "status": "accepted", "payout": payout, "tx_hash": "", "tx_url": "", "mode": r.mode})
        audit(db, user.address, "request.submit", str(r.id), {"results": [(x["sample_id"][:8], x["status"]) for x in results]}, auth.client_ip(request))
        db.commit()
        return {"results": results, "request": request_view(db, r)}


@router.get("/requests/{rid}/pending-payouts")
def pending_payouts(rid: int, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    """Verified samples awaiting the buyer's on-chain releasePayouts call (args ready for the wallet)."""
    r = db.get(DataRequest, rid)
    if not r or r.buyer_id != user.id:
        raise HTTPException(404, "request not found")
    subs = db.query(Submission).filter(Submission.request_id == rid, Submission.status == "verified").order_by(Submission.id).limit(50).all()
    items = []
    for sub in subs:
        s, c = db.get(Sample, sub.sample_id), db.get(User, sub.contributor_id)
        items.append({"submission_id": sub.id, "sample_id": s.id, "sample_hash": "0x" + _sample_hash(s),
                      "contributor": c.address, "contributor_name": c.name, "payout": sub.payout})
    return {"chain_request_id": r.chain_request_id, "price_per_sample": r.price_per_sample, "items": items,
            "total": r.price_per_sample * len(items)}


@router.post("/requests/{rid}/confirm-payouts")
def confirm_payouts(rid: int, body: ConfirmBody, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    """Verify the buyer's releasePayouts tx and mark the matching samples accepted."""
    with _submit_lock:
        r = db.get(DataRequest, rid)
        if not r or r.buyer_id != user.id:
            raise HTTPException(404, "request not found")
        if r.mode != "onchain" or not body.tx_hash:
            raise HTTPException(400, "tx_hash of a releasePayouts transaction is required")
        if db.query(Submission).filter(Submission.tx_hash == body.tx_hash).first():
            raise HTTPException(409, "transaction already recorded")
        try:
            events = chain.verify_events(body.tx_hash, "SampleAccepted", sender=user.address)
        except chain.ChainError as e:
            raise HTTPException(400, str(e))
        pending = {(_sample_hash(db.get(Sample, sub.sample_id)) or "").lower(): sub
                   for sub in db.query(Submission).filter(Submission.request_id == rid, Submission.status == "verified").all()}
        done = []
        for ev in events:
            if int(ev["requestId"]) != r.chain_request_id:
                raise HTTPException(400, "transaction pays a different request")
            sub = pending.pop(str(ev["sampleHash"]).removeprefix("0x").lower(), None)
            if not sub:
                continue
            contributor = db.get(User, sub.contributor_id)
            if (contributor.address or "").lower() != str(ev["contributor"]).lower():
                continue
            _accept(db, r, db.get(Sample, sub.sample_id), sub, contributor, body.tx_hash)
            done.append(sub.id)
        audit(db, user.address, "request.release", str(r.id), {"tx": body.tx_hash, "accepted": len(done)})
        db.commit()
        return request_view(db, r) | {"released": len(done), "tx_url": chain.explorer_tx(body.tx_hash)}


@router.post("/requests/{rid}/refund")
def refund(rid: int, body: ConfirmBody, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    r = db.get(DataRequest, rid)
    if not r or r.buyer_id != user.id:
        raise HTTPException(404, "request not found")
    if r.status == "closed":
        raise HTTPException(409, "already closed")
    if time.time() <= r.deadline and r.accepted < r.quantity:
        raise HTTPException(409, "refund is available after the deadline or once the request is filled")
    amount = r.deposited - r.released
    if r.mode == "onchain":
        if not body.tx_hash:
            raise HTTPException(400, "call closeAndRefund on-chain from your wallet, then submit the tx hash")
        try:
            ev = chain.verify_event(body.tx_hash, "RequestClosed", sender=user.address)
        except chain.ChainError as e:
            raise HTTPException(400, str(e))
        if int(ev["requestId"]) != r.chain_request_id:
            raise HTTPException(400, "transaction closes a different request")
    ledger.record(db, "refund", amount, to=user.id, mode=r.mode, tx_hash=body.tx_hash, ref=f"request:{r.id}")
    r.refunded, r.status = amount, "closed"
    audit(db, user.address, "request.refund", str(r.id), {"amount": amount, "tx": body.tx_hash})
    db.commit()
    return request_view(db, r)
