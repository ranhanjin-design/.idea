"""Data quality suite for PawPlan curated database (data track)."""

from __future__ import annotations

import json
import sqlite3
import unittest
from pathlib import Path

from pawplan.database.db import ROOT, get_connection, get_db_path, init_database
from pawplan.normalize import CANONICAL_DISTRICTS, normalize_district

KNOWN_DISTRICTS = set(CANONICAL_DISTRICTS) | {"Mong Kok", "Yau Tsim Mong", "Central/Western"}


class DataQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_database()
        cls.db_path = get_db_path()
        if not cls.db_path.exists():
            raise unittest.SkipTest("database missing")

    def _conn(self) -> sqlite3.Connection:
        return get_connection()

    # --- presence / volume ---

    def test_restaurants_minimum_volume(self):
        conn = self._conn()
        n = conn.execute("SELECT COUNT(*) FROM restaurants").fetchone()[0]
        conn.close()
        self.assertGreaterEqual(n, 50, "expected FEHD ingest or demo seed")

    def test_parks_minimum_volume(self):
        conn = self._conn()
        n = conn.execute("SELECT COUNT(*) FROM parks").fetchone()[0]
        conn.close()
        self.assertGreaterEqual(n, 50, "run parks pipeline first")

    def test_knowledge_docs_exist(self):
        path = ROOT / "data" / "knowledge" / "midterm_docs.json"
        self.assertTrue(path.exists())
        docs = json.loads(path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(docs), 5)
        for doc in docs:
            for key in (
                "doc_id",
                "content_zh",
                "source_url",
                "last_verified_at",
                "confidence",
            ):
                self.assertIn(key, doc)
                self.assertTrue(doc[key] not in (None, ""), msg=f"{doc.get('doc_id')} missing {key}")

    # --- required provenance fields ---

    def test_restaurants_have_source_and_verified(self):
        conn = self._conn()
        bad = conn.execute(
            """
            SELECT COUNT(*) FROM restaurants
            WHERE source_url IS NULL OR TRIM(source_url) = ''
               OR last_verified_at IS NULL OR TRIM(last_verified_at) = ''
            """
        ).fetchone()[0]
        conn.close()
        self.assertEqual(bad, 0)

    def test_parks_have_source_and_verified(self):
        conn = self._conn()
        bad = conn.execute(
            """
            SELECT COUNT(*) FROM parks
            WHERE source_url IS NULL OR TRIM(source_url) = ''
               OR last_verified_at IS NULL OR TRIM(last_verified_at) = ''
            """
        ).fetchone()[0]
        conn.close()
        self.assertEqual(bad, 0)

    def test_cuisine_overlay_table_present(self):
        """Cuisine overlay is optional for permission search but used for cuisine filter."""
        conn = self._conn()
        restaurants = conn.execute("SELECT COUNT(*) FROM restaurants").fetchone()[0]
        cuisines = conn.execute("SELECT COUNT(*) FROM restaurant_cuisines").fetchone()[0]
        conn.close()
        self.assertGreater(restaurants, 0)
        self.assertGreaterEqual(cuisines, 0)

    # --- keys / uniqueness ---

    def test_restaurant_ids_unique(self):
        conn = self._conn()
        dup = conn.execute(
            """
            SELECT restaurant_id, COUNT(*) c FROM restaurants
            GROUP BY restaurant_id HAVING c > 1
            """
        ).fetchall()
        conn.close()
        self.assertEqual(dup, [])

    def test_park_ids_unique(self):
        conn = self._conn()
        dup = conn.execute(
            """
            SELECT park_id, COUNT(*) c FROM parks
            GROUP BY park_id HAVING c > 1
            """
        ).fetchall()
        conn.close()
        self.assertEqual(dup, [])

    def test_licence_unique_when_present(self):
        conn = self._conn()
        dup = conn.execute(
            """
            SELECT licence_no, COUNT(*) c FROM restaurants
            WHERE licence_no IS NOT NULL AND TRIM(licence_no) != ''
            GROUP BY licence_no HAVING c > 1
            """
        ).fetchall()
        conn.close()
        self.assertEqual(dup, [])

    # --- district normalization ---

    def test_restaurant_districts_known(self):
        conn = self._conn()
        districts = [
            r[0]
            for r in conn.execute("SELECT DISTINCT district FROM restaurants").fetchall()
        ]
        conn.close()
        unknown = []
        for d in districts:
            norm = normalize_district(d)
            if norm not in KNOWN_DISTRICTS and d not in KNOWN_DISTRICTS:
                unknown.append(d)
        self.assertEqual(unknown, [], f"unknown districts: {unknown}")

    def test_park_districts_mostly_known(self):
        conn = self._conn()
        districts = [
            r[0] for r in conn.execute("SELECT DISTINCT district FROM parks").fetchall()
        ]
        conn.close()
        unknown = [
            d
            for d in districts
            if d != "Unknown"
            and normalize_district(d) not in KNOWN_DISTRICTS
            and d not in KNOWN_DISTRICTS
        ]
        # allow a small residue from PDF parse quirks
        self.assertLessEqual(len(unknown), 3, f"unexpected districts: {unknown}")

    # --- coordinates quality ---

    def test_coordinates_in_hong_kong_bbox_when_present(self):
        """HK rough bbox: lat 22.1–22.6, lon 113.8–114.5"""
        conn = self._conn()
        bad_r = conn.execute(
            """
            SELECT COUNT(*) FROM restaurants
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
              AND (
                latitude < 22.1 OR latitude > 22.6
                OR longitude < 113.8 OR longitude > 114.5
              )
            """
        ).fetchone()[0]
        bad_p = conn.execute(
            """
            SELECT COUNT(*) FROM parks
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
              AND (
                latitude < 22.1 OR latitude > 22.6
                OR longitude < 113.8 OR longitude > 114.5
              )
            """
        ).fetchone()[0]
        conn.close()
        self.assertEqual(bad_r, 0)
        self.assertEqual(bad_p, 0)

    def test_pet_garden_coordinate_coverage_high(self):
        conn = self._conn()
        total = conn.execute(
            "SELECT COUNT(*) FROM parks WHERE park_type = 'pet_garden'"
        ).fetchone()[0]
        if total == 0:
            conn.close()
            self.skipTest("no pet gardens")
        geo = conn.execute(
            """
            SELECT COUNT(*) FROM parks
            WHERE park_type = 'pet_garden'
              AND latitude IS NOT NULL AND longitude IS NOT NULL
            """
        ).fetchone()[0]
        conn.close()
        self.assertGreaterEqual(geo / total, 0.9)

    def test_geocode_coverage_high(self):
        """After geocode job: nearly all rows should have coordinates."""
        conn = self._conn()
        r_total = conn.execute("SELECT COUNT(*) FROM restaurants").fetchone()[0]
        r_geo = conn.execute(
            """
            SELECT COUNT(*) FROM restaurants
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
            """
        ).fetchone()[0]
        p_total = conn.execute("SELECT COUNT(*) FROM parks").fetchone()[0]
        p_geo = conn.execute(
            """
            SELECT COUNT(*) FROM parks
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
            """
        ).fetchone()[0]
        conn.close()
        self.assertGreater(r_total, 0)
        self.assertGreater(p_total, 0)
        self.assertGreaterEqual(p_geo / p_total, 0.95)
        self.assertGreaterEqual(r_geo / r_total, 0.95)


if __name__ == "__main__":
    unittest.main()
