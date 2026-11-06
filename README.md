# Veridata

**A decentralized, demand-driven marketplace for verifiable real-world AI training data.**

Capture → Verify → Monetize → Train → Export.

Buyers post funded requests ("2,000 clips of heavy rain at night on rural roads, 0.0005 ETH per accepted clip") and the reward sits in on-chain escrow. Contributors capture with registered ESP32 rigs (camera, ultrasonic, IR, RFID, servo). Each capture gets a manifest signed by the device's P-256 key. Every sample is verified for integrity, signature, quality and privacy; the buyer then releases the escrowed payout for verified samples from their own wallet. Buyers fine-tune models on licensed data inside a controlled Training Room. They can never download the raw media, but they can export the trained weights.

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

## 0G integration (Galileo testnet)

With `WALLET_PRIVATE_KEY` (or the legacy `VERIFIER_PRIVATE_KEY`) in `.env`:

- **Storage** — every live capture is encrypted (AES-256-GCM, unchanged), the ciphertext is
  uploaded to 0G Storage through the Galileo indexer, and the root hash lands **inside the
  signed manifest's media block**; the canonical manifest is uploaded too. `GET /api/zerog/manifest/{root}`
  resolves any manifest by root, and the Proof Card's verify adds a `zerog_root` step that
  re-derives the dataset Merkle root from 0G-resolved manifests, independent of the platform DB.
- **Compute** — the quality VLM runs against any OpenAI-compatible endpoint
  (`AI_BASE_URL`/`AI_API_KEY`/`AI_MODEL`), e.g. the 0G Private Computer router
  (`https://router-api.0g.ai/v1`); request IDs are stored with each assessment and shown in the UI.
  With no explicit endpoint and >= 3 0G in the wallet, the backend auto-resolves a TEE provider
  through the 0G compute broker. Otherwise the deterministic+keyword heuristic is used and labelled.
- **Fine-tuning** — `backend/scripts/zerog_finetune.py` exports a licensed dataset, fine-tunes
  inside a 0G TEE provider and deploys the adapter as a served agent (needs the 3 0G ledger).
- **Deploy** — `backend/scripts/deploy_contract.py` compiles-deploys `contracts/Veridata.sol`
  from the wallet in `.env` and patches `VERIDATA_CONTRACT_ADDRESS` on success.

Seed data never touches 0G (labelled `demo-seed`); only live captures do.

## On-chain mode (Remix + Sepolia)

1. Open `contracts/Veridata.sol` in [Remix](https://remix.ethereum.org). Compile with Solidity 0.8.24+; the optimizer is recommended.
2. Deploy with **Injected Provider (MetaMask) on Sepolia**. Constructor arguments:
   - `_treasury`: the address that receives platform fees (`0x0000000000000000000000000000000000000000` = the deployer).
   - `_uploadFee`: `100000000000000` (0.0001 ETH, in wei).
   - `_feeBps`: `500` (5%).
3. Copy `.env.example` to `.env` at the repo root and set `VERIDATA_CONTRACT_ADDRESS` (and `CHAIN_RPC_URL` if you use your own RPC). **No private key is needed anywhere**: every transaction is signed in a user's wallet.
4. Restart the backend. The header pill turns blue (**Sepolia**). Sign in with **Connect wallet**, then choose **Settle via → Sepolia (wallet)** for device registration, dataset publishing, purchases, request escrow and refunds.

What settles on-chain:

| Action | Who signs | Contract call |
|---|---|---|
| Register device key | device owner's wallet | `registerDevice(keccak(id), pubkey, meta)` |
| Publish dataset | contributor's wallet (pays upload fee) | `publishDataset(contentRoot, price, storageRef)` |
| Buy license | buyer's wallet | `purchaseLicense(id)` |
| Fund request | buyer's wallet | `createRequest(specHash, price, qty, deadline)` |
| Pay verified samples | buyer's wallet (after the backend's checks pass) | `releasePayouts(reqId, sampleHashes[], contributors[])` |
| Refund | buyer's wallet | `closeAndRefund(reqId)` |

The backend verifies each user transaction's receipt and decoded event, checking that the sender, content root, spec hash, amount and paid sample hashes match, before it records anything.

## Whitechain: gasless USDT checkout for people and AI agents (Scale track)

**Why this needs on-chain stablecoins:** an AI training agent has to buy a dataset license per request, by itself, at 2 a.m., with no merchant account, card or invoice. A signed USDT authorization settles in seconds, and the license is enforced by the contract, not by our database.

**Flow (zero crypto steps for the payer):**
1. The agent (or the website) calls `GET /api/x402/datasets/{id}/license` and gets **HTTP 402** with the price in USDT and an EIP-3009 nonce.
2. The payer signs one `ReceiveWithAuthorization` (an EIP-712 message: no gas, no WBT, no approve).
3. It retries with `X-PAYMENT`. Our **relayer** (`backend/app/chain/whitechain.py`) submits `VeridataPay.purchase()` and pays the WBT gas. The contract pulls the USDT and splits seller 95% / treasury 5% **in the same transaction**, records `hasLicense`, and emits `LicensePurchased`.
4. The payer receives the license and an access token, then pulls the signed capture manifests it paid for.

