"""AI-assisted quality and privacy assessment.

Deterministic checks (always run, never delegated to an LLM):
  - decode / corruption, resolution, exposure, sharpness (Laplacian variance)
  - near-duplicate detection (64-bit dHash against existing samples)
  - metadata completeness
  - face detection (OpenCV Haar cascade) for privacy screening
Model-assisted checks (optional, OpenAI-compatible endpoint — e.g. 0G Private Computer):
  - description↔media consistency score, suggested categories, privacy notes
If no model is configured, a keyword heuristic is used and labelled as such.
Cryptographic verification is NOT done here — see verify.py.
"""
from __future__ import annotations

import base64
import io
import json
import re
from typing import Any

import numpy as np
from PIL import Image

from .config import AI_API_KEY, AI_BASE_URL, AI_MODEL

CATEGORIES = [
    "agriculture", "crop-disease", "pest-damage", "insurance", "vehicle-damage", "autonomous-driving",
    "night", "weather", "retail", "warehouse", "inventory", "occupancy", "ir-sensing", "ultrasonic",
    "rfid-tagged", "industrial", "infrastructure",
]
KEYWORDS = {
    "agriculture": ["leaf", "crop", "farm", "plant", "mango", "field"],
    "crop-disease": ["fungal", "disease", "spot", "blight", "rust"],
    "pest-damage": ["pest", "insect", "chewed", "hole", "caterpillar"],
    "insurance": ["claim", "damage", "insur", "accident"],
    "vehicle-damage": ["dent", "scratch", "crack", "bumper", "glass", "car"],
    "autonomous-driving": ["road", "driving", "lane", "highway", "rural"],
    "night": ["night", "dark", "headlight"],
    "weather": ["rain", "fog", "storm", "wet"],
    "retail": ["shelf", "store", "product", "retail", "aisle"],
    "warehouse": ["warehouse", "pallet", "rack", "stock"],
    "inventory": ["inventory", "stock", "sku", "item"],
    "occupancy": ["occupancy", "people count", "presence", "occupied", "empty"],
    "ir-sensing": ["ir", "infrared", "thermal"],
    "ultrasonic": ["distance", "ultrasonic", "proximity"],
    "rfid-tagged": ["rfid", "tag"],
}

_face = None
_face_engine = "unavailable"
YUNET_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"


def _face_detector():
    """Haar cascade if this OpenCV build has it, else YuNet (ONNX, fetched once into data/models)."""
    global _face, _face_engine
    if _face is not None:
        return _face
    import cv2
    if hasattr(cv2, "CascadeClassifier"):
        _face = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        _face_engine = "opencv-haar"
        return _face
    from .config import DATA
    mp = DATA / "models" / "face_detection_yunet.onnx"
    if not mp.exists():
        try:
            import httpx
            mp.parent.mkdir(exist_ok=True)
            r = httpx.get(YUNET_URL, follow_redirects=True, timeout=20)
            r.raise_for_status()
            mp.write_bytes(r.content)
        except Exception:
            _face = False
            return _face
    _face = cv2.FaceDetectorYN.create(str(mp), "", (320, 320), 0.8)
    _face_engine = "opencv-yunet"
    return _face


def detect_faces(rgb) -> int | None:
    """Number of faces, or None if no detector is available."""
    import cv2
    det = _face_detector()
    if det is False:
        return None
    arr = np.asarray(rgb)
    if min(arr.shape[:2]) < 48:
        return 0
    if _face_engine == "opencv-haar":
        return len(det.detectMultiScale(cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY), 1.1, 5, minSize=(24, 24)))
    bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    det.setInputSize((bgr.shape[1], bgr.shape[0]))
    _, faces = det.detect(bgr)
    return 0 if faces is None else len(faces)


def dhash(img: Image.Image) -> str:
    g = np.asarray(img.convert("L").resize((9, 8), Image.BILINEAR), dtype=np.int16)
    bits = (g[:, 1:] > g[:, :-1]).flatten()
    return "%016x" % int("".join("1" if b else "0" for b in bits), 2)


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def image_stats(data: bytes) -> dict[str, Any]:
    img = Image.open(io.BytesIO(data))
    img.load()
    rgb = img.convert("RGB")
    g = np.asarray(rgb.convert("L"), dtype=np.float32)
    lap = g[1:-1, 1:-1] * 4 - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:]
    return {"width": img.width, "height": img.height, "format": img.format, "brightness": float(g.mean()),
            "sharpness": float(lap.var()), "phash": dhash(rgb), "img": rgb}


def heuristic_match(description: str, categories: list[str]) -> tuple[float, list[str]]:
    text = description.lower()
    suggested = [c for c, kws in KEYWORDS.items() if any(k in text for k in kws)]
    if not categories:
        return (0.5 if text else 0.2), suggested
    hits = sum(1 for c in categories if c in suggested)
    return round(0.35 + 0.65 * hits / len(categories), 2), suggested


