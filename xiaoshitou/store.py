from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
PROFILE_PATH = DATA / "profile.json"
CHATS_PATH = DATA / "chats_sample.json"
DB_PATH = DATA / "memory.db"


def load_profile() -> dict:
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def save_profile(profile: dict) -> None:
    PROFILE_PATH.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")


def load_chats() -> list[dict]:
    return json.loads(CHATS_PATH.read_text(encoding="utf-8"))


def get_conn() -> sqlite3.Connection:
    DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            source TEXT,
            confidence REAL NOT NULL DEFAULT 0.5,
            verified INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )
    conn.commit()
    return conn


def add_memory(
    key: str,
    value: str,
    source: str = "user",
    confidence: float = 0.8,
    verified: bool = False,
) -> None:
    conn = get_conn()
    try:
        # upsert-like: keep latest same key
        conn.execute("DELETE FROM memories WHERE key = ? AND verified = 0", (key,))
        conn.execute(
            """
            INSERT INTO memories (key, value, source, confidence, verified)
            VALUES (?, ?, ?, ?, ?)
            """,
            (key, value, source, confidence, 1 if verified else 0),
        )
        conn.commit()
    finally:
        conn.close()


def list_memories(limit: int = 50) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT id, key, value, source, confidence, verified, created_at
            FROM memories
            ORDER BY verified DESC, confidence DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def resolved_facts() -> dict[str, str]:
    """Merge profile + verified memories into a silent fact sheet."""
    profile = load_profile()
    facts = dict(profile.get("facts") or {})
    out: dict[str, str] = {}
    for k, v in facts.items():
        if v is None or v is False:
            continue
        if isinstance(v, bool):
            continue
        s = str(v).strip()
        if not s or s.lower() == "unknown" or "请改成" in s:
            continue
        out[k] = s

    for row in list_memories(100):
        if row.get("verified") or float(row.get("confidence") or 0) >= 0.85:
            out[row["key"]] = row["value"]
    return out


def save_message(role: str, text: str) -> None:
    conn = get_conn()
    try:
        conn.execute("INSERT INTO messages (role, text) VALUES (?, ?)", (role, text))
        conn.commit()
    finally:
        conn.close()


def recent_messages(limit: int = 16) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT role, text, created_at FROM messages
            ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return list(reversed([dict(r) for r in rows]))
    finally:
        conn.close()
