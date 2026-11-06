# Arkiv Entity Schema — VeriData

**Network:** Arkiv Testnet (Rabdi)  
**Chain ID:** `7794095`  
**RPC Endpoint:** `https://rpc.rabdi.db-chain.testnet.arkiv.network`  
**Writing Wallet Address:** `0x399A27F3841D6B82813589B7b5E731737eBdb091`  

All entities are organized under the `veridata.*` schema namespace. Every entity is wallet-owned via Arkiv's native `$owner` attribute and bound to an explicit `$expiresAt` block timestamp.

---

## Entity Definitions

### 1. `veridata.request` — Buyer Data Bounty
The primary marketplace listing for training data requests funded in escrow. Uses Arkiv's native TTL to auto-expire bounties when the deadline passes.

| Attribute | Arkiv Type | Indexed | Description |
|---|---|---|---|
| `request_id` | `dec()` | ✅ | Internal numeric identifier |
| `buyer_wallet` | `addr()` | ✅ | Buyer's wallet (matches `$owner`) |
| `title` | `str()` | ❌ | Human-readable request title |
| `category` | `str()` | ✅ | Category (e.g. `agriculture`, `weather`, `traffic`, `retail`) |
| `quantity` | `dec()` | ✅ | Total samples required |
| `accepted` | `dec()` | ✅ | Samples verified and accepted to date |
| `price_per_sample` | `dec()` | ✅ | Reward per verified sample in gwei |
| `total_escrow` | `dec()` | ✅ | Total locked escrow in gwei (`quantity * price_per_sample`) |
| `remaining_escrow` | `dec()` | ✅ | Unreleased escrow balance |
| `status` | `str()` | ✅ | Request state: `open`, `filled`, `closed` |
| `require_device_sig` | `str()` | ✅ | Strict hardware key signature requirement: `true` / `false` |
| `min_quality` | `dec()` | ✅ | Minimum AI quality threshold (0–100) |
| `sensors` | `str()` | ✅ | Comma-separated required sensors (e.g. `camera,ultrasonic,ir`) |
| `spec_hash` | `str()` | ❌ | SHA-256 hash of canonical specification |
| `chain_request_id` | `dec()` | ❌ | Smart contract escrow ID in `Veridata.sol` |
| `fund_tx` | `str()` | ❌ | Ethereum Sepolia funding transaction hash |
| `mode` | `str()` | ✅ | Settlement mode: `onchain`, `local`, `demo-seed` |
| `created_at` | `dec()` | ✅ | Creation timestamp (Unix seconds) |

* **Ownership:** Owned by the funding buyer's wallet (`buyer_wallet`).
* **Expiration (TTL):** `ExpirationTime.atDate(deadline)` — automatically pruned from queries the instant the bounty deadline is reached.

---

### 2. `veridata.dataset` — Published Training Dataset
Curated, verified multi-sample dataset packages available for model training licenses.

| Attribute | Arkiv Type | Indexed | Description |
|---|---|---|---|
| `dataset_id` | `dec()` | ✅ | Internal dataset identifier |
| `owner_wallet` | `addr()` | ✅ | Publisher's wallet (matches `$owner`) |
| `title` | `str()` | ❌ | Dataset title |
| `categories` | `str()` | ✅ | Comma-separated categories |
| `sensor_types` | `str()` | ✅ | Comma-separated sensor modalities |
| `location` | `str()` | ✅ | Geolocation or environment label |
| `quality_score` | `dec()` | ✅ | Mean AI quality score across all manifests (0–100) |
| `sample_count` | `dec()` | ✅ | Number of validated samples |
| `price` | `dec()` | ✅ | Training license fee in gwei |
| `content_root` | `str()` | ❌ | SHA-256 Merkle root of all sample manifests |
| `chain_dataset_id` | `dec()` | ❌ | Dataset token/index on `Veridata.sol` |
| `publish_tx` | `str()` | ❌ | Sepolia publication transaction hash |
| `mode` | `str()` | ✅ | Settlement mode: `onchain`, `local`, `demo-seed` |
| `status` | `str()` | ✅ | Listing status: `listed`, `delisted` |
| `created_at` | `dec()` | ✅ | Publication timestamp (Unix seconds) |

* **Ownership:** Publisher's wallet (`owner_wallet`).
* **Expiration:** `ExpirationTime.fromDays(3650)` (10-year permanent listing).

---

### 3. `veridata.device` — Hardware Capture Rig
Hardware attestation record for ESP32 and edge sensor rigs equipped with cryptographic keypairs.

| Attribute | Arkiv Type | Indexed | Description |
|---|---|---|---|
| `device_id` | `str()` | ✅ | Hex-encoded bytes32 device identifier |
| `owner_wallet` | `addr()` | ✅ | Device owner address (matches `$owner`) |
| `name` | `str()` | ❌ | Human-readable rig name |
| `kind` | `str()` | ✅ | Hardware type: `esp32-cam`, `simulated` |
| `pubkey_hex` | `str()` | ❌ | P-256 SEC1 uncompressed public key (`04||X||Y`) |
| `signing_mode` | `str()` | ✅ | Key location: `device-hardware`, `dev-software` |
| `registration_tx` | `str()` | ❌ | Sepolia on-chain registration transaction hash |
| `registration_mode`| `str()` | ✅ | Registration context: `onchain`, `local` |
| `status` | `str()` | ✅ | Status: `registered`, `revoked` |
| `created_at` | `dec()` | ✅ | Registration timestamp |

