# Why Arkiv — VeriData Architectural Analysis

**Hackathon:** ETHGlobal Mumbai  
**Core Question:** If you swapped Arkiv for Postgres or any other database, what would your users lose? What did you keep off Arkiv, and why?

---

## 1. What Users Lose If VeriData Uses Postgres Instead of Arkiv

Almost every "decentralized" marketplace harbors an uncomfortable truth: their smart contract handles payment tokens, but their search filters, discovery catalog, and listings query an AWS PostgreSQL or MongoDB instance behind the scenes.

If VeriData swapped Arkiv for a traditional relational database, our users would lose five foundational guarantees:

### A. The "Disappearing Discovery Layer" Risk
In an escrow-based data marketplace, if our centralized backend server crashes or is shut down, **the marketplace ceases to exist**. Even if the Ethereum escrow contract holds $100,000 in bounties, nobody can discover requests, filter by sensor modality, or inspect dataset specifications. With Arkiv, the entire relational discovery engine lives on a decentralized DB-chain. Any independent developer can spin up a frontend or bot and query `arkiv.schema = str('veridata.request') AND status = str('open')` directly.

### B. Autonomous, Trustless Expiration (Native TTL)
Data bounties are time-sensitive (e.g. "We need 1,000 road condition frames before tomorrow's frost advisory"). In PostgreSQL, expiring an offer requires:
* Running a centralized background worker / cron job to poll and flip statuses.
* Exposing the platform to race conditions where contributors submit work to an expired listing that the cron hasn't marked yet.

Arkiv's native `$expiresAt` and `ExpirationTime.atDate(deadline)` mathematically eliminates stale listings. Once the block timestamp elapses, the entity no longer satisfies open queries. No background daemon, no keepers, no centralized intervention.

### C. Cryptographic Wallet Ownership of Listings
In PostgreSQL, "ownership" is just a string or foreign key (`owner_id = 42`) in a row that any database administrator or compromised API key can silently alter. On Arkiv:
* Every entity is stamped with an immutable `$owner` wallet address, verifiable by anyone, and only that wallet can patch it.
* **Today** that owner is the platform writing wallet, and the user's wallet is recorded as an indexed attribute. Even so, nobody (including us) can silently rewrite an entity's history without it showing on-chain.
* **Planned:** user-owned entities, so only the buyer's or contributor's own key can change their listing (e.g. delisting a dataset or revoking a rig).

### D. Permissionless, Uncensorable Developer APIs
AI labs and data aggregators do not need an API key, rate-limit tier, or permission from VeriData to index our training data. They connect directly to Arkiv's JSON-RPC endpoint and run multi-field relational queries against the `veridata.*` schemas.

### E. Verifiable State History & Proof of Existence
Every dataset published and device registered leaves an indelible transaction trace on Arkiv. Users gain mathematical certainty of exactly when a dataset was cataloged and whether its provenance manifest was altered after publication.

---

## 2. What We Deliberately Kept Off Arkiv (and Why)

Decentralization does not mean dumping every bit of ephemeral state into on-chain storage. We adhered to strict architectural boundaries:

| Data Element | Where It Lives | Why It Stays Off Arkiv |
|---|---|---|
| **Raw High-Resolution Media** (JPEG images, video frames) | **0G Storage** | Arkiv is optimized for structured, queryable relational entities, not gigabyte-scale binary payloads. Large ciphertexts belong in dedicated decentralized blob storage. |
| **AES-GCM Decryption Keys** (`key_wrapped`) | **Local Platform Keystore** | Training datasets are encrypted at rest to enforce buyer training rights inside the platform's controlled Training Room. Exposing decryption keys on Arkiv would destroy dataset commercial exclusivity. |
| **Login Nonces & Session Secrets** | **In-Memory / SQLite** | EIP-191 authentication challenge strings are ephemeral single-use secrets. Storing them on a public ledger creates unnecessary security exposure and latency. |
| **Demo Ledger Balances** | **SQLite** | Synthetic demo faucet balances have zero economic value and should not pollute the public Rabdi testnet. Only real on-chain actions are synchronized to Arkiv. |
| **Training Run Checkpoints & Intermediate Loss Tensors** | **Ephemeral Compute Filesystem** | PyTorch model parameters and forward-pass metrics update dozens of times per second and represent transient machine state, not persistent marketplace entities. |

