"""Wallet authentication (EIP-191 personal_sign of a one-time nonce) and session tokens.

Demo personas (no wallet) are clearly flagged and can only transact on the off-chain
demo ledger; real on-chain actions always require a connected wallet."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from .config import SESSION_SECRET
from .db import LoginNonce, User, get_db

TOKEN_TTL = 7 * 24 * 3600


def login_message(address: str, nonce: str) -> str:
    return (f"Sign in to Veridata\n\nAddress: {address.lower()}\nNonce: {nonce}\n"
            "This signature proves wallet ownership. It does not send a transaction or cost gas.")


def issue_nonce(db: Session, address: str) -> str:
    nonce = secrets.token_hex(12)
    row = db.get(LoginNonce, address.lower()) or LoginNonce(address=address.lower())
    row.nonce, row.expires = nonce, time.time() + 300
    db.merge(row)
    db.commit()
    return login_message(address, nonce)


def verify_login(db: Session, address: str, signature: str) -> User:
    from eth_account import Account
    from eth_account.messages import encode_defunct

    row = db.get(LoginNonce, address.lower())
    if not row or row.expires < time.time():
        raise HTTPException(400, "nonce expired; request a new one")
    msg = login_message(address, row.nonce)
    try:
        recovered = Account.recover_message(encode_defunct(text=msg), signature=signature)
    except Exception:
        raise HTTPException(401, "invalid signature")
    if recovered.lower() != address.lower():
        raise HTTPException(401, "signature does not match address")
    db.delete(row)  # single use: prevents replay of the login signature
    user = db.query(User).filter(User.address == address.lower()).first()
    if not user:
        user = User(address=address.lower(), name=f"{address[:6]}…{address[-4:]}")
        db.add(user)
    db.commit()
    return user


def make_token(user_id: int) -> str:
    body = base64.urlsafe_b64encode(json.dumps({"uid": user_id, "exp": int(time.time()) + TOKEN_TTL}).encode()).decode()
    sig = hmac.new(SESSION_SECRET, body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def parse_token(token: str) -> int | None:
    try:
        body, sig = token.split(".")
        if not hmac.compare_digest(sig, hmac.new(SESSION_SECRET, body.encode(), hashlib.sha256).hexdigest()):
            return None
        data = json.loads(base64.urlsafe_b64decode(body))
        return int(data["uid"]) if data["exp"] > time.time() else None
    except Exception:
        return None


def optional_user(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> User | None:
    if not authorization.startswith("Bearer "):
        return None
    uid = parse_token(authorization[7:])
    return db.get(User, uid) if uid else None


def current_user(user: User | None = Depends(optional_user)) -> User:
    if not user:
        raise HTTPException(401, "sign in required")
    return user


def require_role(role: str):
    def dep(user: User = Depends(current_user)) -> User:
        if role not in (user.roles or []):
            raise HTTPException(403, f"{role} role required")
        return user
    return dep


def client_ip(req: Request) -> str:
    return req.client.host if req.client else ""