* **Ownership:** Device operator's wallet (`owner_wallet`).
* **Expiration:** `ExpirationTime.fromDays(3650)` (revocable on-demand via `status = "revoked"`).

---

### 4. `veridata.sample` — Verified Capture Manifest
Cryptographic provenance record for an individual data capture.

| Attribute | Arkiv Type | Indexed | Description |
|---|---|---|---|
| `sample_id` | `str()` | ✅ | Unique sample UUID |
| `contributor_wallet`| `addr()`| ✅ | Contributor wallet address (matches `$owner`) |
| `device_id` | `str()` | ✅ | Capture device identifier |
| `media_sha256` | `str()` | ❌ | SHA-256 hash of original media file |
| `manifest_hash` | `str()` | ✅ | SHA-256 hash of canonical signed JSON manifest |
| `storage_root_media`| `str()` | ❌ | Content address on 0G decentralized storage |
| `storage_root_manifest`| `str()`| ❌ | Content address of canonical manifest on 0G |
| `quality_score` | `dec()` | ✅ | AI verification quality score (0–100) |
| `status` | `str()` | ✅ | Verification status: `verified`, `published` |
| `label` | `str()` | ✅ | Descriptive tag / class label |
| `categories` | `str()` | ✅ | Comma-separated category tags |
| `sensors` | `str()` | ✅ | Comma-separated telemetry keys present |
| `sig_mode` | `str()` | ✅ | Key signature type: `device-hardware`, `dev-software` |
| `captured_at` | `dec()` | ✅ | Physical hardware capture timestamp |
| `dataset_id` | `dec()` | ✅ | Aggregating dataset ID (0 if unbundled) |

* **Ownership:** Contributor's wallet (`contributor_wallet`).
* **Expiration:** `ExpirationTime.fromDays(3650)` (immutable provenance archive).

---

### 5. `veridata.contributor` — Contributor Identity & Reputation
Public contributor profile and attestation record.

| Attribute | Arkiv Type | Indexed | Description |
|---|---|---|---|
| `wallet` | `addr()` | ✅ | Contributor wallet address (matches `$owner`) |
| `name` | `str()` | ❌ | Public display name |
| `bio` | `str()` | ❌ | Public biography |
| `roles` | `str()` | ✅ | Active roles: `contributor`, `buyer`, `both` |
| `reputation` | `dec()` | ✅ | On-chain reputation rating (0.00–5.00) |
| `sample_count` | `dec()` | ✅ | Total validated captures submitted |
| `created_at` | `dec()` | ✅ | Profile creation timestamp |

* **Ownership:** Contributor's wallet.
* **Expiration:** `ExpirationTime.fromDays(3650)`.

---

### 6. `veridata.submission` — Coordination Claim / Bid
Agent coordination state for sample submissions against open data bounties.

| Attribute | Arkiv Type | Indexed | Description |
|---|---|---|---|
| `submission_id` | `dec()` | ✅ | Internal numeric claim ID |
| `request_id` | `dec()` | ✅ | Target buyer request ID |
| `sample_id` | `str()` | ✅ | Submitted sample UUID |
| `contributor_wallet`| `addr()`| ✅ | Submitting contributor's address |
| `status` | `str()` | ✅ | Status: `pending`, `accepted`, `rejected`, `verified` |
| `payout` | `dec()` | ✅ | Released reward amount in gwei |
| `mode` | `str()` | ✅ | Settlement mode: `onchain`, `local` |
| `created_at` | `dec()` | ✅ | Submission timestamp |

* **Ownership:** Contributor's wallet.
* **Expiration:** Co-terminus with the parent request's deadline (`ExpirationTime.atDate(request_deadline)`).

---

### 7. `veridata.audit_event` — Public Audit Trail
Append-only log of security-critical platform events.

| Attribute | Arkiv Type | Indexed | Description |
|---|---|---|---|
| `actor` | `addr()` | ✅ | Initiating wallet address |
| `action` | `str()` | ✅ | Action name (e.g. `request.fund`, `device.register`) |
| `target` | `str()` | ❌ | Target resource identifier |
| `mode` | `str()` | ✅ | Settlement context |
| `created_at` | `dec()` | ✅ | Timestamp |

* **Ownership:** Platform signing wallet.
* **Expiration:** `ExpirationTime.fromDays(90)` (90-day rolling audit window).

---

## Canonical Testnet Queries

### 1. Discover all open agricultural data bounties:
```sql
arkiv.schema = str('veridata.request') AND status = str('open') AND category = str('agriculture')
```

### 2. Discover high-quality camera datasets:
```sql
arkiv.schema = str('veridata.dataset') AND status = str('listed') AND sensor_types = str('camera') AND quality_score >= dec('85')
```

### 3. Verify hardware capture devices by owner:
```sql
arkiv.schema = str('veridata.device') AND status = str('registered') AND owner_wallet = addr('0x399A27F3841D6B82813589B7b5E731737eBdb091')
```

