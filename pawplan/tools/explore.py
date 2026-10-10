"""Browse catalog for the Explore UI (categories + districts + listings)."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from pawplan.database.db import get_connection
from pawplan.ingestion.geocode import DISTRICT_CENTROIDS
from pawplan.normalize import CANONICAL_DISTRICTS, normalize_district

DISTRICT_LABELS: dict[str, str] = {
    "Central/Western": "中西區",
    "Wan Chai": "灣仔區",
    "Eastern": "東區",
    "Southern": "南區",
    "Yau Tsim Mong": "油尖旺區",
    "Mong Kok": "旺角",
    "Sham Shui Po": "深水埗區",
    "Kowloon City": "九龍城區",
    "Wong Tai Sin": "黃大仙區",
    "Kwun Tong": "觀塘區",
    "Kwai Tsing": "葵青區",
    "Tsuen Wan": "荃灣區",
    "Tuen Mun": "屯門區",
    "Yuen Long": "元朗區",
    "North": "北區",
    "Tai Po": "大埔區",
    "Sha Tin": "沙田區",
    "Sai Kung": "西貢區",
    "Islands": "離島區",
}

CATEGORIES: list[dict[str, Any]] = [
    {
        "id": "restaurants",
        "label_en": "Restaurants",
        "label_zh": "寵物友善餐廳",
        "icon": "utensils",
        "blurb": "FEHD dog-permitted premises",
    },
    {
        "id": "parks",
        "label_en": "Pet Parks",
        "label_zh": "寵物公園",
        "icon": "trees",
        "blurb": "LCSD pet gardens & inclusive parks",
    },
    {
        "id": "malls",
        "label_en": "Malls",
        "label_zh": "寵物友善商場",
        "icon": "shopping-bag",
        "blurb": "Official policies + community listings",
    },
    {
        "id": "vets",
        "label_en": "Vets",
        "label_zh": "獸醫診所",
        "icon": "stethoscope",
        "blurb": "Clinics, dental & emergency",
    },
    {
        "id": "groomers",
        "label_en": "Grooming",
        "label_zh": "寵物美容",
        "icon": "scissors",
        "blurb": "Groomers across Hong Kong",
    },
]


def _count(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    try:
        return int(conn.execute(sql, params).fetchone()[0])
    except sqlite3.OperationalError:
        return 0


def explore_catalog() -> dict[str, Any]:
    conn = get_connection()
    try:
        counts = {
            "restaurants": _count(
                conn, "SELECT COUNT(*) FROM restaurants WHERE dog_permission = 1"
            ),
            "parks": _count(conn, "SELECT COUNT(*) FROM parks"),
            "malls": _count(
                conn, "SELECT COUNT(*) FROM places WHERE place_type = 'mall'"
            ),
            "vets": _count(
                conn,
                "SELECT COUNT(*) FROM places WHERE place_type IN ('vet','dental','emergency')",
            ),
            "groomers": _count(
                conn, "SELECT COUNT(*) FROM places WHERE place_type = 'groomer'"
            ),
        }
        categories = [{**cat, "count": counts.get(cat["id"], 0)} for cat in CATEGORIES]

        district_counts: dict[str, int] = {d: 0 for d in CANONICAL_DISTRICTS}
        for sql in (
            "SELECT district, COUNT(*) FROM restaurants WHERE dog_permission = 1 GROUP BY district",
            "SELECT district, COUNT(*) FROM parks GROUP BY district",
            "SELECT district, COUNT(*) FROM places GROUP BY district",
        ):
            try:
                for district, n in conn.execute(sql):
                    key = normalize_district(district) or district
                    if not key:
                        continue
                    district_counts[key] = district_counts.get(key, 0) + int(n)
            except sqlite3.OperationalError:
                continue

        ordered = list(CANONICAL_DISTRICTS)
        for key in sorted(district_counts):
            if key not in ordered and district_counts[key] > 0:
                ordered.append(key)

        districts = [
            {
                "id": d,
                "label_en": d,
                "label_zh": DISTRICT_LABELS.get(d, d),
                "count": district_counts.get(d, 0),
            }
            for d in ordered
        ]

        return {
            "total_venues": sum(counts.values()),
            "categories": categories,
            "districts": districts,
        }
    finally:
        conn.close()


def explore_browse(
    category: str,
    district: str | None = None,
    limit: int = 24,
    offset: int = 0,
) -> dict[str, Any]:
    category = (category or "").strip().lower()
    district_n = normalize_district(district) if district else None
    limit = max(1, min(int(limit), 48))
    offset = max(0, int(offset))

    conn = get_connection()
    try:
        if category == "restaurants":
            return _browse_restaurants(conn, district_n, limit, offset)
        if category == "parks":
            return _browse_parks(conn, district_n, limit, offset)
        if category in {"malls", "vets", "groomers"}:
            return _browse_places(conn, category, district_n, limit, offset)
        return {
            "category": category,
            "district": district_n,
            "total": 0,
            "items": [],
            "error": "unknown_category",
        }
    finally:
        conn.close()


def _browse_restaurants(
    conn: sqlite3.Connection,
    district: str | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    where = ["dog_permission = 1"]
    params: list[Any] = []
    if district:
        where.append("district = ?")
        params.append(district)
    where_sql = " AND ".join(where)
    total = _count(conn, f"SELECT COUNT(*) FROM restaurants WHERE {where_sql}", tuple(params))
    rows = conn.execute(
        f"""
        SELECT restaurant_id, name_en, name_zh, address, district,
               latitude, longitude, source_url, last_verified_at
        FROM restaurants
        WHERE {where_sql}
        ORDER BY name_en COLLATE NOCASE
        LIMIT ? OFFSET ?
        """,
        (*params, limit, offset),
    ).fetchall()
    items = [
        {
            "id": r["restaurant_id"],
            "name_en": r["name_en"],
            "name_zh": r["name_zh"],
            "address": r["address"],
            "district": r["district"],
            "latitude": r["latitude"],
            "longitude": r["longitude"],
            "source_url": r["source_url"],
            "source": "fehd",
            "place_type": "restaurant",
            "tags": ["dog_permitted"],
        }
        for r in rows
    ]
    return {
        "category": "restaurants",
        "district": district,
        "total": total,
        "items": items,
    }


def _browse_parks(
    conn: sqlite3.Connection,
    district: str | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    where = ["1=1"]
    params: list[Any] = []
    if district:
        where.append("district = ?")
        params.append(district)
    where_sql = " AND ".join(where)
    try:
        total = _count(conn, f"SELECT COUNT(*) FROM parks WHERE {where_sql}", tuple(params))
        rows = conn.execute(
            f"""
            SELECT park_id, name_en, name_zh, address, district, park_type,
                   facilities_json, latitude, longitude, source_url
            FROM parks
            WHERE {where_sql}
            ORDER BY name_en COLLATE NOCASE
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        ).fetchall()
    except sqlite3.OperationalError:
        return {"category": "parks", "district": district, "total": 0, "items": []}

    items = []
    for r in rows:
        tags = [r["park_type"] or "park"]
        try:
            fac = json.loads(r["facilities_json"] or "{}")
            if fac.get("has_dog_latrine"):
                tags.append("dog_latrine")
        except (TypeError, json.JSONDecodeError):
            pass
        items.append(
            {
                "id": r["park_id"],
                "name_en": r["name_en"],
                "name_zh": r["name_zh"],
                "address": r["address"],
                "district": r["district"],
                "latitude": r["latitude"],
                "longitude": r["longitude"],
                "source_url": r["source_url"],
                "source": "lcsd",
                "place_type": r["park_type"] or "park",
                "tags": tags,
            }
        )
    return {"category": "parks", "district": district, "total": total, "items": items}


