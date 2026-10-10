"""Fetch PetCircle HK grooming directory (community Tier 3).

Source: https://petcircle-hk.vercel.app/grooming (~262 shops, paginated).
Complements GoPaw's smaller groomer list. Not an official AFCD register —
licensed pet shops are a separate AFCD PDF and mix retail + grooming.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import date
from html import unescape
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from pawplan.ingestion.entity_match import compact_name
from pawplan.normalize import CANONICAL_DISTRICTS, detect_district_in_text, normalize_district

ROOT = Path(__file__).resolve().parents[2]
RAW_PATH = ROOT / "data" / "raw" / "petcircle_groomers.json"
STAGING = ROOT / "data" / "staging" / "petcircle_groomers.json"

BASE = "https://petcircle-hk.vercel.app/grooming"
USER_AGENT = (
    "PawPlanHK/0.3 (COM4101 academic; complementary groomer directory research; "
    "petcircle-hk.vercel.app/grooming)"
)
SOURCE_NAME = "petcircle"

# PetCircle region labels → PawPlan district when address is thin
REGION_HINTS: dict[str, str] = {
    "港島東區": "Eastern",
    "港島中西區": "Central/Western",
    "港島南區": "Southern",
    "港島灣仔區": "Wan Chai",
    "九龍油尖旺區": "Yau Tsim Mong",
    "九龍深水埗區": "Sham Shui Po",
    "九龍九龍城區": "Kowloon City",
    "九龍黃大仙區": "Wong Tai Sin",
    "九龍觀塘區": "Kwun Tong",
    "新界荃灣區": "Tsuen Wan",
    "新界屯門區": "Tuen Mun",
    "新界元朗區": "Yuen Long",
    "新界北區": "North",
    "新界大埔區": "Tai Po",
    "新界沙田區": "Sha Tin",
    "新界西貢區": "Sai Kung",
    "新界葵青區": "Kwai Tsing",
    "新界離島區": "Islands",
    "東區": "Eastern",
    "中西區": "Central/Western",
    "南區": "Southern",
    "灣仔區": "Wan Chai",
    "油尖旺區": "Yau Tsim Mong",
    "深水埗區": "Sham Shui Po",
    "九龍城區": "Kowloon City",
    "黃大仙區": "Wong Tai Sin",
    "觀塘區": "Kwun Tong",
    "荃灣區": "Tsuen Wan",
    "屯門區": "Tuen Mun",
    "元朗區": "Yuen Long",
    "北區": "North",
    "大埔區": "Tai Po",
    "沙田區": "Sha Tin",
    "西貢區": "Sai Kung",
    "葵青區": "Kwai Tsing",
    "離島區": "Islands",
}


def _get(url: str) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    with urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", "replace")


def parse_page(html: str) -> list[dict]:
    """Parse grm-XXX cards from Next.js RSC flight HTML.

    The HTML is already UTF-8; RSC only escapes quotes as \\". Do not
    unicode_escape the payload (it corrupts Chinese text).
    """
    rows: list[dict] = []
    parts = re.split(r'\\"(grm-\d+)\\",\{', html)
    i = 1
    while i + 1 < len(parts):
        gid = parts[i]
        body = parts[i + 1]
        i += 2
        texts = [
            unescape(t.replace("\\\\", "\\"))
            for t in re.findall(r'\\"children\\":\\"([^\\"]{1,200})\\"', body)
        ]
        texts = [t.strip() for t in texts if t and t.strip()]
        if not texts:
            continue
        name = None
        region = None
        address = None
        phone = None
        rating = None
        for t in texts:
            if re.fullmatch(r"\d+(\.\d+)?", t):
                if rating is None and "." in t:
                    try:
                        rating = float(t)
                    except ValueError:
                        pass
                continue
            if t in REGION_HINTS or (t.endswith("區") and len(t) <= 8):
                region = t
                continue
            if re.search(r"\d{4}\s*\d{4}", t) or re.fullmatch(r"[\d\s\-+()]{8,}", t):
                phone = re.sub(r"\s+", " ", t).strip()
                continue
            if any(
                k in t
                for k in (
                    "香港",
                    "九龍",
                    "新界",
                    "街",
                    "道",
                    "號",
                    "舖",
                    "铺",
                    "Shop",
                    "G/F",
                    "地下",
                    "樓",
                    "Road",
                    "Street",
                    "Avenue",
                )
            ):
                if address is None or len(t) > len(address or ""):
                    address = t
                continue
            if name is None and len(t) >= 2 and t not in {"Go", "Pet", "HK"}:
                if len(t) >= 3 or re.search(r"[\u4e00-\u9fff]", t):
                    name = t
        if not name:
            candidates = [
                t
                for t in texts
                if t not in REGION_HINTS
                and not t.endswith("區")
                and not re.fullmatch(r"\d+(\.\d+)?", t)
            ]
            name = max(candidates, key=len) if candidates else gid
        rows.append(
            {
                "petcircle_id": gid,
                "name": name,
                "name_zh": name if re.search(r"[\u4e00-\u9fff]", name or "") else None,
                "name_en": name if re.search(r"[A-Za-z]", name or "") else None,
                "region_label": region,
                "address": address,
                "phone": phone,
                "rating": rating,
                "source_url": f"{BASE}?page=1#{gid}",
            }
        )
    return rows


def resolve_district(row: dict) -> str | None:
    region = row.get("region_label") or ""
    if region in REGION_HINTS:
        return REGION_HINTS[region]
    for alias, district in sorted(REGION_HINTS.items(), key=lambda kv: -len(kv[0])):
        if alias and alias in region:
            return district

    address = row.get("address") or ""
    # Avoid "North Point" → North district false positive.
    lower = address.lower()
    locality_fixes = (
        ("north point", "Eastern"),
        ("北角", "Eastern"),
        ("quarry bay", "Eastern"),
        ("鰂魚涌", "Eastern"),
        ("sai wan ho", "Eastern"),
        ("西灣河", "Eastern"),
        ("chai wan", "Eastern"),
        ("柴灣", "Eastern"),
        ("happy valley", "Wan Chai"),
        ("跑馬地", "Wan Chai"),
        ("causeway bay", "Wan Chai"),
        ("銅鑼灣", "Wan Chai"),
        ("sai ying pun", "Central/Western"),
        ("西營盤", "Central/Western"),
        ("sheung wan", "Central/Western"),
        ("上環", "Central/Western"),
        ("kennedy town", "Central/Western"),
        ("堅尼地城", "Central/Western"),
        ("mid-levels", "Central/Western"),
        ("半山", "Central/Western"),
        ("hung hom", "Kowloon City"),
        ("紅磡", "Kowloon City"),
        ("to kwa wan", "Kowloon City"),
        ("土瓜灣", "Kowloon City"),
        ("prince edward", "Yau Tsim Mong"),
        ("太子", "Yau Tsim Mong"),
        ("mong kok", "Mong Kok"),
        ("旺角", "Mong Kok"),
        ("yuen long", "Yuen Long"),
        ("元朗", "Yuen Long"),
        ("tseung kwan o", "Sai Kung"),
        ("將軍澳", "Sai Kung"),
        ("小西灣", "Eastern"),
        ("sai wan", "Eastern"),
        ("油塘", "Kwun Tong"),
        ("yau tong", "Kwun Tong"),
        ("鴨寮街", "Sham Shui Po"),
        ("塘尾", "Sham Shui Po"),
        ("kai tak", "Kowloon City"),
        ("啟德", "Kowloon City"),
        ("san po kong", "Wong Tai Sin"),
        ("新蒲崗", "Wong Tai Sin"),
        ("竹園", "Wong Tai Sin"),
        ("tai kok tsui", "Yau Tsim Mong"),
        ("大角咀", "Yau Tsim Mong"),
        ("fanling", "North"),
        ("粉嶺", "North"),
        ("kwai fong", "Kwai Tsing"),
        ("葵芳", "Kwai Tsing"),
        ("kwai chung", "Kwai Tsing"),
        ("葵涌", "Kwai Tsing"),
        ("tiu keng leng", "Sai Kung"),
        ("調景嶺", "Sai Kung"),
        ("tin shui wai", "Yuen Long"),
        ("天水圍", "Yuen Long"),
        ("hung shui kiu", "Yuen Long"),
        ("洪水橋", "Yuen Long"),
        ("ping shan", "Yuen Long"),
        ("屏山", "Yuen Long"),
        ("ma on shan", "Sha Tin"),
        ("馬鞍山", "Sha Tin"),
        ("discovery bay", "Islands"),
        ("愉景灣", "Islands"),
        ("lantau", "Islands"),
        ("大嶼山", "Islands"),
        ("馬灣", "Islands"),
        ("ma wan", "Islands"),
        ("stanley", "Southern"),
        ("赤柱", "Southern"),
        ("ho man tin", "Kowloon City"),
        ("何文田", "Kowloon City"),
        ("古洞", "North"),
        ("koo koon", "North"),
        ("新墟", "Tuen Mun"),
        ("元洲", "Sham Shui Po"),
        ("un chau", "Sham Shui Po"),
    )
    # Skip non-HK rows (PetCircle occasionally lists Shenzhen shops).
    if any(x in address for x in ("深圳", "深圳市", "广东省", "廣東省")):
        return None
    for alias, district in locality_fixes:
        if alias in lower or alias in address:
            return district

    hit = detect_district_in_text(address)
    if hit in CANONICAL_DISTRICTS:
        if hit == "North" and ("north point" in lower or "北角" in address):
            return "Eastern"
        return hit
    for alias, district in REGION_HINTS.items():
        if alias in address:
            return district
    return None


def fetch_all(skip_fetch: bool = False, sleep_s: float = 0.3, max_pages: int = 20) -> list[dict]:
    if skip_fetch and RAW_PATH.exists():
        payload = json.loads(RAW_PATH.read_text(encoding="utf-8"))
        return payload.get("groomers") or []

    all_rows: list[dict] = []
    seen: set[str] = set()
    for page in range(1, max_pages + 1):
        url = BASE if page == 1 else f"{BASE}?page={page}"
        try:
            html = _get(url)
        except (URLError, TimeoutError) as exc:
            if page == 1:
                raise
            print(f"[petcircle] stop at page {page}: {exc}")
            break
        rows = parse_page(html)
        new = 0
        for row in rows:
            gid = row["petcircle_id"]
            if gid in seen:
                continue
            seen.add(gid)
            row["district"] = resolve_district(row)
            all_rows.append(row)
            new += 1
        print(f"[petcircle] page {page}: +{new} (total {len(all_rows)})")
        if new == 0:
            break
        if sleep_s:
            time.sleep(sleep_s)

    wrapper = {
        "source": BASE,
        "fetched_at": date.today().isoformat(),
        "evidence_tier": 3,
        "note": (
            "Community groomer directory from PetCircle HK. "
            "Not AFCD licensed-pet-shop register; verify before booking."
        ),
        "count": len(all_rows),
        "groomers": all_rows,
    }
    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    RAW_PATH.write_text(json.dumps(wrapper, ensure_ascii=False, indent=2), encoding="utf-8")
    return all_rows


def to_place_rows(groomers: list[dict]) -> list[dict]:
    today = date.today().isoformat()
    rows: list[dict] = []
    for g in groomers:
        district = g.get("district") or resolve_district(g)
        if district not in CANONICAL_DISTRICTS:
            continue
        name = g.get("name") or g.get("petcircle_id")
        name_zh = g.get("name_zh")
        name_en = g.get("name_en")
        if not name_zh and name and re.search(r"[\u4e00-\u9fff]", name):
            name_zh = name
        if not name_en and name and re.search(r"[A-Za-z]", name):
            name_en = name
        policy = {
            "evidence_tier": 3,
            "directory": "PetCircle HK",
            "rating": g.get("rating"),
            "region_label": g.get("region_label"),
        }
        rows.append(
            {
                "place_id": f"petcircle_{g['petcircle_id']}",
                "place_type": "groomer",
                "name_en": name_en,
                "name_zh": name_zh or name,
                "district": district,
                "address": g.get("address"),
                "phone": g.get("phone"),
                "website": g.get("source_url"),
                "latitude": None,
                "longitude": None,
                "opening_hours_json": None,
                "amenities_json": json.dumps(policy, ensure_ascii=False),
                "pet_policy_json": None,
                "source_url": g.get("source_url") or BASE,
                "source_name": SOURCE_NAME,
                "last_verified_at": today,
            }
        )
    return rows


def write_staging(rows: list[dict]) -> Path:
    STAGING.parent.mkdir(parents=True, exist_ok=True)
    STAGING.write_text(
        json.dumps(
            {
                "source": BASE,
                "parsed_at": date.today().isoformat(),
                "count": len(rows),
                "places": rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return STAGING


def _name_keys(row: dict) -> set[str]:
    keys = set()
    for key in ("name_en", "name_zh"):
        compact = compact_name(row.get(key))
        if compact and len(compact) >= 3:
            keys.add(compact)
    return keys


def import_petcircle_groomers(
    groomers: list[dict] | None = None,
    replace: bool = True,
) -> dict:
    from pawplan.database.db import get_connection, init_database

    if groomers is None:
        groomers = fetch_all(skip_fetch=True)
    rows = to_place_rows(groomers)
    write_staging(rows)
    init_database(apply_second_source=False)
    conn = get_connection()
    try:
        if replace:
            conn.execute("DELETE FROM places WHERE source_name = ?", (SOURCE_NAME,))
        # Prefer PetCircle over GoPaw duplicates for groomers (larger directory)
        pc_keys: set[str] = set()
        for row in rows:
            pc_keys |= _name_keys(row)
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
        removed = 0
        gopaw = conn.execute(
            """
            SELECT place_id, name_en, name_zh FROM places
            WHERE place_type = 'groomer' AND source_name = 'GoPaw'
            """
        ).fetchall()
        for g in gopaw:
            if _name_keys({"name_en": g["name_en"], "name_zh": g["name_zh"]}) & pc_keys:
                conn.execute("DELETE FROM places WHERE place_id = ?", (g["place_id"],))
                removed += 1
        conn.commit()
        return {
            "petcircle_raw": len(groomers),
            "imported": len(rows),
            "gopaw_duplicates_removed": removed,
            "raw": str(RAW_PATH),
            "staging": str(STAGING),
            "evidence_tier": 3,
        }
    finally:
        conn.close()


def refresh_petcircle_groomers(skip_fetch: bool = False) -> dict:
    groomers = fetch_all(skip_fetch=skip_fetch)
    return import_petcircle_groomers(groomers, replace=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch PetCircle HK groomers")
    parser.add_argument("--skip-fetch", action="store_true")
    args = parser.parse_args()
    stats = refresh_petcircle_groomers(skip_fetch=args.skip_fetch)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
