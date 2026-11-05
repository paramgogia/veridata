# Architecture

```
 ESP32-CAM (CameraWebServer)  --/capture, :81/stream--------------+
 ESP32 main (veridata_main)   --/sensors /servo /pubkey /sign--+  |
                                                               v  v
                       +------------- FastAPI backend (:8000) --------------+
 Next.js (:3000) -REST->| auth (EIP-191 nonce -> HMAC session token)        |
   wagmi/viem   --WS--> | devices: registry, WS telemetry, MJPEG proxy,     |
        |               |   servo, capture -> manifest -> ES256 signature   |
        |               | samples: AES-256-GCM storage, quality/privacy      |
        |               | market: datasets (Merkle root), licenses, x402     |
        |               | requests: escrow accounting, verified payouts      |
        |               | training: in-process PyTorch, weights + card       |
        |               | ledger + audit log (SQLite / Postgres)             |
        |               +-------------------+-------------------------------+
        | user-signed txs                   | verifier/facilitator txs + receipt checks
        v                                   v
              Veridata.sol on Ethereum Sepolia (single contract)
```

## Data flow of one sample
1. `POST /api/devices/{id}/capture` → JPEG from the CAM, plus telemetry from the main board (distance, IR, servo, RFID).
2. Manifest `{capture_id, device_id, nonce, captured_at, media.sha256, sensors, rfid, signer}` → canonical JSON → ES256 signature (on-device via `/sign`, or with the dev-software key).
3. The media is encrypted with a fresh AES-256-GCM key (AAD = sample id); the key is wrapped by the master key, and the ciphertext is content-addressed (`local://sha256`, optionally `ipfs://cid`).
4. Assessment: deterministic checks plus an optional VLM; the result is stored as `quality`.
5. Publish: a Merkle root over the manifest hashes becomes `contentRoot`, anchored by `publishDataset`.
6. Training: license check → decrypt in memory → train → export weights plus a model card (dataset roots, license tx, metrics).

## Frontend routes
`/` Demand Board · `/marketplace` · `/marketplace/[id]` (Proof Card) · `/upload` · `/requests` · `/requests/[id]` · `/devices` · `/devices/[id]` (live dashboard) · `/workspace` · `/workspace/[id]` (training session) · `/profile` · `/dashboard` · `/demo/insurance`

## Key API endpoints
| Area | Endpoints |
|---|---|
| Auth | `GET /api/auth/nonce`, `POST /api/auth/verify`, `POST /api/auth/demo`, `GET/PATCH /api/me` |
| Devices | `GET/POST /api/devices`, `GET /api/devices/{id}`, `WS /api/devices/{id}/ws`, `GET /api/devices/{id}/stream`, `POST …/servo`, `POST …/capture`, `POST …/confirm-chain`, `GET/POST /api/rfid` |
| Samples | `POST /api/samples/import`, `PATCH /api/samples/{id}`, `POST …/assess`, `POST …/verify`, `POST /api/demo/tamper/{id}` |
| Market | `GET /api/datasets`, `GET /api/datasets/{id}`, `POST /api/datasets` (prepare), `POST …/confirm`, `POST …/verify`, `POST …/purchase`, `GET /api/x402/datasets/{id}/license` |
| Requests | `GET/POST /api/requests`, `POST …/confirm`, `POST …/submit`, `POST …/refund` |
| Training | `GET /api/training/models`, `GET /api/training/datasets`, `/api/workspaces…`, `POST /api/workspaces/{id}/runs`, `GET /api/runs/{id}`, `…/weights`, `…/card` |

## Settlement modes
Every money movement is a `transactions` row with `mode = onchain | local`:
- `onchain` rows carry a real Sepolia tx hash that the backend verified (receipt and decoded event).
- `local` rows are the demo ledger, used by demo personas or when no contract is configured.
- Seed data is marked `demo-seed`.

The UI badges each of the three differently.

## Units
The DB stores integer **gwei**; the contract uses wei (`gwei × 1e9`).
