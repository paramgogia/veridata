# Contributing to Argus

Thanks for your interest! Argus (formerly Veridata) is a marketplace for verifiable real-world AI training data: signed device captures, 0G storage and AI checks, an Arkiv public index and USDT checkout on Whitechain. See the [README](README.md) for the overview and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how the pieces fit.

By participating you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Ways to help
- Fix a bug or a known limitation listed in [docs/SECURITY.md](docs/SECURITY.md#known-limitations) (good starting points: user-owned Arkiv entities and status patching, automatic payout release, tests for the routers).
- Improve docs, firmware or hardware guides.
- Report bugs with clear steps to reproduce.

## Local setup

```bash
# Backend (Python 3.11-3.12 recommended; some ML/0G wheels may lag the newest Python)
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m app.seed --reset        # demo data, clearly labelled
uvicorn app.main:app --port 8000 --reload

# Frontend
cd web
npm install
npm run dev                       # http://localhost:3000
```

No keys are needed for local development: without them, payments use the labelled demo ledger and 0G, Arkiv and Whitechain features are disabled. Copy `.env.example` to `.env` to enable them. **Never commit `.env`, private keys or `firmware/**/secrets.h`.**

## Before opening a pull request

Run the same checks as CI:

```bash
# Backend
pip install cryptography pytest
python -m compileall -q backend/app backend/scripts
python -m pytest -q backend/tests

# Frontend
cd web && npx tsc --noEmit

# Contracts (if you changed them): compile, then regenerate both ABI copies
npx -y solc@0.8.24 --bin --abi -o /tmp/solc-out --base-path . contracts/Veridata.sol contracts/VeridataPay.sol
```

If you change a contract, update `contracts/<Name>.abi.json` **and** `backend/app/chain/<Name>.abi.json`; CI fails if they drift from the source. If you change an Arkiv schema, update `backend/arkiv/schemas.mjs`, `web/src/lib/arkiv.ts` and `arkiv/schema.md` together.

## Guidelines
- Keep pull requests focused: one change per PR, with a clear description of what and why.
- Add or update tests for behaviour you change, especially anything in `crypto.py`, `provenance.py` or payment code.
- **Don't overclaim.** The project's rule is that nothing is presented as on-chain, hardware-signed or verified unless it actually is. Demo data, simulated devices, test sensor readings and fallbacks must stay labelled in code, UI and docs.
- Never put made-up transaction hashes or addresses in data that could be mistaken for real records.
- Security issues: report privately as described in [SECURITY.md](SECURITY.md), not in a public issue.

## Licence
By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).
