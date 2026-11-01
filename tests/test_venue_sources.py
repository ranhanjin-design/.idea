"""Government-first venue provenance, branch matching and public API regression."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from pawplan.api.main import app
from pawplan.database.db import ROOT, SCHEMA_SQL, get_connection
from pawplan.ingestion.refresh_venue_sources import MANIFEST, _provider_match, match_vet, parse_vet_pdf
from pawplan.ingestion.parse_fehd_pdf import parse_fehd_pdf
from pawplan.sources import AFCD_VETS, FEHD_DISTRICTS, apply_source_metadata, restaurant_source_url, source_identity
from pawplan.tools.search_places import search_places
from pawplan.tools.search_restaurants import search_restaurants
from pawplan.web.chat_markdown import format_chat_markdown


class VenueMatchingTests(unittest.TestCase):
    def setUp(self):
        self.place = {"place_id": "test", "name_en": "Example Veterinary Hospital", "name_zh": "測試動物醫院",
                      "district": "Sha Tin", "address": "1 Test Road", "phone": "+852 2345 6789", "source_name": "GoPaw"}
        self.clinic = {"name": "測試動物醫院 Example Veterinary Hospital", "districts": ["Sha Tin"],
                       "phones": ["23456789"], "address": "1 Test Road", "page": 1}

    def test_clinic_match_requires_name_phone_and_same_district(self):
        self.assertEqual(match_vet(self.place, [self.clinic]), self.clinic)
        self.assertIsNone(match_vet({**self.place, "district": "Eastern"}, [self.clinic]))
        self.assertIsNone(match_vet({**self.place, "phone": "2123 4567"}, [self.clinic]))
        self.assertIsNone(match_vet({**self.place, "name_en": "Another Hospital", "name_zh": "另一獸醫中心"}, [self.clinic]))

    def test_ambiguous_clinic_branch_is_not_promoted_to_government(self):
        self.assertIsNone(match_vet(self.place, [self.clinic, {**self.clinic, "page": 2}]))

    def test_moved_clinic_with_same_phone_is_not_confirmed_at_the_old_address(self):
        self.assertIsNone(match_vet({**self.place, "address": "99 Different Road"}, [self.clinic]))

    def test_wrapped_pdf_rows_keep_their_own_address_and_phone(self):
        rows = parse_vet_pdf(ROOT / "data/raw/afcd_vet_clinics.pdf")
        clinic = next(r for r in rows if "Happy Paws Veterinary Clinic" in r["name"])
        self.assertIn("149-155", clinic["address"])
        self.assertEqual(clinic["phones"], ["26532287"])
        self.assertNotIn("5 Chui Wo Lane", clinic["address"])

    def test_shared_provider_homepage_needs_branch_phone(self):
        html = "<h1>Example Veterinary Hospital 測試動物醫院</h1>"
        self.assertFalse(_provider_match(self.place, html, shared_domain=True))
        self.assertTrue(_provider_match(self.place, html + "Call +852 2345 6789", shared_domain=True))

    def test_changed_address_cannot_inherit_a_previous_government_match(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA_SQL)
        metadata = {"source_url": AFCD_VETS, "source_name": "AFCD", "evidence_tier": 1}
        conn.execute("INSERT INTO venue_sources VALUES (?,?,?,?)", (
            "place", "test", source_identity(self.place), json.dumps(metadata)))
        try:
            matched = apply_source_metadata(conn, "place", [self.place])[0]
            self.assertEqual(matched["source_name"], "AFCD")
            changed = apply_source_metadata(conn, "place", [{**self.place, "address": "99 Another Road"}])[0]
            self.assertEqual(changed["source_status"], "unverified")
            self.assertNotEqual(changed["evidence_tier"], 1)
        finally:
            conn.close()


class VenueSourceIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.feeding = json.loads((ROOT / "data/raw/fehd_dog_restaurants_current.json").read_text(encoding="utf-8"))
        cls.entries = {(e["entity_type"], e["entity_id"]): e for e in cls.report["entries"]}
        cls.client = TestClient(app)

    def test_active_restaurants_exactly_match_current_fehd_licences(self):
        conn = get_connection()
        try:
            active = [dict(r) for r in conn.execute("SELECT * FROM restaurants WHERE dog_permission=1")]
        finally:
            conn.close()
        self.assertEqual({r["licence_no"] for r in active}, {r["licence"] for r in self.feeding["restaurants"]})
        self.assertEqual({r["district"] for r in active}, set(FEHD_DISTRICTS))
        for row in active:
            self.assertEqual(row["source_url"], restaurant_source_url(row["district"]))

    def test_rebuild_uses_official_web_snapshot_and_keeps_district_links(self):
        with tempfile.TemporaryDirectory(prefix=".test_venue_sources_", dir=ROOT) as tmp:
            out = parse_fehd_pdf(Path(tmp) / "unused.pdf", Path(tmp) / "restaurants.json")
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["count"], self.feeding["count"])
            for row in payload["restaurants"]:
                self.assertEqual(row["source_url"], restaurant_source_url(row["district"]))

    def test_unlisted_restaurants_are_retained_but_not_recommended(self):
        conn = get_connection()
        try:
            for old in self.report["unlisted_restaurants"]:
                result = conn.execute("SELECT dog_permission FROM restaurants WHERE restaurant_id=?", (old["restaurant_id"],)).fetchone()
                self.assertIsNotNone(result)
                self.assertEqual(result[0], 0)
        finally:
            conn.close()

    def test_all_places_have_identity_bound_source_records(self):
        conn = get_connection()
        try:
            rows = conn.execute("SELECT * FROM places").fetchall()
        finally:
            conn.close()
        self.assertEqual(len(rows), self.report["place_count"])
        for row in rows:
            with self.subTest(place=row["place_id"]):
                entry = self.entries["place", row["place_id"]]
                self.assertEqual(entry["identity_key"], source_identity(dict(row)))
                metadata = entry["metadata"]
                if metadata["source_status"] == "verified":
                    self.assertNotIn("venues#id=", metadata["source_url"])
                    self.assertNotIn("?page=1#", metadata["source_url"])
                    self.assertFalse(urlsplit(metadata["source_url"]).path.endswith(".pdf"))

    def test_official_medical_evidence_is_limited_to_clinic_identity(self):
        matches = [e for e in self.report["entries"] if e["metadata"]["source_name"] == "AFCD"]
        self.assertGreater(len(matches), 0)
        for entry in matches:
            source = entry["metadata"]
            self.assertEqual(source["source_scope"], "clinic_identity_and_address")
            self.assertEqual(source["source_url"], AFCD_VETS)
            self.assertIn("未确认急诊", source["source_note"])
            self.assertIn("#page=", source["source_record_url"])

    def test_groomers_are_not_promoted_using_an_afcd_pet_shop_licence(self):
        conn = get_connection()
        try:
            ids = [r[0] for r in conn.execute("SELECT place_id FROM places WHERE place_type='groomer'")]
        finally:
            conn.close()
        for pid in ids:
            metadata = self.entries["place", pid]["metadata"]
            self.assertNotEqual(metadata["source_name"], "AFCD")
            if metadata["source_name"] == "petcircle":
                self.assertRegex(metadata["source_url"], r"^https://petcircle-hk\.vercel\.app/businesses/grm-\d+$")

    def test_all_fehd_district_queries_return_their_actual_html_filter(self):
        for district, code in FEHD_DISTRICTS.items():
            with self.subTest(district=district):
                result = self.client.post("/api/search", json={"district": district, "limit": 5})
                self.assertEqual(result.status_code, 200)
                rows = result.json()["restaurants"]
                self.assertGreater(len(rows), 0)
                for row in rows:
                    self.assertEqual(parse_qs(urlsplit(row["source_url"]).query), {"districtID": [code]})
                    self.assertEqual(row["source_name"], "FEHD")
                    self.assertTrue(row["licence_no"])

    def test_place_queries_prefer_verified_government_or_provider_sources(self):
        conn = get_connection()
        try:
            districts = [r[0] for r in conn.execute("SELECT DISTINCT district FROM places")]
        finally:
            conn.close()
        for district in districts:
            for kind in ("clinic", "groomer", "mall"):
                with self.subTest(district=district, kind=kind):
                    result = search_places(district, kind)
                    tiers = [r["evidence_tier"] for r in result["places"]]
                    self.assertEqual(tiers, sorted(tiers))
                    for row in result["places"]:
                        expected = self.entries["place", row["place_id"]]["metadata"]
                        self.assertEqual(row["source_url"], expected["source_url"])
                        self.assertNotEqual(row.get("source_status"), "unverified")

    def test_browse_and_map_return_the_same_sources_as_search(self):
        for category, kind in [("restaurants", None), ("vets", "clinic"), ("groomers", "groomer"), ("malls", "mall")]:
            with self.subTest(category=category):
                search = search_restaurants("Sha Tin") if kind is None else search_places("Sha Tin", kind)
                expected = {r.get("restaurant_id") or r.get("place_id"): r["source_url"] for r in search["restaurants" if kind is None else "places"]}
                browse = self.client.get("/api/explore/browse", params={"category": category, "district": "Sha Tin", "limit": 5})
                points = self.client.get("/api/explore/map", params={"category": category, "district": "Sha Tin", "limit": 5})
                self.assertEqual(browse.status_code, 200)
                self.assertEqual(points.status_code, 200)
                for row in browse.json()["items"] + points.json()["points"]:
                    self.assertEqual(row["source_url"], expected[row["id"]])

    def test_chat_includes_clickable_official_and_branch_sources(self):
        with patch.dict(os.environ, {"PAWPLAN_FORCE_DEV": "1"}):
            for question, expected in [
                ("沙田有没有获准让狗进入的食肆？", restaurant_source_url("Sha Tin")),
                ("沙田有哪些宠物诊所？", AFCD_VETS),
                ("沙田有哪些宠物美容？", "/businesses/grm-"),
            ]:
                result = self.client.post("/api/chat", json={"message": question})
                self.assertEqual(result.status_code, 200)
                reply = result.json()["reply"]
                self.assertIn(expected, reply)
                self.assertIn('<a href="', format_chat_markdown(reply))


if __name__ == "__main__":
    unittest.main()
