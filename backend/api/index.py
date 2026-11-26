from __future__ import annotations

import sys
from pathlib import Path

# Ensure backend/ root is on sys.path for Vercel Python runtime imports
BACKEND_ROOT = str(Path(__file__).resolve().parent.parent)
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.main import app  # noqa: E402, F401
