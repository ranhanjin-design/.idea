"""Fetch GoPaw venue directory (authorized student-project use).

Source: https://gopaw.io/api/venues
GoPaw does not expose a dedicated cuisine field for most restaurants; after
entity-matching to FEHD we may attach a name-inferred cuisine code with
method=gopaw so the complementary source is attributable.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from pawplan.ingestion.entity_match import (
    AUTO_MERGE,
    REVIEW_MIN,
    compact_name,
    district_or_mall_score,
    fold_name,
    identity_match,
)
from pawplan.ingestion.fetch_cuisine_osm import (
    SECOND_SOURCE_PATH,
    _entry_key,
    _load_fehd_rows,
    load_second_source,
)
from pawplan.normalize import (
    CUISINE_LABELS,
    infer_cuisine_from_name,
    normalize_district,
)

ROOT = Path(__file__).resolve().parents[2]
RAW_PATH = ROOT / "data" / "raw" / "gopaw_venues.json"
STAGING_RESTAURANTS = ROOT / "data" / "staging" / "gopaw_restaurants.json"

# Explicit academic UA; owner directed student project to self-fetch.
USER_AGENT = (
    "PawPlanHK/0.3 (COM4101 academic; authorized student data use; "
    "gopaw.io/api/venues)"
)
API_URL = "https://gopaw.io/api/venues"

DISTRICT_MAP = {
    "central_western": "Central/Western",
    "wan_chai": "Wan Chai",
    "eastern": "Eastern",
    "southern": "Southern",
    "yau_tsim_mong": "Yau Tsim Mong",
    "mong_kok": "Mong Kok",
    "sham_shui_po": "Sham Shui Po",
    "kowloon_city": "Kowloon City",
    "wong_tai_sin": "Wong Tai Sin",
    "kwun_tong": "Kwun Tong",
    "kwai_tsing": "Kwai Tsing",
    "tsuen_wan": "Tsuen Wan",
    "tuen_mun": "Tuen Mun",
    "yuen_long": "Yuen Long",
    "north": "North",
    "tai_po": "Tai Po",
    "sha_tin": "Sha Tin",
    "sai_kung": "Sai Kung",
    "islands": "Islands",
}

FOOD_CATEGORIES = {"restaurant"}

# Place-graph categories from GoPaw (briefing: malls + services).
PLACE_CATEGORIES = {
    "mall",
    "vet",
    "dental",
    "emergency",
    "groomer",
}

STAGING_PLACES = ROOT / "data" / "staging" / "gopaw_places.json"


def fetch_gopaw_venues(skip_fetch: bool = False, out_path: Path | None = None) -> Path:
    target = out_path or RAW_PATH
    if skip_fetch and target.exists():
        return target
    req = Request(
        API_URL,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        if target.exists():
            print(f"[gopaw] fetch failed ({exc}); reusing {target}")
            return target
        raise
    if not isinstance(payload, list):
        raise ValueError("unexpected GoPaw payload; expected a JSON list")
    target.parent.mkdir(parents=True, exist_ok=True)
    wrapper = {
        "source": API_URL,
        "fetched_at": date.today().isoformat(),
        "authorized_note": (
            "Fetched for COM4101 student project after GoPaw instructed "
            "the team to self-collect the directory data."
        ),
        "count": len(payload),
        "venues": payload,
    }
    # Compact JSON: full directory is ~3MB+; indenting can OOM on some Windows setups.
    target.write_text(json.dumps(wrapper, ensure_ascii=False), encoding="utf-8")
    return target


def _map_district(raw: str | None) -> str | None:
    if not raw:
        return None
    key = str(raw).strip().lower().replace(" ", "_").replace("-", "_")
    if key in DISTRICT_MAP:
        return DISTRICT_MAP[key]
    return normalize_district(raw.replace("_", " "))


def _venue_url(row: dict) -> str:
    slug = row.get("publicSlug")
    if slug:
        return f"https://gopaw.io/r/{slug}"
    vid = row.get("id")
    if vid is not None:
        return f"https://gopaw.io/venues#id={vid}"
    return "https://gopaw.io/venues"


def parse_gopaw_restaurants(raw_path: Path | None = None) -> list[dict]:
    path = raw_path or RAW_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    venues = payload.get("venues") if isinstance(payload, dict) else payload
    rows: list[dict] = []
    for item in venues or []:
        if not item.get("isActive", True):
            continue
        if str(item.get("category") or "").lower() not in FOOD_CATEGORIES:
            continue
        name_en = (item.get("name") or "").strip() or None
        name_zh = (item.get("nameZh") or "").strip() or None
        if not name_en and not name_zh:
            continue
        district = _map_district(item.get("district"))
        address = (item.get("address") or item.get("addressZh") or "").strip()
        code, conf = infer_cuisine_from_name(name_en or "", name_zh or "")
        rows.append(
            {
                "gopaw_id": item.get("id"),
                "name": name_en or name_zh,
                "name_en": name_en,
                "name_zh": name_zh,
                "district": district,
                "address": address,
                "latitude": item.get("latitude"),
                "longitude": item.get("longitude"),
                "website": item.get("website"),
                "source_url": _venue_url(item),
                "inferred_cuisine": code if code != "unknown" else None,
                "inferred_cuisine_confidence": conf if code != "unknown" else 0.0,
                "rating": item.get("rating"),
            }
        )
    return rows


def _hours_json(value) -> str | None:
    if value in (None, "", [], {}):
        return None
    return json.dumps(value, ensure_ascii=False)


def parse_gopaw_places(raw_path: Path | None = None) -> list[dict]:
    """Parse mall / vet / clinic / groomer rows for the place graph."""
    path = raw_path or RAW_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    venues = payload.get("venues") if isinstance(payload, dict) else payload
    today = date.today().isoformat()
    rows: list[dict] = []
    for item in venues or []:
        if not item.get("isActive", True):
            continue
        category = str(item.get("category") or "").strip().lower()
        if category not in PLACE_CATEGORIES:
            continue
        district = _map_district(item.get("district"))
        if not district:
            continue
        name_en = (item.get("name") or "").strip() or None
        name_zh = (item.get("nameZh") or "").strip() or None
        address = (item.get("address") or item.get("addressZh") or "").strip() or None
        vid = item.get("id")
        rows.append(
            {
                "place_id": f"gopaw_{category}_{vid}",
                "place_type": category,
                "name_en": name_en,
                "name_zh": name_zh,
                "district": district,
                "address": address,
                "phone": item.get("phone"),
                "website": item.get("website"),
                "latitude": item.get("latitude"),
                "longitude": item.get("longitude"),
                "opening_hours_json": _hours_json(item.get("openingHours")),
                "amenities_json": _hours_json(item.get("amenities")),
                "pet_policy_json": _hours_json(item.get("petPolicy")),
                "source_url": _venue_url(item),
                "source_name": "GoPaw",
                "last_verified_at": today,
            }
        )
    return rows


def write_gopaw_places_staging(rows: list[dict], path: Path | None = None) -> Path:
    target = path or STAGING_PLACES
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "source": API_URL,
                "parsed_at": date.today().isoformat(),
                "count": len(rows),
                "places": rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return target


def import_gopaw_places(rows: list[dict] | None = None, replace: bool = True) -> int:
    from pawplan.database.db import get_connection, init_database

    if rows is None:
        staging = STAGING_PLACES
        if not staging.exists():
            rows = parse_gopaw_places()
            write_gopaw_places_staging(rows)
        else:
            payload = json.loads(staging.read_text(encoding="utf-8"))
            rows = payload.get("places") or []

    init_database(apply_second_source=False)
    conn = get_connection()
    try:
        if replace:
            conn.execute(
                "DELETE FROM places WHERE source_name = ?",
                ("GoPaw",),
            )
        for row in rows:
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
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def write_gopaw_restaurant_staging(rows: list[dict], path: Path | None = None) -> Path:
    target = path or STAGING_RESTAURANTS
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "source": API_URL,
                "parsed_at": date.today().isoformat(),
                "count": len(rows),
                "restaurants": rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return target


def _block_keys(row: dict) -> set[str]:
    keys: set[str] = set()
    district = normalize_district(row.get("district")) or row.get("district")
    if district:
        keys.add(f"d:{(district or '').lower()}")
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


def _token_jaccard(left: str | None, right: str | None) -> float:
    """Fast similarity without difflib (avoids rare Windows crashes on long strings)."""
    a = fold_name(left)
    b = fold_name(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ca, cb = compact_name(a), compact_name(b)
    if ca and cb and (ca in cb or cb in ca):
        return 0.96
    ta = {t for t in a.replace(",", " ").split() if len(t) >= 2}
    tb = {t for t in b.replace(",", " ").split() if len(t) >= 2}
    if not ta or not tb:
        # Character overlap fallback for CJK-only names
        sa, sb = set(a), set(b)
        if not sa or not sb:
            return 0.0
        return len(sa & sb) / len(sa | sb)
    return len(ta & tb) / len(ta | tb)


def _gopaw_match_score(gopaw: dict, fehd: dict) -> float:
    names_g = [gopaw.get("name_en"), gopaw.get("name_zh"), gopaw.get("name")]
    names_f = [fehd.get("name_en"), fehd.get("name_zh")]
    name_best = 0.0
    for a in names_g:
        for b in names_f:
            name_best = max(name_best, _token_jaccard(a, b))
    addr = _token_jaccard(gopaw.get("address"), fehd.get("address"))
    dist = district_or_mall_score(gopaw, fehd)
    return 0.45 * name_best + 0.40 * addr + 0.15 * dist


def match_gopaw_to_fehd(
    gopaw_rows: list[dict],
    fehd_rows: list[dict],
) -> tuple[list[dict], list[dict]]:
    auto: list[dict] = []
    review: list[dict] = []
    today = date.today().isoformat()
    index: dict[str, list[dict]] = {}
    for row in fehd_rows:
        for key in _block_keys(row):
            index.setdefault(key, []).append(row)

    for gp in gopaw_rows:
        seen: dict[int, dict] = {}
        for key in _block_keys(gp):
            for row in index.get(key, ()):
                seen[id(row)] = row
        pool = list(seen.values())
        if len(pool) > 60:
            same = [
                r
                for r in pool
                if (normalize_district(r.get("district")) or r.get("district"))
                == (normalize_district(gp.get("district")) or gp.get("district"))
            ]
            pool = same or pool[:60]

        restaurant = None
        score = 0.0
        for row in pool:
            if identity_match(gp, row):
                restaurant, score = row, 1.0
                break
            s = _gopaw_match_score(gp, row)
            if s > score:
                restaurant, score = row, s

        decision = (
            "auto_merge"
            if score >= AUTO_MERGE
            else "review"
            if score >= REVIEW_MIN
            else "skip"
        )
        if decision == "skip" or restaurant is None:
            continue

        cuisine = gp.get("inferred_cuisine")
        conf_name = float(gp.get("inferred_cuisine_confidence") or 0)
        if not cuisine or cuisine not in CUISINE_LABELS or conf_name < 0.65:
            if decision in {"auto_merge", "review"}:
                review.append(
                    {
                        "match_name_en": restaurant.get("name_en"),
                        "match_name_zh": restaurant.get("name_zh"),
                        "district": restaurant.get("district"),
                        "gopaw_name": gp.get("name"),
                        "match_score": round(score, 4),
                        "note": "identity_ok_but_no_cuisine_from_gopaw",
                        "cuisine_source_url": gp.get("source_url"),
                    }
                )
            continue

        entry = {
            "match_name_en": restaurant.get("name_en") or gp.get("name_en"),
            "match_name_zh": restaurant.get("name_zh") or gp.get("name_zh"),
            "district": restaurant.get("district") or gp.get("district"),
            "address": restaurant.get("address") or gp.get("address"),
            "cuisine_code": cuisine,
            "cuisine_source_url": gp.get("source_url") or "https://gopaw.io/venues",
            "cuisine_confidence": round(
                min(0.86, max(0.72, 0.55 * conf_name + 0.35 * score)),
                3,
            ),
            "method": "gopaw",
            "last_verified_at": today,
            "match_score": round(score, 4),
            "restaurant_id": restaurant.get("restaurant_id"),
            "gopaw_name": gp.get("name"),
        }
        if decision == "auto_merge":
            auto.append(entry)
        else:
            review.append(entry)
    return auto, review


def merge_gopaw_into_second_source(gopaw_entries: list[dict], path: Path | None = None) -> Path:
    target = path or SECOND_SOURCE_PATH
    payload = load_second_source(target)
    keep = [
        e
        for e in payload.get("entries") or []
        if e.get("method") in {"human_review", "osm"}
    ]
    keep_keys = {_entry_key(e) for e in keep}
    merged: list[dict] = []
    seen = set()
    for entry in gopaw_entries:
        key = _entry_key(entry)
        if key in keep_keys or key in seen:
            continue
        seen.add(key)
        merged.append(
            {
                "match_name_en": entry.get("match_name_en"),
                "match_name_zh": entry.get("match_name_zh"),
                "district": entry.get("district"),
                "cuisine_code": entry.get("cuisine_code"),
                "cuisine_source_url": entry.get("cuisine_source_url"),
                "cuisine_confidence": entry.get("cuisine_confidence"),
                "method": "gopaw",
                "last_verified_at": entry.get("last_verified_at") or date.today().isoformat(),
                "restaurant_id": entry.get("restaurant_id"),
            }
        )
    # Preserve previous gopaw entries not superseded
    for entry in payload.get("entries") or []:
        if entry.get("method") != "gopaw":
            continue
        key = _entry_key(entry)
        if key in keep_keys or key in seen:
            continue
        seen.add(key)
        merged.append(entry)

    payload["entries"] = keep + merged
    payload["last_verified_at"] = date.today().isoformat()
    payload["source_name"] = (
        "OSM + GoPaw directory (authorized student fetch) + human review"
    )
    payload["terms"] = (
        "Complementary cuisine/venue overlay. FEHD has no official cuisine field. "
        "Sources: OpenStreetMap cuisine tags (ODbL), GoPaw venue directory "
        "(student-authorized self-fetch from https://gopaw.io/api/venues; cuisine "
        "codes may be name-inferred after entity match), and human review. "
        "Unmatched venues are not force-labeled."
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def refresh_gopaw_second_source(
    fehd_staging: Path | None = None,
    skip_fetch: bool = False,
) -> dict:
    raw = fetch_gopaw_venues(skip_fetch=skip_fetch)
    rows = parse_gopaw_restaurants(raw)
    staging = write_gopaw_restaurant_staging(rows)
    place_rows = parse_gopaw_places(raw)
    places_staging = write_gopaw_places_staging(place_rows)
    places_imported = import_gopaw_places(place_rows, replace=True)
    mall_official_stats = {}
    dogdog_stats = {}
    try:
        from pawplan.ingestion.load_mall_policies import import_mall_policies

        mall_official_stats = import_mall_policies()
    except Exception as exc:
        mall_official_stats = {"error": str(exc)}
    try:
        from pawplan.ingestion.fetch_dogdog_malls import refresh_dogdog_malls

        dogdog_stats = refresh_dogdog_malls(skip_fetch=skip_fetch)
    except Exception as exc:
        dogdog_stats = {"error": str(exc)}
    petcircle_stats = {}
    try:
        from pawplan.ingestion.fetch_petcircle_groomers import refresh_petcircle_groomers

        petcircle_stats = refresh_petcircle_groomers(skip_fetch=skip_fetch)
    except Exception as exc:
        petcircle_stats = {"error": str(exc)}
    # Cuisine-bearing rows only — GoPaw rarely has tags; name inference prefilters work.
    cuisine_rows = [r for r in rows if r.get("inferred_cuisine")]
    fehd_rows = _load_fehd_rows(fehd_staging)
    auto, review = (
        match_gopaw_to_fehd(cuisine_rows, fehd_rows) if fehd_rows else ([], [])
    )
    second = merge_gopaw_into_second_source(auto)
    gopaw_review = ROOT / "data" / "staging" / "gopaw_review_queue.json"
    gopaw_review.parent.mkdir(parents=True, exist_ok=True)
    gopaw_review.write_text(
        json.dumps(
            {
                "created_at": date.today().isoformat(),
                "source": "gopaw",
                "count": len(review),
                "entries": review,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    by_type: dict[str, int] = {}
    for r in place_rows:
        by_type[r["place_type"]] = by_type.get(r["place_type"], 0) + 1
    return {
        "raw_path": str(raw),
        "gopaw_restaurants": len(rows),
        "cuisine_candidates": len(cuisine_rows),
        "staging": str(staging),
        "places_staging": str(places_staging),
        "places_imported": places_imported,
        "places_by_type": by_type,
        "mall_official": mall_official_stats,
        "dogdog_malls": dogdog_stats,
        "petcircle_groomers": petcircle_stats,
        "fehd_rows": len(fehd_rows),
        "auto_merged": len(auto),
        "review_queue": len(review),
        "review_path": str(gopaw_review),
        "second_source": str(second),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch GoPaw venues for PawPlan")
    parser.add_argument("--skip-fetch", action="store_true")
    parser.add_argument(
        "--fehd-staging",
        default=str(ROOT / "data" / "staging" / "fehd_restaurants.json"),
    )
    parser.add_argument("--no-match", action="store_true")
    args = parser.parse_args()
    if args.no_match:
        path = fetch_gopaw_venues(skip_fetch=args.skip_fetch)
        rows = parse_gopaw_restaurants(path)
        staging = write_gopaw_restaurant_staging(rows)
        print(f"Wrote {path}; restaurants={len(rows)}; staging={staging}")
        return
    stats = refresh_gopaw_second_source(
        Path(args.fehd_staging) if args.fehd_staging else None,
        skip_fetch=args.skip_fetch,
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
