"""Intent routing for midterm-half agent (knowledge first)."""

from __future__ import annotations

OUT_OF_SCOPE_HINTS = (
    "股票",
    "股巿",
    "股市",
    "作业",
    "功课",
    "作业答案",
    "新闻",
    "stock",
    "homework",
    "crypto",
    "比特币",
    "写代码作业",
    "drop table",
    "删库",
)

KNOWLEDGE_HINTS = (
    "中暑",
    "热射病",
    "散步",
    "喝水",
    "补水",
    "牵绳",
    "清理",
    "泳滩",
    "海滩",
    "沙滩",
    "beach",
    "规则",
    "守则",
    "可不可以",
    "可以带狗",
    "能否",
    "怎么",
    "如何",
    "为什么",
    "heatstroke",
    "轻铁",
    "政策",
    "负责任",
    "注意事项",
)

PARK_HINTS = (
    "公园",
    "公園",
    "宠物公园",
    "寵物公園",
    "狗公园",
    "狗公園",
    "共享公园",
    "共享公園",
    "pet garden",
    "dog garden",
    "inclusive park",
    "狗厕",
    "狗廁",
    "dog latrine",
)

RESTAURANT_HINTS = (
    "餐厅",
    "餐廳",
    "食肆",
    "饭店",
    "飯店",
    "咖啡馆",
    "咖啡店",
    "restaurant",
    "cafe",
    "点心",
    "饮茶",
)

PLACE_HINTS = (
    "找",
    "推荐",
    "附近",
    "哪里",
    "哪间",
    "哪家",
    "地点",
    *RESTAURANT_HINTS,
    *PARK_HINTS,
)


def classify_intent(text: str) -> str:
    """
    Returns one of: out_of_scope | knowledge | place | unclear
    """
    raw = (text or "").strip()
    lower = raw.lower()
    if not raw:
        return "unclear"

    if any(h in lower or h in raw for h in OUT_OF_SCOPE_HINTS):
        return "out_of_scope"

    place_score = sum(1 for h in PLACE_HINTS if h in raw or h in lower)
    knowledge_score = sum(1 for h in KNOWLEDGE_HINTS if h in raw or h in lower)
    park_hit = any(h in raw or h in lower for h in PARK_HINTS)
    restaurant_hit = any(h in raw or h in lower for h in RESTAURANT_HINTS)

    if place_score >= 1 and any(
        k in raw or k in lower
        for k in (
            "找",
            "推荐",
            "附近",
            "哪",
            "有没有",
            "有沒有",
            "restaurant",
            "cafe",
            "食肆",
            "餐厅",
            "公園",
            "公园",
            "pet garden",
            "dog garden",
        )
    ):
        if any(
            k in raw
            for k in ("规则", "守则", "注意事项", "怎么", "如何", "可否", "可以吗", "能不能")
        ):
            if knowledge_score >= 1 and not park_hit and not restaurant_hit:
                return "knowledge"
            if knowledge_score >= 1 and ("规则" in raw or "守则" in raw) and not (
                "找" in raw or "推荐" in raw or "有没有" in raw
            ):
                return "knowledge"
        return "place"

    if knowledge_score >= 1:
        return "knowledge"

    if any(k in raw for k in ("狗", "猫", "宠物", "寵物", "pet", "犬")):
        return "knowledge"

    return "out_of_scope"


def is_park_query(text: str) -> bool:
    lower = text.lower()
    return any(h in text or h in lower for h in PARK_HINTS)


def is_restaurant_query(text: str) -> bool:
    lower = text.lower()
    return any(h in text or h in lower for h in RESTAURANT_HINTS)
