from pawplan.database.db import get_connection
from pawplan.normalize import normalize_cuisine, normalize_district


def search_restaurants(
    district: str,
    cuisine: str | None = None,
    limit: int = 5,
) -> dict:
    """Parameterized restaurant search. Never accepts raw SQL from the model."""
    limit = max(1, min(int(limit), 5))
    district_norm = normalize_district(district) or district
    cuisine_norm = normalize_cuisine(cuisine) if cuisine else None
    if cuisine_norm == "unknown":
        cuisine_norm = None

    conn = get_connection()
    try:
        if cuisine_norm:
            sql = """
            SELECT r.restaurant_id, r.name_en, r.name_zh, r.district, r.address,
                   r.opening_hours_json, r.source_url, r.last_verified_at,
                   c.cuisine_code, c.cuisine_label_zh, c.cuisine_confidence,
                   c.cuisine_source_url
            FROM restaurants r
            JOIN restaurant_cuisines c ON r.restaurant_id = c.restaurant_id
            WHERE r.district = :district
              AND r.dog_permission = 1
              AND c.cuisine_code = :cuisine
            ORDER BY c.cuisine_confidence DESC, r.name_en ASC
            LIMIT :limit
            """
            params = {
                "district": district_norm,
                "cuisine": cuisine_norm,
                "limit": limit,
            }
        else:
            sql = """
            SELECT r.restaurant_id, r.name_en, r.name_zh, r.district, r.address,
                   r.opening_hours_json, r.source_url, r.last_verified_at,
                   (
                     SELECT c.cuisine_code FROM restaurant_cuisines c
                     WHERE c.restaurant_id = r.restaurant_id
                     ORDER BY c.cuisine_confidence DESC LIMIT 1
                   ) AS cuisine_code,
                   (
                     SELECT c.cuisine_label_zh FROM restaurant_cuisines c
                     WHERE c.restaurant_id = r.restaurant_id
                     ORDER BY c.cuisine_confidence DESC LIMIT 1
                   ) AS cuisine_label_zh,
                   (
                     SELECT c.cuisine_confidence FROM restaurant_cuisines c
                     WHERE c.restaurant_id = r.restaurant_id
                     ORDER BY c.cuisine_confidence DESC LIMIT 1
                   ) AS cuisine_confidence,
                   (
                     SELECT c.cuisine_source_url FROM restaurant_cuisines c
                     WHERE c.restaurant_id = r.restaurant_id
                     ORDER BY c.cuisine_confidence DESC LIMIT 1
                   ) AS cuisine_source_url
            FROM restaurants r
            WHERE r.district = :district
              AND r.dog_permission = 1
            ORDER BY r.name_en ASC
            LIMIT :limit
            """
            params = {"district": district_norm, "limit": limit}

        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    restaurants = []
    for row in rows:
        restaurants.append(
            {
                "restaurant_id": row["restaurant_id"],
                "name_en": row["name_en"],
                "name_zh": row["name_zh"],
                "district": row["district"],
                "address": row["address"],
                "opening_hours_json": row["opening_hours_json"],
                "source_url": row["source_url"],
                "last_verified_at": row["last_verified_at"],
                "cuisine_code": row["cuisine_code"],
                "cuisine_label_zh": row["cuisine_label_zh"],
                "cuisine_confidence": row["cuisine_confidence"],
                "cuisine_source_url": row["cuisine_source_url"],
            }
        )

    return {
        "query": {
            "district": district_norm,
            "cuisine": cuisine_norm,
            "limit": limit,
        },
        "count": len(restaurants),
        "restaurants": restaurants,
    }
