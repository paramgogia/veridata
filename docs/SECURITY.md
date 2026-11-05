# Security & trust model

| Threat | Mitigation in this MVP |
|---|---|
| Modified media | sha256 of the decrypted media must equal `manifest.media.sha256`; AES-GCM authentication also detects ciphertext tampering |
| Falsified metadata | Sensor and RFID values are inside the signed manifest. Descriptive metadata (label, description) is editable only before publishing and is not claimed as signed |
| Replayed capture signatures | Unique `capture_id` + random `nonce` per manifest; a duplicate `manifest_hash` fails verification (the `replay` step) |
| Signature from a non-registered key | The manifest's key fingerprint must match the registered device key; ES256 is verified against that key |
| Duplicate samples / double-claimed rewards | Each sample can be accepted once; identical-media check (sha256) across all submissions; near-duplicate dHash in quality checks; global `claimedSample[hash]` in the contract; server-side lock around acceptance |
| Manipulated fulfillment records | Payouts require backend verification; on-chain `acceptSample` is verifier-only and capped at `quantity`; escrow math lives in the contract |
| Unauthorized dataset access | No endpoint returns decrypted media to buyers; `/samples/{id}/original` is owner-only; `/datasets/{id}/download` always returns 403 and is audited; training checks licenses before decrypting |
| Dataset redistribution | Not fully preventable: weights can memorize data. We report a generalization gap and state this limitation |
| Login replay | One-time nonces, deleted on use, expiring after 5 minutes; HMAC-signed session tokens |
| x402 payment replay | EIP-712 intent with a per-buyer nonce and deadline, checked by the contract; the backend checks domain, amount, signer and credit before relaying |
| Abuse | In-memory per-IP rate limiting; 8 MB upload cap; image decode validation |
| Secrets | `.env` is gitignored; master and session keys are generated into `backend/data/` (gitignored); in hardware mode the device private key stays in ESP32 NVS |

## Trusted roles
- **Verifier / facilitator** (backend key): the only address that can release escrow payouts, and it also relays x402 purchases. A compromised verifier could pay out the remaining escrow of open requests to arbitrary addresses. Production mitigations: multisig or threshold verifiers, per-request payout rate limits, optimistic challenge windows.
- **Platform master key**: wraps per-file AES keys and dev-software device keys. Use a KMS/HSM in production.

## Not done (would be required for production)
- Contract audit and formal tests on a fork
- TEE/enclave training
- Hardware secure element or flash encryption on the ESP32
- A distributed rate limiter
- Monitoring
- Key rotation
