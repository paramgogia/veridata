"""Runtime configuration, read from ../.env (repo root) and the process environment."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # backend/
REPO = ROOT.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
(DATA / "blobs").mkdir(exist_ok=True)
(DATA / "previews").mkdir(exist_ok=True)
(DATA / "weights").mkdir(exist_ok=True)


def _load_env_file(p: Path) -> None:
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_env_file(REPO / ".env")


def env(name: str, default: str = "") -> str:
    v = os.environ.get(name, "")
    return v if v else default


def _persistent_secret(name: str, filename: str) -> str:
    v = env(name)
    if v:
        return v
    f = DATA / filename
    if f.exists():
        return f.read_text().strip()
    v = secrets.token_hex(32)
    f.write_text(v)
    return v


DATABASE_URL = env("DATABASE_URL", f"sqlite:///{(DATA / 'veridata.db').as_posix()}")
MASTER_KEY = bytes.fromhex(_persistent_secret("MASTER_KEY_HEX", "master.key"))
SESSION_SECRET = _persistent_secret("SESSION_SECRET", "session.key").encode()
IPFS_API_URL = env("IPFS_API_URL")

CAM_CAPTURE_URL = env("CAM_CAPTURE_URL")
CAM_STREAM_URL = env("CAM_STREAM_URL")
DEVICE_CONTROL_URL = env("DEVICE_CONTROL_URL")

AI_BASE_URL = env("AI_BASE_URL")
AI_API_KEY = env("AI_API_KEY")
AI_MODEL = env("AI_MODEL")

# ---- Chain: a single Veridata.sol deployed from Remix on Ethereum Sepolia ----
CHAIN_ID = int(env("CHAIN_ID", "11155111"))
CHAIN_RPC_URL = env("CHAIN_RPC_URL", "https://ethereum-sepolia-rpc.publicnode.com")
CONTRACT_ADDRESS = env("VERIDATA_CONTRACT_ADDRESS")
EXPLORER_URL = env("EXPLORER_URL", "https://sepolia.etherscan.io")
# Key of the address passed as `verifier` to the constructor. It relays x402 purchases and
# releases escrow payouts. Never commit it.
VERIFIER_PRIVATE_KEY = env("VERIFIER_PRIVATE_KEY")

# DB amounts are integer gwei (1e-9 ETH); the contract uses wei.
GWEI = 10**9
UPLOAD_FEE = int(env("UPLOAD_FEE_GWEI", "100000"))  # 0.0001 ETH, must match the contract
PLATFORM_FEE_BPS = int(env("PLATFORM_FEE_BPS", "500"))
