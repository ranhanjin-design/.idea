"""Midterm-half tests: knowledge Q&A + domain filter (+ light place search)."""

from __future__ import annotations

import unittest

from pawplan.agent.dev_fallback import run_dev_fallback
from pawplan.agent.intent import classify_intent
from pawplan.database.db import db_stats, init_database
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
        self.assertEqual(classify_intent("沙田有没有宠物友好咖啡馆？"), "place")
        self.assertEqual(classify_intent("找一家旺角获准让狗进入的食肆"), "place")
        self.assertEqual(classify_intent("沙田有没有宠物公园？"), "place")


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
        reply, trace = run_dev_fallback("沙田有没有宠物友好咖啡馆？")
        self.assertTrue(any(t["tool"] == "search_restaurants" for t in trace))
        self.assertTrue(len(reply) > 10)

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


if __name__ == "__main__":
    unittest.main()
