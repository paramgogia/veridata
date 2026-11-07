#!/bin/sh
# First boot on an empty volume: create the schema and the demo data. Later boots: no-op.
set -e
mkdir -p data/blobs data/previews data/weights data/models
python -m app.seed || echo "seed skipped/failed; continuing"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips="*"
