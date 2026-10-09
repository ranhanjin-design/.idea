from pawplan.database.db import get_connection
from pawplan.normalize import cuisine_label_zh, normalize_cuisine, normalize_district

MIN_CUISINE_CONFIDENCE = 0.7


def _permission_count(conn, district: str) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) FROM restaurants
        WHERE district = :district AND dog_permission = 1
        """,
        {"district": district},
    ).fetchone()
    return int(row[0]) if row else 0


def search_restaurants(
    district: str,
    limit: int = 5,
    cuisine: str | None = None,
    **_ignored,
) -> dict:
    """Parameterized restaurant search. Never accepts raw SQL from the model.

    District + dog-permission is always required.
    Optional cuisine filter uses restaurant_cuisines (name/curated overlay),
    not an official FEHD cuisine field. Unmatched permission-only rows are
    never returned as cuisine hits.
    """
    limit = max(1, min(int(limit), 5))
    district_norm = normalize_district(district) or district
    cuisine_raw = (cuisine or "").strip() or None
    cuisine_code = normalize_cuisine(cuisine_raw) if cuisine_raw else None
    if cuisine_code == "unknown":
        cuisine_code = None if not cuisine_raw else cuisine_raw.replace(" ", "_")

    conn = get_connection()
    try:
        district_permission_count = _permission_count(conn, district_norm)
        if cuisine_code:
            rows = conn.execute(
                """
                SELECT r.restaurant_id, r.name_en, r.name_zh, r.district, r.address,
                       r.opening_hours_json, r.source_url, r.last_verified_at,
                       c.cuisine_code, c.cuisine_label_zh, c.cuisine_label_en,
                       c.cuisine_source_url, c.cuisine_confidence
                FROM restaurants r
                INNER JOIN restaurant_cuisines c
                    ON c.restaurant_id = r.restaurant_id
                WHERE r.district = :district
                  AND r.dog_permission = 1
                  AND c.cuisine_code = :cuisine
                  AND c.cuisine_confidence >= :min_conf
                ORDER BY c.cuisine_confidence DESC, r.name_en ASC
                LIMIT :limit
                """,
                {
                    "district": district_norm,
                    "cuisine": cuisine_code,
                    "min_conf": MIN_CUISINE_CONFIDENCE,
                    "limit": limit,
                },
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT r.restaurant_id, r.name_en, r.name_zh, r.district, r.address,
                       r.opening_hours_json, r.source_url, r.last_verified_at
                FROM restaurants r
                WHERE r.district = :district
                  AND r.dog_permission = 1
                ORDER BY r.name_en ASC
                LIMIT :limit
                """,
                {"district": district_norm, "limit": limit},
            ).fetchall()
    finally:
        conn.close()

    restaurants = []
    for row in rows:
        item = {
            "restaurant_id": row["restaurant_id"],
            "name_en": row["name_en"],
            "name_zh": row["name_zh"],
            "district": row["district"],
            "address": row["address"],
            "opening_hours_json": row["opening_hours_json"],
            "source_url": row["source_url"],
            "last_verified_at": row["last_verified_at"],
        }
        if cuisine_code:
            item["cuisine_code"] = row["cuisine_code"]
            item["cuisine_label_zh"] = row["cuisine_label_zh"]
            item["cuisine_label_en"] = row["cuisine_label_en"]
            item["cuisine_source_url"] = row["cuisine_source_url"]
            item["cuisine_confidence"] = row["cuisine_confidence"]
        restaurants.append(item)

    query: dict = {"district": district_norm, "limit": limit}
    if cuisine_code:
        query["cuisine"] = cuisine_code

    confirmed = bool(cuisine_code) and bool(restaurants)
    if cuisine_code:
        scope_note = (
            "Cuisine filter applied on name/curated labels; FEHD has no official "
            "cuisine field. Unmatched dog-permitted venues are not returned as "
            f"{cuisine_label_zh(cuisine_code)} recommendations."
        )
    else:
        scope_note = (
            "Restaurant search is district + dog-permission. Pass cuisine to filter "
            "by overlay labels; unmatched permission-only rows are not cuisine hits."
        )

    result = {
        "query": query,
        "count": len(restaurants),
        "restaurants": restaurants,
        "scope_note": scope_note,
        "cuisine_filter_applied": bool(cuisine_code),
        "cuisine_confirmed": confirmed,
    }
    if cuisine_code:
        result["district_permission_count"] = district_permission_count
    return result
