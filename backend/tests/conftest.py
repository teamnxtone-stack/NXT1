"""pytest configuration — load REACT_APP_BACKEND_URL from frontend/.env so the
phase11/12 integration tests don't crash on import."""
import os
from pathlib import Path

from dotenv import load_dotenv

# Load backend env first (Mongo, JWT, etc.)
_BACKEND = Path(__file__).resolve().parent.parent / ".env"
if _BACKEND.exists():
    load_dotenv(_BACKEND, override=False)

# Then load REACT_APP_BACKEND_URL from frontend/.env so requests-based tests can
# hit the live preview URL (kubernetes ingress) instead of localhost.
_FRONTEND = Path("/app/frontend/.env")
if _FRONTEND.exists():
    load_dotenv(_FRONTEND, override=False)

# Final guardrail
os.environ.setdefault("APP_PASSWORD", "555")
