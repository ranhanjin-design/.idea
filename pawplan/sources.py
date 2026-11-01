"""Verified, identity-bound source links shared by search, chat and Explore."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import unicodedata

FEHD_LIST = "https://www.fehd.gov.hk/tc_chi/licensing/dog_restaurants/dog_restaurants_list.html"
AFCD_VETS = "https://www.pets.gov.hk/tc_chi/animal_health_and_welfare/vet_clinics_list.html"
FEHD_DISTRICTS = {
    "Central/Western": "CW", "Eastern": "E", "Islands": "Is", "Kowloon City": "KC",
    "Kwai Tsing": "KwT", "Kwun Tong": "KT", "Mong Kok": "MK", "North": "N",
    "Sai Kung": "SK", "Sha Tin": "ST", "Sham Shui Po": "SSP", "Southern": "S",
    "Tai Po": "TP", "Tsuen Wan": "TW", "Tuen Mun": "TM", "Wan Chai": "Wch",
    "Wong Tai Sin": "WTS", "Yau Tsim Mong": "YT", "Yuen Long": "YL",
}
SOURCE_FIELDS = (
    "source_url", "source_name", "evidence_tier", "source_scope", "source_note",
    "source_detail_url", "source_record_url", "source_last_verified_at",
    "origin_source_name", "original_source_url", "service_source_url", "source_status",
)


def source_fields(row: dict) -> dict:
    return {k: row[k] for k in SOURCE_FIELDS if k in row}


def restaurant_source_url(district: str) -> str:
    code = FEHD_DISTRICTS.get(district)
    return f"{FEHD_LIST}?districtID={code}" if code else FEHD_LIST


def compact(value: str | None) -> str:
    return "".join(c for c in unicodedata.normalize("NFKC", value or "").casefold() if c.isalnum())


def source_identity(row: dict) -> str:
    # Bind a match to its branch. A later import with a changed address/name must
    # not inherit an old government's or another branch's source verification.
    value = [str(row.get(k) or "").strip() for k in ("name_en", "name_zh", "district", "address")]
    return hashlib.sha256(json.dumps(value, ensure_ascii=False).encode()).hexdigest()


def apply_source_metadata(conn: sqlite3.Connection, entity_type: str, rows: list) -> list[dict]:
    items = [dict(row) for row in rows]
    ids = [r.get("restaurant_id") or r.get("place_id") or r.get("id") for r in items]
    matches = {}
    try:
        for start in range(0, len(ids), 500):
            batch = ids[start:start + 500]
            marks = ",".join("?" for _ in batch)
            for r in conn.execute(
                f"SELECT entity_id, identity_key, metadata_json FROM venue_sources "
                f"WHERE entity_type = ? AND entity_id IN ({marks})", (entity_type, *batch)
            ):
                matches[r[0]] = (r[1], json.loads(r[2]))
    except sqlite3.OperationalError:
        # Older databases can still be read before their next schema initialization.
        pass
    for item, entity_id in zip(items, ids):
        match = matches.get(entity_id)
        if match and match[0] == source_identity(item):
            item.update(match[1])
        else:
            item["evidence_tier"] = 1 if entity_type == "restaurant" else (
                2 if item.get("source_name") == "mall_official" else 3
            )
            if entity_type == "restaurant":
                item["source_url"] = restaurant_source_url(item["district"])
                item["source_name"] = "FEHD"
            elif match:
                item["source_status"] = "unverified"
                item["source_note"] = "地点资料已变更，来源需要重新核对。"
            item.setdefault("source_scope", "directory_listing")
    return items


def place_source_order(item: dict) -> tuple:
    origin = item.get("origin_source_name") or item.get("source_name")
    community_order = 0 if origin in {"petcircle", "dogdoghk"} else 1
    return (item.get("evidence_tier", 3), community_order, (item.get("name_en") or "").casefold())
