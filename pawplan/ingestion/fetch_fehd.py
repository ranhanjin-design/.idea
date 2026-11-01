"""Download FEHD dog-permitted restaurant full list PDF."""

from __future__ import annotations

import argparse
import gzip
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from pawplan.normalize import normalize_district
from pawplan.sources import FEHD_DISTRICTS, FEHD_LIST

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_URL = (
    "https://www.fehd.gov.hk/english/licensing/dog_restaurants/fulllist.pdf"
)
DIRECTORY_DATA = "https://www.fehd.gov.hk/english/licensing/dog_restaurants/getData.php"


def fetch_fehd_directory(out_dir: Path | None = None) -> Path:
    """Read the same public JSON used by FEHD's searchable HTML directory."""
    out_dir = out_dir or (ROOT / "data" / "raw")
    out_dir.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        try:
            suffix = "?format=json" if attempt == 0 else f"?_={int(time.time())}"
            req = Request(DIRECTORY_DATA + suffix, headers={
                "User-Agent": "Mozilla/5.0 (PawPlanHK academic project)",
                "Accept": "application/json", "Accept-Encoding": "gzip", "Connection": "close",
            })
            with urlopen(req, timeout=30) as response:
                raw = response.read()
                if response.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
            rows = json.loads(raw.decode("utf-8-sig"))
            licences = [str(row["licence"]) for row in rows]
            districts = {normalize_district(row["district_en"]) for row in rows}
            if (not rows or len(set(licences)) != len(licences)
                    or any(not x.isdigit() or len(x) != 10 for x in licences)
                    or districts != set(FEHD_DISTRICTS)):
                raise ValueError("Incomplete or invalid FEHD directory / district coverage")
            path = out_dir / "fehd_dog_restaurants_current.json"
            path.write_text(json.dumps({
                "source_url": FEHD_LIST, "data_url": DIRECTORY_DATA,
                "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
                "count": len(rows), "restaurants": rows,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            return path
        except Exception:
            if attempt == 2:
                raise
    raise RuntimeError("FEHD directory download failed")


def fetch_fehd_pdf(url: str = DEFAULT_URL, out_dir: Path | None = None) -> Path:
    out_dir = out_dir or (ROOT / "data" / "raw")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = out_dir / f"fehd_dog_restaurants_fulllist_{stamp}.pdf"
    latest = out_dir / "fehd_dog_restaurants_fulllist.pdf"

    req = Request(url, headers={"User-Agent": "PawPlanHK/0.1 (academic project)"})
    with urlopen(req, timeout=120) as resp:
        data = resp.read()

    out_path.write_bytes(data)
    latest.write_bytes(data)
    meta = out_dir / "fehd_fetch_meta.txt"
    meta.write_text(
        f"url={url}\nfetched_at_utc={datetime.now(timezone.utc).isoformat()}\n"
        f"bytes={len(data)}\npath={out_path.name}\n",
        encoding="utf-8",
    )
    return latest


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch FEHD dog restaurant PDF")
    parser.add_argument("--url", default=DEFAULT_URL)
    args = parser.parse_args()
    path = fetch_fehd_pdf(args.url)
    print(f"Saved {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
