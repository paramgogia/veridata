# Building on Whitechain Sepolia: feedback

Written while adding gasless USDT checkout (EIP-3009 + x402 + our own relayer) to Veridata.

## What worked well
- The EVM is standard: web3.py, viem/wagmi, Remix and Blockscout verification worked without changes. We deployed and verified from Remix.
- The qualifying USDT implements EIP-3009 (`transferWithAuthorization`, `receiveWithAuthorization`, `authorizationState`) and EIP-2612 `permit`. That made a truly gasless checkout possible with no extra contracts.
- Gas is cheap and blocks are fast, so a relayer can sponsor thousands of payments from a small WBT balance.

## Friction we hit
1. **No public USDT faucet.** `mint` is owner-only, so we had to ask DevRel for test USDT. A self-serve USDT faucet (or a faucet button next to WBT) would remove the biggest blocker for payment projects.
2. **Two USDT tokens.** The docs/token list also show `USDT.e` (`0xaa79…8f46`), but only `0xcedf…55a7` qualifies. It's easy to integrate the wrong one; the docs should say clearly which token is canonical on testnet.
3. **EIP-712 domain isn't documented.** The token has no `version()` getter. We had to derive the domain (`name="Tether USD"`, `version="1"`, chainId 1874) by matching `DOMAIN_SEPARATOR()` by hand. Please document the domain fields, or expose `eip712Domain()` (EIP-5267).
4. **EIP-3009 support isn't mentioned anywhere.** It's the most useful feature for payment builders and could be a headline in the docs, with a short "gasless USDT" example.
5. **Faucet gating.** The WBT faucet needs a GitHub account at least 30 days old and gives 0.5 WBT per day. That's fine for us, but a first-time hackathon participant can be blocked.
6. **MetaMask setup.** Signing EIP-712 for chain 1874 requires the user to add the network first. An "Add to wallet" button in the docs/explorer would help.

## Suggestions
- An official x402 facilitator (or reference relayer) for Whitechain USDT.
- A testnet USDT faucet with rate limits.
- A docs page listing token addresses, decimals and EIP-712 domains for every testnet asset.
