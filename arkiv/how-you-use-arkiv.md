# How VeriData Uses Arkiv — UX, Filters & Lifecycles

**Hackathon:** ETHGlobal Mumbai  
**Core Question:** Do the things you filter on, who can edit each entity, and when it expires fit what your app does? Does each Arkiv feature you use change something your users see?

---

## 1. UI Filters Mapped Directly to Arkiv Indexed Attributes

In VeriData, Arkiv indexing is not an abstract database configuration—it drives the exact interactive controls visible in the browser:

```
┌────────────────────────────────────────────────────────┐
│                   VERIDATA FRONTEND                    │
├─────────────────────────┬──────────────────────────────┤
│ User Action / UI Control│ Arkiv Filter (SDK Query)     │
├─────────────────────────┼──────────────────────────────┤
│ 1. Demand Board Category│ category = str('agri')       │
│ 2. Only Open Bounties   │ status = str('open')         │
│ 3. Sensor Multi-Select  │ sensor_types = str('camera') │
│ 4. Quality Slider (≥85) │ quality_score >= dec('85')   │
│ 5. Max Price Filter     │ price <= dec('5000000000')   │
│ 6. Contributor Profile  │ wallet = addr('0x399A...b091')│
│ 7. Device Owner Lookup  │ owner_wallet = addr('0x...') │
└─────────────────────────┴──────────────────────────────┘
```

When a user drags the "Min Quality" slider or selects "Agriculture" on the Demand Board:
1. The frontend constructs an `arkiv_query` string dynamically.
2. It calls `@arkiv-network/sdk`'s `arkivClient.query()` against the Rabdi testnet.
3. The entities returned are rendered directly to the screen with zero intermediary server transformation.

---

## 2. Who Can Edit Each Entity (Access Control Matrix)

Entity modification adheres to strict role authorization backed by Arkiv's `$owner` verification:

| Entity Schema | Owner Entity | Allowed Mutations | Security Rationale |
|---|---|---|---|
| `veridata.request` | **Funding Buyer** | May patch `accepted`, `remaining_escrow`, `status` (`filled` / `closed`). | Only the buyer whose ETH is escrowed can modify bounty fulfillment terms. |
| `veridata.dataset` | **Publishing Contributor** | May patch `status` (`listed` / `delisted`). | A contributor can delist their dataset, but cannot tamper with published Merkle roots. |
| `veridata.device` | **Hardware Operator** | May patch `status` (`registered` / `revoked`). | If an ESP32 hardware rig is stolen or compromised, only its owner can broadcast an emergency revocation. |
| `veridata.sample` | **Contributor** | May patch `dataset_id` upon grouping. | Individual capture manifests are otherwise immutable provenance proofs. |
| `veridata.contributor` | **User Wallet** | May patch `name`, `bio`, `roles`. | Sovereign user identity editable exclusively by the holder of the private key. |
| `veridata.submission` | **Submitting Contributor** | Status transitions managed via workflow. | Prevents competing contributors from altering each other's bounty claims. |
| `veridata.audit_event`| **Platform Relayer** | **Append-only (No patches allowed).** | Ensures an untamperable audit record for compliance. |

---

## 3. How Expiration (TTL) Changes What Users Experience

Arkiv's custom expiration timestamps directly control the lifecycle of the user interface:

### 1. The Self-Cleaning Demand Board (`veridata.request`)
* **Expiration Parameter:** `ExpirationTime.atDate(request.deadline)`
* **Visible User Impact:** Data requests posted with a 48-hour deadline disappear from the open listings the second the deadline is reached. Buyers do not have to manually close listings, and contributors never waste bandwidth or gas capturing data for a bounty that has already expired.

### 2. Ephemeral Coordination Bids (`veridata.submission`)
* **Expiration Parameter:** Equal to the parent request's deadline.
* **Visible User Impact:** Bids and claims against a bounty automatically expire with the bounty itself, preventing "ghost claims" from polluting contributor dashboards.

### 3. Rolling Compliance Window (`veridata.audit_event`)
* **Expiration Parameter:** `ExpirationTime.fromDays(90)`
* **Visible User Impact:** Historical audit events are automatically pruned after 90 days, maintaining high query performance while preserving full transparency during active market periods.

### 4. Permanent Heritage Registries (`veridata.dataset`, `veridata.sample`, `veridata.device`)
* **Expiration Parameter:** `ExpirationTime.fromDays(3650)` (10-year persistence).
* **Visible User Impact:** AI researchers can rely on trained model provenance indefinitely. The Merkle tree backing a published model weights checkpoint remains resolvable on Arkiv across the lifetime of the model.

---

## 4. Visualizing Arkiv in the User Interface

To ensure judges immediately recognize Arkiv's contribution to the platform:
1. **The Demand Board Header:** Features an active **"Decentralized DB: Arkiv Rabdi"** pill showing live query latency to the testnet.
2. **The Request Card Footer:** Displays the Arkiv Entity Key and `$expiresAt` countdown timer on every active bounty.
3. **The Proof Card:** Shows the Arkiv transaction hash and entity verification status alongside 0G storage roots and Sepolia smart contract events.

