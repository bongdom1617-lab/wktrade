from __future__ import annotations

import sys
from pathlib import Path

# Expose backend/ so `from app...` imports resolve identically on Vercel and locally
BACKEND_ROOT = str(Path(__file__).resolve().parent.parent / "backend")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.main import app  # noqa: E402, F401
