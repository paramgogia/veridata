import os
import sys
from pathlib import Path

# Deterministic test keys so tests never create or read real key files.
os.environ.setdefault("MASTER_KEY_HEX", "11" * 32)
os.environ.setdefault("SESSION_SECRET", "test-session-secret")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/
