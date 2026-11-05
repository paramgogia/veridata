# Veridata

**A decentralized, demand-driven marketplace for verifiable real-world AI training data.**

Capture → Verify → Monetize → Train → Export.

Buyers post funded requests ("2,000 clips of heavy rain at night on rural roads, 0.0005 ETH per accepted clip") and the reward sits in on-chain escrow. Contributors capture with registered ESP32 rigs (camera, ultrasonic, IR, RFID, servo). Each capture gets a manifest signed by the device's P-256 key. Every sample is verified for integrity, signature, quality and privacy, and each accepted sample releases a payout. Buyers fine-tune models on licensed data inside a controlled Training Room. They can never download the raw media, but they can export the trained weights.

| | |
|---|---|
| Frontend | Next.js 14, React, TypeScript, Tailwind, wagmi/viem (Sepolia) |
| Backend | FastAPI, SQLAlchemy (SQLite by default, Postgres via `DATABASE_URL`), web3.py |
| Contract | One self-contained `contracts/Veridata.sol`, deployed from **Remix** to **Ethereum Sepolia** |
| Crypto | ES256 (P-256) device signatures, sha256 Merkle roots, AES-256-GCM per-file encryption |
| AI | PyTorch fine-tuning (Veri-CNN-S, ResNet-18); OpenAI-compatible VLM for quality checks (0G Private Computer recommended) |
| Hardware | ESP32-CAM (stock CameraWebServer) + ESP32 main board running `firmware/veridata_main` |

---

## Quick start (local, no chain needed)

```bash
# 1. Backend  (Python 3.11+)
cd backend
python -m venv .venv && .venv/Scripts/activate      # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m app.seed --reset                          # synthetic demo data (clearly flagged)
uvicorn app.main:app --port 8000

# 2. Frontend
cd web
npm install
npm run dev                                         # http://localhost:3000
```

Sign in with a **demo persona** (Asha Farms = contributor, Northwind Robotics = buyer). Demo personas settle on an off-chain **demo ledger**, and every amount in the UI is labelled *Demo ledger*, *Demo data* or *On-chain · Sepolia*.

The demo contributor owns a **simulated** device (labelled SIMULATED), so you can run the full capture workflow without hardware.

## On-chain mode (Remix + Sepolia)

1. Open `contracts/Veridata.sol` in [Remix](https://remix.ethereum.org). Compile with Solidity 0.8.24+; the optimizer is recommended.
2. Deploy with **Injected Provider (MetaMask) on Sepolia**. Constructor arguments:
   - `_verifier`: the backend's relayer address. Its key goes in `VERIFIER_PRIVATE_KEY`; fund it with ~0.05 Sepolia ETH for gas.
   - `_treasury`: the address that receives platform fees.
   - `_uploadFee`: `100000000000000` (0.0001 ETH, in wei).
   - `_feeBps`: `500` (5%).
3. Copy `.env.example` to `.env` at the repo root and set `VERIDATA_CONTRACT_ADDRESS`, `VERIFIER_PRIVATE_KEY`, and `CHAIN_RPC_URL` if you use your own RPC.
4. Restart the backend. The header pill turns blue (**Sepolia**). Sign in with **Connect wallet**, then choose **Settle via → Sepolia (wallet)** for device registration, dataset publishing, purchases, request escrow and refunds.

What settles on-chain:

| Action | Who signs | Contract call |
|---|---|---|
| Register device key | device owner's wallet | `registerDevice(keccak(id), pubkey, meta)` |
| Publish dataset | contributor's wallet (pays upload fee) | `publishDataset(contentRoot, price, storageRef)` |
| Buy license | buyer's wallet | `purchaseLicense(id)` |
| Buy license via **x402** | buyer signs an EIP-712 intent; the facilitator relays it | `depositCredit()` once, then `purchaseLicenseWithSig(...)` |
| Fund request | buyer's wallet | `createRequest(specHash, price, qty, deadline)` |
| Accepted sample payout | backend verifier (after checks) | `acceptSample(reqId, sampleHash, contributor)` |
| Refund | buyer's wallet | `closeAndRefund(reqId)` |

The backend verifies each user transaction's receipt and decoded event, checking that the sender, content root, spec hash and amount match, before it records anything.

## Hardware

See [docs/HARDWARE.md](docs/HARDWARE.md). In short: flash the stock **CameraWebServer** to the ESP32-CAM and `firmware/veridata_main` to the main ESP32. Then register a *hardware* device with the CAM and board URLs. If the board answers `/pubkey`, manifests are signed **on the ESP32** (`device-hardware`). Otherwise the platform generates a clearly labelled **dev-software** key.

## Demo script (≈5 min)

1. **Demand Board** (`/`): the highest-value request, escrow totals, trending categories.
2. **Devices** → the rig → **live stream**, ultrasonic/IR readings, servo slider, and an RFID tag held to the reader (associate it with a SKU).
3. **Capture & sign** → inspect the signed manifest (sha256, sensors, RFID, ES256 signature) → **Verify sample**.
4. **/upload?request=3** (retail RFID request): describe → run AI quality & privacy checks → submit → accepted, with the payout and Sepolia tx link (or the demo ledger).
5. **Tamper demo** (`/demo/insurance`): 6 claim photos, 3 valid and 3 rejected (no manifest / foreign key / edited). **Modify one pixel** → hash mismatch.
6. As the buyer: **Marketplace** → dataset → **Proof Card → Verify now** (Merkle root recomputed and compared on-chain) → buy (wallet or x402).
7. **Training Room** → pick licensed datasets → Veri-CNN-S → train (real PyTorch, live loss/accuracy) → before/after → **download weights + model card**.
8. **Attempt raw dataset export** → `403`, written to the audit log.

## Repository

```
contracts/Veridata.sol        single contract (Remix), ABI alongside
backend/app/                  FastAPI app: routers/, provenance, quality, training, storage, chain/
backend/scripts/x402_agent.py autonomous x402 buyer
web/src/app/                  all routes (see docs/ARCHITECTURE.md)
firmware/veridata_main/       ESP32 main-board firmware (sensors, servo, RFID, ES256 signing)
docs/                         architecture, security, hardware, sponsors, checklist
```

## Honest limitations

- **Provenance ≠ authenticity.** Signatures prove that bytes are unchanged and came from a registered key, not that the scene is real. RFID proves a tag was read, not who owns the object.
- **dev-software** keys are held encrypted by the platform. Only `device-hardware` keys live on the ESP32 (in NVS; enable flash encryption for production). The firmware has not yet been compiled or validated on the physical rig.
- The training isolation is a **process plus API boundary**, not a TEE. Exported weights can memorize training data; the UI reports a generalization-gap indicator, not a guarantee.
- The verifier/facilitator is a **trusted platform role** in the contract.
- Storage is AES-GCM encrypted and content-addressed on local disk, with optional IPFS pinning (`IPFS_API_URL`). No other decentralized storage network is integrated.
- The contract is **not audited**. Rate limits and replay caches are in-memory.
- Sponsor integrations are documented in [docs/SPONSORS.md](docs/SPONSORS.md), including what we evaluated and did not build.