`backend/scripts/x402_agent.py` is the agent; the dataset page's "Pay … USDT on Whitechain · no gas" button uses the same endpoint. `/payments` is the business view (volume, seller payouts, fees, gas spent, relayer runway, every payment with explorer links).

**Why it's safe (no trust in the relayer):** the nonce the buyer signs is `keccak256(chainId, VeridataPay, datasetId, seller, salt)`, so a submitter cannot redirect funds to another seller or dataset. `receiveWithAuthorization` requires `to == msg.sender`, so the signature cannot be front-run into a plain transfer. The contract holds no balance between calls and has no admin.

**Who pays gas and why it can't be drained:**
- The relayer wallet pays WBT. It is funded from the faucet on testnet; in production it is topped up from the 5% USDT fee (about 0.0006 WBT per purchase at 5 gwei, so 2 WBT covers about 3,000 purchases).
- It relays only `VeridataPay.purchase`, and only when the amount equals the listed price.
- It verifies the signature off-chain, checks USDT balance and nonce, and simulates the call first, so forged or failing requests cost nothing.
- Caps: gas price (`WHITECHAIN_MAX_GAS_GWEI`), gas limit per tx, payments per day (`WHITECHAIN_DAILY_TX_CAP`) and per wallet per hour, plus per-IP rate limits.
- It pauses automatically below a minimum WBT balance.

| | |
|---|---|
| Network | Whitechain Sepolia, chain 1874 |
| VeridataPay (verified) | [`0x997E7f5B2e1Ea27290a5705F39F1A2e468483FBC`](https://explorer.testnet.whitechain.io/address/0x997E7f5B2e1Ea27290a5705F39F1A2e468483FBC) |
| USDT | [`0xcedfB56113143d55b2358b8CFbB0dEB5Ad2f55a7`](https://explorer.testnet.whitechain.io/token/0xcedfB56113143d55b2358b8CFbB0dEB5Ad2f55a7) |
| Example USDT payment | `TODO_TX` |

Feedback on building with Whitechain: [WHITECHAIN_FEEDBACK.md](WHITECHAIN_FEEDBACK.md).

## Hardware

See [docs/HARDWARE.md](docs/HARDWARE.md). In short: flash the stock **CameraWebServer** to the ESP32-CAM and `firmware/veridata_main` to the main ESP32. Then register a *hardware* device with the CAM and board URLs. If the board answers `/pubkey`, manifests are signed **on the ESP32** (`device-hardware`). Otherwise the platform generates a clearly labelled **dev-software** key.

## Demo script (≈5 min)

1. **Demand Board** (`/`): the highest-value request, escrow totals, trending categories.
2. **Devices** → the rig → **live stream**, ultrasonic/IR readings, servo slider, and an RFID tag held to the reader (associate it with a SKU).
3. **Capture & sign** → inspect the signed manifest (sha256, sensors, RFID, ES256 signature) → **Verify sample**.
4. **/upload?request=3** (retail RFID request): describe → run AI quality & privacy checks → submit → accepted on the demo ledger; for an on-chain request the sample shows **verified**, and the buyer clicks **Release payouts** on the request page.
5. **Tamper demo** (`/demo/insurance`): 6 claim photos, 3 valid and 3 rejected (no manifest / foreign key / edited). **Modify one pixel** → hash mismatch.
6. As the buyer: **Marketplace** → dataset → **Proof Card → Verify now** (Merkle root recomputed and compared on-chain) → buy with the wallet.
7. **Training Room** → pick licensed datasets → Veri-CNN-S → train (real PyTorch, live loss/accuracy) → before/after → **download weights + model card**.
8. **Attempt raw dataset export** → `403`, written to the audit log.

## Repository

```
contracts/Veridata.sol        single contract (Remix), ABI alongside
backend/app/                  FastAPI app: routers/, provenance, quality, training, storage, chain/
web/src/app/                  all routes (see docs/ARCHITECTURE.md)
firmware/veridata_main/       ESP32 main-board firmware (sensors, servo, RFID, ES256 signing)
firmware/veridata_nodemcu/    NodeMCU ESP8266 sensor board (IR, DHT, RFID; dev-software signing)
docs/                         architecture, security, hardware, sponsors, checklist
```

## Honest limitations

- **Provenance ≠ authenticity.** Signatures prove that bytes are unchanged and came from a registered key, not that the scene is real. RFID proves a tag was read, not who owns the object.
- **dev-software** keys are held encrypted by the platform. Only `device-hardware` keys live on the ESP32 (in NVS; enable flash encryption for production). The firmware has not yet been compiled or validated on the physical rig.
- The training isolation is a **process plus API boundary**, not a TEE. Exported weights can memorize training data; the UI reports a generalization-gap indicator, not a guarantee.
- Off-chain checks decide which samples are *verified*, but the **buyer** releases the payout. A buyer could refuse to pay verified samples and reclaim the escrow after the deadline; reputation is the only deterrent in this MVP.
- Storage is AES-GCM encrypted and content-addressed on local disk, with optional IPFS pinning (`IPFS_API_URL`). No other decentralized storage network is integrated.
- The contract is **not audited**. Rate limits and replay caches are in-memory.
- Sponsor integrations are documented in [docs/SPONSORS.md](docs/SPONSORS.md), including what we evaluated and did not build.
