"""JSON run store: atomic writes + thread-safe, tolerant reads."""

import contextlib
import json
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path

STORE = Path(__file__).resolve().parent.parent / "runs" / "history.json"
_LOCK = threading.Lock()


def load() -> list[dict]:
    if not STORE.exists():
        return []
    try:
        data = json.loads(STORE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        # Corrupt file -> back it up instead of crashing the demo
        with contextlib.suppress(Exception):
            STORE.replace(STORE.with_suffix(".corrupt.json"))
        return []


def save(entry: dict) -> list[dict]:
    with _LOCK:
        hist = load()
        entry["run_id"] = f"RUN-{len(hist) + 1:03d}"
        entry["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        hist.append(entry)
        STORE.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(STORE.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(hist, f, indent=2)
            os.replace(tmp, STORE)  # atomic on Windows + POSIX
        finally:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
        return hist
