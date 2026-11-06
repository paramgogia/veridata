"""SQLAlchemy models. SQLite by default, Postgres via DATABASE_URL.
Amounts are integer token base units (6 decimals)."""
from __future__ import annotations

import json
import time
from typing import Any

from sqlalchemy import (JSON, BigInteger, Boolean, Column, Float, ForeignKey, Integer, String, Text, create_engine)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def now() -> float:
    return time.time()


class Base(DeclarativeBase):
    def to_dict(self, exclude: tuple[str, ...] = ()) -> dict[str, Any]:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns if c.name not in exclude}


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    address = Column(String(64), unique=True, index=True)  # lowercase 0x...
    name = Column(String(120), default="")
    bio = Column(Text, default="")
    roles = Column(JSON, default=lambda: ["contributor", "buyer"])
    persona = Column(String(32), default="")  # "contributor"/"buyer" for custodial demo wallets
    reputation = Column(Float, default=0.0)
    created_at = Column(Float, default=now)


class LoginNonce(Base):
    __tablename__ = "login_nonces"
    address = Column(String(64), primary_key=True)
    nonce = Column(String(64))
    expires = Column(Float)


class Device(Base):
    __tablename__ = "devices"
    id = Column(String(64), primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id"), index=True)
    name = Column(String(120))
    kind = Column(String(64), default="esp32-cam")
    sensors = Column(JSON, default=list)
    pubkey_hex = Column(String(200))           # uncompressed P-256, 04||X||Y
    signing_mode = Column(String(32))           # dev-software | device-hardware
    privkey_wrapped = Column(Text, default="")  # dev-software only, AES-GCM wrapped
    stream_url = Column(String(300), default="")
    capture_url = Column(String(300), default="")
    control_url = Column(String(300), default="")
    simulated = Column(Boolean, default=False)
    status = Column(String(32), default="registered")  # registered | revoked
    registration_tx = Column(String(80), default="")
    registration_mode = Column(String(32), default="local")  # onchain | local
    last_seen = Column(Float, default=0)
    created_at = Column(Float, default=now)


class RfidTag(Base):
    __tablename__ = "rfid_tags"
    uid = Column(String(40), primary_key=True)
    label = Column(String(120))
    asset_type = Column(String(64), default="product")
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(Float, default=now)


class Sample(Base):
    __tablename__ = "samples"
    id = Column(String(40), primary_key=True)
    device_id = Column(String(64), ForeignKey("devices.id"), nullable=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), index=True)
    captured_at = Column(Float)
    media_type = Column(String(40), default="image/jpeg")
    media_sha256 = Column(String(64), index=True)
    media_bytes = Column(Integer)
    width = Column(Integer, default=0)
    height = Column(Integer, default=0)
    phash = Column(String(32), default="", index=True)
    storage_ref = Column(String(200))
    key_wrapped = Column(Text)
    storage_root_media = Column(String(80), default="")  # 0G root hash of the ciphertext
    storage_root_manifest = Column(String(80), default="")  # 0G root hash of the canonical manifest
    storage_tx = Column(String(80), default="")  # 0G storage transaction
    preview_file = Column(String(200), default="")
    manifest = Column(JSON, nullable=True)
    manifest_hash = Column(String(64), default="", index=True)
    signature = Column(String(200), default="")
    sig_mode = Column(String(32), default="none")
    label = Column(String(80), default="")
    description = Column(Text, default="")
    keywords = Column(JSON, default=list)
    categories = Column(JSON, default=list)
    rfid = Column(JSON, default=list)
    sensors = Column(JSON, default=dict)
    quality = Column(JSON, nullable=True)
    status = Column(String(24), default="draft")  # draft | verified | rejected | published
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=True, index=True)
    is_demo = Column(Boolean, default=False)
    created_at = Column(Float, default=now)


class Dataset(Base):
    __tablename__ = "datasets"
    id = Column(Integer, primary_key=True)
    title = Column(String(200))
    description = Column(Text, default="")
    owner_id = Column(Integer, ForeignKey("users.id"), index=True)
    categories = Column(JSON, default=list)
    tags = Column(JSON, default=list)
    sensor_types = Column(JSON, default=list)
    location = Column(String(120), default="")
    price = Column(BigInteger, default=0)
    license = Column(String(200), default="Exclusive, non-transferable training license (in-platform only)")
    format = Column(String(60), default="JPEG")
    content_root = Column(String(66), default="")
    sample_count = Column(Integer, default=0)
    quality_score = Column(Float, default=0)
    chain_dataset_id = Column(Integer, nullable=True)
    publish_tx = Column(String(80), default="")
    mode = Column(String(24), default="local")  # onchain | local | demo-seed
    status = Column(String(24), default="listed")
    capture_start = Column(Float, default=0)
    capture_end = Column(Float, default=0)
    is_demo = Column(Boolean, default=False)
    created_at = Column(Float, default=now)


