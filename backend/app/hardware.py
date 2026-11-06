"""ESP32 device bridge.

Real hardware (two boards, one logical device):
  - ESP32-CAM running the stock CameraWebServer: still at  <cam>/capture, MJPEG at <cam>:81/stream
  - Main ESP32 running firmware/veridata_main: HTTP JSON API
        GET  /sensors          -> {ir, temp_c, humidity_pct, rfid:{uid, seen_ms_ago}|null, uptime_ms, fw}
        GET  /pubkey           -> {"pubkey": "04..."}  (P-256 key generated on-device, kept in NVS)
        GET  /sign?digest=HEX  -> {"sig": "r||s hex"}  (ES256 over the 32-byte manifest digest)
If a board is unreachable the dashboard shows it as offline; a device flagged `simulated`
generates synthetic telemetry and frames instead (always labelled SIMULATED).
"""
from __future__ import annotations

import math
import random
import time
from typing import Any

import httpx

from . import synth
from .db import Device


class SimState:
    def __init__(self) -> None:
        self.servo = 90.0  # only used to pan the synthetic frame
        self.tag: str | None = None
        self.tag_at = 0.0
        self.tags = ["04A1B2C3", "04D4E5F6", "0477AA19", "04C0FFEE"]


_sim: dict[str, SimState] = {}


def _state(dev_id: str) -> SimState:
    return _sim.setdefault(dev_id, SimState())


def sim_telemetry(dev: Device) -> dict[str, Any]:
    s = _state(dev.id)
    t = time.time()
    ir = math.sin(t / 4) > 0.35
    temp = round(27.5 + 1.2 * math.sin(t / 60) + random.uniform(-0.1, 0.1), 1)
    hum = round(58 + 6 * math.sin(t / 45) + random.uniform(-0.5, 0.5), 1)
    if random.random() < 0.04:
        s.tag, s.tag_at = random.choice(s.tags), t
    rfid = {"uid": s.tag, "seen_ms_ago": int((t - s.tag_at) * 1000)} if s.tag and t - s.tag_at < 8 else None
    return {"online": True, "simulated": True, "ir": ir, "temp_c": temp, "humidity_pct": hum,
            "rfid": rfid, "uptime_ms": int(t * 1000) % 10**9, "fw": "sim-0.2", "cam_online": True, "ts": t}


async def telemetry(dev: Device) -> dict[str, Any]:
    if dev.simulated:
        return sim_telemetry(dev)
    out: dict[str, Any] = {"online": False, "simulated": False, "cam_online": False, "ts": time.time()}
    async with httpx.AsyncClient(timeout=1.5) as c:
        if dev.control_url:
            try:
                r = await c.get(f"{dev.control_url}/sensors")
                out.update(r.json())
                out["online"] = True
            except Exception as e:
                out["error"] = f"main board unreachable: {type(e).__name__}"
        if dev.capture_url:
            try:
                r = await c.head(dev.capture_url.rsplit("/", 1)[0] + "/status")
                out["cam_online"] = r.status_code < 500
            except Exception:
                out["cam_online"] = False
    return out


def _sim_jpeg(dev: Device) -> bytes:
    tel = sim_telemetry(dev)
    return synth.sim_frame(time.time(), _state(dev.id).servo, 60.0, tel["ir"], (tel["rfid"] or {}).get("uid"))


async def capture_jpeg(dev: Device) -> bytes:
    """A fresh still for a signed capture (never served from the preview cache)."""
    if dev.simulated:
        return _sim_jpeg(dev)
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(dev.capture_url)
        r.raise_for_status()
        if not r.content.startswith(b"\xff\xd8"):
            raise RuntimeError("camera did not return a JPEG")
        _frames[dev.id] = (time.time(), r.content)
        return r.content


# Live preview: viewers poll single frames instead of holding the CAM's one MJPEG socket.
# Concurrent viewers share one upstream fetch per device (cached ~0.25 s), and a stalled CAM
# simply fails one request; the next poll retries, so the preview never freezes for good.
_frames: dict[str, tuple[float, bytes]] = {}
_frame_locks: dict[str, Any] = {}
# One keep-alive client for preview polling: a new TCP connection per frame exhausts the CAM's
# small socket pool (the ESP32 HTTP server allows only a handful of open sockets).
_client: httpx.AsyncClient | None = None


def _cam_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(6, connect=3),
                                    limits=httpx.Limits(max_connections=2, max_keepalive_connections=2))
    return _client


async def _reset_cam_client() -> None:
    global _client
    c, _client = _client, None
    if c is not None:
        try:
            await c.aclose()
        except Exception:
            pass


async def latest_frame(dev: Device, max_age: float = 0.45) -> bytes:
    import asyncio
    if dev.simulated:
        return _sim_jpeg(dev)
    hit = _frames.get(dev.id)
    if hit and time.time() - hit[0] < max_age:
        return hit[1]
    lock = _frame_locks.setdefault(dev.id, asyncio.Lock())
    async with lock:
        hit = _frames.get(dev.id)
        if hit and time.time() - hit[0] < max_age:
            return hit[1]
        try:
            r = await _cam_client().get(dev.capture_url)
            r.raise_for_status()
        except Exception:
            await _reset_cam_client()  # drop a dead keep-alive socket (CAM rebooted / IP changed)
            raise
        if not r.content.startswith(b"\xff\xd8"):
            raise RuntimeError("camera did not return a JPEG")
        _frames[dev.id] = (time.time(), r.content)
        return r.content


async def device_sign(dev: Device, digest_hex: str) -> str:
    async with httpx.AsyncClient(timeout=4) as c:
        r = await c.get(f"{dev.control_url}/sign", params={"digest": digest_hex})
        r.raise_for_status()
        return r.json()["sig"]


async def device_pubkey(control_url: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=2) as c:
            r = await c.get(f"{control_url}/pubkey")
            return r.json().get("pubkey")
    except Exception:
        return None


async def mjpeg_frames(dev: Device):
    """Yields multipart MJPEG chunks: proxied from the CAM, or synthesised for simulated devices."""
    import asyncio
    boundary = b"--frame\r\n"
    if dev.simulated:
        while True:
            jpg = _sim_jpeg(dev)
            yield boundary + b"Content-Type: image/jpeg\r\nContent-Length: " + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n"
            await asyncio.sleep(0.2)
    async with httpx.AsyncClient(timeout=httpx.Timeout(10, read=None)) as c:
        async with c.stream("GET", dev.stream_url) as r:
            async for chunk in r.aiter_raw():
                yield chunk
