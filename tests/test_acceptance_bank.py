"""Midterm acceptance question bank (>=15 cases) with behavior assertions.

Runs offline via run_dev_fallback / local tools. No network, no paid model.
"""

from __future__ import annotations

import unittest

from pawplan.agent.dev_fallback import run_dev_fallback
from pawplan.database.db import init_database
from pawplan.tools.search_knowledge import search_knowledge
from pawplan.tools.search_parks import search_parks
from pawplan.tools.search_places import search_places
from pawplan.tools.search_restaurants import search_restaurants


class MidtermAcceptanceBank(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_database()

    def _chat(self, question: str):
        return run_dev_fallback(question)

    # --- 1–4 knowledge Q&A ---

    def test_01_heatstroke_knowledge_with_source(self):
        reply, trace = self._chat("带狗散步时，怎样降低中暑风险？")
        self.assertEqual(trace[0]["tool"], "search_knowledge")
        self.assertIn("query", trace[0]["arguments"])
        self.assertGreater(trace[0]["result_count"], 0)
        self.assertIn("来源", reply)
        self.assertIn("核实日期", reply)
        self.assertRegex(reply, r"https?://")

    def test_02_beach_rule_knowledge(self):
        reply, trace = self._chat("我可以带狗进入公众泳滩吗？")
        self.assertEqual(trace[0]["tool"], "search_knowledge")
        self.assertIn("来源", reply)
        self.assertTrue("泳滩" in reply or "海滩" in reply or "沙滩" in reply)

    def test_03_dining_policy_knowledge(self):
        reply, trace = self._chat("进入获准食肆后需要遵守哪些规则？")
        self.assertEqual(trace[0]["tool"], "search_knowledge")
        self.assertIn("核实日期", reply)
        self.assertTrue("获准" in reply or "FEHD" in reply or "食环" in reply)

    def test_04_hydration_knowledge(self):
        reply, trace = self._chat("外出时狗狗怎么补水？")
        self.assertEqual(trace[0]["tool"], "search_knowledge")
        self.assertIn("来源", reply)

    # --- 5–7 domain filter: no tools ---

    def test_05_stock_out_of_scope_no_tools(self):
        reply, trace = self._chat("可以总结一下今天的股票市场吗？")
        self.assertEqual(trace, [])
        self.assertIn("范围", reply)

    def test_06_homework_out_of_scope_no_tools(self):
        reply, trace = self._chat("帮我写数据库作业答案")
        self.assertEqual(trace, [])
        self.assertTrue("范围" in reply or "宠物" in reply)

    def test_07_news_out_of_scope_no_tools(self):
        reply, trace = self._chat("今天有什么国际新闻？")
        self.assertEqual(trace, [])
        self.assertIn("范围", reply)

    # --- 8–11 restaurant permission search ---

    def test_08_sha_tin_restaurants(self):
        reply, trace = self._chat("沙田有没有获准让狗进入的食肆？")
        self.assertEqual(trace[0]["tool"], "search_restaurants")
        self.assertEqual(trace[0]["arguments"]["district"], "Sha Tin")
        self.assertNotIn("cuisine", trace[0]["arguments"])
        self.assertGreater(trace[0]["result_count"], 0)
        self.assertIn("地区", reply)
        self.assertIn("来源", reply)
        self.assertIn("核实日期", reply)
        self.assertIn("fehd.gov.hk", reply.lower())

    def test_09_mong_kok_restaurants(self):
        reply, trace = self._chat("找一家旺角获准让狗进入的食肆")
        self.assertEqual(trace[0]["tool"], "search_restaurants")
        self.assertIn(trace[0]["arguments"]["district"], {"Mong Kok", "Yau Tsim Mong"})
        self.assertGreater(trace[0]["result_count"], 0)
        self.assertIn("核实日期", reply)

    def test_10_restaurant_tool_matches_db(self):
        result = search_restaurants("Sha Tin", limit=3)
        self.assertGreater(result["count"], 0)
        for row in result["restaurants"]:
            self.assertTrue(row.get("name_en") or row.get("name_zh"))
            self.assertEqual(row["district"], "Sha Tin")
            self.assertTrue(row["source_url"])
            self.assertTrue(row["last_verified_at"])
            self.assertNotIn("cuisine_code", row)

    def test_11_cuisine_request_does_not_recommend_unmatched(self):
        reply, trace = self._chat("我需要找一间沙田附近的宠物友好点心店。")
        self.assertEqual(trace[0]["tool"], "search_restaurants")
        self.assertEqual(trace[0]["arguments"]["district"], "Sha Tin")
        self.assertEqual(trace[0]["arguments"].get("cuisine"), "dim_sum")
        self.assertTrue("无法确认" in reply or "非正式官方" in reply)
        self.assertTrue("愿意" in reply or "改查" in reply)
        self.assertNotIn("获准食肆示例", reply)
        self.assertNotIn("以下是点心店", reply)
        filtered = search_restaurants("Sha Tin", cuisine="dim_sum")
        if filtered["count"] == 0:
            self.assertEqual(trace[0]["result_count"], 0)
            self.assertNotIn("找到", reply)
        else:
            self.assertGreater(trace[0]["result_count"], 0)
            self.assertIn("来源", reply)
            for row in filtered["restaurants"]:
                self.assertEqual(row["cuisine_code"], "dim_sum")

    def test_11b_find_dim_sum_near_sha_tin_wording(self):
        """Explicit food-shop type: filter if confirmed, else ask; never dump unmatched."""
        from pawplan.web.chat_markdown import format_chat_markdown

        q = "找一家沙田附近的点心店"
        reply, trace = self._chat(q)
        self.assertEqual(trace[0]["tool"], "search_restaurants")
        self.assertEqual(trace[0]["arguments"]["district"], "Sha Tin")
        self.assertEqual(trace[0]["arguments"].get("cuisine"), "dim_sum")
        self.assertNotIn("获准食肆示例", reply)
        self.assertNotIn("以下是点心店", reply)
        self.assertTrue("无法确认" in reply or "非正式官方" in reply)
        self.assertTrue("改查" in reply or "愿意" in reply)
        html = format_chat_markdown(reply)
        self.assertNotIn("| 名称 | 地址 |", html)
        sample_table = (
            "| 名称 | 地址 |\n| --- | --- |\n| Demo | Sha Tin |\n"
        )
        table_html = format_chat_markdown(sample_table)
        self.assertIn("<table", table_html)
        self.assertNotIn("| --- | --- |", table_html)

    def test_11c_unconfirmed_cuisine_asks_to_relax(self):
        reply, trace = self._chat("沙田有没有宠物友好的西班牙菜餐厅？")
        self.assertEqual(trace[0]["tool"], "search_restaurants")
        self.assertEqual(trace[0]["arguments"].get("cuisine"), "spanish")
        filtered = search_restaurants("Sha Tin", cuisine="spanish")
        if filtered["count"] == 0:
            self.assertIn("无法确认", reply)
            self.assertTrue("愿意" in reply or "改查" in reply)
            self.assertNotIn("获准食肆示例", reply)
            permission = search_restaurants("Sha Tin", limit=1)
            if permission["count"] > 0:
                name = (
                    permission["restaurants"][0]["name_zh"]
                    or permission["restaurants"][0]["name_en"]
                    or ""
                )
                if name:
                    self.assertNotIn(name, reply)

    # --- 12–14 park search ---

    def test_12_sha_tin_pet_park(self):
        reply, trace = self._chat("沙田有没有宠物公园？")
        self.assertEqual(trace[0]["tool"], "search_parks")
        self.assertEqual(trace[0]["arguments"]["district"], "Sha Tin")
        self.assertGreater(trace[0]["result_count"], 0)
        self.assertIn("地区", reply)
        self.assertIn("来源", reply)
        self.assertIn("核实日期", reply)

    def test_13_wan_chai_inclusive_park(self):
        reply, trace = self._chat("湾仔有没有宠物共享公园？")
        self.assertEqual(trace[0]["tool"], "search_parks")
        self.assertEqual(trace[0]["arguments"]["district"], "Wan Chai")
        self.assertEqual(trace[0]["arguments"].get("park_type"), "inclusive_park")
        self.assertIn("来源", reply)

    def test_14_park_tool_provenance(self):
        result = search_parks("Sha Tin", limit=3)
        self.assertGreater(result["count"], 0)
        for row in result["parks"]:
            self.assertTrue(row.get("name_en") or row.get("name_zh"))
            self.assertEqual(row["district"], "Sha Tin")
            self.assertTrue(row["source_url"])
            self.assertTrue(row["last_verified_at"])

    # --- 15–17 no-result / clarification ---

    def test_15_restaurant_no_result(self):
        reply, trace = self._chat("南极洲有没有获准让狗进入的食肆？")
        self.assertTrue(any(t["tool"] == "search_restaurants" for t in trace))
        self.assertEqual(trace[0]["result_count"], 0)
        self.assertTrue("暂无" in reply or "没有" in reply)

    def test_16_park_no_result(self):
        reply, trace = self._chat("南极洲有没有宠物公园？")
        self.assertTrue(any(t["tool"] == "search_parks" for t in trace))
        self.assertEqual(trace[0]["result_count"], 0)
        self.assertTrue("暂无" in reply or "没有" in reply)

    def test_17_place_missing_district_no_tool(self):
        reply, trace = self._chat("附近有没有获准让狗进入的食肆？")
        self.assertEqual(trace, [])
        self.assertTrue("地区" in reply or "沙田" in reply)

    # --- 18 knowledge empty / insufficient ---

    def test_17b_followup_one_after_unconfirmed_cuisine(self):
        history = [
            {"role": "user", "content": "旺角茶餐厅"},
            {
                "role": "assistant",
                "content": (
                    "无法确认「旺角」是否有宠物友好的茶餐厅。"
                    "是否愿意改查获准带狗进入的食肆？\n1. 改查获准带狗食肆"
                ),
            },
        ]
        reply, trace = run_dev_fallback("1", history)
        self.assertEqual(trace[0]["tool"], "search_restaurants")
        self.assertIn(trace[0]["arguments"]["district"], {"Mong Kok", "Yau Tsim Mong"})
        self.assertNotIn("cuisine", trace[0]["arguments"])
        self.assertGreater(trace[0]["result_count"], 0)
        self.assertIn("核实日期", reply)

    def test_18_knowledge_insufficient_basis(self):
        result = search_knowledge("xyzzy_nonexistent_pet_topic_999", limit=3)
        # Either zero hits, or if score noise, agent path should still cite only tool docs
        reply, trace = self._chat("xyzzy_nonexistent_pet_topic_999 仓鼠量子疗法")
        if result["count"] == 0:
            self.assertEqual(trace[0]["tool"], "search_knowledge")
            self.assertEqual(trace[0]["result_count"], 0)
            self.assertIn("没有找到足够依据", reply)
        else:
            self.assertEqual(trace[0]["tool"], "search_knowledge")
            self.assertIn("来源", reply)

    # --- 19–21 mall / clinic / groomer ---

    def test_19_sha_tin_pet_friendly_mall(self):
        reply, trace = self._chat("沙田有没有宠物友善商场？")
        self.assertEqual(trace[0]["tool"], "search_places")
        self.assertEqual(trace[0]["arguments"]["district"], "Sha Tin")
        self.assertEqual(trace[0]["arguments"].get("place_type"), "mall")
        self.assertGreater(trace[0]["result_count"], 0)
        self.assertTrue("来源" in reply or "政策" in reply or "GoPaw" in reply or "官网" in reply)
        self.assertIn("核实日期", reply)
        result = search_places("Sha Tin", "mall", limit=5)
        self.assertGreater(result["count"], 0)
        self.assertTrue(
            any(p.get("source_name") == "mall_official" for p in result["places"])
            or any(p.get("evidence_tier") in {2, 3} for p in result["places"])
        )

    def test_20_wan_chai_vet_clinic(self):
        reply, trace = self._chat("湾仔附近的宠物诊所")
        self.assertEqual(trace[0]["tool"], "search_places")
        self.assertEqual(trace[0]["arguments"]["district"], "Wan Chai")
        self.assertEqual(trace[0]["arguments"].get("place_type"), "clinic")
        if trace[0]["result_count"] == 0:
            self.assertTrue("暂无" in reply or "没有" in reply)
        else:
            self.assertIn("核实日期", reply)
            self.assertTrue("诊所" in reply or "vet" in reply.lower() or "兽医" in reply or "獸醫" in reply)

    def test_21_central_groomer(self):
        reply, trace = self._chat("中西区有没有宠物美容？")
        self.assertEqual(trace[0]["tool"], "search_places")
        self.assertIn(trace[0]["arguments"]["district"], {"Central/Western", "Central"})
        self.assertEqual(trace[0]["arguments"].get("place_type"), "groomer")
        self.assertGreater(trace[0]["result_count"], 0)
        self.assertIn("核实日期", reply)
        self.assertTrue("PetCircle" in reply or "GoPaw" in reply or "美容" in reply or "来源" in reply)

    def test_22_places_have_source_url(self):
        for place_type in ("mall", "clinic", "groomer"):
            result = search_places("Sha Tin", place_type, limit=3)
            for row in result.get("places") or []:
                self.assertTrue(row.get("source_url"))
                self.assertTrue(row.get("last_verified_at"))
                self.assertTrue(row.get("name_en") or row.get("name_zh"))


if __name__ == "__main__":
    unittest.main()
