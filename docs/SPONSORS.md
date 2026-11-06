# ETHGlobal Mumbai — sponsor evaluation

Source: https://ethglobal.com/events/mumbai/prizes (fetched during development).

| Sponsor | Technology | Use case for Veridata | Effort | Priority | Status |
|---|---|---|---|---|---|
| **Ethereum (Sepolia)** | EVM testnet | Settles the device registry, licenses and escrow | Low | Core | **Implemented**: single `Veridata.sol`, deployed via Remix |
| x402 (protocol) | HTTP 402 payments | Agents pay per license over HTTP | Medium | Medium | **Removed**: a facilitator needs a platform-held private key, which the team chose not to run. Purchases are direct wallet calls |
| **0G Private Computer** | OpenAI-compatible inference | Vision-language description match + privacy notes | Low | High | **Implemented as config**: point `AI_BASE_URL` / `AI_MODEL` at 0G; request IDs are stored. Not exercised unless configured |
| Whitechain | OP-stack L2, USDT | Stablecoin settlement (Operate / Scale tracks) | Low–Med | Medium | **Not implemented**: the team chose Ethereum Sepolia + Remix. Porting = redeploy with USDT transfers instead of ETH |
| Hedera | x402 on Hedera, HCS | x402 settlement + HCS audit log | Medium | Medium | Not implemented |
| World ID | Proof of personhood | Sybil-resistant contributor onboarding | Medium | Medium | Not implemented |
| Arkiv / Swarm | DB-chain, storage | Queryable dataset metadata, decentralized storage | Medium | Low | Not implemented |
| ENS | Naming | Human-readable contributor and device names | Low | Low | Not implemented |
| Chainlink CRE | Workflows | Oracle-style verification workflow | Medium | Low | Not implemented |
| Arc | Circle L1 | Stablecoin escrow | Medium | Low | Not implemented |
| Uniswap / 1inch / Definitive | DEX / orders | — | — | None | Not relevant |

**Rule we follow:** nothing marked "Not implemented" is claimed anywhere in the app. Without a configured contract, every payment is labelled "Demo ledger".
