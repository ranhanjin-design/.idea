"""Parse FEHD dog-permitted restaurant PDF into staging JSON."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

from pypdf import PdfReader

from pawplan.normalize import normalize_district

ROOT = Path(__file__).resolve().parents[2]

DISTRICTS = [
    "Central/Western",
    "Wan Chai",
    "Eastern",
    "Southern",
    "Mong Kok",
    "Yau Tsim",  # PDF line-wrap of Yau Tsim Mong
    "Sham Shui Po",
    "Kowloon City",
    "Wong Tai Sin",
    "Kwun Tong",
    "Tsuen Wan",
    "Tuen Mun",
    "Yuen Long",
    "North",
    "Tai Po",
    "Sha Tin",
    "Sai Kung",
    "Islands",
    "Kwai Tsing",
]
DISTRICTS_SORTED = sorted(DISTRICTS, key=len, reverse=True)
DISTRICT_RE = re.compile(
    r"(?<![A-Za-z])(" + "|".join(re.escape(d) for d in DISTRICTS_SORTED) + r")(?![A-Za-z])"
)
LICENCE_RE = re.compile(r"\b\d{10}\b")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def extract_pdf_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    parts: list[str] = []
    for i, page in enumerate(reader.pages):
        parts.append(f"\n===== PAGE {i + 1} =====\n")
        parts.append(page.extract_text() or "")
    return "".join(parts)


def clean_body(body: str) -> str:
    cleaned = re.sub(r"===== PAGE \d+ =====", "\n", body)
    cleaned = re.sub(r"List of Food Premises[^\n]*\n?", "", cleaned)
    cleaned = re.sub(r"List updated on[^\n]*\n?", "", cleaned)
    cleaned = re.sub(
        r"Shop Sign Chinese Shop Sign District Address Licence Number\n?",
        "",
        cleaned,
    )
    return cleaned.strip()


def split_names(before: str) -> tuple[str, str]:
    text = " ".join(before.replace("\n", " ").split())
    if not text:
        return "", ""

    # Identical duplicated bilingual label: "FOO FOO"
    tokens = text.split()
    if len(tokens) >= 2 and len(tokens) % 2 == 0:
        mid = len(tokens) // 2
        left = " ".join(tokens[:mid])
        right = " ".join(tokens[mid:])
        if left.lower() == right.lower():
            return left, right

    # Split at first CJK run if mixed
    m = CJK_RE.search(text)
    if m and m.start() > 0:
        en = text[: m.start()].strip(" -|/")
        zh = text[m.start() :].strip(" -|/")
        return en, zh

    if CJK_RE.search(text):
        return "", text
    return text, ""


def parse_records(text: str, source_url: str, verified_at: str) -> list[dict]:
    tokens = re.split(r"(\b\d{10}\b)", text)
    records: list[dict] = []
    seen: set[str] = set()

    for idx in range(1, len(tokens), 2):
        licence = tokens[idx]
        if licence in seen:
            continue
        body = clean_body(tokens[idx - 1])
        matches = list(DISTRICT_RE.finditer(body))
        if not matches:
            continue
        m = matches[0]
        district_raw = m.group(1)
        district = normalize_district(district_raw) or district_raw
        before = body[: m.start()].strip()
        address = " ".join(body[m.end() :].split())
        name_en, name_zh = split_names(before)
        if not name_en and not name_zh:
            continue
        if name_en.lower().startswith("(no record found)"):
            continue

        restaurant_id = f"fehd_{licence}"
        records.append(
            {
                "restaurant_id": restaurant_id,
                "licence_no": licence,
                "name_en": name_en or None,
                "name_zh": name_zh or None,
                "district": district,
                "address": address or "Address unavailable",
                "dog_permission": True,
                "source_url": source_url,
                "last_verified_at": verified_at,
            }
        )
        seen.add(licence)

    return records


def parse_fehd_pdf(pdf_path: Path, out_path: Path | None = None) -> Path:
    pdf_path = Path(pdf_path)
    text = extract_pdf_text(pdf_path)
    raw_txt = ROOT / "data" / "raw" / "fehd_fulllist.txt"
    raw_txt.parent.mkdir(parents=True, exist_ok=True)
    raw_txt.write_text(text, encoding="utf-8")

    source_url = (
        "https://www.fehd.gov.hk/english/licensing/dog_restaurants/fulllist.pdf"
    )
    verified_at = date.today().isoformat()
    records = parse_records(text, source_url, verified_at)

    staging_dir = ROOT / "data" / "staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_path or (staging_dir / "fehd_restaurants.json")
    payload = {
        "source": source_url,
        "parsed_at": verified_at,
        "count": len(records),
        "restaurants": records,
    }
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse FEHD PDF to staging JSON")
    parser.add_argument(
        "--pdf",
        default=str(ROOT / "data" / "raw" / "fehd_dog_restaurants_fulllist.pdf"),
    )
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    out = parse_fehd_pdf(Path(args.pdf), Path(args.out) if args.out else None)
    data = json.loads(out.read_text(encoding="utf-8"))
    print(f"Wrote {out} with {data['count']} restaurants")


if __name__ == "__main__":
    main()
