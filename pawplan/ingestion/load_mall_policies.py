"""Load Tier-2 venue-owned mall pet policies into the places table.

Hong Kong has no official government pet-friendly mall register. This loader
prefers each mall's published policy page over community directories (GoPaw).
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from pawplan.database.db import get_connection, init_database
from pawplan.ingestion.entity_match import compact_name
from pawplan.normalize import normalize_district

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = ROOT / "data" / "knowledge" / "mall_pet_policies.json"
SOURCE_NAME = "mall_official"


def load_policy_file(path: Path | None = None) -> dict:
    target = path or DEFAULT_PATH
    return json.loads(target.read_text(encoding="utf-8"))


def entries_to_place_rows(payload: dict) -> list[dict]:
    verified = payload.get("last_verified_at") or date.today().isoformat()
    rows: list[dict] = []
    for entry in payload.get("entries") or []:
        district = normalize_district(entry.get("district")) or entry.get("district")
        if not district:
            continue
        policy = {
            "access_mode": entry.get("access_mode"),
            "access_summary_zh": entry.get("access_summary_zh"),
            "stroller_loan": entry.get("stroller_loan"),
            "pets_accepted": entry.get("pets_accepted"),
            "evidence_tier": 2,
            "policy_pdf_url": entry.get("policy_pdf_url"),
        }
        rows.append(
            {
                "place_id": entry["place_id"],
                "place_type": "mall",
                "name_en": entry.get("name_en"),
                "name_zh": entry.get("name_zh"),
                "district": district,
                "address": entry.get("address"),
                "phone": entry.get("phone"),
                "website": entry.get("website") or entry.get("policy_url"),
                "latitude": entry.get("latitude"),
                "longitude": entry.get("longitude"),
                "opening_hours_json": None,
                "amenities_json": json.dumps(policy, ensure_ascii=False),
                "pet_policy_json": json.dumps(
                    {
                        "summary_zh": entry.get("access_summary_zh"),
                        "access_mode": entry.get("access_mode"),
                    },
                    ensure_ascii=False,
                ),
                "source_url": entry.get("policy_url"),
                "source_name": SOURCE_NAME,
                "last_verified_at": verified,
            }
        )
    return rows


def _name_keys(row: dict) -> set[str]:
    keys = set()
    for key in ("name_en", "name_zh"):
        compact = compact_name(row.get(key))
        if compact and len(compact) >= 3:
            keys.add(compact)
    return keys


def import_mall_policies(path: Path | None = None, replace_official: bool = True) -> dict:
    payload = load_policy_file(path)
    rows = entries_to_place_rows(payload)
    init_database(apply_second_source=False)
    conn = get_connection()
    removed_gopaw = 0
    try:
        if replace_official:
            conn.execute("DELETE FROM places WHERE source_name = ?", (SOURCE_NAME,))
        official_keys: set[str] = set()
        for row in rows:
            official_keys |= _name_keys(row)
            conn.execute(
                """
                INSERT OR REPLACE INTO places (
                    place_id, place_type, name_en, name_zh, district, address,
                    phone, website, latitude, longitude, opening_hours_json,
                    amenities_json, pet_policy_json, source_url, source_name,
                    last_verified_at
                ) VALUES (
                    :place_id, :place_type, :name_en, :name_zh, :district, :address,
                    :phone, :website, :latitude, :longitude, :opening_hours_json,
                    :amenities_json, :pet_policy_json, :source_url, :source_name,
                    :last_verified_at
                )
                """,
                row,
            )

        # Drop overlapping GoPaw mall rows so Tier-2 policy pages win.
        gopaw_malls = conn.execute(
            """
            SELECT place_id, name_en, name_zh FROM places
            WHERE place_type = 'mall' AND source_name = 'GoPaw'
            """
        ).fetchall()
        for g in gopaw_malls:
            keys = _name_keys({"name_en": g["name_en"], "name_zh": g["name_zh"]})
            if keys & official_keys:
                conn.execute("DELETE FROM places WHERE place_id = ?", (g["place_id"],))
                removed_gopaw += 1

        conn.commit()
        return {
            "official_imported": len(rows),
            "gopaw_mall_duplicates_removed": removed_gopaw,
            "source_file": str(path or DEFAULT_PATH),
            "evidence_tier": 2,
        }
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Tier-2 mall pet policies")
    parser.add_argument("--in", dest="inp", default=str(DEFAULT_PATH))
    args = parser.parse_args()
    stats = import_mall_policies(Path(args.inp))
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
