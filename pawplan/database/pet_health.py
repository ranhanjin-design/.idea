"""Pet health profile, daily records, and memory library (after-midterm Module 2/3)."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pawplan.database.db import ROOT, get_connection

UPLOAD_DIR = ROOT / "data" / "pet_uploads"

PET_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS pets (
    pet_id          TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    species         TEXT NOT NULL DEFAULT 'dog',
    breed           TEXT,
    sex             TEXT,
    birth_date      TEXT,
    age_years       REAL,
    neutered        INTEGER DEFAULT 0,
    avatar_url      TEXT,
    notes           TEXT,
    is_example      INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pet_daily_records (
    record_id       TEXT PRIMARY KEY,
    pet_id          TEXT NOT NULL REFERENCES pets(pet_id) ON DELETE CASCADE,
    record_date     TEXT NOT NULL,
    weight_kg       REAL,
    food_g          REAL,
    food_note       TEXT,
    exercise_min    REAL,
    exercise_note   TEXT,
    notes           TEXT,
    created_at      TEXT NOT NULL,
    UNIQUE(pet_id, record_date)
);

CREATE INDEX IF NOT EXISTS idx_pet_daily_pet_date
    ON pet_daily_records(pet_id, record_date);

CREATE TABLE IF NOT EXISTS pet_memories (
    memory_id       TEXT PRIMARY KEY,
    pet_id          TEXT NOT NULL REFERENCES pets(pet_id) ON DELETE CASCADE,
    memory_type     TEXT NOT NULL,
    title           TEXT,
    body            TEXT,
    image_path      TEXT,
    event_date      TEXT,
    tags_json       TEXT,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pet_memories_pet
    ON pet_memories(pet_id, created_at);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_pet_tables(conn: sqlite3.Connection | None = None) -> None:
    own = conn is None
    if own:
        conn = get_connection()
    assert conn is not None
    try:
        conn.executescript(PET_SCHEMA_SQL)
        _seed_buddy_if_empty(conn)
        conn.commit()
    finally:
        if own:
            conn.close()


def _seed_buddy_if_empty(conn: sqlite3.Connection) -> None:
    n = conn.execute("SELECT COUNT(*) FROM pets").fetchone()[0]
    if n > 0:
        return
    pet_id = "pet_buddy_demo"
    now = _now_iso()
    conn.execute(
        """
        INSERT INTO pets (
            pet_id, name, species, breed, sex, birth_date, age_years, neutered,
            avatar_url, notes, is_example, created_at, updated_at
        ) VALUES (?, ?, 'dog', 'Golden Retriever', 'Male', '2023-03-01', 3, 1,
                  '/static/buddy_avatar.svg', 'Example profile for demo.', 1, ?, ?)
        """,
        (pet_id, "Buddy", now, now),
    )
    # 5 weeks of weight trend matching the briefing mock (30 → 28.5)
    weights = [30.0, 29.2, 28.9, 28.7, 28.5]
    foods = [340, 330, 325, 320, 320]
    exercises = [30, 35, 40, 42, 45]
    today = date.today()
    for i, (w, f, e) in enumerate(zip(weights, foods, exercises)):
        d = (today - timedelta(days=(4 - i) * 7)).isoformat()
        conn.execute(
            """
            INSERT INTO pet_daily_records (
                record_id, pet_id, record_date, weight_kg, food_g, food_note,
                exercise_min, exercise_note, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"rec_buddy_w{i+1}",
                pet_id,
                d,
                w,
                f,
                "dry food",
                e,
                "walk + play",
                f"Week {i+1} demo log",
                now,
            ),
        )
    memories = [
        (
            "mem_buddy_1",
            "note",
            "Adopted Buddy",
            "Brought Buddy home. Soft temperament, loves tennis balls.",
            (today - timedelta(days=400)).isoformat(),
            ["milestone"],
        ),
        (
            "mem_buddy_2",
            "vet",
            "Annual checkup",
            "Vet said teeth look mostly clean; continue brushing 2–3×/week.",
            (today - timedelta(days=60)).isoformat(),
            ["vet", "dental"],
        ),
        (
            "mem_buddy_3",
            "symptom",
            "Mild itch after walk",
            "Redness between toes after wet grass. Cleared next day.",
            (today - timedelta(days=14)).isoformat(),
            ["skin"],
        ),
    ]
    for mid, mtype, title, body, ed, tags in memories:
        conn.execute(
            """
            INSERT INTO pet_memories (
                memory_id, pet_id, memory_type, title, body, image_path,
                event_date, tags_json, created_at
            ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?)
            """,
            (mid, pet_id, mtype, title, body, ed, json.dumps(tags, ensure_ascii=False), now),
        )


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def list_pets() -> list[dict[str, Any]]:
    ensure_pet_tables()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM pets ORDER BY is_example DESC, name COLLATE NOCASE"
        ).fetchall()
        return [_row_to_dict(r) for r in rows]  # type: ignore[misc]
    finally:
        conn.close()


