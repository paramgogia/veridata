"""ESP32 device bridge.

Real hardware (two boards, one logical device):
  - ESP32-CAM running the stock CameraWebServer: still at  <cam>/capture, MJPEG at <cam>:81/stream
  - Main ESP32 running firmware/veridata_main: HTTP JSON API
        GET  /sensors          -> {distance_cm, ir, servo_deg, rfid:{uid, seen_ms_ago}|null, uptime_ms, fw}
        GET  /servo?deg=N      -> moves the camera servo
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
        self.servo = 90.0
        self.tag: str | None = None
        self.tag_at = 0.0
        self.tags = ["04A1B2C3", "04D4E5F6", "0477AA19", "04C0FFEE"]


_sim: dict[str, SimState] = {}


def _state(dev_id: str) -> SimState:
    return _sim.setdefault(dev_id, SimState())


def sim_telemetry(dev: Device) -> dict[str, Any]:
    s = _state(dev.id)
    t = time.time()
    dist = 60 + 45 * math.sin(t / 4) + random.uniform(-2, 2)
    ir = dist < 40
    if random.random() < 0.04:
        s.tag, s.tag_at = random.choice(s.tags), t
    rfid = {"uid": s.tag, "seen_ms_ago": int((t - s.tag_at) * 1000)} if s.tag and t - s.tag_at < 8 else None
    return {"online": True, "simulated": True, "distance_cm": round(dist, 1), "ir": ir, "servo_deg": s.servo,
            "rfid": rfid, "uptime_ms": int(t * 1000) % 10**9, "fw": "sim-0.1", "cam_online": True, "ts": t}


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


async def set_servo(dev: Device, deg: int) -> dict[str, Any]:
    deg = max(0, min(180, int(deg)))
    if dev.simulated:
        _state(dev.id).servo = float(deg)
        return {"ok": True, "servo_deg": deg, "simulated": True}
    async with httpx.AsyncClient(timeout=2.5) as c:
        r = await c.get(f"{dev.control_url}/servo", params={"deg": deg})
        r.raise_for_status()
        return {"ok": True, "servo_deg": deg, **(r.json() if r.headers.get("content-type", "").startswith("application/json") else {})}


async def capture_jpeg(dev: Device) -> bytes:
    if dev.simulated:
        tel = sim_telemetry(dev)
        return synth.sim_frame(time.time(), tel["servo_deg"], tel["distance_cm"], tel["ir"], (tel["rfid"] or {}).get("uid"))
    async with httpx.AsyncClient(timeout=8) as c:
        r = await c.get(dev.capture_url)
        r.raise_for_status()
        if not r.content.startswith(b"\xff\xd8"):
            raise RuntimeError("camera did not return a JPEG")
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
            tel = sim_telemetry(dev)
            jpg = synth.sim_frame(time.time(), tel["servo_deg"], tel["distance_cm"], tel["ir"], (tel["rfid"] or {}).get("uid"))
            yield boundary + b"Content-Type: image/jpeg\r\nContent-Length: " + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n"
            await asyncio.sleep(0.2)
    async with httpx.AsyncClient(timeout=httpx.Timeout(10, read=None)) as c:
        async with c.stream("GET", dev.stream_url) as r:
            async for chunk in r.aiter_raw():
                yield chunk
