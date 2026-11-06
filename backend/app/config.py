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

# ---- 0G (Galileo testnet): decentralized storage + confidential compute ----
ZEROG_RPC_URL = env("0G_RPC_URL", "https://evmrpc-testnet.0g.ai")
ZEROG_STORAGE_INDEXER_URL = env("0G_STORAGE_INDEXER_URL", "https://indexer-storage-testnet-turbo.0g.ai")
ZEROG_FLOW_ADDRESS = env("0G_FLOW_ADDRESS", "0x22E03a6A89B950F1c82ec5e74F8eCa321a105296")
ZEROG_CHAIN_ID = int(env("0G_CHAIN_ID", "16602"))
ZEROG_EXPLORER = env("0G_EXPLORER", "https://storagescan-galileo.0g.ai")
# Wallet used for 0G storage txs (and previously the Sepolia verifier role).
# VERIFIER_PRIVATE_KEY is the legacy name kept for compatibility.
WALLET_PRIVATE_KEY = env("WALLET_PRIVATE_KEY") or env("VERIFIER_PRIVATE_KEY")
# Auto-resolve a TEE inference provider via the 0G compute broker when no
# explicit AI_BASE_URL is configured. Requires >= 3 0G in the wallet ledger.
ZEROG_COMPUTE_AUTO = env("0G_COMPUTE_AUTO", "1") == "1"

# ---- Chain: a single Veridata.sol deployed from Remix on Ethereum Sepolia ----
CHAIN_ID = int(env("CHAIN_ID", "11155111"))
CHAIN_RPC_URL = env("CHAIN_RPC_URL", "https://ethereum-sepolia-rpc.publicnode.com")
CONTRACT_ADDRESS = env("VERIDATA_CONTRACT_ADDRESS")
EXPLORER_URL = env("EXPLORER_URL", "https://sepolia.etherscan.io")
# No platform private key: every transaction is signed in the user's wallet.

# DB amounts are integer gwei (1e-9 ETH); the contract uses wei.
GWEI = 10**9
UPLOAD_FEE = int(env("UPLOAD_FEE_GWEI", "100000"))  # 0.0001 ETH, must match the contract
PLATFORM_FEE_BPS = int(env("PLATFORM_FEE_BPS", "500"))

# ---- Whitechain Sepolia (chain 1874): gasless USDT license checkout (VeridataPay.sol) ----
WC_CHAIN_ID = int(env("WHITECHAIN_CHAIN_ID", "1874"))
WC_RPC_URL = env("WHITECHAIN_RPC_URL", "https://rpc.testnet.whitechain.io")
WC_EXPLORER = env("WHITECHAIN_EXPLORER", "https://explorer.testnet.whitechain.io")
WC_PAY_ADDRESS = env("WHITECHAIN_PAY_ADDRESS")  # VeridataPay deployed from Remix
WC_USDT = env("WHITECHAIN_USDT", "0xcedfB56113143d55b2358b8CFbB0dEB5Ad2f55a7")  # prize-qualifying USDT (6 dp)
WC_USDT_NAME = env("WHITECHAIN_USDT_NAME", "Tether USD")  # EIP-712 domain, verified against DOMAIN_SEPARATOR
WC_USDT_VERSION = env("WHITECHAIN_USDT_VERSION", "1")
# Relayer: pays WBT gas for buyers. Defaults to the backend wallet already used for 0G.
WC_RELAYER_KEY = env("WHITECHAIN_RELAYER_KEY") or WALLET_PRIVATE_KEY
# Price conversion for datasets priced in gwei: USDT per 1 ETH of list price.
WC_USDT_PER_ETH = float(env("WHITECHAIN_USDT_PER_ETH", "100"))
# Drain protection
WC_MAX_GAS_GWEI = float(env("WHITECHAIN_MAX_GAS_GWEI", "50"))      # refuse if gas price spikes above this
WC_GAS_LIMIT = int(env("WHITECHAIN_GAS_LIMIT", "250000"))           # hard per-tx gas cap
WC_DAILY_TX_CAP = int(env("WHITECHAIN_DAILY_TX_CAP", "200"))        # relayed purchases per day
WC_PER_BUYER_HOURLY = int(env("WHITECHAIN_PER_BUYER_HOURLY", "10")) # relayed purchases per buyer per hour
WC_MIN_RELAYER_WBT = float(env("WHITECHAIN_MIN_RELAYER_WBT", "0.01"))  # pause relaying below this balance

# ---- Arkiv (Rabdi testnet — decentralised DB-chain for marketplace data) ----
ARKIV_ACCESS_KEY = env("ARKIV_ACCESS_KEY")
ARKIV_PRIVATE_KEY = env("ARKIV_PRIVATE_KEY")  # same wallet or a dedicated one
ARKIV_RPC_URL = env("ARKIV_RPC_URL", "https://rpc.rabdi.db-chain.testnet.arkiv.network")
