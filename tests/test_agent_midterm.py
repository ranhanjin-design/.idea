"""Midterm-half tests: knowledge Q&A + domain filter (+ light place search)."""

from __future__ import annotations

import unittest

from pawplan.agent.dev_fallback import run_dev_fallback
from pawplan.agent.intent import classify_intent
from pawplan.database.db import db_stats, init_database
from pawplan.normalize import detect_cuisine_in_text
from pawplan.tools.search_knowledge import search_knowledge
from pawplan.tools.search_parks import search_parks


class IntentTests(unittest.TestCase):
    def test_out_of_scope(self):
        self.assertEqual(classify_intent("帮我预测明天股票"), "out_of_scope")
        self.assertEqual(classify_intent("帮我写数据库作业"), "out_of_scope")

    def test_knowledge(self):
        self.assertEqual(classify_intent("带狗散步时怎样降低中暑风险？"), "knowledge")
        self.assertEqual(classify_intent("我可以带狗进入公众泳滩吗？"), "knowledge")
        self.assertEqual(classify_intent("进入获准食肆后需要遵守哪些规则？"), "knowledge")

    def test_place(self):
        self.assertEqual(classify_intent("沙田有没有获准让狗进入的食肆？"), "place")
        self.assertEqual(classify_intent("找一家旺角获准让狗进入的食肆"), "place")
        self.assertEqual(classify_intent("沙田有没有宠物公园？"), "place")
        self.assertEqual(classify_intent("找一家沙田附近的点心店"), "place")
        self.assertEqual(classify_intent("沙田有没有宠物友善商场？"), "place")
        self.assertEqual(classify_intent("湾仔附近的宠物诊所"), "place")
        self.assertEqual(classify_intent("中西区有没有宠物美容？"), "place")

    def test_detect_cuisine_from_food_shop_request(self):
        self.assertEqual(detect_cuisine_in_text("找一家沙田附近的点心店"), "dim_sum")
        self.assertEqual(detect_cuisine_in_text("湾仔咖啡馆"), "cafe")
        self.assertIsNone(detect_cuisine_in_text("沙田有没有获准让狗进入的食肆？"))


class KnowledgeTests(unittest.TestCase):
    def test_heatstroke_retrieval(self):
        result = search_knowledge("带狗散步怎样防中暑", limit=3)
        self.assertGreater(result["count"], 0)
        self.assertTrue(any("source_url" in d for d in result["documents"]))

    def test_beach_retrieval(self):
        result = search_knowledge("公众泳滩可以带狗吗", limit=3)
        self.assertGreater(result["count"], 0)
        ids = {d["doc_id"] for d in result["documents"]}
        self.assertIn("rule_public_beach", ids)


class AgentFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_database()

    def test_knowledge_answer_uses_tool(self):
        reply, trace = run_dev_fallback("带狗散步时，怎样降低中暑风险？")
        self.assertTrue(trace)
        self.assertEqual(trace[0]["tool"], "search_knowledge")
        self.assertIn("来源", reply)

    def test_domain_filter(self):
        reply, trace = run_dev_fallback("可以总结一下今天的股票市场吗？")
        self.assertEqual(trace, [])
        self.assertIn("范围", reply)

    def test_dining_policy_knowledge(self):
        reply, trace = run_dev_fallback("进入获准食肆后需要遵守哪些规则？")
        self.assertEqual(trace[0]["tool"], "search_knowledge")
        self.assertTrue("FEHD" in reply or "食物环境卫生署" in reply or "获准" in reply)

    def test_place_still_works(self):
        reply, trace = run_dev_fallback("沙田有没有获准让狗进入的食肆？")
        self.assertTrue(any(t["tool"] == "search_restaurants" for t in trace))
        self.assertNotIn("cuisine", trace[0]["arguments"])
        self.assertTrue(len(reply) > 10)

    def test_cuisine_filter_does_not_recommend_unmatched(self):
        reply, trace = run_dev_fallback("我需要找一间沙田附近的宠物友好点心店。")
        self.assertTrue(any(t["tool"] == "search_restaurants" for t in trace))
        self.assertEqual(trace[0]["arguments"].get("cuisine"), "dim_sum")
        self.assertNotIn("获准食肆示例", reply)
        self.assertTrue("无法确认" in reply or "非正式官方" in reply)
        self.assertTrue("愿意" in reply or "改查" in reply)

    def test_park_search_tool(self):
        stats = db_stats()
        if stats.get("parks", 0) == 0:
            self.skipTest("parks table empty; run parks pipeline first")
        result = search_parks("Sha Tin", limit=5)
        self.assertGreater(result["count"], 0)

    def test_park_query_uses_tool(self):
        stats = db_stats()
        if stats.get("parks", 0) == 0:
            self.skipTest("parks table empty; run parks pipeline first")
        reply, trace = run_dev_fallback("沙田有没有宠物公园？")
        self.assertTrue(any(t["tool"] == "search_parks" for t in trace))
        self.assertIn("来源", reply)

    def test_followup_one_relaxes_cuisine_from_history(self):
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
        reply, trace = run_dev_fallback("1", history=history)
        self.assertTrue(any(t["tool"] == "search_restaurants" for t in trace))
        self.assertIn(trace[0]["arguments"]["district"], {"Mong Kok", "Yau Tsim Mong"})
        self.assertNotIn("cuisine", trace[0]["arguments"])
        self.assertGreater(trace[0]["result_count"], 0)
        self.assertTrue(len(reply) > 10)

    def test_followup_short_circuits_deepseek_path(self):
        from pawplan.agent.loop import run_agent

        history = [
            {"role": "user", "content": "旺角附近的可以带狗进入的茶餐厅"},
            {
                "role": "assistant",
                "content": (
                    "无法确认旺角茶餐厅/咖啡店类型。\n"
                    "1. 只按可带狗进入筛选获准食肆\n"
                    "2. 换一个地区"
                ),
            },
        ]
        result = run_agent("1", history=history)
        self.assertEqual(result["mode"], "followup")
        self.assertTrue(any(t["tool"] == "search_restaurants" for t in result["tool_trace"]))
        self.assertIn(
            result["tool_trace"][0]["arguments"]["district"],
            {"Mong Kok", "Yau Tsim Mong"},
        )
        self.assertNotIn("cuisine", result["tool_trace"][0]["arguments"])


if __name__ == "__main__":
    unittest.main()
