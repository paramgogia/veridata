# Deploying Argus (frontend + backend in the cloud)

Two containers from this repo:

| Service | Folder | What it runs | Needs |
|---|---|---|---|
| **api** | `backend/` | FastAPI + training (CPU PyTorch) + video (OpenCV) + Arkiv writer (Node) | a persistent volume at `/app/data` |
| **web** | `web/` | Next.js frontend | `NEXT_PUBLIC_API_URL` = the api's public URL (set **before** building) |

On first boot the api seeds the demo data into the empty volume; later boots reuse it.

## Railway (recommended: volumes, websockets, HTTPS domains)

1. **New project:** railway.app → *New Project* → *Deploy from GitHub repo* → `paramgogia/veridata`.
2. **api service**
   - *Settings → Source → Root Directory*: `backend` (the Dockerfile is picked up automatically)
   - *Settings → Deploy → Healthcheck Path*: `/api/health`
   - *Volume*: right-click the service → *Attach Volume* → mount path **`/app/data`**
   - *Variables* (see the table below)
   - *Settings → Networking → Generate Domain* (port **8000**) → e.g. `https://argus-api.up.railway.app`
3. **web service:** *+ New → GitHub Repo* → same repo
   - *Root Directory*: `web`
   - *Variables*: `NEXT_PUBLIC_API_URL=https://argus-api.up.railway.app` (no trailing slash)
   - *Networking → Generate Domain* (port **3000**) → e.g. `https://argus.up.railway.app`
4. Open the web URL. Check `https://<api-domain>/api/health` returns `{"ok": true}`.

CORS already allows any `https://*.up.railway.app` and `https://*.vercel.app` origin; for a custom
domain add `CORS_ORIGINS=https://your-domain` to the api variables.

Use the Hobby plan: model training needs about 1–2 GB of RAM, which may exceed trial limits.

### api variables

| Variable | Value | Needed for |
|---|---|---|
| `VERIDATA_CONTRACT_ADDRESS` | `0x513Fb1925A6a0D81960f1D3eb7d7D4C418D8A596` | Sepolia: devices, datasets, escrow |
| `WHITECHAIN_PAY_ADDRESS` | `0x997E7f5B2e1Ea27290a5705F39F1A2e468483FBC` | gasless USDT checkout |
| `WALLET_PRIVATE_KEY` | backend wallet key (**secret**) | 0G storage uploads + Whitechain relayer gas |
| `AI_BASE_URL` / `AI_API_KEY` / `AI_MODEL` | e.g. `https://router-api.0g.ai/v1`, key, `gemini-2.5-flash` | AI quality/privacy checks |
| `ARKIV_ACCESS_KEY` (+ optional `ARKIV_PRIVATE_KEY`) | Arkiv key (**secret**) | Arkiv index writes |
| `WHITECHAIN_USDT_PER_ETH` | `100` | default USDT price conversion |
| `MASTER_KEY_HEX`, `SESSION_SECRET` | optional | generated into the volume if unset |

Everything else has working defaults (`backend/app/config.py`). Without the optional keys the app
still runs: 0G falls back to local storage, AI checks to heuristics, Arkiv is skipped.

### web variables

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | the api's public URL (**required**, baked in at build: redeploy after changing it) |
| `NEXT_PUBLIC_ARKIV_ACCESS_KEY` | optional: the Demand Board reads requests from Arkiv |

## Render

1. **api:** render.com → *New → Web Service* → this repo
   - Root Directory `backend`, Runtime **Docker**, Instance **Standard (2 GB)** (training needs the RAM)
   - Health Check Path `/api/health`
   - *Advanced → Add Disk*: mount path **`/app/data`**, 1 GB (paid instances only; without it data is lost on every deploy)
   - Environment: the api variables above. Render sets `PORT` itself.
2. **web:** *New → Web Service* → same repo
   - Root Directory `web`, Runtime **Node**, Build `npm ci && npm run build`, Start `npm start`, Instance Free is fine
   - Environment: `NEXT_PUBLIC_API_URL=https://<api-service>.onrender.com`
3. CORS already allows `https://*.onrender.com`.

## Devices in the cloud

A cloud backend cannot reach boards on a private Wi-Fi network (`192.168.x` / `172.20.10.x`). Options:

- **No hardware:** capture with *This device's camera* (works over HTTPS, including phones) and
  *Use test sensor data*, or register a *simulated* device.
- **Your own boards:** make them reachable from the internet (for example a `cloudflared` tunnel per
  board) and paste the public URLs in *Devices → your device → Connection*.
- **Live demo with local boards:** run the backend on the laptop that shares the boards' Wi-Fi and
  expose it with `cloudflared tunnel --url http://localhost:8000`; point the web service at that URL.

## Everything locally in containers

```bash
docker compose up --build        # web on http://localhost:3000, api on http://localhost:8000
```
Uses `./.env` for secrets and a `argus-data` Docker volume for state.
