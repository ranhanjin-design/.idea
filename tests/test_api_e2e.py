"""End-to-end API tests for midterm endpoints (offline, no paid model)."""

from __future__ import annotations

import os
import unittest

from fastapi.testclient import TestClient

# Force offline agent path before app import side effects in tests.
os.environ["PAWPLAN_FORCE_DEV"] = "1"

from pawplan.api.main import app  # noqa: E402
from pawplan.database.db import init_database  # noqa: E402


class ApiE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["PAWPLAN_FORCE_DEV"] = "1"
        init_database()
        cls.client = TestClient(app)

    def test_health_ok(self):
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("database", data)
        self.assertIn("restaurants", data["database"])
        self.assertIn("parks", data["database"])
        self.assertIn("capabilities", data)
        self.assertTrue(data["capabilities"]["knowledge_qa"])
        self.assertTrue(data["capabilities"]["restaurant_permission_search"])
        self.assertTrue(data["capabilities"]["cuisine_filter"])
        self.assertFalse(data["capabilities"]["cuisine_recommendation"])

    def test_knowledge_endpoint(self):
        res = self.client.post(
            "/api/knowledge",
            json={"query": "带狗散步怎样防中暑", "limit": 3},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("count", data)
        self.assertIn("documents", data)
        self.assertGreater(data["count"], 0)
        doc = data["documents"][0]
        for key in ("source_name", "source_url", "last_verified_at", "title_zh"):
            self.assertIn(key, doc)
            self.assertTrue(doc[key])

    def test_parks_endpoint(self):
        res = self.client.post(
            "/api/parks",
            json={"district": "Sha Tin", "limit": 3},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreater(data["count"], 0)
        park = data["parks"][0]
        for key in ("name_en", "district", "source_url", "last_verified_at"):
            self.assertIn(key, park)
        self.assertEqual(park["district"], "Sha Tin")
        self.assertNotIn("cuisine", data.get("query", {}))

    def test_search_restaurants_endpoint(self):
        res = self.client.post(
            "/api/search",
            json={"district": "Sha Tin", "limit": 3},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreater(data["count"], 0)
        row = data["restaurants"][0]
        for key in ("district", "source_url", "last_verified_at"):
            self.assertIn(key, row)
        self.assertTrue(row.get("name_en") or row.get("name_zh"))
        self.assertEqual(data["query"]["district"], "Sha Tin")
        self.assertNotIn("cuisine", data["query"])

    def test_search_restaurants_cuisine_filter(self):
        res = self.client.post(
            "/api/search",
            json={"district": "Sha Tin", "cuisine": "dim_sum", "limit": 3},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["query"]["district"], "Sha Tin")
        self.assertEqual(data["query"]["cuisine"], "dim_sum")
        self.assertTrue(data["cuisine_filter_applied"])
        for row in data["restaurants"]:
            self.assertEqual(row["cuisine_code"], "dim_sum")
        if data["count"] == 0:
            self.assertFalse(data["cuisine_confirmed"])
        else:
            self.assertTrue(data["cuisine_confirmed"])

    def test_chat_knowledge(self):
        res = self.client.post(
            "/api/chat",
            json={"message": "带狗散步时，怎样降低中暑风险？"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("reply", data)
        self.assertIn("mode", data)
        self.assertIn("tool_trace", data)
        self.assertEqual(data["mode"], "dev")
        self.assertTrue(data["tool_trace"])
        self.assertEqual(data["tool_trace"][0]["tool"], "search_knowledge")
        self.assertIn("result_count", data["tool_trace"][0])
        self.assertIn("来源", data["reply"])

    def test_chat_out_of_scope_no_tools(self):
        res = self.client.post(
            "/api/chat",
            json={"message": "帮我预测明天股票"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["tool_trace"], [])
        self.assertIn("范围", data["reply"])

    def test_chat_restaurant_place(self):
        res = self.client.post(
            "/api/chat",
            json={"message": "沙田有没有获准让狗进入的食肆？"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["tool_trace"][0]["tool"], "search_restaurants")
        self.assertEqual(data["tool_trace"][0]["arguments"]["district"], "Sha Tin")
        self.assertNotIn("cuisine", data["tool_trace"][0]["arguments"])
        self.assertIn("核实日期", data["reply"])

    def test_chat_park_place(self):
        res = self.client.post(
            "/api/chat",
            json={"message": "沙田有没有宠物公园？"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["tool_trace"][0]["tool"], "search_parks")
        self.assertIn("来源", data["reply"])


if __name__ == "__main__":
    unittest.main()
