# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Report them privately through GitHub: go to the repository's **Security** tab → **Report a vulnerability** (GitHub private vulnerability reporting). Include:

- what is affected (file, endpoint, contract function)
- steps to reproduce, or a proof of concept on a testnet or local setup
- the impact you expect

We aim to acknowledge reports within 7 days. Please give us a reasonable time to fix an issue before disclosing it publicly.

## Scope and status

Argus is a hackathon-stage project running on **testnets** (Ethereum Sepolia, Whitechain Sepolia, 0G Galileo, Arkiv Rabdi). The contracts are **not audited**. Do not use it with real funds.

Never test against other people's wallets, deployments or data. Use your own local setup or testnet deployment.

## Trust model

The threat model, the keys the backend holds and the known limitations are documented in [docs/SECURITY.md](docs/SECURITY.md).
