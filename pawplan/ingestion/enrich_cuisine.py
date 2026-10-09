"""Cuisine overlay for optional restaurant filtering.

FEHD official list has no cuisine field. Labels come from curated name
overlays and name-keyword heuristics; never present them as official
FEHD cuisine confirmation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pawplan.normalize import CUISINE_LABELS, infer_cuisine_from_name, normalize_cuisine

ROOT = Path(__file__).resolve().parents[2]

# High-confidence curated labels for midterm demos (name/district keyed).
# Confidence reflects human/venue check, not LLM guessing.
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
        "confidence": 0.85,
        "source_url": "curated://pawplan/cuisine_overlay",
    },
]


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
        return code, float(item.get("confidence", 0.8)), item.get(
            "source_url", "curated://pawplan/cuisine_overlay"
        )
    return None


def enrich_restaurants(
    staging_path: Path,
    out_path: Path | None = None,
    overlay_path: Path | None = None,
) -> Path:
    payload = json.loads(staging_path.read_text(encoding="utf-8"))
    overlays = load_overlay(overlay_path)
    enriched = []

    for row in payload.get("restaurants", []):
        overlay = apply_overlay(row, overlays)
        if overlay:
            code, confidence, source = overlay
        else:
            code, confidence = infer_cuisine_from_name(
                row.get("name_en") or "",
                row.get("name_zh") or "",
            )
            source = "heuristic://pawplan/name_keywords"

        label_zh, label_en = CUISINE_LABELS.get(code, ("未标注", "Unknown"))
        item = dict(row)
        item["cuisines"] = [
            {
                "cuisine_code": code,
                "cuisine_label_zh": label_zh,
                "cuisine_label_en": label_en,
                "cuisine_source_url": source,
                "cuisine_confidence": confidence,
            }
        ]
        # Also tag cantonese/chinese lightly for dim_sum venues
        if code == "dim_sum":
            item["cuisines"].append(
                {
                    "cuisine_code": "cantonese",
                    "cuisine_label_zh": "粤菜",
                    "cuisine_label_en": "Cantonese",
                    "cuisine_source_url": source,
                    "cuisine_confidence": min(confidence, 0.7),
                }
            )
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich FEHD staging with cuisine")
    parser.add_argument(
        "--in",
        dest="inp",
        default=str(ROOT / "data" / "staging" / "fehd_restaurants.json"),
    )
    parser.add_argument("--out", default=None)
    parser.add_argument("--overlay", default=None)
    args = parser.parse_args()
    out = enrich_restaurants(
        Path(args.inp),
        Path(args.out) if args.out else None,
        Path(args.overlay) if args.overlay else None,
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    codes = {}
    for r in data["restaurants"]:
        for c in r["cuisines"]:
            codes[c["cuisine_code"]] = codes.get(c["cuisine_code"], 0) + 1
    print(f"Wrote {out} ({data['count']} restaurants)")
    print("cuisine distribution:", dict(sorted(codes.items(), key=lambda x: -x[1])[:12]))


if __name__ == "__main__":
    main()
