# Argus (formerly Veridata)

**A decentralized, demand-driven marketplace for verifiable real-world AI training data.**

> The product is called **Argus** in the UI. Code identifiers, schemas (`veridata.*`), contracts (`Veridata.sol`, `VeridataPay.sol`) and env vars keep the original `veridata` name so existing deployments keep working.

Capture → Verify → Monetize → Train → Export.

Buyers post funded requests ("2,000 clips of heavy rain at night on rural roads, 0.0005 ETH per accepted clip") and the reward sits in on-chain escrow. Contributors capture with registered rigs (an ESP32-CAM plus a sensor board with IR presence, temperature/humidity and RFID). Each capture gets a manifest signed by the device's P-256 key. Every sample is verified for integrity, signature, quality and privacy; the buyer then releases the escrowed payout for verified samples from their own wallet. Buyers fine-tune models on licensed data inside a controlled Training Room. They can never download the raw media, but they can export the trained weights.

| | |
|---|---|
| Frontend | Next.js 14, React, TypeScript, Tailwind, wagmi/viem (Sepolia) |
| Backend | FastAPI, SQLAlchemy (SQLite by default, Postgres via `DATABASE_URL`), web3.py |
| Contract | One self-contained `contracts/Veridata.sol`, deployed from **Remix** to **Ethereum Sepolia** |
| Crypto | ES256 (P-256) device signatures, sha256 Merkle roots, AES-256-GCM per-file encryption |
| AI | PyTorch fine-tuning (Veri-CNN-S, ResNet-18); OpenAI-compatible VLM for quality checks (0G Private Computer recommended) |
| Hardware | ESP32-CAM + NodeMCU sensor board (`firmware/setup_v2`, current rig); ESP32 DevKit with on-device signing (`firmware/veridata_main`, not yet validated on hardware) |

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

## Arkiv Integration (Decentralized DB-Chain on Rabdi Testnet)

