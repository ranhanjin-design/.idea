"""Fetch HK OSM/Overpass venues that already carry a cuisine tag.

This is a complementary public directory, not an official FEHD cuisine field.
Timeouts and HTTP errors must not crash the ingestion pipeline.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pawplan.ingestion.entity_match import best_match, compact_name, fold_name
from pawplan.normalize import CUISINE_LABELS, normalize_cuisine, normalize_district

ROOT = Path(__file__).resolve().parents[2]
RAW_PATH = ROOT / "data" / "raw" / "osm_hk_cuisines.json"
SECOND_SOURCE_PATH = ROOT / "data" / "knowledge" / "cuisine_second_source.json"
REVIEW_QUEUE_PATH = ROOT / "data" / "staging" / "cuisine_review_queue.json"

USER_AGENT = "PawPlanHK/0.3 (COM4101 academic; educational use)"
OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
BBOX = "22.1,113.8,22.6,114.5"
OVERPASS_QUERY = f"""
[out:json][timeout:90];
(
  nwr["amenity"="restaurant"]["cuisine"]({BBOX});
  nwr["amenity"="cafe"]["cuisine"]({BBOX});
  nwr["amenity"="fast_food"]["cuisine"]({BBOX});
);
out tags center;
""".strip()

KNOWN_CUISINES = set(CUISINE_LABELS) - {"unknown"}
_SPLIT_CUISINE = re.compile(r"[;,/|]")


def map_osm_cuisine(raw: str | None) -> list[str]:
    """Map OSM cuisine strings to PawPlan codes; drop unmapped tags."""
    codes: list[str] = []
    for part in _SPLIT_CUISINE.split(raw or ""):
        code = normalize_cuisine(part)
        if code in KNOWN_CUISINES and code not in codes:
            codes.append(code)
    return codes


def _osm_address(tags: dict) -> str:
    if tags.get("addr:full"):
        return str(tags["addr:full"]).strip()
    parts = [
        tags.get("addr:housenumber"),
        tags.get("addr:street"),
        tags.get("addr:place"),
        tags.get("addr:suburb"),
        tags.get("addr:district"),
        tags.get("addr:city"),
    ]
    return ", ".join(str(p).strip() for p in parts if p)


def _osm_district(tags: dict) -> str | None:
    for key in ("addr:district", "addr:suburb", "addr:city"):
        value = tags.get(key)
        if value:
            return normalize_district(str(value))
    return None


def _osm_url(element: dict) -> str:
    kind = element.get("type") or "node"
    osm_id = element.get("id")
    if osm_id is None:
        return "https://www.openstreetmap.org/"
    return f"https://www.openstreetmap.org/{kind}/{osm_id}"


def parse_osm_elements(payload: dict) -> list[dict]:
    rows: list[dict] = []
    for element in payload.get("elements") or []:
        tags = element.get("tags") or {}
        codes = map_osm_cuisine(tags.get("cuisine"))
        if not codes:
            continue
        name = tags.get("name") or tags.get("name:en") or tags.get("name:zh")
        if not name:
            continue
        center = element.get("center") or {}
        rows.append(
            {
                "osm_type": element.get("type"),
                "osm_id": element.get("id"),
                "name": name,
                "name_en": tags.get("name:en") or tags.get("name"),
                "name_zh": tags.get("name:zh") or tags.get("name:zh-Hant") or tags.get("name"),
                "address": _osm_address(tags),
                "district": _osm_district(tags),
                "cuisine_raw": tags.get("cuisine"),
                "cuisine_codes": codes,
                "cuisine_source_url": _osm_url(element),
                "lat": element.get("lat") or center.get("lat"),
                "lon": element.get("lon") or center.get("lon"),
            }
        )
    return rows


def fetch_osm_cuisines(skip_fetch: bool = False, timeout: int = 90) -> Path:
    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    if skip_fetch and RAW_PATH.exists():
        return RAW_PATH

    last_error = None
    for endpoint in OVERPASS_ENDPOINTS:
        req = Request(
            endpoint,
            data=urlencode({"data": OVERPASS_QUERY}).encode("utf-8"),
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            payload.setdefault("osm3s", {})
            payload["_pawplan"] = {
                "endpoint": endpoint,
                "fetched_at": date.today().isoformat(),
                "bbox": BBOX,
                "query": OVERPASS_QUERY,
            }
            RAW_PATH.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return RAW_PATH
        except (URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            continue

    if RAW_PATH.exists():
        return RAW_PATH
    stub = {
        "elements": [],
        "error": str(last_error) if last_error else "overpass_unavailable",
        "_pawplan": {"fetched_at": date.today().isoformat(), "bbox": BBOX},
    }
    RAW_PATH.write_text(json.dumps(stub, ensure_ascii=False, indent=2), encoding="utf-8")
    return RAW_PATH


def load_raw_osm(path: Path | None = None) -> dict:
    target = path or RAW_PATH
    if not target.exists():
        return {"elements": []}
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"elements": []}


def _load_fehd_rows(staging_path: Path | None) -> list[dict]:
    if staging_path and staging_path.exists():
        payload = json.loads(staging_path.read_text(encoding="utf-8"))
        return payload.get("restaurants") or []
    try:
        from pawplan.database.db import get_connection

        conn = get_connection()
        try:
            rows = conn.execute(
                """
                SELECT restaurant_id, name_en, name_zh, district, address
                FROM restaurants
                """
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except Exception:
        return []


def _block_keys(row: dict) -> set[str]:
    keys: set[str] = set()
    district = normalize_district(row.get("district")) if row.get("district") else None
    if district:
        keys.add(f"d:{district.lower()}")
    for name in (
        row.get("name"),
        row.get("name_en"),
        row.get("name_zh"),
        row.get("match_name_en"),
        row.get("match_name_zh"),
    ):
        compact = compact_name(name)
        folded = fold_name(name)
        if compact:
            keys.add(f"n:{compact[:4]}")
        if folded:
            keys.add(f"f:{folded[:8]}")
    return keys


def _candidate_pool(osm: dict, index: dict[str, list[dict]]) -> list[dict]:
    seen: dict[int, dict] = {}
    for key in _block_keys(osm):
        for row in index.get(key, ()):
            seen[id(row)] = row
    return list(seen.values())


def match_osm_to_fehd(
    osm_rows: list[dict],
    fehd_rows: list[dict],
) -> tuple[list[dict], list[dict]]:
    auto: list[dict] = []
    review: list[dict] = []
    today = date.today().isoformat()
    index: dict[str, list[dict]] = {}
    for row in fehd_rows:
        for key in _block_keys(row):
            index.setdefault(key, []).append(row)
    for osm in osm_rows:
        pool = _candidate_pool(osm, index)
        restaurant, score, decision = best_match(osm, pool)
        if decision == "skip" or restaurant is None:
            continue
        for code in osm.get("cuisine_codes") or []:
            entry = {
                "match_name_en": restaurant.get("name_en") or osm.get("name_en"),
                "match_name_zh": restaurant.get("name_zh") or osm.get("name_zh"),
                "district": restaurant.get("district") or osm.get("district"),
                "address": restaurant.get("address") or osm.get("address"),
                "cuisine_code": code,
                "cuisine_source_url": osm.get("cuisine_source_url"),
                "cuisine_confidence": round(min(0.88, max(0.80, score - 0.08)), 3),
                "method": "osm",
                "last_verified_at": today,
                "match_score": round(score, 4),
                "restaurant_id": restaurant.get("restaurant_id"),
                "osm_name": osm.get("name"),
            }
            if decision == "auto_merge":
                auto.append(entry)
            else:
                review.append(entry)
    return auto, review


def load_second_source(path: Path | None = None) -> dict:
    target = path or SECOND_SOURCE_PATH
    if not target.exists():
        return {
            "source_name": "OSM public directory + human review queue",
            "last_verified_at": date.today().isoformat(),
            "terms": (
                "Complementary cuisine overlay. FEHD has no official cuisine field. "
                "Sources: OpenStreetMap amenities with a cuisine tag (ODbL) and "
                "human review of FEHD shop names. Unmatched venues are not force-labeled."
            ),
            "entries": [],
        }
    return json.loads(target.read_text(encoding="utf-8"))


def _entry_key(entry: dict) -> tuple[str, str, str, str]:
    return (
        (entry.get("match_name_en") or "").strip().lower(),
        (entry.get("match_name_zh") or "").strip().lower(),
        (entry.get("district") or "").strip().lower(),
        (entry.get("cuisine_code") or "").strip().lower(),
    )


def merge_osm_into_second_source(
    osm_entries: list[dict],
    path: Path | None = None,
) -> Path:
    target = path or SECOND_SOURCE_PATH
    payload = load_second_source(target)
    human = [e for e in payload.get("entries") or [] if e.get("method") == "human_review"]
    human_keys = {_entry_key(e) for e in human}
    merged_osm: list[dict] = []
    seen = set()
    for entry in osm_entries:
        key = _entry_key(entry)
        if key in human_keys or key in seen:
            continue
        seen.add(key)
        merged_osm.append(
            {
                "match_name_en": entry.get("match_name_en"),
                "match_name_zh": entry.get("match_name_zh"),
                "district": entry.get("district"),
                "cuisine_code": entry.get("cuisine_code"),
                "cuisine_source_url": entry.get("cuisine_source_url"),
                "cuisine_confidence": entry.get("cuisine_confidence"),
                "method": "osm",
                "last_verified_at": entry.get("last_verified_at") or date.today().isoformat(),
            }
        )
    payload["entries"] = human + merged_osm
    payload["last_verified_at"] = date.today().isoformat()
    payload["source_name"] = payload.get("source_name") or (
        "OSM public directory + human review queue"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_review_queue(rows: list[dict], path: Path | None = None) -> Path:
    target = path or REVIEW_QUEUE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "created_at": date.today().isoformat(),
                "threshold": "0.75-0.90",
                "count": len(rows),
                "entries": rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return target


def refresh_second_source(
    fehd_staging: Path | None = None,
    skip_fetch: bool = False,
) -> dict:
    """Fetch (or reuse) OSM raw data, match to FEHD, merge auto-hits."""
    raw_path = fetch_osm_cuisines(skip_fetch=skip_fetch)
    osm_rows = parse_osm_elements(load_raw_osm(raw_path))
    fehd_rows = _load_fehd_rows(fehd_staging)
    auto, review = match_osm_to_fehd(osm_rows, fehd_rows) if fehd_rows else ([], [])
    second_path = merge_osm_into_second_source(auto)
    review_path = write_review_queue(review)
    return {
        "raw_path": str(raw_path),
        "osm_records": len(osm_rows),
        "fehd_rows": len(fehd_rows),
        "auto_merged": len(auto),
        "review_queue": len(review),
        "second_source": str(second_path),
        "review_path": str(review_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch OSM HK cuisine tags")
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Reuse existing data/raw/osm_hk_cuisines.json if present",
    )
    parser.add_argument(
        "--fehd-staging",
        default=str(ROOT / "data" / "staging" / "fehd_restaurants.json"),
    )
    parser.add_argument("--no-match", action="store_true")
    args = parser.parse_args()
    if args.no_match:
        path = fetch_osm_cuisines(skip_fetch=args.skip_fetch)
        payload = load_raw_osm(path)
        parsed = parse_osm_elements(payload)
        print(f"Wrote {path} ({len(payload.get('elements') or [])} raw, {len(parsed)} mapped)")
        return
    stats = refresh_second_source(
        Path(args.fehd_staging) if args.fehd_staging else None,
        skip_fetch=args.skip_fetch,
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
