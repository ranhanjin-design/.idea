"""Import staged park JSON into SQLite parks table."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pawplan.database.db import get_connection, init_database
from pawplan.ingestion.park_sources import park_source_url

ROOT = Path(__file__).resolve().parents[2]


def import_parks(staging_path: Path, replace: bool = True) -> int:
    payload = json.loads(staging_path.read_text(encoding="utf-8"))
    rows = payload.get("parks", [])
    conn = get_connection()
    try:
        init_database()
        coordinates = {
            r["park_id"]: (r["latitude"], r["longitude"])
            for r in conn.execute("SELECT park_id, latitude, longitude FROM parks")
            if r["latitude"] is not None and r["longitude"] is not None
        }
        if replace:
            conn.execute("DELETE FROM parks")
        for row in rows:
            # Also accept older staging files without restoring bulk PDF/JSON links.
            row = {**row, "source_url": park_source_url(row["district"], row["park_type"])}
            if (row.get("latitude") is None or row.get("longitude") is None) and row["park_id"] in coordinates:
                row["latitude"], row["longitude"] = coordinates[row["park_id"]]
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
