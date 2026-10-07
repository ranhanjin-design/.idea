"""Fetch LCSD pet garden JSON and Inclusive Park for Pets PDF."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]

PET_GARDEN_JSON = "https://www.lcsd.gov.hk/datagovhk/facility/facility-dgpg.json"
IPP_PDF = "https://www.lcsd.gov.hk/en/common/pdf/Annex_IPP_Venue.pdf"


def _download(url: str, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    req = Request(url, headers={"User-Agent": "PawPlanHK/0.1 (academic project)"})
    with urlopen(req, timeout=120) as resp:
        data = resp.read()
    out_path.write_bytes(data)
    return out_path


def fetch_park_sources(out_dir: Path | None = None) -> dict[str, Path]:
    out_dir = out_dir or (ROOT / "data" / "raw")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    paths = {
        "pet_gardens_json": _download(
            PET_GARDEN_JSON, out_dir / "lcsd_pet_gardens.json"
        ),
        "ipp_pdf": _download(IPP_PDF, out_dir / "lcsd_ipp_venue.pdf"),
    }
    # dated copies
    (out_dir / f"lcsd_pet_gardens_{stamp}.json").write_bytes(
        paths["pet_gardens_json"].read_bytes()
    )
    (out_dir / f"lcsd_ipp_venue_{stamp}.pdf").write_bytes(paths["ipp_pdf"].read_bytes())
    meta = out_dir / "lcsd_parks_fetch_meta.txt"
    meta.write_text(
        f"fetched_at_utc={datetime.now(timezone.utc).isoformat()}\n"
        f"pet_gardens={PET_GARDEN_JSON}\n"
        f"ipp={IPP_PDF}\n",
        encoding="utf-8",
    )
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch LCSD park source files")
    parser.parse_args()
    paths = fetch_park_sources()
    for key, path in paths.items():
        print(f"{key}: {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
