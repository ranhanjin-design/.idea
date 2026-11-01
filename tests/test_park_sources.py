"""Offline regression for all-district LCSD sources and authoritative venue matching."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from pawplan.api.main import app
from pawplan.database.db import ROOT, get_connection, init_database
from pawplan.ingestion.build_parks_db import import_parks
from pawplan.ingestion.park_sources import DISTRICT_IDS, ParkPageParser, park_source_url
from pawplan.ingestion.parse_parks import parse_park_pages, parse_pet_gardens_json
from pawplan.web.chat_markdown import format_chat_markdown

SNAPSHOT = ROOT / "data" / "raw" / "lcsd_park_pages.json"


class ParkPageTests(unittest.TestCase):
    def test_parser_preserves_venue_names_map_ids_and_selected_district(self):
        parser = ParkPageParser()
        parser.feed('''<select id="linkList"><option value="1">中西區</option>
            <option value="10" selected>沙田區</option></select>
            <table class="table fac-table"><tr><td>場地名稱</td>
            <td>沙田公園(指定位置)</td></tr><tr><td>地址</td><td>沙田源禾路2號
            <a href="javascript:showPopupStaticMap('testID','tc')">位置圖</a></td></tr>
            <tr><td>設施</td><td><ul><li>狗廁所</li><li>飲水器 &amp; 座椅</li></ul></td></tr></table>''')
        self.assertEqual(parser.selected_district, 10)
        self.assertEqual(parser.district_options[1], "中西區")
        self.assertEqual(parser.venues[0]["場地名稱"], "沙田公園(指定位置)")
        self.assertEqual(parser.venues[0]["map_id"], "testID")
        self.assertIn("狗廁所 飲水器 & 座椅", parser.venues[0]["設施"])

    def test_unknown_district_uses_index_instead_of_a_wrong_district(self):
        self.assertTrue(park_source_url("Unknown", "inclusive_park").endswith("District.do?ftid=165"))

    def test_json_fallback_returns_a_public_page(self):
        parks = parse_pet_gardens_json(ROOT / "data/raw/lcsd_pet_gardens.json", "2026-11-01")
        park = next(p for p in parks if p["district"] == "Sha Tin")
        self.assertEqual(parse_qs(urlsplit(park["source_url"]).query), {"ftid": ["47"], "did": ["10"]})

    def test_partial_snapshot_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix=".test_park_sources_", dir=ROOT) as tmp:
            path = Path(tmp) / "partial.json"
            path.write_text(json.dumps({"pages": []}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "all 18 districts"):
                parse_park_pages(path, [])

    def test_current_pages_control_membership_and_preserve_renamed_venue_id(self):
        seed = parse_pet_gardens_json(ROOT / "data/raw/lcsd_pet_gardens.json", "2026-10-07")
        parks, unlisted = parse_park_pages(SNAPSHOT, seed)
        renamed = next(p for p in parks if p["name_zh"] == "民康街寵物公園")
        self.assertEqual(renamed["park_id"], "lcsd_pg_pW3ZYoEnir")
        self.assertIsNotNone(renamed["latitude"])
        self.assertTrue(any(p["name_zh"] == "山頂花園" and p["park_type"] == "inclusive_park" for p in parks))
        self.assertFalse(any(p["name_zh"] == "海皇路花園" for p in parks))
        self.assertTrue(any(p["name_zh"] == "海皇路花園" for p in unlisted))

    def test_import_preserves_coordinates_and_repairs_legacy_sources(self):
        with tempfile.TemporaryDirectory(prefix=".test_park_sources_", dir=ROOT) as tmp, patch.dict(os.environ, {"PAWPLAN_DB_PATH": str(Path(tmp) / "test.db")}):
            init_database()
            row = {
                "park_id": "test_park", "park_type": "inclusive_park", "district": "Sha Tin",
                "name_en": "Test Park", "name_zh": "測試公園", "address": None,
                "facilities_json": "{}", "opening_hours": None, "phone": None,
                "latitude": 22.38, "longitude": 114.19,
                "source_url": "https://www.lcsd.gov.hk/en/common/pdf/Annex_IPP_Venue.pdf",
                "last_verified_at": "2026-10-07",
            }
            path = Path(tmp) / "parks.json"
            path.write_text(json.dumps({"parks": [row]}), encoding="utf-8")
            import_parks(path)
            row.update(latitude=None, longitude=None)
            path.write_text(json.dumps({"parks": [row]}), encoding="utf-8")
            import_parks(path)
            conn = get_connection()
            try:
                result = conn.execute("SELECT * FROM parks").fetchone()
                self.assertEqual((result["latitude"], result["longitude"]), (22.38, 114.19))
                self.assertEqual(result["last_verified_at"], "2026-10-07")
                self.assertEqual(result["source_url"], park_source_url("Sha Tin", "inclusive_park"))
                self.assertGreater(conn.execute("SELECT COUNT(*) FROM restaurants").fetchone()[0], 0)
            finally:
                conn.close()


class ParkSourceIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        cls.client = TestClient(app)

    def test_snapshot_contains_all_18_districts_and_both_categories(self):
        pages = self.manifest["pages"]
        self.assertEqual(len(pages), 36)
        self.assertEqual({p["district"] for p in pages}, set(DISTRICT_IDS))
        for page in pages:
            with self.subTest(district=page["district"], kind=page["park_type"]):
                self.assertEqual(page["district_id"], DISTRICT_IDS[page["district"]])
                self.assertEqual(len(page["venue_details"]), page["venue_count"])
                self.assertGreater(page["venue_count"], 0)

    def test_every_stored_park_is_on_its_exact_official_source_page(self):
        conn = get_connection()
        try:
            rows = conn.execute("SELECT * FROM parks").fetchall()
        finally:
            conn.close()
        pages = {p["source_url"]: p for p in self.manifest["pages"]}
        self.assertEqual(len(rows), sum(p["venue_count"] for p in pages.values()))
        for row in rows:
            with self.subTest(park=row["name_zh"]):
                page = pages[row["source_url"]]
                self.assertEqual((row["district"], row["park_type"]), (page["district"], page["park_type"]))
                self.assertIn(row["name_zh"], page["venues"])

    def test_park_api_returns_correct_district_and_category_links_for_all_districts(self):
        for page in self.manifest["pages"]:
            with self.subTest(district=page["district"], kind=page["park_type"]):
                res = self.client.post("/api/parks", json={"district": page["district"], "park_type": page["park_type"], "limit": 5})
                self.assertEqual(res.status_code, 200)
                data = res.json()
                self.assertGreater(data["count"], 0)
                for park in data["parks"]:
                    self.assertEqual(park["source_url"], page["source_url"])
                    self.assertIn(park["name_zh"], page["venues"])

    def test_explore_returns_the_same_official_links_for_all_districts(self):
        pages = {p["source_url"]: p for p in self.manifest["pages"]}
        for district in DISTRICT_IDS:
            res = self.client.get("/api/explore/browse", params={"category": "parks", "district": district, "limit": 50})
            self.assertEqual(res.status_code, 200)
            items = res.json()["items"]
            self.assertGreater(len(items), 0)
            for item in items:
                self.assertEqual(pages[item["source_url"]]["district"], district)
                self.assertIn(item["name_zh"], pages[item["source_url"]]["venues"])

    def test_chat_source_is_clickable_and_matches_the_queried_category(self):
        with patch.dict(os.environ, {"PAWPLAN_FORCE_DEV": "1"}):
            for question, kind in [("沙田有哪些狗公园", "pet_garden"), ("沙田有没有宠物共享公园", "inclusive_park")]:
                res = self.client.post("/api/chat", json={"message": question, "history": []})
                self.assertEqual(res.status_code, 200)
                reply = res.json()["reply"]
                url = park_source_url("Sha Tin", kind)
                self.assertIn(url, reply)
                html = format_chat_markdown(reply)
                self.assertIn(url.replace("&", "&amp;"), html)
                self.assertIn("<a href=", html)
                self.assertNotIn("Annex_IPP_Venue.pdf", reply)


if __name__ == "__main__":
    unittest.main()
