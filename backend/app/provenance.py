"""Capture manifests and integrity/signature verification.

Manifest (canonical JSON, signed with ES256 by the device key):
  {v, capture_id, device_id, nonce, captured_at, media:{sha256, type, bytes, width, height},
   sensors:{distance_cm, ir, servo_deg}, rfid:[{uid, label?, seen_ms_ago}], meta:{...},
   signer:{alg:"ES256", mode, key_fp}}
manifest_hash = sha256(canonical(manifest)); signature = ES256(canonical(manifest)).

What verification proves: the media bytes are unchanged since signing, and the manifest was
signed by the key registered to that device. It does NOT prove the depicted scene is genuine
(a registered camera can still be pointed at a screen), nor that an RFID tag is authentic.
"""
from __future__ import annotations

import secrets
import time
import uuid
from typing import Any

from sqlalchemy.orm import Session

from . import crypto, storage
from .db import Dataset, Device, Sample

REPLAY_WINDOW_S = 600


def dev_key(dev: Device):
    return crypto.priv_from_bytes(crypto.unwrap(dev.privkey_wrapped, f"device:{dev.id}"))


def build_manifest(dev: Device | None, media: bytes, width: int, height: int, sensors: dict, rfid: list,
                   meta: dict, captured_at: float | None = None, media_type: str = "image/jpeg",
                   media_extra: dict | None = None) -> dict[str, Any]:
    return {
        "v": 1,
        "capture_id": str(uuid.uuid4()),
        "device_id": dev.id if dev else None,
        "nonce": secrets.token_hex(8),
        "captured_at": round(captured_at or time.time(), 3),
        "media": {"sha256": crypto.sha256_hex(media), "type": media_type, "bytes": len(media), "width": width, "height": height,
                  **(media_extra or {})},
        "sensors": sensors,
        "rfid": rfid,
        "meta": meta,
        "signer": {"alg": "ES256", "mode": dev.signing_mode if dev else "none",
                   "key_fp": crypto.key_fingerprint(dev.pubkey_hex) if dev else None},
    }


def sign_manifest_dev(dev: Device, manifest: dict) -> str:
    return crypto.sign_digest_hex(dev_key(dev), crypto.canonical(manifest))


def store_sample(db: Session, *, owner_id: int, media: bytes, manifest: dict | None, signature: str, dev: Device | None,
                 label: str = "", description: str = "", keywords: list | None = None, categories: list | None = None,
                 rfid: list | None = None, sensors: dict | None = None, is_demo: bool = False, phash: str = "",
                 blur_preview: bool = True, media_store: dict | None = None, media_type: str = "image/jpeg",
                 keyframe: bytes | None = None, duration_s: float = 0) -> Sample:
    sid = manifest["capture_id"] if manifest else str(uuid.uuid4())
    if media_store and media_store.get("ref") and media_store.get("wrapped"):
        ref, wrapped = media_store["ref"], media_store["wrapped"]  # already encrypted (+0G-uploaded) by the caller
    else:
        ref, wrapped = storage.put_encrypted(media, sid)
    image = keyframe or media  # video samples: previews and image stats come from the keyframe
    preview = storage.make_preview(image, sid, blur=blur_preview)
    from .quality import image_stats
    st = image_stats(image)
    kf_ref, kf_wrapped = storage.put_encrypted(keyframe, f"{sid}:keyframe") if keyframe else ("", "")
    s = Sample(
        id=sid, device_id=dev.id if dev else None, owner_id=owner_id,
        captured_at=manifest["captured_at"] if manifest else time.time(),
        media_sha256=crypto.sha256_hex(media), media_bytes=len(media), width=st["width"], height=st["height"],
        phash=phash or st["phash"], storage_ref=ref, key_wrapped=wrapped, preview_file=preview,
        storage_root_media=(media_store or {}).get("root", ""), storage_tx=(media_store or {}).get("tx", ""),
        manifest=manifest, manifest_hash=crypto.sha256_hex(crypto.canonical(manifest)) if manifest else "",
        signature=signature, sig_mode=(manifest or {}).get("signer", {}).get("mode", "none") if signature else "none",
        label=label, description=description, keywords=keywords or [], categories=categories or [],
        rfid=rfid or [], sensors=sensors or {}, is_demo=is_demo,
        media_type=media_type, keyframe_ref=kf_ref, keyframe_wrapped=kf_wrapped, duration_s=duration_s,
    )
    db.add(s)
    return s


