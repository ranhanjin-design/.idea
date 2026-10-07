"""Download FEHD dog-permitted restaurant full list PDF."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_URL = (
    "https://www.fehd.gov.hk/english/licensing/dog_restaurants/fulllist.pdf"
)


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
