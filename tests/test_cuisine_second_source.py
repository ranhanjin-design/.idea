"""Complementary cuisine second source (OSM + human review), not FEHD official."""

from __future__ import annotations

import json
import unittest

from pawplan.database.db import ROOT, get_connection, init_database
from pawplan.ingestion.enrich_cuisine import (
    apply_second_source_to_db,
    is_second_source_url,
)
from pawplan.ingestion.entity_match import classify_match, identity_match, match_score
from pawplan.ingestion.fetch_cuisine_osm import SECOND_SOURCE_PATH, load_second_source
from pawplan.tools.search_restaurants import search_restaurants


class EntityMatchTests(unittest.TestCase):
    def test_score_formula_auto_merges_identical_rows(self):
        row = {
            "name_en": "ALDA BOLL JAPANESE RESTAURANT",
            "name_zh": "火蓮花日本餐廳",
            "address": "1 YUEN HONG STREET, SHA TIN",
            "district": "Sha Tin",
        }
        score = match_score(row, row)
        self.assertGreaterEqual(score, 0.90)
        self.assertEqual(classify_match(score), "auto_merge")

    def test_identity_match_requires_same_district(self):
        left = {
            "match_name_en": "%ARABICA",
            "match_name_zh": "%ARABICA",
            "district": "Central/Western",
        }
        right = {
            "name_en": "%ARABICA",
            "name_zh": "%ARABICA",
            "district": "Central/Western",
        }
        other = dict(right, district="Kowloon City")
        self.assertTrue(identity_match(left, right))
        self.assertFalse(identity_match(left, other))


class CuisineSecondSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_database()
        cls.apply_stats = apply_second_source_to_db()

    def test_second_source_json_exists_and_has_entries(self):
        self.assertTrue(SECOND_SOURCE_PATH.exists())
        payload = load_second_source()
        self.assertTrue(payload.get("source_name"))
        self.assertTrue(payload.get("last_verified_at"))
        self.assertTrue(payload.get("terms"))
        entries = payload.get("entries") or []
        self.assertGreaterEqual(len(entries), 6)
        required = {
            "match_name_en",
            "match_name_zh",
            "district",
            "cuisine_code",
            "cuisine_source_url",
            "cuisine_confidence",
            "method",
            "last_verified_at",
        }
        methods = set()
        for entry in entries:
            self.assertTrue(required.issubset(entry.keys()), msg=entry)
            self.assertIn(entry["method"], {"osm", "human_review"})
            methods.add(entry["method"])
        self.assertIn("human_review", methods)

    def test_apply_matches_at_least_one_restaurant(self):
        self.assertGreaterEqual(self.apply_stats.get("auto_merged", 0), 1)
        conn = get_connection()
        try:
            n = conn.execute(
                """
                SELECT COUNT(*) FROM restaurant_cuisines
                WHERE cuisine_source_url LIKE 'human_review://%'
                   OR LOWER(cuisine_source_url) LIKE '%openstreetmap.org%'
                """
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertGreaterEqual(n, 1)

    def test_sha_tin_dim_sum_and_japanese_use_second_source_url(self):
        dim_sum = search_restaurants("Sha Tin", cuisine="dim_sum")
        japanese = search_restaurants("Sha Tin", cuisine="japanese")
        self.assertGreater(dim_sum["count"], 0)
        self.assertGreater(japanese["count"], 0)
        self.assertTrue(dim_sum["cuisine_confirmed"])
        self.assertTrue(japanese["cuisine_confirmed"])
        for result in (dim_sum, japanese):
            for row in result["restaurants"]:
                self.assertTrue(is_second_source_url(row["cuisine_source_url"]))
                self.assertGreaterEqual(row["cuisine_confidence"], 0.7)
                self.assertNotIn("heuristic://", (row["cuisine_source_url"] or "").lower())

    def test_heuristic_only_must_not_be_cuisine_confirmed(self):
        self.assertFalse(is_second_source_url("heuristic://pawplan/name_keywords"))
        self.assertFalse(is_second_source_url("curated://pawplan/cuisine_overlay"))
        self.assertTrue(is_second_source_url("https://www.openstreetmap.org/node/1"))
        self.assertTrue(is_second_source_url("human_review://pawplan/fehd-name-check"))

        conn = get_connection()
        try:
            high_heuristic = conn.execute(
                """
                SELECT COUNT(*) FROM restaurant_cuisines
                WHERE cuisine_confidence >= 0.7
                  AND (
                    cuisine_source_url LIKE 'heuristic://%'
                    OR cuisine_source_url = 'curated://pawplan/cuisine_overlay'
                  )
                """
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(high_heuristic, 0)

        # A cuisine that only exists as a name guess must not come back confirmed.
        heuristic_only = search_restaurants("Sha Tin", cuisine="spanish")
        if heuristic_only["count"] == 0:
            self.assertFalse(heuristic_only["cuisine_confirmed"])
        else:
            for row in heuristic_only["restaurants"]:
                self.assertTrue(is_second_source_url(row["cuisine_source_url"]))

    def test_knowledge_file_is_valid_json(self):
        path = ROOT / "data" / "knowledge" / "cuisine_second_source.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIsInstance(data.get("entries"), list)


if __name__ == "__main__":
    unittest.main()
