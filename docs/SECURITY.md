# Security & trust model

| Threat | Mitigation in this MVP |
|---|---|
| Modified media | sha256 of the decrypted media must equal `manifest.media.sha256`; AES-GCM authentication also detects ciphertext tampering |
| Falsified metadata | Sensor and RFID values are inside the signed manifest. Descriptive metadata (label, description) is editable only before publishing and is not claimed as signed |
| Replayed capture signatures | Unique `capture_id` + random `nonce` per manifest; a duplicate `manifest_hash` fails verification (the `replay` step) |
| Signature from a non-registered key | The manifest's key fingerprint must match the registered device key; ES256 is verified against that key |
| Duplicate samples / double-claimed rewards | Each sample can be accepted once; identical-media check (sha256) across all submissions; near-duplicate dHash in quality checks; global `claimedSample[hash]` in the contract; server-side lock around acceptance |
| Manipulated fulfillment records | Only the request's buyer can call `releasePayouts`, capped at `quantity`; the backend records a payout only after decoding `SampleAccepted` events whose sample hash and contributor match a verified submission |
| Unauthorized dataset access | No endpoint returns decrypted media to buyers; `/samples/{id}/original` is owner-only; `/datasets/{id}/download` always returns 403 and is audited; training checks licenses before decrypting |
| Dataset redistribution | Not fully preventable: weights can memorize data. We report a generalization gap and state this limitation |
| Login replay | One-time nonces, deleted on use, expiring after 5 minutes; HMAC-signed session tokens |
| Abuse | In-memory per-IP rate limiting; 8 MB upload cap; image decode validation |
| Secrets | `.env` is gitignored; master and session keys are generated into `backend/data/` (gitignored); in hardware mode the device private key stays in ESP32 NVS |

## Trusted roles
- **No platform signing key.** The backend never sends transactions. The contract admin can only change the treasury address, upload fee and fee rate (capped at 20%).
- **Buyer** releases payouts for samples the platform verified. A buyer can withhold payment and refund after the deadline. Production mitigation: an optimistic window after which verified samples become claimable by contributors, or an arbiter.
- **Platform master key**: wraps per-file AES keys and dev-software device keys. Use a KMS/HSM in production.

## Not done (would be required for production)
- Contract audit and formal tests on a fork
- TEE/enclave training
- Hardware secure element or flash encryption on the ESP32
- A distributed rate limiter
- Monitoring
- Key rotation
