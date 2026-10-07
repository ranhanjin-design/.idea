"""Import staged park JSON into SQLite parks table."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pawplan.database.db import get_connection, init_database

ROOT = Path(__file__).resolve().parents[2]


def import_parks(staging_path: Path, replace: bool = True) -> int:
    payload = json.loads(staging_path.read_text(encoding="utf-8"))
    rows = payload.get("parks", [])
    conn = get_connection()
    try:
        init_database()
        if replace:
            conn.execute("DELETE FROM parks")
        for row in rows:
            conn.execute(
                """
                INSERT OR REPLACE INTO parks (
                    park_id, park_type, name_en, name_zh, district, address,
                    facilities_json, opening_hours, phone, latitude, longitude,
                    source_url, last_verified_at
                ) VALUES (
                    :park_id, :park_type, :name_en, :name_zh, :district, :address,
                    :facilities_json, :opening_hours, :phone, :latitude, :longitude,
                    :source_url, :last_verified_at
                )
                """,
                row,
            )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Import parks into SQLite")
    parser.add_argument(
        "--in",
        dest="inp",
        default=str(ROOT / "data" / "staging" / "lcsd_parks.json"),
    )
    args = parser.parse_args()
    n = import_parks(Path(args.inp), replace=True)
    print(f"Imported {n} parks")


if __name__ == "__main__":
    main()
