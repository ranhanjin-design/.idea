import json
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS restaurants (
    restaurant_id       TEXT PRIMARY KEY,
    licence_no          TEXT UNIQUE,
    name_en             TEXT,
    name_zh             TEXT,
    district            TEXT NOT NULL,
    address             TEXT NOT NULL,
    latitude            REAL,
    longitude           REAL,
    dog_permission      INTEGER NOT NULL CHECK (dog_permission IN (0, 1)),
    opening_hours_json  TEXT,
    source_url          TEXT NOT NULL,
    last_verified_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS restaurant_cuisines (
    restaurant_id       TEXT NOT NULL REFERENCES restaurants(restaurant_id),
    cuisine_code        TEXT NOT NULL,
    cuisine_label_zh    TEXT,
    cuisine_label_en    TEXT,
    cuisine_source_url  TEXT NOT NULL,
    cuisine_confidence  REAL NOT NULL,
    PRIMARY KEY (restaurant_id, cuisine_code)
);

CREATE INDEX IF NOT EXISTS idx_restaurants_district
    ON restaurants(district);
CREATE INDEX IF NOT EXISTS idx_cuisines_code
    ON restaurant_cuisines(cuisine_code);

CREATE TABLE IF NOT EXISTS parks (
    park_id             TEXT PRIMARY KEY,
    park_type           TEXT NOT NULL,
    name_en             TEXT,
    name_zh             TEXT,
    district            TEXT NOT NULL,
    address             TEXT,
    facilities_json     TEXT,
    opening_hours       TEXT,
    phone               TEXT,
    latitude            REAL,
    longitude           REAL,
    source_url          TEXT NOT NULL,
    last_verified_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_parks_district ON parks(district);
CREATE INDEX IF NOT EXISTS idx_parks_type ON parks(park_type);

CREATE TABLE IF NOT EXISTS places (
    place_id            TEXT PRIMARY KEY,
    place_type          TEXT NOT NULL,
    name_en             TEXT,
    name_zh             TEXT,
    district            TEXT NOT NULL,
    address             TEXT,
    phone               TEXT,
    website             TEXT,
    latitude            REAL,
    longitude           REAL,
    opening_hours_json  TEXT,
    amenities_json      TEXT,
    pet_policy_json     TEXT,
    source_url          TEXT NOT NULL,
    source_name         TEXT NOT NULL,
    last_verified_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_places_district ON places(district);
CREATE INDEX IF NOT EXISTS idx_places_type ON places(place_type);
"""

# Demo rows used only when DB is empty (before FEHD pipeline).
SEED_ROWS = [
    {
        "restaurant_id": "demo_st_001",
        "licence_no": "DEMO001",
        "name_en": "Harbour Dim Sum Cafe",
        "name_zh": "港畔点心坊",
        "district": "Sha Tin",
        "address": "Shop 12, New Town Plaza Phase 1, Sha Tin",
        "dog_permission": 1,
        "opening_hours_json": None,
        "source_url": "https://www.fehd.gov.hk/english/licensing/dog_restaurants/fulllist.pdf",
        "last_verified_at": "2026-09-02",
        "cuisine_code": "dim_sum",
        "cuisine_label_zh": "点心",
        "cuisine_label_en": "Dim Sum",
        "cuisine_source_url": "curated://pawplan/demo",
        "cuisine_confidence": 0.92,
    },
    {
        "restaurant_id": "demo_st_002",
        "licence_no": "DEMO002",
        "name_en": "Sha Tin Tea Garden",
        "name_zh": "沙田茶楼",
        "district": "Sha Tin",
        "address": "G/F, Citylink Plaza, Sha Tin",
        "dog_permission": 1,
        "opening_hours_json": None,
        "source_url": "https://www.fehd.gov.hk/english/licensing/dog_restaurants/fulllist.pdf",
        "last_verified_at": "2026-09-02",
        "cuisine_code": "dim_sum",
        "cuisine_label_zh": "点心",
        "cuisine_label_en": "Dim Sum",
        "cuisine_source_url": "curated://pawplan/demo",
        "cuisine_confidence": 0.88,
    },
    {
        "restaurant_id": "demo_mk_001",
        "licence_no": "DEMO003",
        "name_en": "Mong Kok Yum Cha House",
        "name_zh": "旺角饮茶轩",
        "district": "Mong Kok",
        "address": "2/F, Sample Building, Mong Kok",
        "dog_permission": 1,
        "opening_hours_json": None,
        "source_url": "https://www.fehd.gov.hk/english/licensing/dog_restaurants/fulllist.pdf",
        "last_verified_at": "2026-09-02",
        "cuisine_code": "dim_sum",
        "cuisine_label_zh": "点心",
        "cuisine_label_en": "Dim Sum",
        "cuisine_source_url": "curated://pawplan/demo",
        "cuisine_confidence": 0.85,
    },
    {
        "restaurant_id": "demo_cw_001",
        "licence_no": "DEMO004",
        "name_en": "Peak Side Cafe",
        "name_zh": "山顶咖啡",
        "district": "Central/Western",
        "address": "Shop G17, The Peak Tower, Hong Kong",
        "dog_permission": 1,
        "opening_hours_json": None,
        "source_url": "https://www.fehd.gov.hk/english/licensing/dog_restaurants/fulllist.pdf",
        "last_verified_at": "2026-09-02",
        "cuisine_code": "cafe",
        "cuisine_label_zh": "咖啡店",
        "cuisine_label_en": "Cafe",
        "cuisine_source_url": "curated://pawplan/demo",
        "cuisine_confidence": 0.9,
    },
]


def get_db_path() -> Path:
    raw = os.environ.get("PAWPLAN_DB_PATH", "data/curated/pawplan.db")
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    return path


def get_connection() -> sqlite3.Connection:
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def seed_demo_rows(conn: sqlite3.Connection) -> None:
    for row in SEED_ROWS:
        conn.execute(
            """
            INSERT OR REPLACE INTO restaurants (
                restaurant_id, licence_no, name_en, name_zh, district, address,
                latitude, longitude, dog_permission, opening_hours_json,
                source_url, last_verified_at
            ) VALUES (
                :restaurant_id, :licence_no, :name_en, :name_zh, :district, :address,
                NULL, NULL, :dog_permission, :opening_hours_json,
                :source_url, :last_verified_at
            )
            """,
            row,
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO restaurant_cuisines (
                restaurant_id, cuisine_code, cuisine_label_zh, cuisine_label_en,
                cuisine_source_url, cuisine_confidence
            ) VALUES (
                :restaurant_id, :cuisine_code, :cuisine_label_zh, :cuisine_label_en,
                :cuisine_source_url, :cuisine_confidence
            )
            """,
            row,
        )


def init_database(force_seed: bool = False, apply_second_source: bool = True) -> None:
    conn = get_connection()
    try:
        conn.executescript(SCHEMA_SQL)
        count = conn.execute("SELECT COUNT(*) FROM restaurants").fetchone()[0]
        if force_seed:
            conn.execute("DELETE FROM restaurant_cuisines")
            conn.execute("DELETE FROM restaurants")
            seed_demo_rows(conn)
        elif count == 0:
            seed_demo_rows(conn)
        conn.commit()
    finally:
        conn.close()
    if apply_second_source:
        try:
            from pawplan.ingestion.enrich_cuisine import apply_second_source_to_db

            apply_second_source_to_db()
        except (OSError, ValueError, json.JSONDecodeError, sqlite3.Error) as exc:
            print(f"[pawplan] second-source cuisine patch skipped: {exc}")


def db_stats() -> dict:
    conn = get_connection()
    try:
        restaurants = conn.execute("SELECT COUNT(*) FROM restaurants").fetchone()[0]
        cuisines = conn.execute("SELECT COUNT(*) FROM restaurant_cuisines").fetchone()[0]
        districts = conn.execute(
            "SELECT COUNT(DISTINCT district) FROM restaurants"
        ).fetchone()[0]
        try:
            parks = conn.execute("SELECT COUNT(*) FROM parks").fetchone()[0]
            pet_gardens = conn.execute(
                "SELECT COUNT(*) FROM parks WHERE park_type = 'pet_garden'"
            ).fetchone()[0]
            inclusive = conn.execute(
                "SELECT COUNT(*) FROM parks WHERE park_type = 'inclusive_park'"
            ).fetchone()[0]
        except sqlite3.OperationalError:
            parks = pet_gardens = inclusive = 0
        try:
            places = conn.execute("SELECT COUNT(*) FROM places").fetchone()[0]
            malls = conn.execute(
                "SELECT COUNT(*) FROM places WHERE place_type = 'mall'"
            ).fetchone()[0]
            vets = conn.execute(
                "SELECT COUNT(*) FROM places WHERE place_type IN ('vet', 'dental', 'emergency')"
            ).fetchone()[0]
            groomers = conn.execute(
                "SELECT COUNT(*) FROM places WHERE place_type = 'groomer'"
            ).fetchone()[0]
        except sqlite3.OperationalError:
            places = malls = vets = groomers = 0
        return {
            "restaurants": restaurants,
            "cuisine_rows": cuisines,
            "districts": districts,
            "parks": parks,
            "pet_gardens": pet_gardens,
            "inclusive_parks": inclusive,
            "places": places,
            "malls": malls,
            "vets": vets,
            "groomers": groomers,
            "db_path": str(get_db_path()),
        }
    finally:
        conn.close()
