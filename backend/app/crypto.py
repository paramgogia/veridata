"""Provenance cryptography.

- Canonical JSON (sorted keys, no whitespace) for manifests.
- ES256 (ECDSA P-256 / SHA-256) device signatures, raw r||s hex (64 bytes).
  The same algorithm is used by dev-mode software keys and by the ESP32 firmware
  (mbedtls), so verification is identical for both.
- Merkle root (sha256, sorted pairs) of manifest hashes = dataset contentRoot.
- AES-256-GCM key wrapping with the platform master key.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .config import MASTER_KEY


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------- ES256 ----------

def gen_p256() -> tuple[ec.EllipticCurvePrivateKey, str]:
    k = ec.generate_private_key(ec.SECP256R1())
    return k, pubkey_hex(k.public_key())


def pubkey_hex(pub: ec.EllipticCurvePublicKey) -> str:
    return pub.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint).hex()


def priv_to_bytes(k: ec.EllipticCurvePrivateKey) -> bytes:
    return k.private_numbers().private_value.to_bytes(32, "big")


def priv_from_bytes(b: bytes) -> ec.EllipticCurvePrivateKey:
    return ec.derive_private_key(int.from_bytes(b, "big"), ec.SECP256R1())


def sign_digest_hex(k: ec.EllipticCurvePrivateKey, message: bytes) -> str:
    der = k.sign(message, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    return r.to_bytes(32, "big").hex() + s.to_bytes(32, "big").hex()


def verify_es256(pub_hex: str, message: bytes, sig_hex: str) -> bool:
    try:
        pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), bytes.fromhex(pub_hex))
        raw = bytes.fromhex(sig_hex)
        if len(raw) != 64:
            return False
        der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
        pub.verify(der, message, ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, ValueError):
        return False


def key_fingerprint(pub_hex: str) -> str:
    return sha256_hex(bytes.fromhex(pub_hex))[:16]


# ---------- Merkle ----------

def merkle_root(leaves_hex: list[str]) -> str:
    """sha256 Merkle root over hex leaves; pairs are sorted so proofs are order-free."""
    if not leaves_hex:
        return "0" * 64
    level = sorted(bytes.fromhex(h) for h in leaves_hex)
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level), 2):
            a = level[i]
            b = level[i + 1] if i + 1 < len(level) else level[i]
            lo, hi = sorted((a, b))
            nxt.append(hashlib.sha256(lo + hi).digest())
        level = nxt
    return level[0].hex()


# ---------- AES-GCM ----------

def aes_encrypt(key: bytes, plaintext: bytes, aad: bytes = b"") -> bytes:
    iv = os.urandom(12)
    return iv + AESGCM(key).encrypt(iv, plaintext, aad or None)


def aes_decrypt(key: bytes, blob: bytes, aad: bytes = b"") -> bytes:
    return AESGCM(key).decrypt(blob[:12], blob[12:], aad or None)


def wrap(secret: bytes, context: str) -> str:
    return base64.b64encode(aes_encrypt(MASTER_KEY, secret, context.encode())).decode()


def unwrap(wrapped: str, context: str) -> bytes:
    return aes_decrypt(MASTER_KEY, base64.b64decode(wrapped), context.encode())
