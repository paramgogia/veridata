"""0G (Galileo testnet) integration: decentralized storage + confidential compute.

Storage: ciphertext and canonical manifests are uploaded through the storage
indexer; the returned root hash is a content address anyone can resolve. If a
wallet key is configured, storage is on 0G; otherwise everything stays local
(seed data never touches 0G).

Compute: the quality VLM can run (a) against any OpenAI-compatible endpoint via
AI_BASE_URL (OpenAI, Meta, 0G Router), or (b) against a TEE provider settled
on-chain through the 0G compute broker (needs >= 3 0G in the wallet ledger).
Resolution is cached and degrades gracefully to the keyword heuristic.
"""
from __future__ import annotations

import os
import tempfile
import time
import threading
from typing import Any

from . import config, storage

_lock = threading.Lock()

# The 0G storage SDK reads/writes files with os.pread/os.pwrite, which exist only on POSIX.
# On Windows, emulate them with seek + read/write under a lock (same semantics for our use).
if not hasattr(os, "pread"):
    _pio_lock = threading.Lock()

    def _pread(fd: int, n: int, offset: int) -> bytes:
        with _pio_lock:
            pos = os.lseek(fd, 0, os.SEEK_CUR)
            try:
                os.lseek(fd, offset, os.SEEK_SET)
                chunks, left = [], n
                while left > 0:
                    b = os.read(fd, left)
                    if not b:
                        break
                    chunks.append(b)
                    left -= len(b)
                return b"".join(chunks)
            finally:
                os.lseek(fd, pos, os.SEEK_SET)

    def _pwrite(fd: int, data: bytes, offset: int) -> int:
        with _pio_lock:
            pos = os.lseek(fd, 0, os.SEEK_CUR)
            try:
                os.lseek(fd, offset, os.SEEK_SET)
                return os.write(fd, data)
            finally:
                os.lseek(fd, pos, os.SEEK_SET)

    os.pread = _pread    # type: ignore[attr-defined]
    os.pwrite = _pwrite  # type: ignore[attr-defined]
_ai_cache: tuple[float, dict[str, str] | None] = (0.0, None)
VISION_HINT = ("omni", "vision", "glm-4.5", "glm-5", "gemma", "vlm", "vl-", "multimodal")
# The 0G compute ledger contract requires this minimum to even create a ledger.
MIN_COMPUTE_LEDGER_0G = 3


def enabled() -> bool:
    """Storage is on 0G only when a signing wallet is configured."""
    return bool(config.WALLET_PRIVATE_KEY)


def _evm():
    from zg_storage import EvmClient
    return EvmClient(rpc_url=config.ZEROG_RPC_URL, private_key=config.WALLET_PRIVATE_KEY)


def _indexer():
    from zg_storage import IndexerClient
    return IndexerClient(config.ZEROG_STORAGE_INDEXER_URL, evm_client=_evm(), flow_address=config.ZEROG_FLOW_ADDRESS)


def upload_bytes(data: bytes, name: str) -> tuple[str, str]:
    """Upload raw bytes to 0G storage. Returns (tx_hash, root_hash)."""
    if not enabled():
        raise RuntimeError("0G storage disabled: no wallet key configured")
    with tempfile.NamedTemporaryFile(suffix=f"-{name}", delete=False) as f:
        f.write(data)
        tmp = f.name
    try:
        from zg_storage import UploadOption
        tx, root, _size = _indexer().upload(tmp, tags=b"veridata",
                                            option=UploadOption(finality_required="file_finalized", fast_mode=True))
        return tx, root
    finally:
        os.unlink(tmp)


def download_bytes(root: str) -> bytes:
    """Resolve a root hash from 0G storage. Raises on failure."""
    with tempfile.TemporaryDirectory() as d:
        target = os.path.join(d, "blob")
        from zg_storage import IndexerDownloader
        IndexerDownloader(_indexer()).download(root, target)
        return open(target, "rb").read()


