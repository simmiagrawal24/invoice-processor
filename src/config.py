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

# --- Models: provider dropdown, Gemini default. Only model calls in the codebase. ---
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
AGENT_MAX_REPAIRS = int(os.getenv("AGENT_MAX_REPAIRS", "2"))
