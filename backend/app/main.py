"""Veridata API — run with:  uvicorn app.main:app --port 8000  (from backend/)"""
from __future__ import annotations

import os
import time
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import config
from .db import init_db
from .routers import core, devices, market, requests, samples, training, whitechain

app = FastAPI(title="Veridata API", version="0.1.0")
# Browser origins allowed to call the API: local dev, extra origins in CORS_ORIGINS (comma separated),
# and hosted deployments via CORS_ORIGIN_REGEX (default: *.vercel.app, *.up.railway.app, *.onrender.com; empty disables).
_origins = ["http://localhost:3000", "http://127.0.0.1:3000"] + [o.strip().rstrip("/") for o in config.env("CORS_ORIGINS").split(",") if o.strip()]
_origin_regex = os.environ.get("CORS_ORIGIN_REGEX", r"https://[a-z0-9-]+\.(vercel\.app|up\.railway\.app|onrender\.com)")
# Auth is a Bearer token in the Authorization header (no cookies), so credentialed CORS is not
# needed. Keeping it off means another site on an allowed domain can never ride a user's cookies.
app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_origin_regex=_origin_regex or None, allow_credentials=False,
                   allow_methods=["*"], allow_headers=["*"], expose_headers=["X-PAYMENT-RESPONSE"])

# Simple sliding-window rate limit per IP (in-memory; use a shared store in production).
_hits: dict[str, deque] = defaultdict(deque)
LIMITS = {"/api/auth": 20, "/api/devices/": 600, "default": 300}


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    path = request.url.path
    if path.endswith("/stream") or path.startswith("/api/previews"):
        return await call_next(request)
    key_prefix = next((p for p in LIMITS if p != "default" and path.startswith(p)), "default")
    ip = request.client.host if request.client else "?"
    q = _hits[f"{ip}|{key_prefix}"]
    now = time.time()
    while q and q[0] < now - 60:
        q.popleft()
    if len(q) >= LIMITS[key_prefix]:
        return JSONResponse({"detail": "rate limit exceeded, slow down"}, status_code=429)
    q.append(now)
    return await call_next(request)


for r in (core, devices, samples, market, requests, training, whitechain):
    app.include_router(r.router)


@app.on_event("startup")
def _startup():
    init_db()
    # Warm the 0G fine-tuning status cache in the background so the first
    # dashboard request doesn't wait on the (flaky) 0G RPC.
    import threading
    from . import zerog
    threading.Thread(target=zerog.ft_status, daemon=True).start()


@app.get("/api/health")
def health():
    return {"ok": True, "ts": time.time()}