def store_media(media: bytes, aad: str) -> dict[str, Any]:
    """Encrypt media (local, as before), then upload the ciphertext to 0G.

    Returns {"ref", "wrapped", "root", "tx"} where `root` is the 0G root hash
    of the ciphertext (resolvable by anyone) and `tx` the storage transaction.
    """
    ref, wrapped = storage.put_encrypted(media, aad)
    out: dict[str, Any] = {"ref": ref, "wrapped": wrapped, "root": "", "tx": ""}
    if not enabled():
        return out
    try:
        with _lock:
            digest = ref.removeprefix("local://")
            ciphertext = (storage.BLOBS / digest).read_bytes()
        tx, root = upload_bytes(ciphertext, f"{aad}.jpg.enc")
        out.update({"root": root, "tx": tx})
    except Exception as e:  # 0G outage must never break capture: fall back to local
        out["error"] = f"{type(e).__name__}: {str(e)[:120]}"
    return out


# ---------------- compute (TEE inference via the 0G broker) ----------------

def wallet_balance_0g() -> int:
    from web3 import Web3
    from eth_account import Account
    w3 = Web3(Web3.HTTPProvider(config.ZEROG_RPC_URL, request_kwargs={"timeout": 15}))
    acct = Account.from_key(config.WALLET_PRIVATE_KEY)
    return w3.eth.get_balance(acct.address)


def compute_status() -> dict[str, Any]:
    """Report for /api/config: what the compute layer will do."""
    if config.AI_BASE_URL and config.AI_MODEL:
        return {"mode": "explicit", "provider": config.AI_BASE_URL, "model": config.AI_MODEL}
    if not (enabled() and config.ZEROG_COMPUTE_AUTO):
        return {"mode": "off", "reason": "no AI_BASE_URL and 0G compute auto-disabled"}
    bal = wallet_balance_0g()
    if bal < MIN_COMPUTE_LEDGER_0G * 10**18:
        return {"mode": "unfunded", "reason": f"wallet holds {bal / 1e18:.2f} 0G; the compute ledger needs >= {MIN_COMPUTE_LEDGER_0G} 0G",
                "suggest": "top up the wallet (faucet.0g.ai) or set AI_BASE_URL/AI_MODEL to any OpenAI-compatible endpoint"}
    return {"mode": "broker", "reason": "will resolve a TEE vision provider via the 0G compute broker"}


def ai_config(ttl: int = 1800) -> dict[str, str] | None:
    """Resolve the AI endpoint for quality checks.

    Priority: explicit AI_BASE_URL/AI_MODEL (OpenAI, Meta, 0G Router, …) →
    0G compute broker TEE provider (wallet-settled) → None (keyword heuristic).
    """
    if config.AI_BASE_URL and config.AI_MODEL:
        return {"base_url": config.AI_BASE_URL, "api_key": config.AI_API_KEY, "model": config.AI_MODEL, "engine": "explicit"}
    if not (enabled() and config.ZEROG_COMPUTE_AUTO):
        return None
    now = time.time()
    if _ai_cache[0] > now - ttl:
        return _ai_cache[1]
    if wallet_balance_0g() < MIN_COMPUTE_LEDGER_0G * 10**18:
        _ai_cache = (now, None)  # underfunded: degrade to heuristics, retry later
        return None
    cfg = _resolve_broker()
    _ai_cache = (now, cfg)
    return cfg


def _resolve_broker() -> dict[str, str] | None:
    """Pick a vision-capable TEE provider and obtain its app secret."""
    import zerog_py_sdk as z
    try:
        broker = z.create_broker(config.WALLET_PRIVATE_KEY, network="testnet", rpc_url=config.ZEROG_RPC_URL)
        services = broker.inference.list_service()
        svc = next((s for s in services if any(h in s.model.lower() for h in VISION_HINT)), services[0] if services else None)
        if svc is None:
            return None
        # Ensure the ledger exists and this provider is funded + acknowledged.
        detail = broker.ledger.get_ledger_with_detail()  # raises until created
        if int(detail.total_balance) == 0:
            broker.ledger.add_ledger(str(MIN_COMPUTE_LEDGER_0G))
        try:
            broker.inference.acknowledge_provider_signer(svc.provider)
        except Exception:
            pass
        try:
            broker.ledger.transfer_fund(svc.provider, "inference", int(1e18))
        except Exception:
            pass  # may already be funded
        secret = broker.inference.get_secret(svc.provider)
        return {"base_url": f"{svc.url.rstrip('/')}/v1/proxy", "api_key": secret, "model": svc.model, "engine": "0g-tee"}
    except Exception:
        return None
