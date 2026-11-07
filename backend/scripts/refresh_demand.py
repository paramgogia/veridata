"""Replace old seeded demo requests with ones that fit the Argus rig (RFID, IR, DHT, photo/video).

    cd backend && python scripts/refresh_demand.py

Only demo-ledger requests with no real samples submitted are replaced; everything else is untouched.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.seed import refresh_demand  # noqa: E402

refresh_demand()
