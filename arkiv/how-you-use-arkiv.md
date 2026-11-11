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

## 2. Who Can Edit Each Entity

**Today:** all entities are created by the platform writing wallet (`0x399A27F3841D6B82813589B7b5E731737eBdb091`), so only that wallet can patch them. The acting user's wallet is stored in an indexed attribute (`buyer_wallet`, `owner_wallet`, `contributor_wallet`, `wallet`) so anyone can query "everything this wallet posted". Entities are created once and not yet patched.

**Planned:** user-owned entities, where each wallet creates and patches its own:

| Entity Schema | Intended owner | Intended mutations |
|---|---|---|
| `veridata.request` | Funding buyer | `accepted`, `remaining_escrow`, `status` |
| `veridata.dataset` | Publishing contributor | `status` (`listed` / `delisted`) |
| `veridata.device` | Hardware operator | `status` (`registered` / `revoked`) |
| `veridata.sample` | Contributor | `dataset_id` when grouped |
| `veridata.contributor` | User wallet | `name`, `bio`, `roles` |
| `veridata.submission` | Submitting contributor | status transitions (schema defined, not yet written) |
| `veridata.audit_event` | Platform | append-only (schema defined, not yet written) |

---

## 3. How Expiration (TTL) Changes What Users Experience

Arkiv's custom expiration timestamps directly control the lifecycle of the user interface:

### 1. The Self-Cleaning Demand Board (`veridata.request`)
* **Expiration Parameter:** `ExpirationTime.atDate(request.deadline)`
* **Visible User Impact:** Data requests posted with a 48-hour deadline disappear from the open listings the second the deadline is reached. Buyers do not have to manually close listings, and contributors never waste bandwidth or gas capturing data for a bounty that has already expired.

### 2. Ephemeral Coordination Bids (`veridata.submission`, planned: schema defined, not yet written)
* **Expiration Parameter:** Equal to the parent request's deadline.
* **Visible User Impact:** Bids and claims against a bounty automatically expire with the bounty itself, preventing "ghost claims" from polluting contributor dashboards.

### 3. Rolling Compliance Window (`veridata.audit_event`, planned: schema defined, not yet written)
* **Expiration Parameter:** `ExpirationTime.fromDays(90)`
* **Visible User Impact:** Historical audit events are automatically pruned after 90 days, maintaining high query performance while preserving full transparency during active market periods.

### 4. Long-lived Registries (`veridata.dataset`, `veridata.sample`, `veridata.device`)
* **Expiration Parameter:** `ExpirationTime.max()` (the longest expiration the SDK allows).
* **Visible User Impact:** AI researchers can rely on trained model provenance indefinitely. The Merkle tree backing a published model weights checkpoint remains resolvable on Arkiv across the lifetime of the model.

---

## 4. Visualizing Arkiv in the User Interface

1. **The Demand Board header** shows a "Decentralized DB: Arkiv Rabdi" badge when the open requests on screen were read from Arkiv (if Arkiv is unreachable or returns nothing, the board falls back to the backend API).
2. **Request deadlines** come from each entity's `$expiresAt`.
3. **Planned:** showing the Arkiv entity key on each request card and the Arkiv transaction on the Proof Card.
