from pawplan.database.db import get_connection
from pawplan.normalize import normalize_district


def search_parks(
    district: str,
    park_type: str | None = None,
    require_dog_latrine: bool = False,
    limit: int = 5,
) -> dict:
    """Search LCSD pet gardens / inclusive parks. Parameterized only."""
    limit = max(1, min(int(limit), 5))
    district_norm = normalize_district(district) or district
    type_norm = None
    if park_type:
        raw = park_type.strip().lower().replace(" ", "_").replace("-", "_")
        aliases = {
            "pet_garden": "pet_garden",
            "dog_garden": "pet_garden",
            "petgarden": "pet_garden",
            "inclusive_park": "inclusive_park",
            "inclusive": "inclusive_park",
            "ipp": "inclusive_park",
            "宠物公园": "pet_garden",
            "寵物公園": "pet_garden",
            "狗公园": "pet_garden",
            "狗公園": "pet_garden",
            "宠物共享公园": "inclusive_park",
            "寵物共享公園": "inclusive_park",
            "共享公园": "inclusive_park",
        }
        type_norm = aliases.get(raw) or aliases.get(park_type) or raw

    clauses = ["district = :district"]
    params: dict = {"district": district_norm, "limit": limit}
    if type_norm in {"pet_garden", "inclusive_park"}:
        clauses.append("park_type = :park_type")
        params["park_type"] = type_norm
    if require_dog_latrine:
        clauses.append("facilities_json LIKE :latrine")
        params["latrine"] = '%"has_dog_latrine": true%'

    sql = f"""
    SELECT park_id, park_type, name_en, name_zh, district, address,
           facilities_json, opening_hours, phone, latitude, longitude,
           source_url, last_verified_at
    FROM parks
    WHERE {' AND '.join(clauses)}
    ORDER BY
      CASE park_type WHEN 'pet_garden' THEN 0 ELSE 1 END,
      name_en ASC
    LIMIT :limit
    """

    conn = get_connection()
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    parks = []
    for row in rows:
        parks.append(
            {
                "park_id": row["park_id"],
                "park_type": row["park_type"],
                "name_en": row["name_en"],
                "name_zh": row["name_zh"],
                "district": row["district"],
                "address": row["address"],
                "facilities_json": row["facilities_json"],
                "opening_hours": row["opening_hours"],
                "phone": row["phone"],
                "latitude": row["latitude"],
                "longitude": row["longitude"],
                "source_url": row["source_url"],
                "last_verified_at": row["last_verified_at"],
            }
        )

    return {
        "query": {
            "district": district_norm,
            "park_type": type_norm,
            "require_dog_latrine": require_dog_latrine,
            "limit": limit,
        },
        "count": len(parks),
        "parks": parks,
    }
