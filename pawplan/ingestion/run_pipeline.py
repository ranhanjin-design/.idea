"""Run FEHD -> staging -> second cuisine source -> enrich -> curated DB."""

from __future__ import annotations

import argparse
from pathlib import Path

from pawplan.ingestion.build_db import build_from_enriched
from pawplan.ingestion.enrich_cuisine import apply_second_source_to_db, enrich_restaurants
from pawplan.ingestion.fetch_cuisine_osm import refresh_second_source
from pawplan.ingestion.fetch_fehd import fetch_fehd_pdf
from pawplan.ingestion.fetch_gopaw import refresh_gopaw_second_source
from pawplan.ingestion.parse_fehd_pdf import parse_fehd_pdf

ROOT = Path(__file__).resolve().parents[2]


def run_pipeline(skip_fetch: bool = False) -> None:
    pdf = ROOT / "data" / "raw" / "fehd_dog_restaurants_fulllist.pdf"
    if not skip_fetch or not pdf.exists():
        pdf = fetch_fehd_pdf()
        print(f"[1/6] fetched {pdf}")
    else:
        print(f"[1/6] using existing {pdf}")

    staging = parse_fehd_pdf(pdf)
    print(f"[2/6] parsed -> {staging}")

    try:
        osm_stats = refresh_second_source(staging, skip_fetch=skip_fetch)
        print(
            "[3/6] OSM second source: "
            f"osm={osm_stats.get('osm_records', 0)} "
            f"auto={osm_stats.get('auto_merged', 0)} "
            f"review={osm_stats.get('review_queue', 0)}"
        )
    except Exception as exc:
        print(f"[3/6] OSM second source skipped ({exc})")

    try:
        gopaw_stats = refresh_gopaw_second_source(staging, skip_fetch=skip_fetch)
        print(
            "[4/6] GoPaw second source: "
            f"restaurants={gopaw_stats.get('gopaw_restaurants', 0)} "
            f"auto={gopaw_stats.get('auto_merged', 0)} "
            f"review={gopaw_stats.get('review_queue', 0)}"
        )
    except Exception as exc:
        print(f"[4/6] GoPaw second source skipped ({exc})")

    enriched = enrich_restaurants(staging)
    print(f"[5/6] enriched -> {enriched}")

    n = build_from_enriched(enriched, replace=True)
    patched = apply_second_source_to_db()
    print(f"[6/6] imported {n} restaurants; second-source patches={patched}")


def main() -> None:
    parser = argparse.ArgumentParser(description="FEHD ingestion pipeline")
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Reuse existing local FEHD PDF and OSM raw file if present",
    )
    args = parser.parse_args()
    run_pipeline(skip_fetch=args.skip_fetch)


if __name__ == "__main__":
    main()
