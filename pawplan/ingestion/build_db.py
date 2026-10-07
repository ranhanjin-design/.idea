"""Build curated SQLite DB from enriched staging JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pawplan.database.db import get_connection, init_database

ROOT = Path(__file__).resolve().parents[2]


def load_enriched(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("restaurants", [])


def import_restaurants(rows: list[dict], replace: bool = True) -> int:
    conn = get_connection()
    try:
        init_database()  # ensure schema
        if replace:
            conn.execute("DELETE FROM restaurant_cuisines")
            conn.execute("DELETE FROM restaurants")

        count = 0
        for row in rows:
            conn.execute(
                """
                INSERT OR REPLACE INTO restaurants (
                    restaurant_id, licence_no, name_en, name_zh, district, address,
                    latitude, longitude, dog_permission, opening_hours_json,
                    source_url, last_verified_at
                ) VALUES (
                    :restaurant_id, :licence_no, :name_en, :name_zh, :district, :address,
                    :latitude, :longitude, :dog_permission, :opening_hours_json,
                    :source_url, :last_verified_at
                )
                """,
                {
                    "restaurant_id": row["restaurant_id"],
                    "licence_no": row.get("licence_no"),
                    "name_en": row.get("name_en"),
                    "name_zh": row.get("name_zh"),
                    "district": row["district"],
                    "address": row["address"],
                    "latitude": row.get("latitude"),
                    "longitude": row.get("longitude"),
                    "dog_permission": 1 if row.get("dog_permission", True) else 0,
                    "opening_hours_json": row.get("opening_hours_json"),
                    "source_url": row["source_url"],
                    "last_verified_at": row["last_verified_at"],
                },
            )
            for c in row.get("cuisines") or []:
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
                    {
                        "restaurant_id": row["restaurant_id"],
                        "cuisine_code": c["cuisine_code"],
                        "cuisine_label_zh": c.get("cuisine_label_zh"),
                        "cuisine_label_en": c.get("cuisine_label_en"),
                        "cuisine_source_url": c.get("cuisine_source_url")
                        or "unknown://",
                        "cuisine_confidence": float(c.get("cuisine_confidence", 0.1)),
                    },
                )
            count += 1
        conn.commit()
        return count
    finally:
        conn.close()


def build_from_enriched(path: Path, replace: bool = True) -> int:
    rows = load_enriched(path)
    return import_restaurants(rows, replace=replace)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import enriched JSON into SQLite")
    parser.add_argument(
        "--in",
        dest="inp",
        default=str(ROOT / "data" / "staging" / "fehd_restaurants_enriched.json"),
    )
    parser.add_argument("--keep-existing", action="store_true")
    args = parser.parse_args()
    n = build_from_enriched(Path(args.inp), replace=not args.keep_existing)
    print(f"Imported {n} restaurants into database")


if __name__ == "__main__":
    main()
