"""Encrypted media storage.

Every media file gets its own random AES-256-GCM key; the ciphertext is content-addressed
by sha256(ciphertext) and written to backend/data/blobs. If IPFS_API_URL points at a Kubo
node, the ciphertext is also pinned to IPFS and the storage ref becomes ipfs://<cid>.
Only ciphertext ever leaves the process; plaintext is produced in memory for verification
and in-platform training only.
"""
from __future__ import annotations

import io
import os

import httpx
from PIL import Image, ImageFilter, ImageDraw

from . import crypto
from .config import DATA, IPFS_API_URL

BLOBS = DATA / "blobs"
PREVIEWS = DATA / "previews"


def put_encrypted(plaintext: bytes, aad: str) -> tuple[str, str]:
    """Returns (storage_ref, wrapped_key)."""
    key = os.urandom(32)
    blob = crypto.aes_encrypt(key, plaintext, aad.encode())
    digest = crypto.sha256_hex(blob)
    (BLOBS / digest).write_bytes(blob)
    ref = f"local://{digest}"
    if IPFS_API_URL:
        try:
            r = httpx.post(f"{IPFS_API_URL}/api/v0/add?pin=true&cid-version=1", files={"file": blob}, timeout=10)
            r.raise_for_status()
            ref = f"ipfs://{r.json()['Hash']}#sha256={digest}"
        except Exception:
            pass  # fall back to local content-addressed storage
    return ref, crypto.wrap(key, f"media:{aad}")


def _local_digest(ref: str) -> str:
    if ref.startswith("local://"):
        return ref[len("local://"):]
    if "#sha256=" in ref:
        return ref.split("#sha256=")[1]
    raise ValueError("unknown storage ref")


def get_ciphertext(ref: str) -> bytes:
    p = BLOBS / _local_digest(ref)
    if p.exists():
        return p.read_bytes()
    if ref.startswith("ipfs://") and IPFS_API_URL:
        cid = ref[len("ipfs://"):].split("#")[0]
        r = httpx.post(f"{IPFS_API_URL}/api/v0/cat?arg={cid}", timeout=20)
        r.raise_for_status()
        return r.content
    raise FileNotFoundError(ref)


def get_decrypted(ref: str, wrapped_key: str, aad: str) -> bytes:
    key = crypto.unwrap(wrapped_key, f"media:{aad}")
    return crypto.aes_decrypt(key, get_ciphertext(ref), aad.encode())


def make_preview(image_bytes: bytes, name: str, blur: bool = True) -> str:
    """Privacy-safe preview: downscaled, lightly blurred and watermarked. Stored unencrypted."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img.thumbnail((320, 240))
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(1.6))
    d = ImageDraw.Draw(img)
    d.rectangle([0, img.height - 16, img.width, img.height], fill=(10, 12, 16))
    d.text((6, img.height - 14), "VERIDATA PREVIEW · training-only", fill=(160, 170, 185))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=70)
    fname = f"{name}.jpg"
    (PREVIEWS / fname).write_bytes(out.getvalue())
    return fname
