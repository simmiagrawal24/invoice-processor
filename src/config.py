"""Central config — .env file first, real environment always wins."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

TOLERANCE_PCT = float(os.getenv("TOLERANCE_PCT", "0.02"))
TOLERANCE_ABS = float(os.getenv("TOLERANCE_ABS", "25.00"))
# Fuzzy vendor-match allowed overage multiplier (relative to tolerance)
FUZZY_TOL_MULT = float(os.getenv("FUZZY_TOL_MULT", "3.0"))

# --- Gemini (LangChain). Only model calls in the codebase. ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
AGENT_MAX_REPAIRS = int(os.getenv("AGENT_MAX_REPAIRS", "2"))
