"""Geocode addresses via Nominatim with district-centroid fallback + cache."""

from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

from pawplan.database.db import get_connection, init_database
from pawplan.normalize import normalize_district

ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = ROOT / "data" / "staging" / "geocode_cache.json"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "PawPlanHK/0.3 (COM4101 academic; educational use)"

# Approximate administrative centroids for midterm map readiness.
# Used only when Nominatim cannot resolve a place/address.
DISTRICT_CENTROIDS: dict[str, tuple[float, float]] = {
    "Central/Western": (22.2819, 114.1557),
    "Wan Chai": (22.2760, 114.1750),
    "Eastern": (22.2840, 114.2240),
    "Southern": (22.2470, 114.1600),
    "Yau Tsim Mong": (22.3110, 114.1700),
    "Mong Kok": (22.3193, 114.1694),
    "Sham Shui Po": (22.3307, 114.1622),
    "Kowloon City": (22.3300, 114.1910),
    "Wong Tai Sin": (22.3420, 114.1930),
    "Kwun Tong": (22.3120, 114.2250),
    "Kwai Tsing": (22.3550, 114.1270),
    "Tsuen Wan": (22.3710, 114.1140),
    "Tuen Mun": (22.3910, 113.9770),
    "Yuen Long": (22.4445, 114.0220),
    "North": (22.4940, 114.1380),
    "Tai Po": (22.4500, 114.1650),
    "Sha Tin": (22.3870, 114.1950),
    "Sai Kung": (22.3820, 114.2730),
    "Islands": (22.2860, 113.9430),
}


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _nominatim(query: str, sleep_s: float) -> dict | None:
    params = urllib.parse.urlencode(
        {
            "q": query,
            "format": "json",
            "limit": 1,
            "viewbox": "113.8,22.6,114.5,22.1",
            "bounded": 0,
        }
    )
    req = urllib.request.Request(
        f"{NOMINATIM}?{params}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        time.sleep(sleep_s)
        return None
    time.sleep(sleep_s)
    if not data:
        return None
    item = data[0]
    return {
        "lat": float(item["lat"]),
        "lon": float(item["lon"]),
        "display_name": item.get("display_name"),
        "provider": "nominatim",
        "precision": "address_or_place",
    }


def geocode_place(
    *,
    name: str | None,
    address: str | None,
    district: str | None,
    cache: dict,
    sleep_s: float = 1.1,
    allow_centroid: bool = True,
    use_network: bool = True,
) -> dict | None:
    district_norm = normalize_district(district) if district else None
    queries = []
    if address:
        queries.append(f"{address}, Hong Kong")
    if name and district_norm:
        queries.append(f"{name}, {district_norm}, Hong Kong")
    if name:
        queries.append(f"{name}, Hong Kong")
    if district_norm:
        queries.append(f"{district_norm}, Hong Kong")

    for q in queries:
        key = f"nominatim::{q}"
        if key in cache:
            if cache[key]:
                return cache[key]
            continue
        if not use_network:
            continue
        result = _nominatim(q, sleep_s=sleep_s)
        cache[key] = result
        _save_cache(cache)
        if result:
            return result

    if allow_centroid and district_norm in DISTRICT_CENTROIDS:
        lat, lon = DISTRICT_CENTROIDS[district_norm]
        result = {
            "lat": lat,
            "lon": lon,
            "display_name": f"{district_norm} district centroid",
            "provider": "district_centroid",
            "precision": "district",
        }
        cache[f"centroid::{district_norm}"] = result
        _save_cache(cache)
        return result
    return None


def coverage_report() -> dict:
    conn = get_connection()
    try:
        r_total = conn.execute("SELECT COUNT(*) FROM restaurants").fetchone()[0]
        r_geo = conn.execute(
            "SELECT COUNT(*) FROM restaurants WHERE latitude IS NOT NULL AND longitude IS NOT NULL"
        ).fetchone()[0]
        p_total = conn.execute("SELECT COUNT(*) FROM parks").fetchone()[0]
        p_geo = conn.execute(
            "SELECT COUNT(*) FROM parks WHERE latitude IS NOT NULL AND longitude IS NOT NULL"
        ).fetchone()[0]
        return {
            "restaurants_total": r_total,
            "restaurants_geocoded": r_geo,
            "restaurants_coverage": round(r_geo / r_total, 3) if r_total else 0,
            "parks_total": p_total,
            "parks_geocoded": p_geo,
            "parks_coverage": round(p_geo / p_total, 3) if p_total else 0,
        }
    finally:
        conn.close()


def geocode_missing(
    target: str = "all",
    limit: int | None = None,
    sleep_s: float = 1.1,
    centroid_only: bool = False,
) -> dict:
    init_database()
    cache = _load_cache()
    conn = get_connection()
    stats = {
        "restaurants_attempted": 0,
        "restaurants_filled": 0,
        "parks_attempted": 0,
        "parks_filled": 0,
        "by_provider": {},
    }

    def bump(provider: str) -> None:
        stats["by_provider"][provider] = stats["by_provider"].get(provider, 0) + 1

    try:
        if target in {"restaurants", "all"}:
            rows = conn.execute(
                """
                SELECT restaurant_id, name_en, name_zh, address, district
                FROM restaurants
                WHERE latitude IS NULL OR longitude IS NULL
                ORDER BY restaurant_id
                """
            ).fetchall()
            if limit is not None:
                rows = rows[:limit]
            for idx, row in enumerate(rows, 1):
                stats["restaurants_attempted"] += 1
                result = geocode_place(
                    name=row["name_en"] or row["name_zh"],
                    address=row["address"],
                    district=row["district"],
                    cache=cache,
                    sleep_s=sleep_s,
                    allow_centroid=True,
                    use_network=not centroid_only,
                )
                if result:
                    conn.execute(
                        """
                        UPDATE restaurants
                        SET latitude = ?, longitude = ?
                        WHERE restaurant_id = ?
                        """,
                        (result["lat"], result["lon"], row["restaurant_id"]),
                    )
                    stats["restaurants_filled"] += 1
                    bump(result.get("provider") or "unknown")
                if idx % 25 == 0:
                    conn.commit()
            conn.commit()

        if target in {"parks", "all"}:
            rows = conn.execute(
                """
                SELECT park_id, name_en, name_zh, address, district
                FROM parks
                WHERE latitude IS NULL OR longitude IS NULL
                ORDER BY park_id
                """
            ).fetchall()
            if limit is not None and target == "parks":
                rows = rows[:limit]
            for idx, row in enumerate(rows, 1):
                stats["parks_attempted"] += 1
                result = geocode_place(
                    name=row["name_en"] or row["name_zh"],
                    address=row["address"],
                    district=row["district"],
                    cache=cache,
                    sleep_s=sleep_s,
                    allow_centroid=True,
                    use_network=not centroid_only,
                )
                if result:
                    conn.execute(
                        """
                        UPDATE parks
                        SET latitude = ?, longitude = ?
                        WHERE park_id = ?
                        """,
                        (result["lat"], result["lon"], row["park_id"]),
                    )
                    stats["parks_filled"] += 1
                    bump(result.get("provider") or "unknown")
                if idx % 25 == 0:
                    conn.commit()
            conn.commit()
    finally:
        conn.close()

    report = {"run": stats, "coverage": coverage_report()}
    report_path = ROOT / "data" / "staging" / "geocode_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Geocode missing restaurant/park coords")
    parser.add_argument("--target", choices=["restaurants", "parks", "all"], default="all")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--sleep", type=float, default=1.1)
    parser.add_argument(
        "--centroid-only",
        action="store_true",
        help="Skip Nominatim; fill missing coords with district centroids",
    )
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument(
        "--clear-negative-cache",
        action="store_true",
        help="Remove failed Nominatim cache entries before running",
    )
    args = parser.parse_args()

    if args.clear_negative_cache and CACHE_PATH.exists():
        cache = _load_cache()
        cleaned = {k: v for k, v in cache.items() if v}
        _save_cache(cleaned)
        print(f"cleared negative cache entries; kept {len(cleaned)}")

    if args.report_only:
        print(json.dumps(coverage_report(), ensure_ascii=False, indent=2))
        return

    result = geocode_missing(
        args.target,
        args.limit,
        args.sleep,
        centroid_only=args.centroid_only,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