def get_pet(pet_id: str) -> dict[str, Any] | None:
    ensure_pet_tables()
    conn = get_connection()
    try:
        return _row_to_dict(
            conn.execute("SELECT * FROM pets WHERE pet_id = ?", (pet_id,)).fetchone()
        )
    finally:
        conn.close()


def upsert_pet(payload: dict[str, Any]) -> dict[str, Any]:
    ensure_pet_tables()
    conn = get_connection()
    try:
        pet_id = (payload.get("pet_id") or "").strip() or f"pet_{uuid.uuid4().hex[:10]}"
        now = _now_iso()
        existing = conn.execute(
            "SELECT pet_id FROM pets WHERE pet_id = ?", (pet_id,)
        ).fetchone()
        fields = {
            "pet_id": pet_id,
            "name": (payload.get("name") or "").strip() or "Unnamed",
            "species": (payload.get("species") or "dog").strip() or "dog",
            "breed": payload.get("breed"),
            "sex": payload.get("sex"),
            "birth_date": payload.get("birth_date"),
            "age_years": payload.get("age_years"),
            "neutered": 1 if payload.get("neutered") else 0,
            "avatar_url": payload.get("avatar_url"),
            "notes": payload.get("notes"),
            "is_example": 1 if payload.get("is_example") else 0,
            "updated_at": now,
        }
        if existing:
            conn.execute(
                """
                UPDATE pets SET name=:name, species=:species, breed=:breed, sex=:sex,
                    birth_date=:birth_date, age_years=:age_years, neutered=:neutered,
                    avatar_url=:avatar_url, notes=:notes, is_example=:is_example,
                    updated_at=:updated_at
                WHERE pet_id=:pet_id
                """,
                fields,
            )
        else:
            fields["created_at"] = now
            conn.execute(
                """
                INSERT INTO pets (
                    pet_id, name, species, breed, sex, birth_date, age_years, neutered,
                    avatar_url, notes, is_example, created_at, updated_at
                ) VALUES (
                    :pet_id, :name, :species, :breed, :sex, :birth_date, :age_years, :neutered,
                    :avatar_url, :notes, :is_example, :created_at, :updated_at
                )
                """,
                fields,
            )
        conn.commit()
        return get_pet(pet_id) or fields
    finally:
        conn.close()


def list_daily_records(pet_id: str, limit: int = 90) -> list[dict[str, Any]]:
    ensure_pet_tables()
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM pet_daily_records
            WHERE pet_id = ?
            ORDER BY record_date ASC
            LIMIT ?
            """,
            (pet_id, limit),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]  # type: ignore[misc]
    finally:
        conn.close()


def upsert_daily_record(payload: dict[str, Any]) -> dict[str, Any]:
    ensure_pet_tables()
    pet_id = (payload.get("pet_id") or "").strip()
    if not pet_id:
        raise ValueError("pet_id required")
    if not get_pet(pet_id):
        raise ValueError("pet not found")
    record_date = (payload.get("record_date") or date.today().isoformat()).strip()
    record_id = (payload.get("record_id") or "").strip() or f"rec_{uuid.uuid4().hex[:12]}"
    now = _now_iso()
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT record_id FROM pet_daily_records WHERE pet_id=? AND record_date=?",
            (pet_id, record_date),
        ).fetchone()
        data = {
            "record_id": existing["record_id"] if existing else record_id,
            "pet_id": pet_id,
            "record_date": record_date,
            "weight_kg": payload.get("weight_kg"),
            "food_g": payload.get("food_g"),
            "food_note": payload.get("food_note"),
            "exercise_min": payload.get("exercise_min"),
            "exercise_note": payload.get("exercise_note"),
            "notes": payload.get("notes"),
            "created_at": now,
        }
        conn.execute(
            """
            INSERT INTO pet_daily_records (
                record_id, pet_id, record_date, weight_kg, food_g, food_note,
                exercise_min, exercise_note, notes, created_at
            ) VALUES (
                :record_id, :pet_id, :record_date, :weight_kg, :food_g, :food_note,
                :exercise_min, :exercise_note, :notes, :created_at
            )
            ON CONFLICT(pet_id, record_date) DO UPDATE SET
                weight_kg=excluded.weight_kg,
                food_g=excluded.food_g,
                food_note=excluded.food_note,
                exercise_min=excluded.exercise_min,
                exercise_note=excluded.exercise_note,
                notes=excluded.notes
            """,
            data,
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM pet_daily_records WHERE pet_id=? AND record_date=?",
            (pet_id, record_date),
        ).fetchone()
        return _row_to_dict(row) or data
    finally:
        conn.close()


def dashboard_for_pet(pet_id: str) -> dict[str, Any]:
    pet = get_pet(pet_id)
    if not pet:
        raise ValueError("pet not found")
    records = list_daily_records(pet_id, limit=120)
    latest = next((r for r in reversed(records) if r), None)
    weight_series = [
        {"date": r["record_date"], "weight_kg": r["weight_kg"]}
        for r in records
        if r.get("weight_kg") is not None
    ]
    return {
        "pet": pet,
        "latest": {
            "weight_kg": (latest or {}).get("weight_kg"),
            "food_g": (latest or {}).get("food_g"),
            "exercise_min": (latest or {}).get("exercise_min"),
            "record_date": (latest or {}).get("record_date"),
        },
        "weight_series": weight_series,
        "records": records,
        "memories": list_memories(pet_id, limit=30),
    }


def list_memories(pet_id: str, limit: int = 50) -> list[dict[str, Any]]:
    ensure_pet_tables()
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM pet_memories
            WHERE pet_id = ?
            ORDER BY COALESCE(event_date, created_at) DESC
            LIMIT ?
            """,
            (pet_id, limit),
        ).fetchall()
        out = []
        for r in rows:
            d = _row_to_dict(r)
            if not d:
                continue
            try:
                d["tags"] = json.loads(d.get("tags_json") or "[]")
            except json.JSONDecodeError:
                d["tags"] = []
            out.append(d)
        return out
    finally:
        conn.close()