Public marketplace data is mirrored to **Arkiv DB-Chain** so anyone can query it without our API. Buyer requests, published datasets, capture devices, samples, submissions and contributor profiles are written to Arkiv as typed entities and queried from the browser with SQL-like filters. The backend database (SQLite/Postgres) remains the source of truth; Arkiv is a public index written in the background. Entities are currently created by the platform wallet below (so it is the Arkiv `$owner`), and status fields are written once and not yet patched; see [docs/SECURITY.md](docs/SECURITY.md#known-limitations).

* **Network:** Arkiv Testnet (Rabdi) · Chain ID `7794095`
* **Public RPC:** `https://rpc.rabdi.db-chain.testnet.arkiv.network`
* **Explorer:** `https://rabdi.explorer.arkiv.network`
* **Writing Entity Wallet:** `0x399A27F3841D6B82813589B7b5E731737eBdb091`

### Example Arkiv Queries (Run with `@arkiv-network/sdk` or JSON-RPC)

Query all open data bounties under the `veridata.request` schema with active TTLs:
```sql
arkiv.schema = str('veridata.request') AND status = str('open') AND category = str('agriculture')
```

Query camera-based datasets with high AI quality scores:
```sql
arkiv.schema = str('veridata.dataset') AND status = str('listed') AND sensor_types = str('camera') AND quality_score >= dec('85')
```

### Required Arkiv Documentation & Judging Criteria
* **Schema Definition:** [/arkiv/schema.md](arkiv/schema.md) — 7 entity schemas, indexed fields, wallet ownership, and custom TTL configurations.
* **Developer Friction:** [/arkiv/friction.md](arkiv/friction.md) — Honest feedback on building with `@arkiv-network/sdk` and testnet infrastructure.
* **Reach & Market:** [/arkiv/reach.md](arkiv/reach.md) — Target audiences, live testnet deployment, and post-hackathon roadmap.
* **Why Arkiv:** [/arkiv/why-arkiv.md](arkiv/why-arkiv.md) — What users lose if we used PostgreSQL instead of Arkiv, and what we deliberately kept off-chain.
* **How We Use Arkiv:** [/arkiv/how-you-use-arkiv.md](arkiv/how-you-use-arkiv.md) — Mapping UI filters to indexed fields, entity ownership, and TTL expiration.

### AI Usage Disclosure (ETHGlobal Compliance)
In accordance with ETHGlobal hackathon rules: Claude Opus and Gemini 3.8 Flash were utilized as agentic pair-programming assistants to scaffold schema definitions, write integration glue code between FastAPI and Arkiv's TypeScript SDK, and document architectural friction points.

---

## On-chain mode (Remix + Sepolia)

1. Open `contracts/Veridata.sol` in [Remix](https://remix.ethereum.org). Compile with Solidity 0.8.24+; the optimizer is recommended.
2. Deploy with **Injected Provider (MetaMask) on Sepolia**. Constructor arguments:
   - `_treasury`: the address that receives platform fees (`0x0000000000000000000000000000000000000000` = the deployer).
   - `_uploadFee`: `100000000000000` (0.0001 ETH, in wei).
   - `_feeBps`: `500` (5%).
3. Copy `.env.example` to `.env` at the repo root and set `VERIDATA_CONTRACT_ADDRESS` (and `CHAIN_RPC_URL` if you use your own RPC). Every Sepolia transaction below is signed in the user's own wallet; the backend needs no key for this contract. (The backend does use one operational key for 0G uploads, Arkiv writes and the Whitechain gas relayer; see [docs/SECURITY.md](docs/SECURITY.md#keys-and-trusted-roles).)
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

**Flow (the payer needs no gas and no WBT):**
1. The agent (or the website) calls `GET /api/x402/datasets/{id}/license` and gets **HTTP 402** with the price in USDT and an EIP-3009 nonce.
2. The payer signs one `ReceiveWithAuthorization` (an EIP-712 message: no gas, no WBT, no approve). An agent signs in code; in the browser this is one wallet signature on Whitechain Sepolia.
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
| Example USDT payment | [`0x7937bd2f27313d57…`](https://explorer.testnet.whitechain.io/tx/0x7937bd2f27313d571f64542c25c714e5d82b5103802a7cc54091a4173320d066) |

Feedback on building with Whitechain: [WHITECHAIN_FEEDBACK.md](WHITECHAIN_FEEDBACK.md).

## Hardware

See [firmware/setup_v2/README.md](firmware/setup_v2/README.md) for the current rig and [docs/HARDWARE.md](docs/HARDWARE.md) for the ESP32 DevKit design.

- **Current rig (`firmware/setup_v2`):** ESP32-CAM + NodeMCU ESP8266 with IR presence, DHT temperature/humidity and an RC522 RFID reader. The NodeMCU does not sign, so captures from this rig use a platform-held **dev-software** key, labelled as such in every manifest.
- **On-device signing (`firmware/veridata_main`):** an ESP32 DevKit that exposes `/pubkey` and `/sign`. If a registered board answers `/pubkey`, manifests are signed **on the ESP32** (`device-hardware`). This firmware has not yet been validated on physical hardware.

## Demo script (≈5 min)

1. **Demand Board** (`/demand`): the highest-value request, escrow totals, trending categories.
2. **Devices** → the rig → **live stream**, IR presence and temperature/humidity readings, and an RFID tag held to the reader (associate it with a SKU).
3. **Capture & sign** → inspect the signed manifest (sha256, sensors, RFID, ES256 signature) → **Verify sample**.
4. **/upload?request=3** (retail RFID request): describe → run AI quality & privacy checks → submit → accepted on the demo ledger; for an on-chain request the sample shows **verified**, and the buyer clicks **Release payouts** on the request page.
5. **Tamper demo** (`/demo/insurance`): 6 claim photos, 3 valid and 3 rejected (no manifest / foreign key / edited). **Modify one pixel** → hash mismatch.
6. As the buyer: **Marketplace** → dataset → **Proof Card → Verify now** (Merkle root recomputed and compared on-chain) → buy with the wallet.
7. **Training Room** → pick licensed datasets → Veri-CNN-S → train (real PyTorch, live loss/accuracy) → before/after → **download weights + model card**.
8. **Attempt raw dataset export** → `403`, written to the audit log.

## Repository

```
contracts/Veridata.sol        Sepolia: device registry, dataset roots, licences, request escrow
contracts/VeridataPay.sol     Whitechain: gasless USDT licence checkout (EIP-3009)
backend/app/                  FastAPI app: routers/, provenance, quality, training, storage, chain/, zerog, arkiv
backend/arkiv/                Arkiv schemas and the Node.js writer used by the backend
backend/scripts/              deploy, 0G fine-tuning/health, x402 agent, Arkiv seeding
web/src/app/                  all routes (see docs/ARCHITECTURE.md)
firmware/setup_v2/            current rig: ESP32-CAM + NodeMCU sensor board (IR, DHT, RFID)
firmware/veridata_main/       ESP32 DevKit firmware with on-device ES256 signing (not yet validated on hardware)
firmware/veridata_cam/, firmware/veridata_nodemcu/   earlier sketches, kept for reference
arkiv/                        Arkiv judging docs (schema, friction, reach, why, how)
docs/                         architecture, security, hardware, sponsors, checklist
```

## Honest limitations

- **Provenance ≠ authenticity.** Signatures prove that bytes are unchanged and came from a registered key, not that the scene is real. RFID proves a tag was read, not who owns the object.
- **dev-software** keys are held encrypted by the platform, so those signatures are only as trustworthy as the platform. The current rig (`firmware/setup_v2`) signs this way. Only `device-hardware` keys live on the device (`firmware/veridata_main`, in NVS; enable flash encryption and secure boot for production), and that firmware has not yet been validated on physical hardware.
- Captures made with the browser camera or with test sensor readings (when the sensor board is offline) are allowed for demos, and are labelled in the signed manifest (`camera`, `sensor_board`, `test_fields`).
- The training isolation is a **process plus API boundary**, not a TEE. Exported weights can memorize training data; the UI reports a generalization-gap indicator, not a guarantee.
- Off-chain checks decide which samples are *verified*, but the **buyer** releases the payout. A buyer could refuse to pay verified samples and reclaim the escrow after the deadline; reputation is the only deterrent in this MVP.
- Media is AES-GCM encrypted and content-addressed on local disk; when `WALLET_PRIVATE_KEY` is set, the ciphertext and the signed manifest are also uploaded to **0G Storage** (optional IPFS pinning via `IPFS_API_URL`). If a 0G upload fails, the capture still succeeds locally and the error is recorded.
- The backend holds one operational hot-wallet key for 0G uploads, Arkiv writes and the Whitechain gas relayer. It cannot move user funds on Sepolia or redirect a buyer's USDT (see [docs/SECURITY.md](docs/SECURITY.md#keys-and-trusted-roles)).
- Arkiv is a public index, not the source of truth: entities are owned by the platform wallet and their status fields are not yet updated after creation.
- Without a configured AI endpoint (0G Router, 0G broker or any OpenAI-compatible API), quality checks fall back to a deterministic + keyword heuristic, labelled in the result.
- The contracts are **not audited**. Rate limits and replay caches are in-memory.
- Sponsor integrations are documented in [docs/SPONSORS.md](docs/SPONSORS.md), including what we evaluated and did not build.

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, tests and the pull-request checklist, and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Please report security issues privately as described in [SECURITY.md](SECURITY.md), not in public issues.

## License

[MIT](LICENSE). Third-party libraries keep their own licences.
