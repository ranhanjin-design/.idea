"""Run full FEHD -> staging -> curated DB pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path

from pawplan.ingestion.build_db import build_from_enriched
from pawplan.ingestion.enrich_cuisine import enrich_restaurants
from pawplan.ingestion.fetch_fehd import fetch_fehd_pdf
from pawplan.ingestion.parse_fehd_pdf import parse_fehd_pdf

ROOT = Path(__file__).resolve().parents[2]


def run_pipeline(skip_fetch: bool = False) -> None:
    pdf = ROOT / "data" / "raw" / "fehd_dog_restaurants_fulllist.pdf"
    if not skip_fetch or not pdf.exists():
        pdf = fetch_fehd_pdf()
        print(f"[1/4] fetched {pdf}")
    else:
        print(f"[1/4] using existing {pdf}")

    staging = parse_fehd_pdf(pdf)
    print(f"[2/4] parsed -> {staging}")

    enriched = enrich_restaurants(staging)
    print(f"[3/4] enriched -> {enriched}")

    n = build_from_enriched(enriched, replace=True)
    print(f"[4/4] imported {n} restaurants")


def main() -> None:
    parser = argparse.ArgumentParser(description="FEHD ingestion pipeline")
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Reuse existing local PDF if present",
    )
    args = parser.parse_args()
    run_pipeline(skip_fetch=args.skip_fetch)


if __name__ == "__main__":
    main()