def add_memory(payload: dict[str, Any]) -> dict[str, Any]:
    ensure_pet_tables()
    pet_id = (payload.get("pet_id") or "").strip()
    if not pet_id or not get_pet(pet_id):
        raise ValueError("pet not found")
    memory_id = f"mem_{uuid.uuid4().hex[:12]}"
    now = _now_iso()
    tags = payload.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO pet_memories (
                memory_id, pet_id, memory_type, title, body, image_path,
                event_date, tags_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory_id,
                pet_id,
                (payload.get("memory_type") or "note").strip() or "note",
                payload.get("title"),
                payload.get("body"),
                payload.get("image_path"),
                payload.get("event_date") or date.today().isoformat(),
                json.dumps(tags, ensure_ascii=False),
                now,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM pet_memories WHERE memory_id = ?", (memory_id,)
        ).fetchone()
        d = _row_to_dict(row) or {}
        d["tags"] = tags
        return d
    finally:
        conn.close()


def save_upload(filename: str, data: bytes) -> str:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe = "".join(c for c in Path(filename).name if c.isalnum() or c in "._-") or "upload.bin"
    out_name = f"{uuid.uuid4().hex[:10]}_{safe}"
    path = UPLOAD_DIR / out_name
    path.write_bytes(data)
    return f"/api/pets/uploads/{out_name}"


def observe_health(pet_id: str, question: str, image_path: str | None = None) -> dict[str, Any]:
    """Safety-first multimodal stub: describe uncertainty, ask follow-ups, never diagnose."""
    pet = get_pet(pet_id)
    if not pet:
        raise ValueError("pet not found")
    q = (question or "").strip()
    q_lower = q.lower()
    visible = []
    followups = []
    topic = "general"

    if any(k in q for k in ("牙", "齿", "结石", "口臭")) or "tooth" in q_lower or "tartar" in q_lower:
        topic = "dental"
        visible.append("照片中若可见牙齿表面黄褐色沉积，可能与牙垢或牙结石有关，但仅凭照片不能确诊。")
        followups = [
            "狗狗是否有明显口臭？",
            "是否有牙龈出血或红肿？",
            "是否出现进食困难或只吃一边？",
        ]
        advice = "建议安排兽医口腔检查；日常可在兽医指导下清洁牙齿。本助手不作诊断或开药。"
    elif any(k in q for k in ("脚", "趾", "红肿", "皮肤", "疹")) or "paw" in q_lower or "skin" in q_lower:
        topic = "skin_paw"
        visible.append("照片中若可见红肿、破皮或异常分泌物，属于需要关注的可见现象，仍不能据此确诊。")
        followups = [
            "是否持续舔咬该部位？",
            "是否有明显疼痛或跛行？",
            "症状持续多久了？",
        ]
        advice = "若红肿加重、渗液或影响行走，请尽快联系兽医。本助手仅作观察提示。"
    else:
        visible.append("已收到描述" + ("与图片" if image_path else "") + "。仅凭文字/单张照片无法确诊健康问题。")
        followups = [
            "症状大约从什么时候开始？",
            "是否影响食欲、精神或活动？",
            "是否已看过兽医？",
        ]
        advice = "请把可观察现象与症状告诉兽医；紧急情况（呼吸困难、持续呕吐、抽搐等）请立即就医。"

    reply_parts = [
        f"关于 {pet['name']}：",
        *visible,
        "",
        "想再确认几件事：",
        *[f"- {f}" for f in followups],
        "",
        advice,
        "",
        "免责声明：PawPlan Health Assistant 提供日常观察与教育信息，不能替代专业兽医诊疗。",
    ]
    reply = "\n".join(reply_parts)

    # Persist as memory so the library keeps the observation trail
    mem = add_memory(
        {
            "pet_id": pet_id,
            "memory_type": "observe",
            "title": f"Health observe · {topic}",
            "body": f"Q: {q}\n\nA: {reply}",
            "image_path": image_path,
            "event_date": date.today().isoformat(),
            "tags": ["observe", topic],
        }
    )
    return {
        "reply": reply,
        "topic": topic,
        "followups": followups,
        "image_path": image_path,
        "memory": mem,
        "disclaimer": "Not a veterinary diagnosis.",
    }
