## What and why

## How it was tested

## Checklist
- [ ] `python -m pytest -q backend/tests` passes
- [ ] `cd web && npx tsc --noEmit` passes
- [ ] Contract changes: both ABI copies regenerated (`contracts/` and `backend/app/chain/`)
- [ ] Arkiv schema changes: `backend/arkiv/schemas.mjs`, `web/src/lib/arkiv.ts` and `arkiv/schema.md` updated together
- [ ] No secrets, private keys or `.env` values committed
- [ ] Demo, simulated or fallback behaviour stays clearly labelled; docs don't claim more than the code does
