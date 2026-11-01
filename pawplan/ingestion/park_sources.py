"""Public LCSD park pages, separated by facility type and all 18 districts."""

from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

from pawplan.normalize import normalize_district

ROOT = Path(__file__).resolve().parents[2]
FACILITY_BASE = "https://www.lcsd.gov.hk/clpss/tc/webApp/Facility/"

# IDs come from the LCSD district selector, not the project's district ordering.
DISTRICT_IDS = {
    "Central/Western": 1,
    "Eastern": 2,
    "Islands": 3,
    "Kowloon City": 4,
    "Kwai Tsing": 5,
    "Kwun Tong": 6,
    "North": 7,
    "Sai Kung": 8,
    "Sham Shui Po": 9,
    "Sha Tin": 10,
    "Southern": 11,
    "Tai Po": 12,
    "Tsuen Wan": 13,
    "Tuen Mun": 14,
    "Wan Chai": 15,
    "Wong Tai Sin": 16,
    "Yau Tsim Mong": 17,
    "Yuen Long": 18,
}
DISTRICT_LABELS = (
    "中西區", "東區", "離島區", "九龍城區", "葵青區", "觀塘區",
    "北區", "西貢區", "深水埗區", "沙田區", "南區", "大埔區",
    "荃灣區", "屯門區", "灣仔區", "黃大仙區", "油尖旺區", "元朗區",
)
FACILITY_TYPES = {"pet_garden": 47, "inclusive_park": 165}
FACILITY_LABELS = {"pet_garden": "狗公園 / 寵物公園", "inclusive_park": "寵物共享公園"}


def park_source_url(district: str, park_type: str) -> str:
    """Use the district's public list; an unknown district gets the official index."""
    ftid = FACILITY_TYPES[park_type]
    did = DISTRICT_IDS.get(normalize_district(district) or district)
    if did is None:
        return f"{FACILITY_BASE}District.do?ftid={ftid}"
    return f"{FACILITY_BASE}Details.do?ftid={ftid}&fcid=&did={did}"


class ParkPageParser(HTMLParser):
    """Read the district selector and venue tables without optional dependencies."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.district_options: dict[int, str] = {}
        self.selected_district: int | None = None
        self.venues: list[dict[str, str]] = []
        self._selector = False
        self._option: int | None = None
        self._table = False
        self._cell: list[str] | None = None
        self._row: list[str] = []
        self._venue: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag == "select" and attr.get("id") == "linkList":
            self._selector = True
        elif tag == "option" and self._selector:
            self._option = int(attr["value"])
            self.district_options[self._option] = ""
            if "selected" in attr:
                self.selected_district = self._option
        elif tag == "table" and "fac-table" in (attr.get("class") or "").split():
            self._table = True
            self._venue = {}
        elif self._table and tag == "tr":
            self._row = []
        elif self._table and tag in {"td", "th"}:
            self._cell = []
        elif self._cell is not None and tag in {"br", "li", "p"}:
            self._cell.append(" ")
        if self._table and tag == "a":
            match = re.search(r"showPopupStaticMap\('([^']+)'", attr.get("href") or "")
            if match:
                self._venue["map_id"] = match.group(1)

    def handle_data(self, data: str) -> None:
        if self._option is not None:
            self.district_options[self._option] += data
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "option":
            if self._option is not None:
                self.district_options[self._option] = self.district_options[self._option].strip()
            self._option = None
        elif tag == "select":
            self._selector = False
        elif tag in {"td", "th"} and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._table and len(self._row) == 2:
            self._venue[self._row[0]] = self._row[1]
        elif tag == "table" and self._table:
            if self._venue.get("場地名稱") or self._venue.get("Name of Venue"):
                self.venues.append(self._venue)
            self._table = False


def fetch_park_pages(out_dir: Path | None = None) -> Path:
    """Fetch and validate every district/type pair before publishing the manifest."""
    out_dir = out_dir or (ROOT / "data" / "raw")
    cache = out_dir / "lcsd_park_pages"
    cache.mkdir(parents=True, exist_ok=True)
    fetched_at = datetime.now(timezone.utc).isoformat()
    expected = {i: label for i, label in enumerate(DISTRICT_LABELS, 1)}

    def fetch(pair: tuple[str, str]) -> dict:
        district, park_type = pair
        url = park_source_url(district, park_type)
        def download(page_url: str) -> str:
            request = Request(page_url, headers={"User-Agent": "PawPlanHK/0.1 (academic project)"})
            with urlopen(request, timeout=30) as response:
                return response.read().decode("utf-8-sig")

        html = download(url)
        parser = ParkPageParser()
        parser.feed(html)
        did = DISTRICT_IDS[district]
        if parser.district_options != expected or parser.selected_district != did:
            raise ValueError(f"LCSD district selector changed or returned the wrong district: {url}")
        heading = re.search(r"<h1\b[^>]*>(.*?)</h1>", html, re.S | re.I)
        title = " ".join(re.sub(r"<[^>]+>", "", heading.group(1)).split()) if heading else ""
        if title != FACILITY_LABELS[park_type] or not parser.venues:
            raise ValueError(f"LCSD facility page has no expected venue data: {url}")
        english_url = url.replace("/tc/", "/en/")
        english_html = download(english_url)
        english = ParkPageParser()
        english.feed(english_html)
        if english.selected_district != did or len(english.venues) != len(parser.venues):
            raise ValueError(f"LCSD Chinese/English venue lists differ: {url}")
        details = []
        for zh, en in zip(parser.venues, english.venues):
            if (zh.get("map_id") != en.get("map_id")
                    or not en.get("Name of Venue")):
                raise ValueError(f"LCSD Chinese/English venue order differs: {url}")
            details.append({"zh": zh, "en": en})
        (cache / f"{park_type}_{did:02d}.html").write_text(html, encoding="utf-8")
        (cache / f"{park_type}_{did:02d}_en.html").write_text(english_html, encoding="utf-8")
        return {
            "district": district,
            "district_zh": expected[did],
            "district_id": did,
            "park_type": park_type,
            "facility_type_id": FACILITY_TYPES[park_type],
            "source_url": url,
            "venue_count": len(parser.venues),
            "venues": [v["場地名稱"] for v in parser.venues],
            "venue_details": details,
        }

    pairs = [(district, kind) for district in DISTRICT_IDS for kind in FACILITY_TYPES]
    with ThreadPoolExecutor(max_workers=3) as pool:
        pages = list(pool.map(fetch, pairs))
    manifest = out_dir / "lcsd_park_pages.json"
    manifest.write_text(json.dumps({
        "fetched_at_utc": fetched_at,
        "district_count": len(DISTRICT_IDS),
        "page_count": len(pages),
        "downloaded_page_count": len(pages) * 2,
        "pages": pages,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    argparse.ArgumentParser(description="Verify LCSD park pages for all 18 districts").parse_args()
    path = fetch_park_pages()
    print(f"Verified 36 LCSD pages across 18 districts: {path}")


if __name__ == "__main__":
    main()
