# Arkiv Reach & Impact Assessment — VeriData

**Track:** Build on Arkiv (from scratch)  
**Hackathon:** ETHGlobal Mumbai  

---

## 1. Target Audience: Who is VeriData For?

VeriData bridges two distinct, high-growth user bases that desperately lack a decentralized data exchange:

1. **AI & Robotics perception teams (Buyers):**
   * Autonomous driving teams, agricultural vision researchers, and smart retail developers who require verified, physical-world training datasets (e.g., rain driving scenes, night road clips, leaf-blight progression).
   * **Their pain point:** Existing datasets are either scraped with questionable rights, lack cryptographic authenticity, or are locked behind closed proprietary data vendors.
2. **DePIN & Edge Hardware Contributors (Sellers):**
   * Smallholder farms, automated warehouses, and IoT hobbyists deploying ESP32 rigs with multi-sensor telemetry (cameras, ultrasonic distance, temperature, RFID).
   * **Their pain point:** No permissionless marketplace exists to monetize edge data streams with cryptographic hardware provenance and instant escrow payouts.

Both groups require a registry of demands and datasets that is **publicly queryable, vendor-neutral, and permanent**—a core value proposition that centralized cloud databases fail to deliver.

---

## 2. Immediate Usability: Can Users Try It Today?

**Yes.** VeriData is fully operational across its live multi-network stack:

* **Arkiv Rabdi Testnet (`chainId: 7794095`):** Serves as the decentralized relational database and indexing engine. The Next.js frontend queries open data bounties and verified datasets directly from Arkiv nodes via `@arkiv-network/sdk`.
* **Ethereum Sepolia (`chainId: 11155111`):** Settles non-custodial smart contract escrow for buyer bounties, platform fee collection, and dataset license purchases.
* **0G Galileo Testnet:** Content-addresses encrypted media blobs and signed hardware manifests.
* **Physical & Simulated Hardware:** Contributor capture workflows support real ESP32-CAM rigs over Wi-Fi as well as simulated hardware rigs generating authentic P-256 signed manifests.

Anyone with a Web3 wallet can visit the dApp, browse live bounties fetched directly from Arkiv, submit sensor captures, and verify Merkle provenance.

---

## 3. Long-Term Roadmap: Building Beyond Mumbai

We intend to continue active development of VeriData following ETHGlobal Mumbai:

1. **Migration to Arkiv Mainnet:** Transition our production schemas (`veridata.*`) from Rabdi testnet to Arkiv mainnet as soon as public mainnet availability opens.
2. **ENSv2 Hierarchical Integration:** Link Arkiv entity keys directly into our planned ENSv2 subregistry (`*.veridata.eth`) so that a query like `alice.contributors.veridata.eth` dynamically resolves to her Arkiv contributor entity and verified dataset portfolio.
3. **Autonomous Agent Data Bounties:** Equip autonomous AI agents with wallet keys and Arkiv query capabilities, allowing them to autonomously scan Arkiv for needed training distributions, fund bounties, and ingest verified weights without human intervention.
4. **Hardware SDK Integration:** Embed lightweight Arkiv-compatible attestation proofs directly onto ESP32 and Raspberry Pi microcontroller firmware.

