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

def wallet_balance_0g(network: str = "testnet") -> int:
    from web3 import Web3
    from eth_account import Account
    import zerog_py_sdk as z
    rpc = config.ZEROG_RPC_URL if network == "testnet" else z.get_rpc_url("mainnet")
    w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 15}))
    acct = Account.from_key(config.WALLET_PRIVATE_KEY)
    return w3.eth.get_balance(acct.address)


TESTNET_RPC_FALLBACKS = [config.ZEROG_RPC_URL, "https://0g-galileo.drpc.org"]


def broker(network: str = "testnet"):
    """0G compute broker for the given network (contract addresses are built into the SDK).

    The public Galileo RPC drops connections intermittently — try the fallbacks in order."""
    import zerog_py_sdk as z
    rpcs = TESTNET_RPC_FALLBACKS if network == "testnet" else [z.get_rpc_url("mainnet")]
    last: Exception | None = None
    for rpc in rpcs:
        try:
            return z.create_broker(config.WALLET_PRIVATE_KEY, network=network, rpc_url=rpc)
        except Exception as e:
            last = e
    raise last or RuntimeError("no 0G RPC reachable")


_ft_cache: dict[str, Any] = {"data": None, "at": 0.0}
_ft_lock = threading.Lock()


def ft_status() -> dict[str, Any]:
    """Read-only status of the 0G TEE fine-tuning pipeline (no txs).

    The 0G RPC and provider hosts are flaky — this never blocks the API:
    a 20s timeout guards the refresh, results are cached for 20s, and on
    failure the last good snapshot (or a clear error) is returned."""
    now = time.time()
    with _ft_lock:
        if _ft_cache["data"] is not None and now - _ft_cache["at"] < 20:
            return _ft_cache["data"]
    result: dict[str, Any] = {}

    def run() -> None:
        try:
            result["data"] = _ft_refresh()
        except Exception as e:  # noqa: BLE001 - keep the endpoint alive
            result["error"] = f"{type(e).__name__}: {str(e)[:160]}"

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout=20)  # never block the API longer than this; refresh finishes in background
    with _ft_lock:
        if result.get("data"):
            _ft_cache["data"], _ft_cache["at"] = result["data"], time.time()
            return result["data"]
        if _ft_cache["data"] is not None:
            d = dict(_ft_cache["data"])
            d["stale"] = True
            d["error"] = d.get("error") or "0G RPC slow — showing cached status"
            return d
        return {"enabled": enabled(), "network": "testnet", "provider": "", "funding": {},
                "tasks": [], "error": result.get("error") or "0G unreachable — status will appear when the network recovers"}


def _ft_refresh() -> dict[str, Any]:
    """One full status refresh; may take a while and runs inside a timeout guard."""
    out: dict[str, Any] = {"enabled": enabled(), "network": "testnet", "provider": "", "funding": {}, "tasks": [], "error": ""}
    if not enabled():
        return out
    try:
        b = broker("testnet")
        svcs = b.fine_tuning.list_service()
        if not svcs:
            out["error"] = "no fine-tuning provider registered"
            return out
        provider = svcs[0].provider
        out["provider"] = provider
        bal = wallet_balance_0g("testnet")
        out["funding"]["wallet_0g"] = round(bal / 1e18, 4)
        out["funding"]["min_ledger_0g"] = MIN_COMPUTE_LEDGER_0G
        try:
            det = b.ledger.get_ledger_with_detail()
            out["funding"]["ledger_total_0g"] = round(int(det.total_balance) / 1e18, 4)
        except Exception:
            out["funding"]["ledger_total_0g"] = 0
        try:
            acc = b.fine_tuning.get_account(provider)
            d = getattr(acc, "account", acc) or acc
            out["funding"]["provider_balance_0g"] = round(int(getattr(d, "balance", 0)) / 1e18, 4)
        except Exception:
            out["funding"]["provider_balance_0g"] = 0
        tasks = b.fine_tuning.list_task(provider)
        for t in (tasks if isinstance(tasks, list) else [tasks]):
            out["tasks"].append({
                "id": getattr(t, "id", ""),
                "created_at": getattr(t, "created_at", ""),
                "progress": getattr(t, "progress", ""),
                "deliver_index": getattr(t, "deliver_index", 0),
                "fee_0g": round(int(getattr(t, "fee", 0) or 0) / 1e18, 6),
                "params": getattr(t, "training_params", ""),
            })
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {str(e)[:160]}"
    return out


def fund_provider(provider_address: str, service_type: str, amount_wei: int, network: str = "testnet") -> str:
    """Create/fund a provider sub-account in the compute ledger.

    Sends transferFund with 2M gas — the SDK's 300k default is too low for the
    account-creation path (needs ~1.6M). Resolves the ledger's on-chain service
    name (e.g. \"fine-tuning-v1.1\") so the transfer doesn't revert ServiceNotFound."""
    from web3 import Web3
    b = broker(network)
    name = b.ledger._resolve_service_name(service_type, "fund_provider")
    w3 = b.ledger.web3
    c = b.ledger.contract
    acct = b.ledger.account
    tx = c.functions.transferFund(Web3.to_checksum_address(provider_address), name, int(amount_wei)).build_transaction(
        {"from": acct.address, "nonce": w3.eth.get_transaction_count(acct.address), "gas": 2000000})
    h = w3.eth.send_raw_transaction(acct.sign_transaction(tx).raw_transaction)
    rcpt = w3.eth.wait_for_transaction_receipt(h, timeout=300)
    if rcpt.status != 1:
        raise RuntimeError("transferFund reverted")
    return "0x" + h.hex().removeprefix("0x")


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
