"""Device registry, live telemetry (WebSocket), MJPEG stream proxy, servo, RFID and capture."""
from __future__ import annotations

import asyncio
import secrets
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import auth, crypto, hardware, provenance, quality
from ..chain import client as chain
from ..config import CAM_CAPTURE_URL, CAM_STREAM_URL, DEVICE_CONTROL_URL
from ..db import Device, RfidTag, Sample, SessionLocal, User, audit, get_db
from ..serialize import device_view, sample_view

router = APIRouter(prefix="/api")

SENSORS = ["esp32-cam", "hc-sr04 ultrasonic", "ir obstacle", "rc522 rfid", "sg90 servo", "dht temp/humidity"]


def chain_device_id(dev_id: str) -> str:
    from web3 import Web3
    return Web3.keccak(text=dev_id).hex().removeprefix("0x")


class DeviceCreate(BaseModel):
    name: str
    simulated: bool = False
    capture_url: str = ""
    stream_url: str = ""
    control_url: str = ""


@router.get("/devices")
def list_devices(db: Session = Depends(get_db), mine: bool = False, user: User | None = Depends(auth.optional_user)):
    q = db.query(Device)
    if mine and user:
        q = q.filter(Device.owner_id == user.id)
    return [device_view(d) | {"chain_device_id": chain_device_id(d.id)} for d in q.order_by(Device.created_at.desc()).all()]


@router.get("/devices/defaults")
def device_defaults():
    return {"capture_url": CAM_CAPTURE_URL, "stream_url": CAM_STREAM_URL, "control_url": DEVICE_CONTROL_URL}


