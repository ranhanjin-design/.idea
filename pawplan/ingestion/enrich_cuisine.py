"""Cuisine overlay for optional restaurant filtering.

FEHD official list has no cuisine field. Confirmed labels come from a
complementary second source (OSM public directory and/or human review)
after entity match. Name-keyword heuristics stay low-confidence only and
must never be presented as official FEHD cuisine. LLM must not guess
cuisine during data prep.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pawplan.ingestion.entity_match import identity_match, match_score
from pawplan.ingestion.fetch_cuisine_osm import SECOND_SOURCE_PATH, load_second_source
from pawplan.normalize import CUISINE_LABELS, infer_cuisine_from_name, normalize_cuisine

ROOT = Path(__file__).resolve().parents[2]
HEURISTIC_MAX_CONFIDENCE = 0.45
HEURISTIC_SOURCES = (
    "heuristic://pawplan/name_keywords",
    "curated://pawplan/cuisine_overlay",
)

# Legacy name-contains overlay. Kept only as a low-confidence heuristic.
CURATED_CUISINES: list[dict] = [
    {
        "match_name_contains": [
            "茶楼",
            "茶樓",
            "茶餐廳",
            "茶餐厅",
            "茶餐室",
            "点心",
            "點心",
            "飲茶",
            "饮茶",
            "Dim Sum",
            "Yum Cha",
            "Tea House",
        ],
        "cuisine_code": "dim_sum",
        "confidence": HEURISTIC_MAX_CONFIDENCE,
        "source_url": "heuristic://pawplan/name_keywords",
    },
]


def is_second_source_url(url: str | None) -> bool:
    if not url:
        return False
    lower = str(url).lower()
    return any(
        marker in lower
        for marker in (
            "openstreetmap.org",
            "gopaw.io",
            "human_review://",
            "human://pawplan",
        )
    )


def load_overlay(path: Path | None) -> list[dict]:
    if path and path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("overlays", data if isinstance(data, list) else [])
    return CURATED_CUISINES


def apply_overlay(row: dict, overlays: list[dict]) -> tuple[str, float, str] | None:
    name_blob = f"{row.get('name_en') or ''} {row.get('name_zh') or ''}"
    district = row.get("district") or ""
    for item in overlays:
        needles = item.get("match_name_contains") or []
        want_district = item.get("match_district")
        if want_district and want_district != district:
            continue
        if needles and not any(n.lower() in name_blob.lower() or n in name_blob for n in needles):
            continue
        if not needles and not want_district:
            continue
        code = normalize_cuisine(item.get("cuisine_code")) or "unknown"
        return (
            code,
            min(float(item.get("confidence", HEURISTIC_MAX_CONFIDENCE)), HEURISTIC_MAX_CONFIDENCE),
            item.get("source_url", "heuristic://pawplan/name_keywords"),
        )
    return None


def _cuisine_tuple(code: str, confidence: float, source: str) -> dict:
    label_zh, label_en = CUISINE_LABELS.get(code, ("未标注", "Unknown"))
    return {
        "cuisine_code": code,
        "cuisine_label_zh": label_zh,
        "cuisine_label_en": label_en,
        "cuisine_source_url": source,
        "cuisine_confidence": float(confidence),
    }


def match_second_source_entries(row: dict, entries: list[dict]) -> list[dict]:
    """Return auto-merge second-source hits. Review-queue / unmatched stay unlabeled."""
    hits: list[dict] = []
    seen = set()
    for entry in entries:
        method = (entry.get("method") or "").lower()
        if method not in {"osm", "human_review", "gopaw"}:
            continue
        code = normalize_cuisine(entry.get("cuisine_code"))
        if not code or code == "unknown":
            continue
        if identity_match(entry, row) or match_score(entry, row) >= 0.90:
            key = (code, entry.get("cuisine_source_url"))
            if key in seen:
                continue
            seen.add(key)
            hits.append(entry)
    return hits


def _heuristic_guess(row: dict, overlays: list[dict]) -> tuple[str, float, str]:
    overlay = apply_overlay(row, overlays)
    if overlay:
        return overlay
    code, confidence = infer_cuisine_from_name(
        row.get("name_en") or "",
        row.get("name_zh") or "",
    )
    return code, min(float(confidence), HEURISTIC_MAX_CONFIDENCE), "heuristic://pawplan/name_keywords"


def merge_row_cuisines(row: dict, entries: list[dict], overlays: list[dict]) -> list[dict]:
    heuristic_code, heuristic_conf, heuristic_source = _heuristic_guess(row, overlays)
    hits = match_second_source_entries(row, entries)
    cuisines: list[dict] = []
    seen_codes: set[str] = set()

    for entry in hits:
        code = normalize_cuisine(entry.get("cuisine_code")) or "unknown"
        confidence = float(entry.get("cuisine_confidence", 0.8))
        source = entry.get("cuisine_source_url") or "human_review://pawplan/fehd-name-check"
        if heuristic_code == code and heuristic_code != "unknown":
            confidence = min(0.98, max(confidence, heuristic_conf) + 0.05)
        item = _cuisine_tuple(code, confidence, source)
        if code not in seen_codes:
            cuisines.append(item)
            seen_codes.add(code)

    if not cuisines and heuristic_code and heuristic_code != "unknown":
        cuisines.append(
            _cuisine_tuple(heuristic_code, heuristic_conf, heuristic_source)
        )
        seen_codes.add(heuristic_code)
    elif not cuisines:
        cuisines.append(_cuisine_tuple("unknown", 0.1, "heuristic://pawplan/name_keywords"))
        seen_codes.add("unknown")

    if "dim_sum" in seen_codes and "cantonese" not in seen_codes:
        parent = next(c for c in cuisines if c["cuisine_code"] == "dim_sum")
        cuisines.append(
            _cuisine_tuple(
                "cantonese",
                min(parent["cuisine_confidence"], 0.7),
                parent["cuisine_source_url"],
            )
        )
    return cuisines


def enrich_restaurants(
    staging_path: Path,
    out_path: Path | None = None,
    overlay_path: Path | None = None,
    second_source_path: Path | None = None,
) -> Path:
    payload = json.loads(staging_path.read_text(encoding="utf-8"))
    overlays = load_overlay(overlay_path)
    second = load_second_source(second_source_path or SECOND_SOURCE_PATH)
    entries = second.get("entries") or []
    enriched = []

    for row in payload.get("restaurants", []):
        item = dict(row)
        item["cuisines"] = merge_row_cuisines(row, entries, overlays)
        enriched.append(item)

    staging_dir = ROOT / "data" / "staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_path or (staging_dir / "fehd_restaurants_enriched.json")
    out_payload = {
        "source": payload.get("source"),
        "parsed_at": payload.get("parsed_at"),
        "count": len(enriched),
        "restaurants": enriched,
    }
    out_path.write_text(
        json.dumps(out_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out_path


def apply_second_source_to_db(second_source_path: Path | None = None) -> dict:
    """Patch live SQLite restaurant_cuisines from the complementary source.

    Identity / auto-merge (>=0.90) only. Unmatched restaurants are not
    force-labeled. Existing name-heuristic rows are capped at 0.45.
    """
    from pawplan.database.db import get_connection
    from pawplan.normalize import CUISINE_LABELS as LABELS

    second = load_second_source(second_source_path or SECOND_SOURCE_PATH)
    entries = [
        e
        for e in (second.get("entries") or [])
        if (e.get("method") or "").lower() in {"osm", "human_review", "gopaw"}
    ]
    conn = get_connection()
    stats = {
        "entries": len(entries),
        "restaurants_considered": 0,
        "auto_merged": 0,
        "heuristic_downgraded": 0,
    }
    try:
        downgraded = conn.execute(
            """
            UPDATE restaurant_cuisines
            SET cuisine_confidence = MIN(cuisine_confidence, ?)
            WHERE cuisine_source_url LIKE 'heuristic://%'
               OR cuisine_source_url = 'curated://pawplan/cuisine_overlay'
            """,
            (HEURISTIC_MAX_CONFIDENCE,),
        )
        stats["heuristic_downgraded"] = downgraded.rowcount if downgraded.rowcount is not None else 0

        restaurants = conn.execute(
            """
            SELECT restaurant_id, name_en, name_zh, district, address
            FROM restaurants
            """
        ).fetchall()
        stats["restaurants_considered"] = len(restaurants)
        matched_ids: set[str] = set()

        def _write_cuisine(restaurant_id: str, entry: dict) -> None:
            code = normalize_cuisine(entry.get("cuisine_code")) or "unknown"
            label_zh, label_en = LABELS.get(code, ("未标注", "Unknown"))
            confidence = float(entry.get("cuisine_confidence", 0.8))
            source = entry.get("cuisine_source_url") or "human_review://pawplan/fehd-name-check"
            conn.execute(
                """
                INSERT OR REPLACE INTO restaurant_cuisines (
                    restaurant_id, cuisine_code, cuisine_label_zh, cuisine_label_en,
                    cuisine_source_url, cuisine_confidence
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (restaurant_id, code, label_zh, label_en, source, confidence),
            )

        # Prefer restaurant_id when present (GoPaw auto-merge already entity-matched).
        by_id = {r["restaurant_id"]: r for r in restaurants}
        remaining: list[dict] = []
        for entry in entries:
            rid = entry.get("restaurant_id")
            if rid and rid in by_id:
                matched_ids.add(rid)
                _write_cuisine(rid, entry)
            else:
                remaining.append(entry)

        for row in restaurants:
            restaurant = {key: row[key] for key in row.keys()}
            hits = match_second_source_entries(restaurant, remaining)
            if not hits:
                continue
            matched_ids.add(restaurant["restaurant_id"])
            for entry in hits:
                _write_cuisine(restaurant["restaurant_id"], entry)
        stats["auto_merged"] = len(matched_ids)
        conn.commit()
        return stats
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich FEHD staging with cuisine")
    parser.add_argument(
        "--in",
        dest="inp",
        default=str(ROOT / "data" / "staging" / "fehd_restaurants.json"),
    )
    parser.add_argument("--out", default=None)
    parser.add_argument("--overlay", default=None)
    parser.add_argument("--second-source", default=None)
    parser.add_argument(
        "--apply-db",
        action="store_true",
        help="Patch live SQLite restaurant_cuisines from the second source",
    )
    args = parser.parse_args()
    if args.apply_db:
        stats = apply_second_source_to_db(
            Path(args.second_source) if args.second_source else None
        )
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return
    out = enrich_restaurants(
        Path(args.inp),
        Path(args.out) if args.out else None,
        Path(args.overlay) if args.overlay else None,
        Path(args.second_source) if args.second_source else None,
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    codes: dict[str, int] = {}
    for r in data["restaurants"]:
        for c in r["cuisines"]:
            codes[c["cuisine_code"]] = codes.get(c["cuisine_code"], 0) + 1
    print(f"Wrote {out} ({data['count']} restaurants)")
    print("cuisine distribution:", dict(sorted(codes.items(), key=lambda x: -x[1])[:12]))


if __name__ == "__main__":
    main()
