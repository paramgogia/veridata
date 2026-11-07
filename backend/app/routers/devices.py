"""Device registry, live telemetry (WebSocket), live preview frames, MJPEG proxy, RFID and capture."""
from __future__ import annotations

import asyncio
import secrets
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import auth, crypto, hardware, provenance, quality, zerog
from .. import video as video_mod
from ..chain import client as chain
from ..config import CAM_CAPTURE_URL, CAM_STREAM_URL, DEVICE_CONTROL_URL
from ..db import Device, RfidTag, Sample, SessionLocal, User, audit, get_db
from ..serialize import device_view, sample_view

router = APIRouter(prefix="/api")

SENSORS = ["esp32-cam", "ir obstacle", "rc522 rfid", "dht temp/humidity"]


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
    from .. import arkiv
    arkiv.background(arkiv.write_device, dev.id, user.address, dev.name, "simulated" if dev.simulated else dev.kind,
                       dev.pubkey_hex, dev.signing_mode, dev.registration_tx, dev.registration_mode,
                       dev.status, dev.created_at)
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


class DeviceUrls(BaseModel):
    capture_url: str | None = None
    stream_url: str | None = None
    control_url: str | None = None


@router.patch("/devices/{dev_id}")
def update_device_urls(dev_id: str, body: DeviceUrls, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    """Hotspot/DHCP IPs change: let the owner repoint the CAM and sensor board (signing key unchanged)."""
    dev = _own(db, dev_id, user)
    if dev.simulated:
        raise HTTPException(400, "simulated devices have no URLs")
    for k in ("capture_url", "stream_url", "control_url"):
        v = getattr(body, k)
        if v is not None:
            v = v.strip().rstrip("/") if k == "control_url" else v.strip()
            if v and not v.startswith(("http://", "https://")):
                raise HTTPException(400, f"{k} must start with http://")
            setattr(dev, k, v)
    hardware._frames.pop(dev.id, None)
    audit(db, user.address, "device.update_urls", dev.id, body.model_dump(exclude_none=True))
    db.commit()
    return device_view(dev)


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


@router.get("/devices/{dev_id}/frame")
async def frame(dev_id: str, db: Session = Depends(get_db)):
    """One JPEG for the live preview (polled by the dashboard; see hardware.latest_frame)."""
    dev = db.get(Device, dev_id)
    if not dev:
        raise HTTPException(404, "device not found")
    if not dev.simulated and not dev.capture_url:
        raise HTTPException(404, "no camera configured")
    try:
        jpg = await hardware.latest_frame(dev)
    except Exception as e:
        raise HTTPException(502, f"camera unreachable: {type(e).__name__}")
    return Response(jpg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


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


class CaptureBody(BaseModel):
    attach_rfid: bool = True
    rfid_uids: list[str] = []
    label: str = ""
    description: str = ""
    categories: list[str] = []
    keywords: list[str] = []
    # Fallback when the ESP32-CAM is down: a JPEG taken with the browser's own camera
    # (base64). Sensors, RFID and signing are unchanged; the manifest records the camera used.
    image_b64: str | None = None
    # Demo fallback when the sensor board (or one sensor) is down: fill ONLY the missing readings
    # with test values. Real readings always win. The signed manifest lists every test field.
    test_sensors: bool = False
    # Video: kind="video" records a short clip. The rig camera is sampled frame by frame on the
    # server; a browser clip arrives as video_b64 (WebM/MP4) with image_b64 as a fallback keyframe.
    kind: str = "photo"
    seconds: float = 5
    video_b64: str | None = None


TEST_TAG_UID = "TEST0001"


def _test_readings() -> dict:
    import random
    return {"ir": random.random() < 0.5, "temp_c": round(random.uniform(26.0, 30.0), 1),
            "humidity_pct": round(random.uniform(48.0, 65.0), 1)}


def _browser_video(b64: str) -> tuple[bytes, str]:
    import base64
    if "," in b64[:100]:
        b64 = b64.split(",", 1)[1]
    try:
        data = base64.b64decode(b64, validate=True)
    except Exception:
        raise HTTPException(400, "video_b64 is not valid base64")
    if len(data) > video_mod.MAX_VIDEO_BYTES:
        raise HTTPException(413, "video larger than 25 MB: record a shorter clip")
    mime = video_mod.is_supported(data)
    if not mime:
        raise HTTPException(400, "browser video must be WebM or MP4")
    return data, mime


async def _record_rig_clip(dev: Device, seconds: float) -> tuple[list[bytes], float]:
    """Sample the rig camera as fast as it answers for `seconds` (the ESP32-CAM gives ~2-5 fps)."""
    frames: list[bytes] = []
    fails = 0
    t0 = time.time()
    while time.time() - t0 < seconds and len(frames) < 150:
        try:
            frames.append(await hardware.capture_jpeg(dev))
        except Exception as e:
            fails += 1
            if fails >= 4 and not frames:
                raise HTTPException(502, f"rig camera not answering: {type(e).__name__}")
        if dev.simulated:
            await asyncio.sleep(0.12)  # simulated camera answers instantly: keep ~8 fps
    if len(frames) < 2:
        raise HTTPException(502, "rig camera returned too few frames for a video")
    return frames, time.time() - t0


def _browser_jpeg(b64: str) -> bytes:
    import base64
    if "," in b64[:100]:  # strip a data: URL prefix
        b64 = b64.split(",", 1)[1]
    try:
        data = base64.b64decode(b64, validate=True)
    except Exception:
        raise HTTPException(400, "image_b64 is not valid base64")
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(413, "image larger than 8 MB")
    if not data.startswith(b"\xff\xd8"):
        raise HTTPException(400, "browser image must be a JPEG")
    return data


@router.post("/devices/{dev_id}/capture")
async def capture(dev_id: str, body: CaptureBody, request: Request, user: User = Depends(auth.current_user), db: Session = Depends(get_db)):
    dev = _own(db, dev_id, user)
    is_video = body.kind == "video"
    seconds = max(2.0, min(10.0, float(body.seconds or 5)))
    camera = "browser" if (body.image_b64 or body.video_b64) else ("simulated" if dev.simulated else "esp32-cam")
    clip: bytes | None = None
    media_type, media_extra, duration, tel_start = "image/jpeg", None, 0.0, None
    if is_video and body.video_b64:  # clip recorded in the browser
        clip, media_type = _browser_video(body.video_b64)
        jpeg, nframes = video_mod.keyframe_and_probe(clip, ".webm" if media_type == "video/webm" else ".mp4")
        if jpeg is None and body.image_b64:
            jpeg = _browser_jpeg(body.image_b64)  # browser-supplied keyframe if the clip can't be decoded here
        if jpeg is None:
            raise HTTPException(400, "could not read a frame from the video")
        duration = seconds
    elif is_video:  # rig camera, sampled frame by frame
        tel_start = _enrich(db, await hardware.telemetry(dev))
        frames, duration = await _record_rig_clip(dev, seconds)
        try:
            clip = video_mod.frames_to_webm(frames, len(frames) / max(duration, 0.1))
        except Exception as e:
            raise HTTPException(500, f"video encoding failed: {type(e).__name__}: {str(e)[:120]}")
        media_type, jpeg, nframes = "video/webm", frames[len(frames) // 2], len(frames)
    elif body.image_b64:
        jpeg = _browser_jpeg(body.image_b64)
    else:
        try:
            jpeg = await hardware.capture_jpeg(dev)
        except Exception as e:
            raise HTTPException(502, f"capture failed: {type(e).__name__}: {str(e)[:120]}")
    if is_video:
        # the keyframe's hash is signed too, so the still used for checks/training is bound to the clip
        media_extra = {"keyframe_sha256": crypto.sha256_hex(jpeg), "duration_s": round(duration, 2), "frames": nframes}
    media = clip if is_video else jpeg
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
    board_online = dev.simulated or bool(tel.get("online"))
    sensors = {k: tel.get(k) for k in ("ir", "temp_c", "humidity_pct") if board_online and tel.get(k) is not None}
    test_fields: list[str] = []
    if body.test_sensors:
        fake = _test_readings()
        for k in ("ir", "temp_c", "humidity_pct"):
            if k not in sensors:
                sensors[k] = fake[k]
                test_fields.append(k)
        if not rfid:
            tag = db.get(RfidTag, TEST_TAG_UID)
            rfid.append({"uid": TEST_TAG_UID, "label": tag.label if tag else "Test tag", "seen_ms_ago": None})
            test_fields.append("rfid")
    if not board_online and camera != "browser" and not body.test_sensors:
        raise HTTPException(502, "sensor board offline: use test sensor data or this device's camera")
    # `camera`, `sensor_board` and `test_fields` are signed into the manifest, so a browser photo or
    # a capture with test readings can never pass as a full rig capture.
    meta = {"fw": tel.get("fw"), "simulated": dev.simulated, "source": "device-capture", "camera": camera,
            "sensor_board": ("online" if board_online else "offline") if not test_fields else
                            ("online+test-data" if board_online else "test-data")}
    if test_fields:
        meta["test_fields"] = test_fields
    if tel_start and tel_start.get("online"):  # rig clips: readings at the start and the end of recording
        meta["sensors_start"] = {k: tel_start.get(k) for k in ("ir", "temp_c", "humidity_pct") if tel_start.get(k) is not None}
    manifest = provenance.build_manifest(dev, media, st["width"], st["height"], sensors, rfid, meta,
                                         media_type=media_type, media_extra=media_extra)
    # 0G storage: encrypt + upload the ciphertext BEFORE signing, so the storage
    # root is part of the signed manifest's media block (resolvable independently).
    media_store = None
    if zerog.enabled():
        media_store = zerog.store_media(media, manifest["capture_id"])
        manifest["media"]["storage"] = {"local": media_store["ref"],
                                        "root_0g": media_store["root"] or "", "tx_0g": media_store["tx"] or ""}
        if media_store.get("error"):
            manifest["meta"]["0g_error"] = media_store["error"]
    if dev.signing_mode == "device-hardware":
        try:
            sig = await hardware.device_sign(dev, crypto.sha256_hex(crypto.canonical(manifest)))
        except Exception as e:
            raise HTTPException(502, f"device signing failed: {type(e).__name__}")
    else:
        sig = provenance.sign_manifest_dev(dev, manifest)
    s = provenance.store_sample(db, owner_id=user.id, media=media, manifest=manifest, signature=sig, dev=dev,
                                label=body.label, description=body.description, categories=body.categories,
                                keywords=body.keywords, rfid=rfid, sensors=sensors, phash=st["phash"], blur_preview=False,
                                media_store=media_store, media_type=media_type,
                                keyframe=jpeg if is_video else None, duration_s=round(duration, 2))
    if zerog.enabled():
        try:  # manifest itself goes to 0G too; its root is stored beside the sample
            _mtx, mroot = zerog.upload_bytes(crypto.canonical(manifest), f"{s.id}.manifest.json")
            s.storage_root_manifest = mroot
            if not s.storage_tx:
                s.storage_tx = _mtx
        except Exception as e:
            audit(db, user.address, "capture.0g-manifest-failed", s.id, {"error": str(e)[:120]}, auth.client_ip(request))
    dev.last_seen = time.time()
    audit(db, user.address, "capture", s.id, {"device": dev.id, "sha256": s.media_sha256, "sig_mode": dev.signing_mode,
                                              "0g": {"root_media": s.storage_root_media, "root_manifest": s.storage_root_manifest}},
          auth.client_ip(request))
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