@router.post("/devices")
async def create_device(body: DeviceCreate, request: Request, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    dev_id = f"vd-{secrets.token_hex(4)}"
    hw_key = None
    if not body.simulated and body.control_url:
        hw_key = await hardware.device_pubkey(body.control_url.rstrip("/"))
    if hw_key:
        dev = Device(id=dev_id, owner_id=user.id, name=body.name[:120], pubkey_hex=hw_key, signing_mode="device-hardware")
    else:
        k, pub = crypto.gen_p256()
        dev = Device(id=dev_id, owner_id=user.id, name=body.name[:120], pubkey_hex=pub, signing_mode="dev-software",
                     privkey_wrapped=crypto.wrap(crypto.priv_to_bytes(k), f"device:{dev_id}"))
    dev.simulated = body.simulated
    dev.sensors = SENSORS
    dev.capture_url = body.capture_url.strip()
    dev.stream_url = body.stream_url.strip()
    dev.control_url = body.control_url.strip().rstrip("/")
    db.add(dev)
    audit(db, user.address, "device.register", dev_id, {"signing_mode": dev.signing_mode, "simulated": dev.simulated}, auth.client_ip(request))
    db.commit()
    return device_view(dev) | {"chain_device_id": chain_device_id(dev.id)}


@router.get("/devices/{dev_id}")
def get_device(dev_id: str, db: Session = Depends(get_db)):
    dev = db.get(Device, dev_id)
    if not dev:
        raise HTTPException(404, "device not found")
    recent = db.query(Sample).filter(Sample.device_id == dev_id).order_by(Sample.captured_at.desc()).limit(12).all()
    return device_view(dev) | {"chain_device_id": chain_device_id(dev.id), "owner": db.get(User, dev.owner_id).address,
                               "recent": [sample_view(s) for s in recent]}


def _own(db: Session, dev_id: str, user: User) -> Device:
    dev = db.get(Device, dev_id)
    if not dev:
        raise HTTPException(404, "device not found")
    if dev.owner_id != user.id:
        raise HTTPException(403, "not your device")
    if dev.status != "registered":
        raise HTTPException(409, "device revoked")
    return dev


class TxBody(BaseModel):
    tx_hash: str


@router.post("/devices/{dev_id}/confirm-chain")
def confirm_chain(dev_id: str, body: TxBody, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    dev = _own(db, dev_id, user)
    try:
        ev = chain.verify_event(body.tx_hash, "DeviceRegistered", sender=user.address)
    except chain.ChainError as e:
        raise HTTPException(400, str(e))
    if ev["deviceId"].removeprefix("0x") != chain_device_id(dev.id) or ev["pubKey"].removeprefix("0x") != dev.pubkey_hex:
        raise HTTPException(400, "on-chain registration does not match this device")
    dev.registration_tx, dev.registration_mode = body.tx_hash, "onchain"
    audit(db, user.address, "device.chain_registered", dev_id, {"tx": body.tx_hash})
    db.commit()
    return device_view(dev)


@router.post("/devices/{dev_id}/revoke")
def revoke(dev_id: str, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    dev = _own(db, dev_id, user)
    dev.status = "revoked"
    audit(db, user.address, "device.revoke", dev_id)
    db.commit()
    return device_view(dev)


@router.get("/devices/{dev_id}/telemetry")
async def telemetry(dev_id: str, db: Session = Depends(get_db)):
    dev = db.get(Device, dev_id)
    if not dev:
        raise HTTPException(404, "device not found")
    t = await hardware.telemetry(dev)
    if t.get("online"):
        dev.last_seen = time.time()
        db.commit()
    return _enrich(db, t)


def _enrich(db: Session, t: dict) -> dict:
    rf = t.get("rfid")
    if rf and rf.get("uid"):
        tag = db.get(RfidTag, rf["uid"])
        rf["label"] = tag.label if tag else None
        rf["asset_type"] = tag.asset_type if tag else None
    return t


@router.websocket("/devices/{dev_id}/ws")
async def telemetry_ws(ws: WebSocket, dev_id: str):
    await ws.accept()
    db = SessionLocal()
    try:
        dev = db.get(Device, dev_id)
        if not dev:
            await ws.close(code=4404)
            return
        while True:
            db.refresh(dev)
            t = await hardware.telemetry(dev)
            await ws.send_json(_enrich(db, t))
            await asyncio.sleep(0.5 if dev.simulated else 0.8)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        db.close()


@router.get("/devices/{dev_id}/stream")
async def stream(dev_id: str, db: Session = Depends(get_db)):
    dev = db.get(Device, dev_id)
    if not dev:
        raise HTTPException(404, "device not found")
    if dev.simulated:
        return StreamingResponse(hardware.mjpeg_frames(dev), media_type="multipart/x-mixed-replace; boundary=frame")
    if not dev.stream_url:
        raise HTTPException(404, "no stream configured")
    client = httpx.AsyncClient(timeout=httpx.Timeout(5, read=None))
    try:
        upstream = await client.send(client.build_request("GET", dev.stream_url), stream=True)
    except Exception as e:
        await client.aclose()
        raise HTTPException(502, f"camera stream unreachable: {type(e).__name__}")

    async def body():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(body(), media_type=upstream.headers.get("content-type", "multipart/x-mixed-replace"))


class ServoBody(BaseModel):
    deg: int


@router.post("/devices/{dev_id}/servo")
async def servo(dev_id: str, body: ServoBody, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    dev = _own(db, dev_id, user)
    try:
        return await hardware.set_servo(dev, body.deg)
    except Exception as e:
        raise HTTPException(502, f"servo command failed: {type(e).__name__}")


class CaptureBody(BaseModel):
    attach_rfid: bool = True
    rfid_uids: list[str] = []
    label: str = ""
    description: str = ""
    categories: list[str] = []
    keywords: list[str] = []


@router.post("/devices/{dev_id}/capture")
async def capture(dev_id: str, body: CaptureBody, request: Request, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    dev = _own(db, dev_id, user)
    try:
        jpeg = await hardware.capture_jpeg(dev)
    except Exception as e:
        raise HTTPException(502, f"capture failed: {type(e).__name__}: {str(e)[:120]}")
    tel = _enrich(db, await hardware.telemetry(dev))
    st = quality.image_stats(jpeg)
    rfid = []
    uids = list(body.rfid_uids)
    if body.attach_rfid and tel.get("rfid") and tel["rfid"].get("uid") and tel["rfid"]["uid"] not in uids:
        uids.append(tel["rfid"]["uid"])
    for uid in uids:
        tag = db.get(RfidTag, uid)
        rfid.append({"uid": uid, "label": tag.label if tag else None,
                     "seen_ms_ago": (tel.get("rfid") or {}).get("seen_ms_ago") if (tel.get("rfid") or {}).get("uid") == uid else None})
    sensors = {k: tel.get(k) for k in ("distance_cm", "ir", "servo_deg", "temp_c", "humidity_pct") if tel.get(k) is not None}
    meta = {"fw": tel.get("fw"), "simulated": dev.simulated, "source": "device-capture"}
    manifest = provenance.build_manifest(dev, jpeg, st["width"], st["height"], sensors, rfid, meta)
    if dev.signing_mode == "device-hardware":
        try:
            sig = await hardware.device_sign(dev, crypto.sha256_hex(crypto.canonical(manifest)))
        except Exception as e:
            raise HTTPException(502, f"device signing failed: {type(e).__name__}")
    else:
        sig = provenance.sign_manifest_dev(dev, manifest)
    s = provenance.store_sample(db, owner_id=user.id, media=jpeg, manifest=manifest, signature=sig, dev=dev,
                                label=body.label, description=body.description, categories=body.categories,
                                keywords=body.keywords, rfid=rfid, sensors=sensors, phash=st["phash"], blur_preview=False)
    dev.last_seen = time.time()
    audit(db, user.address, "capture", s.id, {"device": dev.id, "sha256": s.media_sha256, "sig_mode": dev.signing_mode}, auth.client_ip(request))
    db.commit()
    return sample_view(s, full=True)


# ---------------- RFID tag registry ----------------

class TagBody(BaseModel):
    uid: str
    label: str
    asset_type: str = "product"


@router.get("/rfid")
def list_tags(db: Session = Depends(get_db)):
    return [t.to_dict() for t in db.query(RfidTag).order_by(RfidTag.created_at.desc()).all()]


@router.post("/rfid")
def upsert_tag(body: TagBody, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    uid = body.uid.strip().upper()
    if not uid or len(uid) > 40:
        raise HTTPException(400, "bad uid")
    t = db.get(RfidTag, uid) or RfidTag(uid=uid, owner_id=user.id)
    t.label, t.asset_type = body.label[:120], body.asset_type[:64]
    db.merge(t)
    audit(db, user.address, "rfid.associate", uid, {"label": body.label})
    db.commit()
    return t.to_dict()