def sample_image(s: Sample) -> bytes:
    """The still image used for quality checks, previews and training: the keyframe for videos."""
    if s.keyframe_ref:
        return storage.get_decrypted(s.keyframe_ref, s.keyframe_wrapped, f"{s.id}:keyframe")
    return storage.get_decrypted(s.storage_ref, s.key_wrapped, s.id)


def verify_sample(db: Session, s: Sample, media_override: bytes | None = None) -> dict[str, Any]:
    """Real integrity + signature verification. Each step reports what it checked."""
    steps: list[dict[str, Any]] = []

    def step(name: str, ok: bool | None, detail: str):
        steps.append({"name": name, "ok": ok, "detail": detail})

    try:
        media = media_override if media_override is not None else storage.get_decrypted(s.storage_ref, s.key_wrapped, s.id)
        step("decrypt", True, f"AES-256-GCM authenticated decrypt of {s.storage_ref[:28]}…")
    except Exception as e:
        step("decrypt", False, f"storage/decrypt failed: {type(e).__name__}")
        return {"valid": False, "steps": steps}

    actual = crypto.sha256_hex(media)
    m = s.manifest
    if not m:
        step("manifest", False, "no signed capture manifest — provenance unknown")
        step("content_hash", actual == s.media_sha256, f"sha256 {actual[:16]}… vs recorded {s.media_sha256[:16]}…")
        return {"valid": False, "steps": steps, "computed_sha256": actual}

    step("content_hash", actual == m["media"]["sha256"],
         f"computed {actual[:20]}… {'==' if actual == m['media']['sha256'] else '!='} manifest {m['media']['sha256'][:20]}…")
    kf_sha = m["media"].get("keyframe_sha256")
    if kf_sha:
        try:
            kf = storage.get_decrypted(s.keyframe_ref, s.keyframe_wrapped, f"{s.id}:keyframe")
            got = crypto.sha256_hex(kf)
            step("keyframe_hash", got == kf_sha, f"video keyframe {got[:16]}… {'==' if got == kf_sha else '!='} manifest {kf_sha[:16]}…")
        except Exception as e:
            step("keyframe_hash", False, f"keyframe missing or undecryptable: {type(e).__name__}")
    mh = crypto.sha256_hex(crypto.canonical(m))
    step("manifest_hash", mh == s.manifest_hash, f"sha256(canonical manifest) = {mh[:20]}…")

    dev = db.get(Device, m.get("device_id")) if m.get("device_id") else None
    if not dev:
        step("device", False, "device not found in registry")
        return {"valid": False, "steps": steps, "computed_sha256": actual}
    step("device", dev.status == "registered",
         f"{dev.id} · {dev.status} · registration {dev.registration_mode}{(' ' + dev.registration_tx[:12] + '…') if dev.registration_tx else ''}")
    fp_ok = m["signer"].get("key_fp") == crypto.key_fingerprint(dev.pubkey_hex)
    step("key_binding", fp_ok, f"manifest key fp {m['signer'].get('key_fp')} vs registered {crypto.key_fingerprint(dev.pubkey_hex)}")
    sig_ok = bool(s.signature) and crypto.verify_es256(dev.pubkey_hex, crypto.canonical(m), s.signature)
    mode = m["signer"].get("mode")
    step("signature", sig_ok, f"ES256 P-256 signature {'valid' if sig_ok else 'INVALID'} · signer mode: {mode}"
         + (" (development software key held by the platform — not hardware-backed)" if mode == "dev-software" else ""))
    dup = db.query(Sample).filter(Sample.manifest_hash == s.manifest_hash, Sample.id != s.id).count()
    step("replay", dup == 0, "manifest nonce/capture_id unique" if dup == 0 else f"manifest reused by {dup} other sample(s)")
    valid = all(x["ok"] for x in steps if x["ok"] is not None)
    return {"valid": valid, "steps": steps, "computed_sha256": actual, "signer_mode": mode,
            "note": "Verifies integrity and device signature only — not that the depicted event is genuine."}


def dataset_root(db: Session, ds: Dataset) -> tuple[str, int]:
    leaves = [x.manifest_hash or x.media_sha256 for x in db.query(Sample).filter(Sample.dataset_id == ds.id).all()]
    return crypto.merkle_root(leaves), len(leaves)
