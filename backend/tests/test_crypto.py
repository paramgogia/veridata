"""Tests for the provenance primitives every verification step relies on."""
import hashlib

import pytest
from cryptography.exceptions import InvalidTag

from app import crypto


def test_canonical_is_key_order_independent_and_compact():
    a = crypto.canonical({"b": 1, "a": {"y": 2, "x": [3, "é"]}})
    b = crypto.canonical({"a": {"x": [3, "é"], "y": 2}, "b": 1})
    assert a == b
    assert a == '{"a":{"x":[3,"é"],"y":2},"b":1}'.encode()


def test_es256_sign_and_verify_roundtrip():
    key, pub = crypto.gen_p256()
    assert pub.startswith("04") and len(bytes.fromhex(pub)) == 65
    msg = crypto.canonical({"capture_id": "abc", "media": {"sha256": "00" * 32}})
    sig = crypto.sign_digest_hex(key, msg)
    assert len(bytes.fromhex(sig)) == 64  # raw r||s, same format as the ESP32 firmware
    assert crypto.verify_es256(pub, msg, sig)


def test_es256_rejects_tampered_message_wrong_key_and_bad_signature():
    key, pub = crypto.gen_p256()
    _, other_pub = crypto.gen_p256()
    msg = b'{"a":1}'
    sig = crypto.sign_digest_hex(key, msg)
    assert not crypto.verify_es256(pub, b'{"a":2}', sig)
    assert not crypto.verify_es256(other_pub, msg, sig)
    assert not crypto.verify_es256(pub, msg, sig[:-2])  # wrong length
    assert not crypto.verify_es256(pub, msg, "zz" * 64)  # not hex


def test_private_key_bytes_roundtrip():
    key, pub = crypto.gen_p256()
    restored = crypto.priv_from_bytes(crypto.priv_to_bytes(key))
    assert crypto.pubkey_hex(restored.public_key()) == pub


def test_key_fingerprint():
    _, pub = crypto.gen_p256()
    assert crypto.key_fingerprint(pub) == hashlib.sha256(bytes.fromhex(pub)).hexdigest()[:16]


def _leaf(i: int) -> str:
    return hashlib.sha256(str(i).encode()).hexdigest()


def test_merkle_root_empty_single_and_order_independent():
    assert crypto.merkle_root([]) == "0" * 64
    assert crypto.merkle_root([_leaf(1)]) == _leaf(1)
    leaves = [_leaf(i) for i in range(7)]  # odd count exercises the duplicate-last rule
    assert crypto.merkle_root(leaves) == crypto.merkle_root(list(reversed(leaves)))


def test_merkle_root_matches_manual_two_leaf_computation():
    a, b = bytes.fromhex(_leaf(1)), bytes.fromhex(_leaf(2))
    lo, hi = sorted((a, b))
    assert crypto.merkle_root([_leaf(1), _leaf(2)]) == hashlib.sha256(lo + hi).hexdigest()


def test_merkle_root_changes_when_any_leaf_changes():
    leaves = [_leaf(i) for i in range(5)]
    changed = leaves[:]
    changed[3] = _leaf(99)
    assert crypto.merkle_root(leaves) != crypto.merkle_root(changed)


def test_aes_gcm_roundtrip_and_tamper_detection():
    key = bytes(range(32))
    blob = crypto.aes_encrypt(key, b"secret media", b"sample-1")
    assert crypto.aes_decrypt(key, blob, b"sample-1") == b"secret media"
    with pytest.raises(InvalidTag):
        crypto.aes_decrypt(key, blob, b"sample-2")  # wrong associated data
    flipped = blob[:-1] + bytes([blob[-1] ^ 1])
    with pytest.raises(InvalidTag):
        crypto.aes_decrypt(key, flipped, b"sample-1")


def test_wrap_unwrap_binds_context():
    wrapped = crypto.wrap(b"device-key-bytes", "device:vd-1")
    assert crypto.unwrap(wrapped, "device:vd-1") == b"device-key-bytes"
    with pytest.raises(InvalidTag):
        crypto.unwrap(wrapped, "device:vd-2")
