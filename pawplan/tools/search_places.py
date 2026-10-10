"""Search complementary places (malls, vets, groomers) from GoPaw-backed table."""

from __future__ import annotations

from pawplan.database.db import get_connection
from pawplan.normalize import normalize_district

# User-facing groups → stored place_type values
PLACE_TYPE_GROUPS: dict[str, tuple[str, ...]] = {
    "mall": ("mall",),
    "vet": ("vet", "dental", "emergency"),
    "clinic": ("vet", "dental", "emergency"),
    "groomer": ("groomer",),
    "grooming": ("groomer",),
}

PLACE_TYPE_ALIASES: dict[str, str] = {
    "mall": "mall",
    "商场": "mall",
    "商場": "mall",
    "购物中心": "mall",
    "購物中心": "mall",
    "shopping mall": "mall",
    "vet": "vet",
    "clinic": "clinic",
    "veterinary": "vet",
    "兽医": "vet",
    "獸醫": "vet",
    "宠物诊所": "clinic",
    "寵物診所": "clinic",
    "诊所": "clinic",
    "診所": "clinic",
    "宠物医院": "clinic",
    "寵物醫院": "clinic",
    "hospital": "clinic",
    "emergency": "clinic",
    "dental": "clinic",
    "groomer": "groomer",
    "grooming": "groomer",
    "美容": "groomer",
    "洗护": "groomer",
    "洗護": "groomer",
    "宠物美容": "groomer",
    "寵物美容": "groomer",
}


def normalize_place_type(place_type: str | None) -> str | None:
    if not place_type:
        return None
    raw = place_type.strip().lower().replace("-", " ").replace("_", " ")
    compact = raw.replace(" ", "")
    if place_type in PLACE_TYPE_ALIASES:
        return PLACE_TYPE_ALIASES[place_type]
    if raw in PLACE_TYPE_ALIASES:
        return PLACE_TYPE_ALIASES[raw]
    if compact in {k.replace(" ", "") for k in PLACE_TYPE_ALIASES}:
        for key, group in PLACE_TYPE_ALIASES.items():
            if key.replace(" ", "") == compact:
                return group
    if raw in PLACE_TYPE_GROUPS:
        return raw
    return raw.replace(" ", "_")


def search_places(
    district: str,
    place_type: str | None = None,
    limit: int = 5,
) -> dict:
    """Search GoPaw-backed places by district and type. Parameterized only."""
    limit = max(1, min(int(limit), 5))
    district_norm = normalize_district(district) or district
    type_group = normalize_place_type(place_type)

    clauses = ["district = :district"]
    params: dict = {"district": district_norm, "limit": limit}
    if type_group:
        types = PLACE_TYPE_GROUPS.get(type_group, (type_group,))
        placeholders = ", ".join(f":t{i}" for i in range(len(types)))
        clauses.append(f"place_type IN ({placeholders})")
        for i, t in enumerate(types):
            params[f"t{i}"] = t

    sql = f"""
    SELECT place_id, place_type, name_en, name_zh, district, address,
           phone, website, latitude, longitude, opening_hours_json,
           amenities_json, pet_policy_json, source_url, source_name,
           last_verified_at
    FROM places
    WHERE {' AND '.join(clauses)}
    ORDER BY
      CASE source_name
        WHEN 'mall_official' THEN 0
        WHEN 'dogdoghk' THEN 1
        WHEN 'petcircle' THEN 1
        ELSE 2
      END,
      CASE place_type
        WHEN 'mall' THEN 0
        WHEN 'vet' THEN 1
        WHEN 'emergency' THEN 2
        WHEN 'dental' THEN 3
        WHEN 'groomer' THEN 4
        ELSE 9
      END,
      name_en ASC
    LIMIT :limit
    """

    conn = get_connection()
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    places = []
    for row in rows:
        item = {key: row[key] for key in row.keys()}
        src = (item.get("source_name") or "").lower()
        if src == "mall_official":
            item["evidence_tier"] = 2
        else:
            item["evidence_tier"] = 3
        places.append(item)

    sources = {p.get("source_name") for p in places}
    if type_group == "mall" and "mall_official" in sources:
        source_note = (
            "Prefer venue-owned mall pet policy pages (Tier 2). "
            "DogDogHK / GoPaw fill gaps as Tier 3 community directories. "
            "No government pet-friendly mall register — re-check before visiting."
        )
    elif type_group == "mall" and "dogdoghk" in sources:
        source_note = (
            "Community mall directory from DogDogHK (Tier 3; ~46 HK malls). "
            "Not a government list — prefer linked venue policy pages when available."
        )
    elif type_group in {"groomer", "grooming"} and "petcircle" in sources:
        source_note = (
            "Community groomer directory from PetCircle HK (Tier 3; ~260 shops). "
            "Not the AFCD licensed pet-shop register — confirm services before booking."
        )
    else:
        source_note = (
            "Complementary venue directory (GoPaw / curated). "
            "Not a government list; verify access rules before visiting."
        )

    return {
        "query": {
            "district": district_norm,
            "place_type": type_group,
            "limit": limit,
        },
        "count": len(places),
        "source_note": source_note,
        "places": places,
    }
