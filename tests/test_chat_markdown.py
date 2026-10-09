"""Presentation contract: chat Markdown must render tables/links, not raw pipes."""

from __future__ import annotations

import unittest

from pawplan.web.chat_markdown import format_chat_markdown


class ChatMarkdownTests(unittest.TestCase):
    def test_table_renders_as_html_not_raw_pipes(self):
        md = (
            "沙田获准食肆示例\n\n"
            "| 名称 | 地址 |\n"
            "| --- | --- |\n"
            "| 2+2 Cafe & Bar | 沙田某某路 |\n"
            "| Bar Pacific | 沙田另一路 |\n"
        )
        html = format_chat_markdown(md)
        self.assertIn("<table", html)
        self.assertIn("<th>", html)
        self.assertIn("2+2 Cafe &amp; Bar", html)
        self.assertIn("沙田某某路", html)
        # Must not leave GFM table source as the primary visible form
        self.assertNotIn("| 名称 | 地址 |", html)
        self.assertNotIn("| --- | --- |", html)

    def test_fehd_link_is_clickable(self):
        md = (
            "来源：[FEHD 获准食肆名单]"
            "(https://www.fehd.gov.hk/english/licensing/dog_restaurants/fulllist.pdf)"
            "（核实日期 2026-10-08）"
        )
        html = format_chat_markdown(md)
        self.assertIn('<a href="https://www.fehd.gov.hk/english/licensing/dog_restaurants/fulllist.pdf"', html)
        self.assertIn("FEHD 获准食肆名单", html)
        self.assertIn("核实日期 2026-10-08", html)

    def test_bare_url_becomes_link(self):
        html = format_chat_markdown(
            "来源：https://www.fehd.gov.hk/english/licensing/dog_restaurants/fulllist.pdf"
        )
        self.assertIn('<a href="https://www.fehd.gov.hk/english/licensing/dog_restaurants/fulllist.pdf"', html)

    def test_bold_and_list_remain_readable(self):
        html = format_chat_markdown("系统**不能按菜系筛选**\n1. **銀泉茶餐廳**")
        self.assertIn("<strong>不能按菜系筛选</strong>", html)
        self.assertIn("<strong>銀泉茶餐廳</strong>", html)


if __name__ == "__main__":
    unittest.main()