def model_assess(data: bytes, description: str, categories: list[str]) -> dict[str, Any] | None:
    if not (AI_BASE_URL and AI_MODEL):
        return None
    import httpx
    b64 = base64.b64encode(data).decode()
    prompt = (
        "You assess images submitted to a data marketplace. Reply with JSON only: "
        '{"description_match":0..1,"suggested_categories":[...],"privacy_risk":"none|low|high",'
        '"privacy_notes":"...","quality_notes":"..."}. '
        f"Allowed categories: {', '.join(CATEGORIES)}. Contributor description: {description!r}. "
        f"Declared categories: {categories}. High privacy risk = identifiable faces, licence plates, documents, screens with personal data."
    )
    try:
        r = httpx.post(
            f"{AI_BASE_URL.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {AI_API_KEY}"},
            json={"model": AI_MODEL, "temperature": 0, "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}]},
            timeout=40,
        )
        r.raise_for_status()
        body = r.json()
        txt = body["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", txt, re.S)
        out = json.loads(m.group(0)) if m else {}
        out["request_id"] = r.headers.get("x-request-id") or r.headers.get("request-id") or body.get("id", "")
        out["model"] = AI_MODEL
        out["provider"] = AI_BASE_URL
        return out
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:160]}"}


def assess(data: bytes, description: str, categories: list[str], label: str, existing_phashes: list[str],
           use_model: bool = True) -> dict[str, Any]:
    reasons: list[str] = []
    checks: list[dict[str, Any]] = []
    try:
        st = image_stats(data)
    except Exception as e:
        return {"approved": False, "quality_score": 0, "description_match": 0, "privacy": {"risk": "unknown"},
                "suggested_categories": [], "rejection_reasons": [f"corrupted or unsupported media ({type(e).__name__})"],
                "checks": [{"name": "decode", "ok": False}], "engine": "deterministic"}
    checks.append({"name": "decode", "ok": True, "detail": f"{st['format']} {st['width']}x{st['height']}"})
    res_ok = st["width"] >= 96 and st["height"] >= 96
    checks.append({"name": "resolution", "ok": res_ok, "detail": f"{st['width']}x{st['height']}"})
    if not res_ok:
        reasons.append("resolution below 96px")
    exp_ok = 15 < st["brightness"] < 245
    checks.append({"name": "exposure", "ok": exp_ok, "detail": f"mean luma {st['brightness']:.0f}"})
    if not exp_ok:
        reasons.append("image is over- or under-exposed")
    sharp_ok = st["sharpness"] > 25
    checks.append({"name": "sharpness", "ok": sharp_ok, "detail": f"laplacian var {st['sharpness']:.0f}"})
    if not sharp_ok:
        reasons.append("image is too blurry")
    dup = min((hamming(st["phash"], p) for p in existing_phashes if p), default=64)
    dup_ok = dup > 3
    checks.append({"name": "duplicate", "ok": dup_ok, "detail": f"nearest dHash distance {dup}"})
    if not dup_ok:
        reasons.append("near-duplicate of an existing sample")
    meta_fields = {"description": bool(description.strip()), "categories": bool(categories), "label": bool(label)}
    meta_score = sum(meta_fields.values()) / len(meta_fields)
    checks.append({"name": "metadata", "ok": meta_score >= 0.67, "detail": ", ".join(k for k, v in meta_fields.items() if not v) or "complete"})

    nf = detect_faces(st["img"])
    privacy = {"faces_detected": nf, "risk": "unknown" if nf is None else ("high" if nf else "none"), "engine": _face_engine}
    if nf:
        reasons.append(f"privacy: {nf} identifiable face(s) detected")

    match, suggested = heuristic_match(description, categories)
    engine = "deterministic+keyword-heuristic"
    model = model_assess(data, description, categories) if use_model else None
    if model and "error" not in model:
        match = float(model.get("description_match", match))
        suggested = [c for c in model.get("suggested_categories", []) if c in CATEGORIES] or suggested
        if model.get("privacy_risk") == "high":
            privacy["risk"] = "high"
            reasons.append(f"privacy (model): {model.get('privacy_notes', 'flagged')}")
        privacy["model_notes"] = model.get("privacy_notes", "")
        engine = f"deterministic+model:{model.get('model')}"
    if match < 0.4:
        reasons.append("description does not match media/categories")

    tech = (0.25 * res_ok + 0.2 * exp_ok + 0.3 * min(1.0, st["sharpness"] / 300) + 0.25 * dup_ok)
    quality = round(100 * (0.6 * tech + 0.2 * meta_score + 0.2 * match), 1)
    return {
        "approved": not reasons, "quality_score": quality, "description_match": round(match, 2),
        "privacy": privacy, "suggested_categories": suggested, "rejection_reasons": reasons,
        "checks": checks, "engine": engine, "model": model, "phash": st["phash"],
        "width": st["width"], "height": st["height"],
    }