class License(Base):
    __tablename__ = "licenses"
    id = Column(Integer, primary_key=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), index=True)
    buyer_id = Column(Integer, ForeignKey("users.id"), index=True)
    price = Column(BigInteger)
    tx_hash = Column(String(80), default="")
    mode = Column(String(24), default="local")
    via = Column(String(24), default="direct")  # direct | x402
    created_at = Column(Float, default=now)


class DataRequest(Base):
    __tablename__ = "requests"
    id = Column(Integer, primary_key=True)
    buyer_id = Column(Integer, ForeignKey("users.id"), index=True)
    title = Column(String(200))
    description = Column(Text, default="")
    category = Column(String(80))
    quantity = Column(Integer)
    accepted = Column(Integer, default=0)
    price_per_sample = Column(BigInteger)
    deadline = Column(Float)
    spec = Column(JSON, default=dict)
    spec_hash = Column(String(66), default="")
    chain_request_id = Column(Integer, nullable=True)
    fund_tx = Column(String(80), default="")
    mode = Column(String(24), default="local")
    status = Column(String(24), default="open")  # open | filled | closed
    deposited = Column(BigInteger, default=0)
    released = Column(BigInteger, default=0)
    refunded = Column(BigInteger, default=0)
    is_demo = Column(Boolean, default=False)
    created_at = Column(Float, default=now)


class Submission(Base):
    __tablename__ = "submissions"
    id = Column(Integer, primary_key=True)
    request_id = Column(Integer, ForeignKey("requests.id"), index=True)
    sample_id = Column(String(40), ForeignKey("samples.id"))
    contributor_id = Column(Integer, ForeignKey("users.id"), index=True)
    status = Column(String(24), default="pending")
    reasons = Column(JSON, default=list)
    payout = Column(BigInteger, default=0)
    tx_hash = Column(String(80), default="")
    mode = Column(String(24), default="local")
    created_at = Column(Float, default=now)


class Tx(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    kind = Column(String(40))
    from_user = Column(Integer, nullable=True, index=True)
    to_user = Column(Integer, nullable=True, index=True)
    amount = Column(BigInteger, default=0)
    tx_hash = Column(String(80), default="")
    mode = Column(String(24), default="local")
    chain_id = Column(Integer, nullable=True)
    ref = Column(String(80), default="")
    memo = Column(String(200), default="")
    created_at = Column(Float, default=now)


class Workspace(Base):
    __tablename__ = "workspaces"
    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id"), index=True)
    name = Column(String(120))
    dataset_ids = Column(JSON, default=list)
    created_at = Column(Float, default=now)


class TrainingRun(Base):
    __tablename__ = "training_runs"
    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), index=True)
    owner_id = Column(Integer, ForeignKey("users.id"))
    base_model = Column(String(60))
    params = Column(JSON, default=dict)
    dataset_ids = Column(JSON, default=list)
    status = Column(String(24), default="queued")  # queued|running|completed|failed
    progress = Column(Float, default=0)
    logs = Column(JSON, default=list)
    history = Column(JSON, default=list)
    before = Column(JSON, nullable=True)
    after = Column(JSON, nullable=True)
    classes = Column(JSON, default=list)
    weights_file = Column(String(200), default="")
    weights_sha256 = Column(String(64), default="")
    card = Column(JSON, nullable=True)
    error = Column(Text, default="")
    created_at = Column(Float, default=now)
    finished_at = Column(Float, nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id = Column(Integer, primary_key=True)
    actor = Column(String(64), default="")
    action = Column(String(64))
    target = Column(String(120), default="")
    detail = Column(JSON, default=dict)
    ip = Column(String(64), default="")
    created_at = Column(Float, default=now)


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def audit(db: Session, actor: Any, action: str, target: str = "", detail: dict | None = None, ip: str = "") -> None:
    db.add(AuditEvent(actor=str(actor or ""), action=action, target=target, detail=json.loads(json.dumps(detail or {}, default=str)), ip=ip))
