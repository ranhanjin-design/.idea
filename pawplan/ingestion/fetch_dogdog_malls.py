"""Fetch DogDogHK pet-friendly mall directory (community Tier 3).

Source: https://dogdoghk.com/malls/
~46 mall pages with access-mode notes. Not a government register; venue-owned
policy pages (mall_official) still rank higher when both exist.
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
from pawplan.ingestion.load_mall_policies import SOURCE_NAME as OFFICIAL_SOURCE
from pawplan.normalize import CANONICAL_DISTRICTS, detect_district_in_text, normalize_district

ROOT = Path(__file__).resolve().parents[2]
RAW_INDEX = ROOT / "data" / "raw" / "dogdog_malls_index.html"
RAW_JSON = ROOT / "data" / "raw" / "dogdog_malls.json"
STAGING = ROOT / "data" / "staging" / "dogdog_malls.json"

BASE = "https://dogdoghk.com"
INDEX_URL = f"{BASE}/malls/"
USER_AGENT = (
    "PawPlanHK/0.3 (COM4101 academic; complementary mall directory research; "
    "+https://dogdoghk.com/malls/)"
)
SOURCE_NAME = "dogdoghk"

ACCESS_MAP = {
    "可牽繩落地": "leash_ok",
    "須放寵物車 / 袋": "carrier_required",
    "須放寵物車/袋": "carrier_required",
    "指定範圍": "designated_zones",
    "混合政策": "mixed",
}

# Locality phrases often appear in mall addresses but are not 18-district names.
LOCALITY_TO_DISTRICT: dict[str, str] = {
    "stanley": "Southern",
    "赤柱": "Southern",
    "the peak": "Central/Western",
    "peak": "Central/Western",
    "山頂": "Central/Western",
    "repulse bay": "Southern",
    "淺水灣": "Southern",
    "wong chuk hang": "Southern",
    "黃竹坑": "Southern",
    "pok fu lam": "Southern",
    "薄扶林": "Southern",
    "cyberport": "Southern",
    "數碼港": "Southern",
    "admiralty": "Central/Western",
    "金鐘": "Central/Western",
    "queensway": "Central/Western",
    "san po kong": "Wong Tai Sin",
    "新蒲崗": "Wong Tai Sin",
    "kai tak": "Kowloon City",
    "啟德": "Kowloon City",
    "kowloon tong": "Kowloon City",
    "九龍塘": "Kowloon City",
    "hung hom": "Kowloon City",
    "紅磡": "Kowloon City",
    "lai chi kok": "Sham Shui Po",
    "荔枝角": "Sham Shui Po",
    "cheung sha wan": "Sham Shui Po",
    "長沙灣": "Sham Shui Po",
    "nam cheong": "Sham Shui Po",
    "南昌": "Sham Shui Po",
    "tai kok tsui": "Yau Tsim Mong",
    "大角咀": "Yau Tsim Mong",
    "大角嘴": "Yau Tsim Mong",
    "kowloon bay": "Kwun Tong",
    "九龍灣": "Kwun Tong",
    "tai wai": "Sha Tin",
    "大圍": "Sha Tin",
    "ma on shan": "Sha Tin",
    "馬鞍山": "Sha Tin",
    "tseung kwan o": "Sai Kung",
    "將軍澳": "Sai Kung",
    "sai sha": "Sai Kung",
    "西沙": "Sai Kung",
    "lohas": "Sai Kung",
    "康城": "Sai Kung",
    "siu chik sha": "Sai Kung",
    "小赤沙": "Sai Kung",
    "kwai chung": "Kwai Tsing",
    "葵芳": "Kwai Tsing",
    "葵涌": "Kwai Tsing",
    "tsing yi": "Kwai Tsing",
    "青衣": "Kwai Tsing",
    "sheung shui": "North",
    "上水": "North",
    "fanling": "North",
    "粉嶺": "North",
}


def resolve_district(*texts: str | None) -> str | None:
    blob = " ".join(t for t in texts if t)
    if not blob:
        return None
    hit = detect_district_in_text(blob)
    if hit in CANONICAL_DISTRICTS:
        return hit
    lower = blob.lower()
    # Longer locality keys first
    for alias, district in sorted(LOCALITY_TO_DISTRICT.items(), key=lambda kv: -len(kv[0])):
        if alias in blob or alias in lower:
            return district
    for part in reversed([p.strip() for p in blob.split(",")]):
        cand = normalize_district(part)
        if cand in CANONICAL_DISTRICTS:
            return cand
    return None


def _get(url: str, timeout: int = 60) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def fetch_index_html(skip_fetch: bool = False) -> str:
    if skip_fetch and RAW_INDEX.exists():
        return RAW_INDEX.read_text(encoding="utf-8")
    html = _get(INDEX_URL)
    RAW_INDEX.parent.mkdir(parents=True, exist_ok=True)
    RAW_INDEX.write_text(html, encoding="utf-8")
    return html


def parse_index(html: str) -> list[dict]:
    chunks = re.split(r'(?=<a[^>]+href="/malls/[a-z0-9\-]+/?")', html)
    seen: dict[str, dict] = {}
    for ch in chunks:
        m = re.search(r'href="(/malls/[a-z0-9\-]+/?)"', ch)
        if not m:
            continue
        slug = m.group(1).rstrip("/").split("/")[-1]
        if not slug or slug == "malls":
            continue
        title = re.search(r"<h3[^>]*>(.*?)</h3>", ch, re.S)
        name_zh = unescape(re.sub(r"<[^>]+>", "", title.group(1))).strip() if title else None
        en_m = re.search(r"</h3>\s*<p[^>]*>\s*([^<]{2,80})\s*</p>", ch, re.S)
        name_en = unescape(en_m.group(1)).strip() if en_m else None
        if name_en and not re.search(r"[A-Za-z]", name_en):
            name_en = None
        text = unescape(re.sub(r"<[^>]+>", " ", ch))
        text = re.sub(r"\s+", " ", text)
        mode_label = None
        for label in ACCESS_MAP:
            if label in text:
                mode_label = label
                break
        snippet = None
        for s in re.findall(r"[\u4e00-\u9fffA-Za-z0-9，。；、／\-]{24,220}", text):
            if name_zh and name_zh in s and len(s) < 40:
                continue
            snippet = s
            break
        seen[slug] = {
            "slug": slug,
            "name_zh": name_zh,
            "name_en": name_en,
            "access_mode_label": mode_label,
            "access_mode": ACCESS_MAP.get(mode_label or "", "unknown"),
            "snippet": snippet,
            "source_url": f"{BASE}/malls/{slug}/",
        }
    return list(seen.values())


def enrich_detail(row: dict) -> dict:
    html = _get(row["source_url"])
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    if h1:
        row["name_zh"] = unescape(re.sub(r"<[^>]+>", "", h1.group(1))).strip() or row.get(
            "name_zh"
        )
    # Location card
    loc = re.search(
        r"位置</h2>\s*<p[^>]*>\s*([^<]+)\s*</p>\s*<p[^>]*>\s*([^<]+)\s*</p>",
        html,
        re.S,
    )
    if loc:
        row["address_zh"] = unescape(loc.group(1)).strip()
        row["address_en"] = unescape(loc.group(2)).strip()
        row["address"] = row["address_en"] or row["address_zh"]
    # Access mode on detail page overrides index when present
    arr = re.search(r"場內規則\s*</[^>]+>\s*([^<]{2,40})", html)
    if arr:
        label = unescape(arr.group(1)).strip()
        row["access_mode_label"] = label
        row["access_mode"] = ACCESS_MAP.get(label, row.get("access_mode") or "unknown")
    row["district"] = resolve_district(
        row.get("address_en"),
        row.get("address_zh"),
        row.get("name_zh"),
        row.get("name_en"),
    )
    # Longer summary from intro paragraphs if available
    intro = re.search(
        r"同狗狗行商場.*?</h2>\s*<p[^>]*>\s*([^<]{30,400})\s*</p>",
        html,
        re.S,
    )
    if intro:
        row["summary_zh"] = unescape(intro.group(1)).strip()
    else:
        row["summary_zh"] = row.get("snippet")
    return row


def fetch_all_malls(skip_fetch: bool = False, sleep_s: float = 0.35) -> list[dict]:
    if skip_fetch and RAW_JSON.exists():
        payload = json.loads(RAW_JSON.read_text(encoding="utf-8"))
        return payload.get("malls") or []

    html = fetch_index_html(skip_fetch=False)
    rows = parse_index(html)
    enriched: list[dict] = []
    for i, row in enumerate(rows):
        try:
            enriched.append(enrich_detail(dict(row)))
        except (URLError, TimeoutError, ValueError) as exc:
            row["fetch_error"] = str(exc)
            enriched.append(row)
        if sleep_s and i + 1 < len(rows):
            time.sleep(sleep_s)

    wrapper = {
        "source": INDEX_URL,
        "fetched_at": date.today().isoformat(),
        "evidence_tier": 3,
        "note": (
            "Community directory from DogDogHK. Cross-check venue-owned policy "
            "pages when available. Not an official government register."
        ),
        "count": len(enriched),
        "malls": enriched,
    }
    RAW_JSON.parent.mkdir(parents=True, exist_ok=True)
    RAW_JSON.write_text(json.dumps(wrapper, ensure_ascii=False, indent=2), encoding="utf-8")
    return enriched


def to_place_rows(malls: list[dict]) -> list[dict]:
    today = date.today().isoformat()
    rows: list[dict] = []
    for m in malls:
        district = m.get("district")
        if district not in CANONICAL_DISTRICTS:
            district = resolve_district(
                m.get("address_en"),
                m.get("address_zh"),
                m.get("name_zh"),
                m.get("name_en"),
            )
        if district not in CANONICAL_DISTRICTS:
            continue
        m["district"] = district
        summary = m.get("summary_zh") or m.get("snippet") or m.get("access_mode_label")
        policy = {
            "access_mode": m.get("access_mode"),
            "access_mode_label": m.get("access_mode_label"),
            "access_summary_zh": summary,
            "evidence_tier": 3,
            "directory": "DogDogHK",
        }
        rows.append(
            {
                "place_id": f"dogdog_mall_{m['slug']}",
                "place_type": "mall",
                "name_en": m.get("name_en"),
                "name_zh": m.get("name_zh"),
                "district": district,
                "address": m.get("address") or m.get("address_en") or m.get("address_zh"),
                "phone": None,
                "website": m.get("source_url"),
                "latitude": None,
                "longitude": None,
                "opening_hours_json": None,
                "amenities_json": json.dumps(policy, ensure_ascii=False),
                "pet_policy_json": json.dumps(
                    {
                        "summary_zh": summary,
                        "access_mode": m.get("access_mode"),
                    },
                    ensure_ascii=False,
                ),
                "source_url": m.get("source_url"),
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
                "source": INDEX_URL,
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


def import_dogdog_malls(malls: list[dict] | None = None, replace: bool = True) -> dict:
    from pawplan.database.db import get_connection, init_database

    if malls is None:
        malls = fetch_all_malls(skip_fetch=True)
    rows = to_place_rows(malls)
    write_staging(rows)
    init_database(apply_second_source=False)
    conn = get_connection()
    skipped_overlap = 0
    try:
        if replace:
            conn.execute("DELETE FROM places WHERE source_name = ?", (SOURCE_NAME,))
        # Prefer official policy pages and existing GoPaw only when names collide
        # with official; DogDog fills gaps.
        protected = conn.execute(
            """
            SELECT name_en, name_zh FROM places
            WHERE place_type = 'mall' AND source_name = ?
            """,
            (OFFICIAL_SOURCE,),
        ).fetchall()
        protected_keys: set[str] = set()
        for p in protected:
            protected_keys |= _name_keys({"name_en": p["name_en"], "name_zh": p["name_zh"]})

        imported = 0
        for row in rows:
            if _name_keys(row) & protected_keys:
                skipped_overlap += 1
                continue
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
            imported += 1
        # Remove GoPaw malls that now duplicate DogDog entries (DogDog richer notes)
        dog_keys: set[str] = set()
        for row in rows:
            dog_keys |= _name_keys(row)
        gopaw = conn.execute(
            """
            SELECT place_id, name_en, name_zh FROM places
            WHERE place_type = 'mall' AND source_name = 'GoPaw'
            """
        ).fetchall()
        removed_gopaw = 0
        for g in gopaw:
            if _name_keys({"name_en": g["name_en"], "name_zh": g["name_zh"]}) & dog_keys:
                conn.execute("DELETE FROM places WHERE place_id = ?", (g["place_id"],))
                removed_gopaw += 1
        conn.commit()
        return {
            "dogdog_raw": len(malls),
            "with_district": len(rows),
            "imported": imported,
            "skipped_official_overlap": skipped_overlap,
            "gopaw_duplicates_removed": removed_gopaw,
            "staging": str(STAGING),
            "raw": str(RAW_JSON),
            "evidence_tier": 3,
        }
    finally:
        conn.close()


def refresh_dogdog_malls(skip_fetch: bool = False) -> dict:
    malls = fetch_all_malls(skip_fetch=skip_fetch)
    return import_dogdog_malls(malls, replace=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch DogDogHK mall directory")
    parser.add_argument("--skip-fetch", action="store_true")
    args = parser.parse_args()
    stats = refresh_dogdog_malls(skip_fetch=args.skip_fetch)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
