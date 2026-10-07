"""Parse LCSD pet gardens JSON + Inclusive Park for Pets PDF into staging."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

from pypdf import PdfReader

from pawplan.normalize import normalize_district

ROOT = Path(__file__).resolve().parents[2]

SOURCE_PET_GARDEN = "https://www.lcsd.gov.hk/datagovhk/facility/facility-dgpg.json"
SOURCE_IPP = "https://www.lcsd.gov.hk/en/common/pdf/Annex_IPP_Venue.pdf"

# Prefer Chinese headers from LCSD PDF (more reliable than wrapped English lines).
DISTRICT_MARKERS: list[tuple[str, str]] = [
    ("中西區", "Central/Western"),
    ("中西区", "Central/Western"),
    ("灣仔區", "Wan Chai"),
    ("湾仔区", "Wan Chai"),
    ("灣仔", "Wan Chai"),
    ("东区", "Eastern"),
    ("東區", "Eastern"),
    ("南区", "Southern"),
    ("南區", "Southern"),
    ("油尖旺區", "Yau Tsim Mong"),
    ("油尖旺区", "Yau Tsim Mong"),
    ("油尖旺", "Yau Tsim Mong"),
    ("深水埗區", "Sham Shui Po"),
    ("深水埗区", "Sham Shui Po"),
    ("深水埗", "Sham Shui Po"),
    ("九龍城區", "Kowloon City"),
    ("九龙城区", "Kowloon City"),
    ("九龍城", "Kowloon City"),
    ("黃大仙區", "Wong Tai Sin"),
    ("黄大仙区", "Wong Tai Sin"),
    ("黃大仙", "Wong Tai Sin"),
    ("观塘区", "Kwun Tong"),
    ("觀塘區", "Kwun Tong"),
    ("觀塘", "Kwun Tong"),
    ("葵青區", "Kwai Tsing"),
    ("葵青区", "Kwai Tsing"),
    ("葵青", "Kwai Tsing"),
    ("荃灣區", "Tsuen Wan"),
    ("荃湾区", "Tsuen Wan"),
    ("荃灣", "Tsuen Wan"),
    ("屯門區", "Tuen Mun"),
    ("屯门区", "Tuen Mun"),
    ("屯門", "Tuen Mun"),
    ("元朗區", "Yuen Long"),
    ("元朗区", "Yuen Long"),
    ("元朗", "Yuen Long"),
    ("西貢區", "Sai Kung"),
    ("西贡区", "Sai Kung"),
    ("西貢", "Sai Kung"),
    ("沙田區", "Sha Tin"),
    ("沙田区", "Sha Tin"),
    ("沙田", "Sha Tin"),
    ("大埔區", "Tai Po"),
    ("大埔区", "Tai Po"),
    ("大埔", "Tai Po"),
    ("北區", "North"),
    ("北区", "North"),
    ("離島區", "Islands"),
    ("离岛区", "Islands"),
    ("離島", "Islands"),
    ("Central and Western", "Central/Western"),
    ("Central & Western", "Central/Western"),
    ("Wan Chai", "Wan Chai"),
    ("Yau Tsim Mong", "Yau Tsim Mong"),
    ("Sham Shui Po", "Sham Shui Po"),
    ("Kowloon City", "Kowloon City"),
    ("Wong Tai Sin", "Wong Tai Sin"),
    ("Kwun Tong", "Kwun Tong"),
    ("Kwai Tsing", "Kwai Tsing"),
    ("Tsuen Wan", "Tsuen Wan"),
    ("Tuen Mun", "Tuen Mun"),
    ("Yuen Long", "Yuen Long"),
    ("Sai Kung", "Sai Kung"),
    ("Sha Tin", "Sha Tin"),
    ("Tai Po", "Tai Po"),
    ("Eastern", "Eastern"),
    ("Southern", "Southern"),
    ("Islands", "Islands"),
    ("North", "North"),
]


def _strip_html(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"<[^>]+>", " ", value)
    text = " ".join(text.split())
    return text or None


def _dms_to_decimal(value: str | None) -> float | None:
    """Convert LCSD '114-11-0' style to decimal degrees."""
    if not value:
        return None
    parts = str(value).strip().split("-")
    if len(parts) != 3:
        return None
    try:
        deg, minutes, seconds = (float(p) for p in parts)
    except ValueError:
        return None
    return deg + minutes / 60.0 + seconds / 3600.0


def parse_pet_gardens_json(path: Path, verified_at: str) -> list[dict]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    out: list[dict] = []
    for i, row in enumerate(rows, 1):
        district = normalize_district(row.get("District_en") or row.get("District_cn"))
        if not district:
            continue
        name_en = (row.get("Name_en") or "").strip() or None
        name_zh = (row.get("Name_cn") or "").strip() or None
        address = (row.get("Address_en") or row.get("Address_cn") or "").strip() or None
        fac_blob = " ".join(
            [
                row.get("Facilities_en") or "",
                row.get("Facilities_b5") or "",
                row.get("Ancillary_facilities_en") or "",
                row.get("Ancillary_facilities_cn") or "",
            ]
        )
        facilities = {
            "facilities_en": _strip_html(row.get("Facilities_en")),
            "facilities_zh": _strip_html(row.get("Facilities_b5")),
            "ancillary_en": _strip_html(row.get("Ancillary_facilities_en")),
            "ancillary_zh": _strip_html(row.get("Ancillary_facilities_cn")),
            "remarks_en": _strip_html(row.get("Remarks_en")),
            "remarks_zh": _strip_html(row.get("Remarks_cn")),
            "has_dog_latrine": (
                "latrine" in fac_blob.lower()
                or "狗厕" in fac_blob
                or "狗廁" in fac_blob
            ),
        }
        gihs = (row.get("GIHS") or "").strip()
        park_id = f"lcsd_pg_{gihs}" if gihs else f"lcsd_pg_{i:03d}"
        out.append(
            {
                "park_id": park_id,
                "park_type": "pet_garden",
                "name_en": name_en,
                "name_zh": name_zh,
                "district": district,
                "address": address,
                "facilities_json": json.dumps(facilities, ensure_ascii=False),
                "opening_hours": row.get("Opening_hours_en")
                or row.get("Opening_hours_cn"),
                "phone": row.get("Phone"),
                "latitude": _dms_to_decimal(row.get("Latitude")),
                "longitude": _dms_to_decimal(row.get("Longitude")),
                "source_url": SOURCE_PET_GARDEN,
                "last_verified_at": verified_at,
            }
        )
    return out


def _extract_ipp_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    parts = []
    for i, page in enumerate(reader.pages):
        parts.append(f"\n===== PAGE {i + 1} =====\n")
        parts.append(page.extract_text() or "")
    return "".join(parts)


def parse_ipp_pdf(pdf_path: Path, verified_at: str) -> list[dict]:
    text = _extract_ipp_text(pdf_path)
    (ROOT / "data" / "raw" / "lcsd_ipp_venue.txt").write_text(text, encoding="utf-8")

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    current_district: str | None = None
    pending_zh: str | None = None
    records: list[dict] = []
    seen: set[str] = set()

    def set_district_from_line(line: str) -> None:
        nonlocal current_district
        # Exact / startswith match; longer Chinese markers first (list order).
        for marker, canonical in DISTRICT_MARKERS:
            if marker.isascii():
                low = line.lower().strip()
                if low == marker.lower():
                    current_district = canonical
                    return
                # wrapped "Central and" / "Western"
                if marker.lower() == "central and western" and low in {
                    "central and",
                    "western",
                }:
                    current_district = canonical
                    return
                if marker == "North" and "point" in low:
                    continue
            else:
                if line.strip() == marker or line.strip().startswith(marker):
                    # Avoid "沙田" matching inside longer unrelated strings poorly
                    if len(marker) <= 2 and line.strip() != marker:
                        continue
                    current_district = canonical
                    return

    i = 0
    while i < len(lines):
        line = lines[i]
        set_district_from_line(line)

        m = re.match(r"^(\d+)\.\s+(.+)$", line)
        if m:
            rest = m.group(2).strip()
            # Chinese title line; English usually next
            if re.search(r"[\u4e00-\u9fff]", rest):
                pending_zh = rest.replace("*", "").replace("#", "").strip()
                if i + 1 < len(lines) and re.match(r"^[A-Za-z]", lines[i + 1]):
                    en = lines[i + 1]
                    # merge continuation if next next is continuation fragment
                    j = i + 2
                    while j < len(lines):
                        nxt = lines[j]
                        if re.match(r"^\d+\.", nxt):
                            break
                        if re.search(r"[\u4e00-\u9fff]", nxt):
                            break
                        if re.match(r"^[A-Za-z]", nxt) and (
                            any(
                                nxt.lower().startswith(x)
                                for x in (
                                    "food market",
                                    "section",
                                    "phase",
                                    "and ",
                                )
                            )
                            or len(nxt.split()) <= 4
                        ):
                            en = en + " " + nxt
                            j += 1
                            continue
                        break
                    name_en = en.replace("*", "").replace("#", "").strip(" -–")
                    name_en = re.sub(r"\s+", " ", name_en)
                    if name_en.lower() in {"district", "venue", "attachment"}:
                        i += 1
                        continue
                    district = current_district or "Unknown"
                    key = f"{district}|{name_en.lower()}"
                    if key not in seen and len(name_en) >= 5:
                        seen.add(key)
                        park_id = f"lcsd_ipp_{len(records) + 1:03d}"
                        records.append(
                            {
                                "park_id": park_id,
                                "park_type": "inclusive_park",
                                "name_en": name_en,
                                "name_zh": pending_zh,
                                "district": district,
                                "address": None,
                                "facilities_json": json.dumps(
                                    {
                                        "note_en": "Inclusive Park for Pets; pets usually must be leashed",
                                        "note_zh": "宠物共享公园；一般须牵绳看管",
                                    },
                                    ensure_ascii=False,
                                ),
                                "opening_hours": None,
                                "phone": None,
                                "latitude": None,
                                "longitude": None,
                                "source_url": SOURCE_IPP,
                                "last_verified_at": verified_at,
                            }
                        )
                    pending_zh = None
                    i = j
                    continue
        i += 1

    return records


def parse_all_parks(
    pet_garden_json: Path | None = None,
    ipp_pdf: Path | None = None,
    out_path: Path | None = None,
) -> Path:
    verified_at = date.today().isoformat()
    pet_garden_json = pet_garden_json or (
        ROOT / "data" / "raw" / "lcsd_pet_gardens.json"
    )
    ipp_pdf = ipp_pdf or (ROOT / "data" / "raw" / "lcsd_ipp_venue.pdf")

    parks: list[dict] = []
    if pet_garden_json.exists():
        parks.extend(parse_pet_gardens_json(pet_garden_json, verified_at))
    if ipp_pdf.exists():
        parks.extend(parse_ipp_pdf(ipp_pdf, verified_at))

    staging = ROOT / "data" / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    out_path = out_path or (staging / "lcsd_parks.json")
    payload = {
        "sources": [SOURCE_PET_GARDEN, SOURCE_IPP],
        "parsed_at": verified_at,
        "count": len(parks),
        "pet_gardens": sum(1 for p in parks if p["park_type"] == "pet_garden"),
        "inclusive_parks": sum(1 for p in parks if p["park_type"] == "inclusive_park"),
        "parks": parks,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse LCSD park sources")
    parser.add_argument("--pet-garden-json", default=None)
    parser.add_argument("--ipp-pdf", default=None)
    args = parser.parse_args()
    out = parse_all_parks(
        Path(args.pet_garden_json) if args.pet_garden_json else None,
        Path(args.ipp_pdf) if args.ipp_pdf else None,
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    print(
        f"Wrote {out}: total={data['count']} "
        f"pet_gardens={data['pet_gardens']} inclusive={data['inclusive_parks']}"
    )


if __name__ == "__main__":
    main()
