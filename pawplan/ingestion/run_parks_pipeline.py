"""Run LCSD parks ingestion pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path

from pawplan.ingestion.build_parks_db import import_parks
from pawplan.ingestion.fetch_parks import fetch_park_sources
from pawplan.ingestion.parse_parks import parse_all_parks

ROOT = Path(__file__).resolve().parents[2]


def run_parks_pipeline(skip_fetch: bool = False) -> None:
    json_path = ROOT / "data" / "raw" / "lcsd_pet_gardens.json"
    pdf_path = ROOT / "data" / "raw" / "lcsd_ipp_venue.pdf"
    if not skip_fetch or not json_path.exists() or not pdf_path.exists():
        paths = fetch_park_sources()
        print(f"[1/3] fetched {paths}")
    else:
        print("[1/3] using existing raw park files")

    staging = parse_all_parks()
    print(f"[2/3] parsed -> {staging}")
    n = import_parks(staging, replace=True)
    print(f"[3/3] imported {n} parks")


def main() -> None:
    parser = argparse.ArgumentParser(description="LCSD parks pipeline")
    parser.add_argument("--skip-fetch", action="store_true")
    args = parser.parse_args()
    run_parks_pipeline(skip_fetch=args.skip_fetch)


if __name__ == "__main__":
    main()
