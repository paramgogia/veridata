"""Auth, profile, dashboard, platform stats, config, transactions, audit."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import auth, ledger
from ..chain import client as chain
from .. import config
from ..config import CHAIN_ID, EXPLORER_URL, PLATFORM_FEE_BPS, UPLOAD_FEE
from ..db import (AuditEvent, DataRequest, Dataset, Device, License, Sample, Submission, TrainingRun, Tx, User, audit, get_db)
from ..serialize import dataset_view, device_view, request_view, user_brief

router = APIRouter(prefix="/api")

DEMO_PERSONAS = {
    "contributor": {"name": "Asha Farms Collective", "bio": "Smallholder farmers' co-op in Ratnagiri capturing crop data with ESP32 rigs.",
                    "address": "0xa5ba000000000000000000000000000000c0ffee"},
    "buyer": {"name": "Northwind Robotics", "bio": "Perception team building retail and agri vision models.",
              "address": "0xb0b0000000000000000000000000000000beef01"},
}


class VerifyBody(BaseModel):
    address: str
    signature: str


@router.get("/auth/nonce")
def nonce(address: str, db: Session = Depends(get_db)):
    if not (address.startswith("0x") and len(address) == 42):
        raise HTTPException(400, "bad address")
    return {"message": auth.issue_nonce(db, address)}


@router.post("/auth/verify")
def verify(body: VerifyBody, request: Request, db: Session = Depends(get_db)):
    user = auth.verify_login(db, body.address, body.signature)
    audit(db, user.address, "login", "wallet", ip=auth.client_ip(request))
    db.commit()
    return {"token": auth.make_token(user.id), "user": me_view(db, user)}


def ensure_persona(db: Session, persona: str) -> User:
    p = DEMO_PERSONAS[persona]
    u = db.query(User).filter(User.address == p["address"]).first()
    if not u:
        u = User(address=p["address"], name=p["name"], bio=p["bio"], persona=persona,
                 roles=["contributor", "buyer"], reputation=4.6 if persona == "contributor" else 4.2)
        db.add(u)
        db.flush()
        ledger.record(db, "faucet", ledger.DEMO_FAUCET, to=u.id, memo="demo-ledger starting balance")
        db.commit()
    return u


@router.post("/auth/demo")
def demo_login(persona: str, db: Session = Depends(get_db)):
    if persona not in DEMO_PERSONAS:
        raise HTTPException(400, "unknown persona")
    u = ensure_persona(db, persona)
    return {"token": auth.make_token(u.id), "user": me_view(db, u)}


def me_view(db: Session, u: User) -> dict:
    return {**user_brief(u), "bio": u.bio, "roles": u.roles, "persona": u.persona, "created_at": u.created_at,
            "balances": ledger.summary(db, u.id)}


@router.get("/me")
def me(user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    return me_view(db, user)


class ProfileBody(BaseModel):
    name: str | None = None
    bio: str | None = None
    roles: list[str] | None = None


@router.patch("/me")
def update_me(body: ProfileBody, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    if body.name is not None:
        user.name = body.name[:120]
    if body.bio is not None:
        user.bio = body.bio[:1000]
    if body.roles is not None:
        user.roles = [r for r in body.roles if r in ("contributor", "buyer")] or ["contributor"]
    db.commit()
    from .. import arkiv
    sample_count = db.query(Sample).filter(Sample.owner_id == user.id).count()
    arkiv.write_contributor(user.address, user.name, user.bio, user.roles or [],
                            user.reputation or 0.0, sample_count, user.created_at)
    return me_view(db, user)


@router.post("/me/faucet")
def faucet(user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    ledger.record(db, "faucet", ledger.DEMO_FAUCET, to=user.id, memo="demo-ledger top-up (no real value)")
    db.commit()
    return me_view(db, user)


@router.get("/config")
def config_view():
    from .. import zerog, arkiv
    return {"chain": chain.status(), "chainId": CHAIN_ID, "explorer": EXPLORER_URL, "uploadFee": UPLOAD_FEE,
            "platformFeeBps": PLATFORM_FEE_BPS, "units": "gwei",
            "zerog": {"storage": zerog.enabled(), "compute": zerog.compute_status(), "explorer": config.ZEROG_EXPLORER},
            "arkiv": {"enabled": arkiv.enabled(), "rpc": config.ARKIV_RPC_URL}}


@router.get("/zerog/ft")
def zerog_ft_status():
    """Live status of the 0G TEE fine-tuning pipeline: funding + provider tasks."""
    from .. import zerog
    return zerog.ft_status()


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    q = db.query
    earnings = int(q(func.coalesce(func.sum(Tx.amount), 0)).filter(Tx.kind.in_(["payout", "purchase"])).scalar())
    cats: dict[str, int] = {}
    for r in q(DataRequest).filter(DataRequest.status == "open").all():
        cats[r.category] = cats.get(r.category, 0) + (r.quantity - r.accepted)
    return {
        "contributor_earnings": earnings,
        "verified_datasets": q(Dataset).filter(Dataset.status == "listed").count(),
        "active_devices": q(Device).filter(Device.status == "registered").count(),
        "verified_samples": q(Sample).filter(Sample.signature != "").count(),
        "open_requests": q(DataRequest).filter(DataRequest.status == "open").count(),
        "escrow_locked": int(sum(max(0, r.deposited - r.released - r.refunded) for r in q(DataRequest).filter(DataRequest.status == "open").all())),
        "trending_categories": sorted(({"category": k, "demand": v} for k, v in cats.items()), key=lambda x: -x["demand"])[:8],
        "onchain_txs": q(Tx).filter(Tx.mode == "onchain").count(),
    }


@router.get("/profile/{address}")
def profile(address: str, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.address == address.lower()).first()
    if not u:
        raise HTTPException(404, "no such user")
    return profile_data(db, u)


def profile_data(db: Session, u: User) -> dict:
    subs = db.query(Submission).filter(Submission.contributor_id == u.id).all()
    return {
        "user": {**user_brief(u), "bio": u.bio, "roles": u.roles, "created_at": u.created_at},
        "devices": [device_view(d) for d in db.query(Device).filter(Device.owner_id == u.id).all()],
        "datasets": [dataset_view(db, d) for d in db.query(Dataset).filter(Dataset.owner_id == u.id, Dataset.status == "listed").all()],
        "stats": {
            "samples": db.query(Sample).filter(Sample.owner_id == u.id).count(),
            "accepted_submissions": sum(1 for s in subs if s.status == "accepted"),
            "rejected_submissions": sum(1 for s in subs if s.status == "rejected"),
            "fulfilled_requests": len({s.request_id for s in subs if s.status == "accepted"}),
            "licenses_bought": db.query(License).filter(License.buyer_id == u.id).count(),
            **ledger.summary(db, u.id),
        },
    }


@router.get("/dashboard")
def dashboard(user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    my_reqs = db.query(DataRequest).filter(DataRequest.buyer_id == user.id).all()
    lic = db.query(License).filter(License.buyer_id == user.id).all()
    runs = db.query(TrainingRun).filter(TrainingRun.owner_id == user.id).order_by(TrainingRun.id.desc()).limit(5).all()
    subs = db.query(Submission).filter(Submission.contributor_id == user.id).order_by(Submission.id.desc()).limit(10).all()
    return {
        **profile_data(db, user),
        "me": me_view(db, user),
        "requests": [request_view(db, r) for r in my_reqs],
        "escrow": {
            "deposited": sum(r.deposited for r in my_reqs), "released": sum(r.released for r in my_reqs),
            "refunded": sum(r.refunded for r in my_reqs),
            "locked": sum(max(0, r.deposited - r.released - r.refunded) for r in my_reqs if r.status == "open"),
        },
        "licenses": [{"dataset": dataset_view(db, db.get(Dataset, l.dataset_id)), "tx_hash": l.tx_hash, "tx_url": chain.explorer_tx(l.tx_hash),
                      "mode": l.mode, "via": l.via, "price": l.price, "created_at": l.created_at} for l in lic],
        "runs": [{"id": r.id, "status": r.status, "base_model": r.base_model, "after": r.after, "created_at": r.created_at, "workspace_id": r.workspace_id} for r in runs],
        "submissions": [{"id": s.id, "request_id": s.request_id, "status": s.status, "payout": s.payout, "tx_hash": s.tx_hash,
                         "tx_url": chain.explorer_tx(s.tx_hash), "mode": s.mode, "reasons": s.reasons, "created_at": s.created_at} for s in subs],
    }


@router.get("/transactions")
def transactions(user: User = Depends(auth.current_user), db: Session = Depends(get_db), limit: int = 100):
    rows = (db.query(Tx).filter((Tx.from_user == user.id) | (Tx.to_user == user.id)).order_by(Tx.id.desc()).limit(min(limit, 500)).all())
    return [{**t.to_dict(), "direction": "in" if t.to_user == user.id else "out", "tx_url": chain.explorer_tx(t.tx_hash)} for t in rows]


@router.get("/audit")
def audit_log(user: User = Depends(auth.current_user), db: Session = Depends(get_db), limit: int = 100):
    rows = db.query(AuditEvent).filter(AuditEvent.actor == user.address).order_by(AuditEvent.id.desc()).limit(min(limit, 500)).all()
    return [r.to_dict(exclude=("ip",)) for r in rows]
