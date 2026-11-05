"""Money movements. Every payment is recorded here with its settlement mode:
  - "onchain": settled by the Veridata contract on Sepolia (tx_hash is a real tx)
  - "local":   off-chain demo ledger (used for demo personas / when chain is not configured)
Amounts are integer gwei."""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from .config import PLATFORM_FEE_BPS
from .db import Tx

DEMO_FAUCET = 5 * 10**9  # 5 demo ETH on the off-chain ledger


def record(db: Session, kind: str, amount: int, *, frm: int | None = None, to: int | None = None,
           mode: str = "local", tx_hash: str = "", ref: str = "", memo: str = "", chain_id: int | None = None) -> Tx:
    t = Tx(kind=kind, amount=int(amount), from_user=frm, to_user=to, mode=mode, tx_hash=tx_hash, ref=ref, memo=memo, chain_id=chain_id)
    db.add(t)
    return t


def fee(amount: int) -> int:
    return amount * PLATFORM_FEE_BPS // 10_000


def local_balance(db: Session, user_id: int) -> int:
    inc = db.query(func.coalesce(func.sum(Tx.amount), 0)).filter(Tx.to_user == user_id, Tx.mode == "local").scalar()
    out = db.query(func.coalesce(func.sum(Tx.amount), 0)).filter(Tx.from_user == user_id, Tx.mode == "local").scalar()
    return int(inc) - int(out)


def require_local_funds(db: Session, user_id: int, amount: int) -> None:
    from fastapi import HTTPException
    if local_balance(db, user_id) < amount:
        raise HTTPException(402, "insufficient demo-ledger balance")


def summary(db: Session, user_id: int) -> dict:
    def s(q):
        return int(q.scalar() or 0)
    earned = s(db.query(func.sum(Tx.amount)).filter(Tx.to_user == user_id, Tx.kind.in_(["payout", "purchase"])))
    spent = s(db.query(func.sum(Tx.amount)).filter(Tx.from_user == user_id, Tx.kind.in_(["purchase", "platform_fee", "upload_fee"])))
    return {"earned": earned, "spent": spent, "demo_balance": local_balance(db, user_id)}
