# ETHGlobal Mumbai — sponsor evaluation

Source: https://ethglobal.com/events/mumbai/prizes (fetched during development).

| Sponsor | Technology | Use case for Veridata | Effort | Priority | Status |
|---|---|---|---|---|---|
| **Ethereum (Sepolia)** | EVM testnet | Settles the device registry, licenses and escrow | Low | Core | **Implemented**: single `Veridata.sol`, deployed via Remix |
| **x402** (protocol) | HTTP 402 payments | AI agents buy a training license over HTTP | Medium | High | **Implemented on Whitechain**: `GET /api/x402/datasets/{id}/license` returns 402 + requirements; the payer retries with `X-PAYMENT` and our relayer settles it. Used by the web checkout and `backend/scripts/x402_agent.py` |
| **0G** | Storage, Router (inference), TEE compute | Encrypted media + signed manifests on 0G Storage (roots inside the signed manifest), vision quality/privacy checks, fine-tuning | Medium | High | **Implemented**: uploads via the storage indexer (e.g. [tx 0xea2651…](https://chainscan-galileo.0g.ai/tx/0xea265131829484323aede3797567c6d6566a7f1c77b14a965604e3c8b1856e17)), Proof Card re-derives dataset roots from 0G, checks on the 0G Router, TEE fine-tuning from the Training Room |
| **Whitechain** | Chain 1874, USDT (EIP-3009) | Gasless USDT license checkout (Scale track) | Medium | High | **Implemented**: `VeridataPay.sol` [verified](https://explorer.testnet.whitechain.io/address/0x997E7f5B2e1Ea27290a5705F39F1A2e468483FBC), relayer with drain protection, [USDT payment](https://explorer.testnet.whitechain.io/tx/0x7937bd2f27313d571f64542c25c714e5d82b5103802a7cc54091a4173320d066). See README and `WHITECHAIN_FEEDBACK.md` |
| Hedera | x402 on Hedera, HCS | x402 settlement + HCS audit log | Medium | Medium | Not implemented |
| World ID | Proof of personhood | Sybil-resistant contributor onboarding | Medium | Medium | Not implemented |
| **Arkiv** | DB-chain | Decentralized relational database for marketplace discovery, SQL filtering, and native TTL expiration | Medium | High | **Implemented**: 7 schemas on Rabdi testnet, frontend queries via `@arkiv-network/sdk`, see `/arkiv` docs |
| ENS | Naming | Human-readable contributor and device names | Low | Low | Not implemented |
| Chainlink CRE | Workflows | Oracle-style verification workflow | Medium | Low | Not implemented |
| Arc | Circle L1 | Stablecoin escrow | Medium | Low | Not implemented |
| Uniswap / 1inch / Definitive | DEX / orders | — | — | None | Not relevant |

**Rule we follow:** nothing marked "Not implemented" is claimed anywhere in the app. Without a configured contract, every payment is labelled "Demo ledger".
