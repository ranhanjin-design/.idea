"""Simple JSONL logging for agent tool calls and replies."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "logs"


def log_event(event: dict) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / "agent.jsonl"
    payload = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "event_id": uuid.uuid4().hex[:12],
        **event,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    return path