def _browse_places(
    conn: sqlite3.Connection,
    category: str,
    district: str | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    type_map = {
        "malls": ("mall",),
        "vets": ("vet", "dental", "emergency"),
        "groomers": ("groomer",),
    }
    types = type_map[category]
    placeholders = ",".join("?" * len(types))
    where = [f"place_type IN ({placeholders})"]
    params: list[Any] = list(types)
    if district:
        where.append("district = ?")
        params.append(district)
    where_sql = " AND ".join(where)
    try:
        total = _count(conn, f"SELECT COUNT(*) FROM places WHERE {where_sql}", tuple(params))
        rows = conn.execute(
            f"""
            SELECT place_id, name_en, name_zh, address, district, place_type,
                   phone, website, latitude, longitude, source_url, source_name,
                   pet_policy_json
            FROM places
            WHERE {where_sql}
            ORDER BY
              CASE source_name
                WHEN 'mall_official' THEN 0
                WHEN 'dogdoghk' THEN 1
                WHEN 'petcircle' THEN 1
                ELSE 2
              END,
              name_en COLLATE NOCASE
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        ).fetchall()
    except sqlite3.OperationalError:
        return {"category": category, "district": district, "total": 0, "items": []}

    items = []
    for r in rows:
        items.append(
            {
                "id": r["place_id"],
                "name_en": r["name_en"],
                "name_zh": r["name_zh"],
                "address": r["address"],
                "district": r["district"],
                "latitude": r["latitude"],
                "longitude": r["longitude"],
                "phone": r["phone"],
                "website": r["website"],
                "source_url": r["source_url"],
                "source": r["source_name"],
                "place_type": r["place_type"],
                "tags": [r["place_type"]],
            }
        )
    return {"category": category, "district": district, "total": total, "items": items}


def _jitter(place_id: str, lat: float, lon: float) -> tuple[float, float]:
    """Spread stacked district-centroid pins so they remain clickable."""
    seed = abs(hash(place_id)) % 360
    # ~250–450 m at Hong Kong latitude
    dlat = 0.0035 * ((seed % 17) / 16.0 - 0.5)
    dlon = 0.0038 * (((seed // 17) % 17) / 16.0 - 0.5)
    return lat + dlat, lon + dlon


def _resolve_coords(
    place_id: str,
    district: str | None,
    lat: Any,
    lon: Any,
) -> tuple[float, float, str] | None:
    if lat is not None and lon is not None:
        try:
            return float(lat), float(lon), "geocoded"
        except (TypeError, ValueError):
            pass
    key = normalize_district(district) if district else None
    if key and key in DISTRICT_CENTROIDS:
        clat, clon = DISTRICT_CENTROIDS[key]
        jlat, jlon = _jitter(place_id or "", clat, clon)
        return jlat, jlon, "district_centroid"
    return None


def _query_category_rows(
    conn: sqlite3.Connection,
    category: str,
    district_n: str | None,
    q: str | None,
    limit: int,
) -> list[sqlite3.Row]:
    """Fetch raw rows for one category (or empty on missing table)."""
    like = f"%{q}%" if q else None

    if category == "restaurants":
        where = ["dog_permission = 1"]
        params: list[Any] = []
        if district_n:
            where.append("district = ?")
            params.append(district_n)
        if like:
            where.append(
                "(name_en LIKE ? OR name_zh LIKE ? OR address LIKE ? OR district LIKE ?)"
            )
            params.extend([like, like, like, like])
        sql = f"""
            SELECT restaurant_id AS id, name_en, name_zh, address, district,
                   latitude, longitude, 'restaurant' AS place_type,
                   'restaurants' AS category
            FROM restaurants
            WHERE {" AND ".join(where)}
            ORDER BY name_en COLLATE NOCASE
            LIMIT ?
        """
        return list(conn.execute(sql, (*params, limit)).fetchall())

    if category == "parks":
        where = ["1=1"]
        params = []
        if district_n:
            where.append("district = ?")
            params.append(district_n)
        if like:
            where.append(
                "(name_en LIKE ? OR name_zh LIKE ? OR IFNULL(address,'') LIKE ? OR district LIKE ?)"
            )
            params.extend([like, like, like, like])
        sql = f"""
            SELECT park_id AS id, name_en, name_zh, address, district,
                   latitude, longitude, park_type AS place_type,
                   'parks' AS category
            FROM parks
            WHERE {" AND ".join(where)}
            ORDER BY name_en COLLATE NOCASE
            LIMIT ?
        """
        try:
            return list(conn.execute(sql, (*params, limit)).fetchall())
        except sqlite3.OperationalError:
            return []

    if category in {"malls", "vets", "groomers"}:
        type_map = {
            "malls": ("mall",),
            "vets": ("vet", "dental", "emergency"),
            "groomers": ("groomer",),
        }
        types = type_map[category]
        placeholders = ",".join("?" * len(types))
        where = [f"place_type IN ({placeholders})"]
        params = list(types)
        if district_n:
            where.append("district = ?")
            params.append(district_n)
        if like:
            where.append(
                "(name_en LIKE ? OR name_zh LIKE ? OR IFNULL(address,'') LIKE ? OR district LIKE ?)"
            )
            params.extend([like, like, like, like])
        sql = f"""
            SELECT place_id AS id, name_en, name_zh, address, district,
                   latitude, longitude, place_type,
                   ? AS category
            FROM places
            WHERE {" AND ".join(where)}
            ORDER BY name_en COLLATE NOCASE
            LIMIT ?
        """
        try:
            return list(conn.execute(sql, (category, *params, limit)).fetchall())
        except sqlite3.OperationalError:
            return []
    return []


def explore_map_points(
    category: str = "all",
    district: str | None = None,
    limit: int = 400,
    q: str | None = None,
) -> dict[str, Any]:
    """Compact lat/lng payload for the Explore map (supports category=all)."""
    category = (category or "all").strip().lower()
    district_n = normalize_district(district) if district else None
    q_n = (q or "").strip() or None
    limit = max(1, min(int(limit), 800))

    cats = (
        ["restaurants", "parks", "malls", "vets", "groomers"]
        if category in {"", "all", "*"}
        else [category]
    )
    if any(c not in {"restaurants", "parks", "malls", "vets", "groomers"} for c in cats):
        return {
            "category": category,
            "district": district_n,
            "q": q_n,
            "count": 0,
            "geocoded": 0,
            "centroid_fallback": 0,
            "points": [],
            "error": "unknown_category",
        }

    per_cat = max(1, limit // len(cats)) if len(cats) > 1 else limit
    conn = get_connection()
    try:
        rows: list[sqlite3.Row] = []
        for cat in cats:
            rows.extend(_query_category_rows(conn, cat, district_n, q_n, per_cat))
    finally:
        conn.close()

    points = []
    geocoded = 0
    fallback = 0
    for r in rows[:limit]:
        coords = _resolve_coords(r["id"], r["district"], r["latitude"], r["longitude"])
        if not coords:
            continue
        lat, lon, precision = coords
        if precision == "geocoded":
            geocoded += 1
        else:
            fallback += 1
        cat = r["category"] if "category" in r.keys() else category
        points.append(
            {
                "id": r["id"],
                "name_en": r["name_en"],
                "name_zh": r["name_zh"],
                "address": r["address"],
                "district": r["district"],
                "latitude": lat,
                "longitude": lon,
                "precision": precision,
                "place_type": r["place_type"] if "place_type" in r.keys() else cat,
                "category": cat,
            }
        )
    return {
        "category": category,
        "district": district_n,
        "q": q_n,
        "count": len(points),
        "geocoded": geocoded,
        "centroid_fallback": fallback,
        "points": points,
    }
