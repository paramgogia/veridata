# Arkiv Developer Feedback & Friction Report — VeriData

**Hackathon:** ETHGlobal Mumbai  
**Project:** VeriData (Decentralized AI Training Data Marketplace)  
**SDK Evaluated:** `@arkiv-network/sdk` on Rabdi Testnet (`chainId: 7794095`)  

---

## 1. What Went Exceptionally Well

1. **`defineSchema` with Explicit Types:**
   Defining entities using `str()`, `addr()`, `dec()`, and `.indexed()` gives a clean mental model. Being able to choose which fields are indexed keeps storage overhead low while enabling fast, SQL-like queries.
2. **First-Class Expiration (`ExpirationTime`):**
   `ExpirationTime.atDate(deadline)` solved an architectural pain point for VeriData. In a traditional stack, expiring a data bounty requires a cron daemon or periodic on-chain keeper polling. With Arkiv, expired entities automatically stop appearing in queries once their timestamp passes.
3. **Permissionless Client-Side Reads:**
   The `createPublicClient` API allowed our Next.js frontend to query marketplace listings directly without needing an API key or a centralized server proxy. Any third party can independently query the marketplace.

---

## 2. Friction Points & What Got in Our Way

### Friction 1: JavaScript/TypeScript SDK Only (No Python Support)
* **The Problem:** Many Web3 AI projects, backend microservices, and DePIN pipelines are built in Python (FastAPI, PyTorch, OpenCV). Because Arkiv only provides `@arkiv-network/sdk` for JS/TS, our Python backend had to orchestrate writes through a subprocess bridge to a Node.js CLI script.
* **Expected:** Either an official lightweight Python client (`arkiv-py` wrapping `eth_sendRawTransaction`) or documented JSON-RPC payload structures for creating/patching entities.
* **Suggested Improvement:** Publish a minimal Python SDK or a language-agnostic OpenAPI/REST gateway for Arkiv RPC nodes.

### Friction 2: Ambiguity in `patchEntity` Behavior
* **The Problem:** When updating attributes on an existing entity (e.g. updating `accepted` counts and `remaining_escrow` on `veridata.request`), it was initially unclear whether non-indexed fields could be patched alongside indexed ones, and how partial updates interact with `$owner` verification.
* **Expected:** Clear examples in the docs demonstrating updating numerical values, unsetting optional fields, and how error responses are formatted if an unauthorized wallet attempts a patch.
* **Suggested Improvement:** Add an explicit "Entity Lifecycles & Mutation" cookbook to `docs.arkiv.network`.

### Friction 3: Faucet Rate Limiting During Prototyping
* **The Problem:** The Rabdi faucet limits claims to 10 tGLM per hour per wallet. During initial contract setup, schema iteration, and integration testing, test tokens were depleted rapidly across multiple test wallets.
* **Suggested Improvement:** Provide a hackathon-tier faucet bypass or grant 50–100 tGLM with an ETHGlobal event badge.

### Friction 4: Opacity of On-Chain Write Reverts
* **The Problem:** If an entity creation transaction fails (e.g. due to payload formatting or insufficient gas limit), the error returned is often a generic EVM-style `execution reverted` without detailing whether the failure was due to an unregistered schema, attribute type mismatch, or expired timestamp.
* **Expected:** Decoded Arkiv error strings (e.g. `ArkivError: InvalidAttributeType('expected dec, got string')`).

---

## 3. High-Value Features We Wish Existed

1. **Native Query Aggregations (`COUNT`, `SUM`, `AVG`):**
   Our Demand Board computes metrics such as total escrow locked and average quality scores. Currently, we must fetch entities and aggregate them client-side. Native support for `SELECT COUNT(*) WHERE status = 'open'` would eliminate substantial network overhead.
2. **WebSocket / Server-Sent Event Query Subscriptions:**
   A `publicClient.subscribe(query, callback)` helper that pushes new entities matching a filter in real time would enable reactive UI updates without polling.
3. **Batch Entity Creation (`createEntities`):**
   When contributors upload batches of 20–50 verified camera captures, creating individual entities creates sequential transaction bottlenecks. A batched multi-entity write method would streamline high-throughput DePIN ingestion.

