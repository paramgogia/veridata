# Argus backend (FastAPI) — one container with Python (API, training, video) and Node (Arkiv writer).
# Persistent state lives in /app/data (SQLite DB, encrypted media, keys): mount a volume there.
FROM node:20-slim AS node

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

# Node 20 for backend/arkiv/writer.mjs (copied from the official image: small and current)
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
 && apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
# CPU-only PyTorch (the default index pulls ~2.5 GB of CUDA libraries); headless OpenCV (no GUI libs,
# still bundles FFmpeg for the WebM/VP8 video encoder).
RUN pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu \
 && grep -viE '^(torch|torchvision|opencv-python)\b' requirements.txt > /tmp/req.txt \
 && pip install -r /tmp/req.txt opencv-python-headless

COPY arkiv/package.json arkiv/package-lock.json* arkiv/
RUN cd arkiv && npm install --omit=dev --no-audit --no-fund

COPY . .
RUN chmod +x docker-entrypoint.sh
ENV PORT=8000
EXPOSE 8000
CMD ["./docker-entrypoint.sh"]
