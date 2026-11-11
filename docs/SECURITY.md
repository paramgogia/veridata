# Security & trust model

To report a vulnerability, see [SECURITY.md](../SECURITY.md) at the repository root.

| Threat | Mitigation in this MVP |
|---|---|
| Modified media | sha256 of the decrypted media must equal `manifest.media.sha256`; AES-GCM authentication also detects ciphertext tampering |
| Falsified metadata | Sensor and RFID values are inside the signed manifest. Descriptive metadata (label, description) is editable only before publishing and is not claimed as signed |
| Test or browser captures passed off as rig captures | `camera`, `sensor_board` and `test_fields` are signed into the manifest, so a browser photo or a capture using test sensor readings is labelled as such and cannot pass as a full rig capture |
| Replayed capture signatures | Unique `capture_id` + random `nonce` per manifest; a duplicate `manifest_hash` fails verification (the `replay` step) |
| Signature from a non-registered key | The manifest's key fingerprint must match the registered device key; ES256 is verified against that key |
| Duplicate samples / double-claimed rewards | Each sample can be accepted once; identical-media check (sha256) across all submissions; near-duplicate dHash in quality checks; global `claimedSample[hash]` in the contract; server-side lock around acceptance |
| Manipulated fulfillment records | Only the request's buyer can call `releasePayouts`, capped at `quantity`; the backend records a payout only after decoding `SampleAccepted` events whose sample hash and contributor match a verified submission |
| Unauthorized dataset access | No endpoint returns decrypted media to buyers; `/samples/{id}/original` is owner-only; `/datasets/{id}/download` always returns 403 and is audited; training checks licenses before decrypting |
| Dataset redistribution | Not fully preventable: weights can memorize data. We report a generalization gap and state this limitation |
| Login replay | One-time nonces, deleted on use, expiring after 5 minutes; HMAC-signed session tokens |
| Cross-site requests | Auth is a Bearer token in a header, not a cookie; CORS is limited to configured origins and does not allow credentials |
| Whitechain relayer drain | The relayer only calls `VeridataPay.purchase`; it checks the signature off-chain, the price, expiry, nonce binding and buyer balance, simulates the call, caps gas price and gas limit, rate-limits per buyer and per day, and pauses below a minimum balance |
| Abuse | In-memory per-IP rate limiting; 8 MB upload cap; image decode validation |
| Secrets | `.env` and `firmware/**/secrets.h` are gitignored; master and session keys are generated into `backend/data/` (gitignored); in hardware mode the device private key stays on the ESP32 |

## Keys and trusted roles

**User actions on Sepolia are signed in the user's own wallet.** Device registration, dataset publishing, licence purchases, request escrow, payout release and refunds on `Veridata.sol` are all user transactions; the backend only verifies their receipts.

**The backend does hold one operational key** (`WALLET_PRIVATE_KEY`, optionally split into `WHITECHAIN_RELAYER_KEY` and `ARKIV_PRIVATE_KEY`). It is used to:

| Use | What the key can do | What it cannot do |
|---|---|---|
| 0G Storage uploads | Pay storage fees for encrypted media and manifests | Read media (it is encrypted before upload) |
| 0G compute broker (optional) | Pay for TEE inference and fine-tuning from the backend's 0G balance | — |
| Arkiv writes | Create the public index entities (all entities are currently owned by this wallet) | Change on-chain escrow, licences or payments |
| Whitechain relayer | Pay WBT gas to submit buyer-signed USDT authorizations | Move a buyer's USDT anywhere except the signed seller/treasury split for the signed dataset, because the EIP-3009 nonce commits to the dataset and seller |

Treat this key as a hot wallet: fund it with small testnet amounts and keep it out of the repository.

**Other roles**
- **Contract admin (`Veridata.sol`):** can change only the treasury address, upload fee and fee rate (capped at 20% in code). `VeridataPay.sol` has no admin; its fee is immutable.
- **Buyer:** releases payouts for samples the platform verified. A buyer can withhold payment and refund after the deadline. Production mitigation: an optimistic window after which verified samples become claimable by contributors, or an arbiter.
- **Platform master key:** wraps per-file AES keys and `dev-software` device keys. A `dev-software` device is therefore only as trustworthy as the platform; only `device-hardware` keys live on the device. Use a KMS/HSM in production.

## Known limitations
- `releasePayouts` pays contributors in a loop; a contributor address that rejects ETH makes that batch revert. The buyer can resubmit the batch without that sample.
- Arkiv is a best-effort public index, not the source of truth: writes happen in the background, entities are owned by the platform wallet, and status fields (`accepted`, `remaining_escrow`, `status`) are written once and not yet patched.
- When no AI endpoint is configured, quality checks fall back to a deterministic + keyword heuristic, which is labelled in the result.
- Device signing on the ESP32 uses keys stored in NVS; without flash encryption and secure boot they can be extracted with physical access.

## Not done (would be required for production)
- Contract audit and formal tests on a fork
- Automatic or arbiter-based release of verified payouts
- TEE/enclave training for the local Training Room
- Hardware secure element or flash encryption + secure boot on the ESP32
- User-owned Arkiv entities and status patching
- A distributed rate limiter and replay cache
- Monitoring and key rotation
