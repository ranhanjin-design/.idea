"""Rule-based path when DEEPSEEK_API_KEY is not set (midterm-half demo)."""

from __future__ import annotations

import re

from pawplan.agent.intent import classify_intent, is_park_query, is_restaurant_query
from pawplan.normalize import cuisine_label_zh, detect_cuisine_in_text, detect_district_in_text
from pawplan.tools.search_knowledge import search_knowledge
from pawplan.tools.search_parks import search_parks
from pawplan.tools.search_restaurants import search_restaurants


def _guess_unknown_district(text: str) -> str | None:
    """Use an explicit place phrase so unknown areas can return honest empty results."""
    raw = (text or "").strip()
    patterns = (
        r"^([\u4e00-\u9fffA-Za-z]{2,12})有没有",
        r"^([\u4e00-\u9fffA-Za-z]{2,12})有沒有",
        r"^([\u4e00-\u9fffA-Za-z ]{2,20})附近",
    )
    skip = {"附近", "哪里", "哪裡", "什么", "什麼", "哪些"}
    for pat in patterns:
        m = re.search(pat, raw)
        if not m:
            continue
        cand = m.group(1).strip()
        if cand and cand not in skip:
            return cand
    return None


def _park_type_from_text(text: str) -> str | None:
    lower = text.lower()
    if any(k in text or k in lower for k in ("共享", "inclusive")):
        return "inclusive_park"
    if any(
        k in text or k in lower
        for k in ("宠物公园", "寵物公園", "狗公园", "狗公園", "pet garden", "dog garden")
    ):
        return "pet_garden"
    return None


def _answer_knowledge(user_question: str) -> tuple[str, list[dict]]:
    args = {"query": user_question, "limit": 3}
    result = search_knowledge(**args)
    trace = [
        {
            "tool": "search_knowledge",
            "arguments": args,
            "result_count": result["count"],
        }
    ]
    if result["count"] == 0:
        return (
            "我在当前知识库里没有找到足够依据来回答。你可以换个问法，例如："
            "「带狗散步怎样防中暑？」「公众泳滩可以带狗吗？」「获准食肆内要注意什么？」",
            trace,
        )

    lines = ["根据 PawPlan 知识库，相关说明如下：", ""]
    for i, doc in enumerate(result["documents"], 1):
        lines.append(f"{i}. **{doc['title_zh']}**")
        lines.append(doc.get("content_zh") or doc.get("summary_zh") or "")
        lines.append(
            f"来源：{doc.get('source_name')} — {doc.get('source_url')} "
            f"（核实日期 {doc.get('last_verified_at')}；置信度 {doc.get('confidence')}）"
        )
        lines.append("")
    lines.append("以上为资料摘要，出发前请再核对官方最新公告；健康问题请咨询兽医。")
    return "\n".join(lines), trace


def _answer_parks(user_question: str, district: str) -> tuple[str, list[dict]]:
    park_type = _park_type_from_text(user_question)
    require_latrine = any(
        k in user_question.lower() or k in user_question
        for k in ("狗厕", "狗廁", "latrine", "dog toilet")
    )
    args: dict = {
        "district": district,
        "limit": 5,
        "require_dog_latrine": require_latrine,
    }
    if park_type:
        args["park_type"] = park_type
    result = search_parks(**args)
    trace = [
        {
            "tool": "search_parks",
            "arguments": args,
            "result_count": result["count"],
        }
    ]
    if result["count"] == 0 and park_type:
        relaxed = search_parks(district=district, limit=5)
        trace.append(
            {
                "tool": "search_parks",
                "arguments": {"district": district, "limit": 5},
                "result_count": relaxed["count"],
                "note": "relaxed_park_type",
            }
        )
        if relaxed["count"] == 0:
            return (f"数据库中暂无「{district}」的宠物公园/共享公园记录。", trace)
        result = relaxed
        header = (
            f"未找到指定类型的完全匹配；以下是 {district} 的 {result['count']} 个相关场地："
        )
    elif result["count"] == 0:
        return (f"数据库中暂无「{district}」的宠物公园/共享公园记录。", trace)
    else:
        label = district + (f"、{park_type}" if park_type else "")
        header = f"找到 {result['count']} 个符合「{label}」的场地："

    type_label = {
        "pet_garden": "宠物公园",
        "inclusive_park": "宠物共享公园",
    }
    lines = [header, ""]
    for i, p in enumerate(result["parks"], 1):
        name = p["name_zh"] or p["name_en"] or p["park_id"]
        en = f"（{p['name_en']}）" if p.get("name_en") and p["name_en"] != name else ""
        kind = type_label.get(p["park_type"], p["park_type"])
        addr = p.get("address") or "地址见康文署资料"
        hours = p.get("opening_hours") or "开放时间未收录"
        lines.append(f"{i}. **{name}**{en} — {kind}")
        lines.append(f"   地区：{p.get('district') or district}")
        lines.append(f"   地址：{addr}")
        lines.append(f"   开放：{hours}")
        lines.append(
            f"   来源：{p['source_url']}（核实日期 {p['last_verified_at']}）"
        )
    lines.append("")
    lines.append(
        "宠物公园通常有围栏；宠物共享公园一般须牵绳。"
        "资料来自康文署公开名单，出发前请再确认场规。"
    )
    return "\n".join(lines), trace


def _format_restaurant_block(restaurants: list[dict], district: str) -> list[str]:
    lines: list[str] = []
    for i, r in enumerate(restaurants, 1):
        name = r["name_zh"] or r["name_en"] or r["restaurant_id"]
        source = r["source_url"]
        lines.append(f"{i}. **{name}**")
        lines.append(f"   地区：{r.get('district') or district}")
        lines.append(f"   地址：{r['address']}")
        label = r.get("cuisine_label_zh")
        if label:
            conf = r.get("cuisine_confidence")
            conf_txt = f"，置信度 {conf:.2f}" if isinstance(conf, (int, float)) else ""
            lines.append(f"   菜系标签：{label}{conf_txt}（非正式官方确认）")
        lines.append(
            f"   来源：[{source}]({source})（核实日期 {r['last_verified_at']}）"
        )
    return lines


def _answer_restaurants(user_question: str, district: str) -> tuple[str, list[dict]]:
    cuisine = detect_cuisine_in_text(user_question)
    args: dict = {"district": district, "limit": 5}
    if cuisine:
        args["cuisine"] = cuisine
    result = search_restaurants(**args)
    trace = [
        {
            "tool": "search_restaurants",
            "arguments": args,
            "result_count": result["count"],
        }
    ]

    if cuisine:
        label = cuisine_label_zh(cuisine)
        if result.get("cuisine_confirmed") and result["count"] > 0:
            lines = [
                f"按菜系「{label}」筛选到 {result['count']} 间「{district}」获准带狗食肆。",
                "食环署公开名单**没有官方菜系字段**，以下仅按店名/策展标签匹配，"
                "**非正式官方确认**，不能当作已核实的菜系推荐。",
                "",
            ]
            lines.extend(_format_restaurant_block(result["restaurants"], district))
            lines.append("")
            lines.append(
                f"若你更需要官方许可名单，是否愿意改查「{district}」获准带狗进入的食肆？"
                f"可以说「{district}有没有获准让狗进入的食肆」。"
            )
            return "\n".join(lines), trace

        permission_count = int(result.get("district_permission_count") or 0)
        if permission_count == 0:
            return (
                f"数据库中暂无「{district}」的获准带狗食肆，因此也无法确认是否有{label}。",
                trace,
            )
        return (
            f"食环署名单没有菜系字段，**无法确认**「{district}」是否有宠物友好的{label}。"
            f"我不会把其他不匹配的获准食肆当作{label}推荐。"
            f"是否愿意改查「{district}」获准带狗进入的食肆？"
            f"若愿意，请直接问「{district}有没有获准让狗进入的食肆」。",
            trace,
        )

    if result["count"] == 0:
        return (f"数据库中暂无「{district}」的匹配食肆。可以换一个地区再试。", trace)

    lines = [
        f"找到 {result['count']} 间「{district}」获准让狗只进入的食肆：",
        "",
    ]
    lines.extend(_format_restaurant_block(result["restaurants"], district))
    lines.append("")
    lines.append(
        "名单来自食环署公开资料；出发前请再确认是否仍在最新名单及店内守则。"
    )
    return "\n".join(lines), trace


def _answer_place(user_question: str) -> tuple[str, list[dict]]:
    district = detect_district_in_text(user_question) or _guess_unknown_district(
        user_question
    )
    park = is_park_query(user_question)
    restaurant = is_restaurant_query(user_question)

    if not district:
        if park and not restaurant:
            return (
                "可以帮你查康文署宠物公园/宠物共享公园。请告诉我地区（例如沙田、湾仔）。",
                [],
            )
        return (
            "可以帮你查获准带狗食肆，或康文署宠物公园/共享公园。"
            "请告诉我地区（例如沙田、旺角），并说明要找餐厅还是公园。",
            [],
        )

    if park and not restaurant:
        return _answer_parks(user_question, district)
    if restaurant and not park:
        return _answer_restaurants(user_question, district)
    if park and restaurant:
        # Prefer explicit park if both mentioned lightly; otherwise restaurants
        return _answer_parks(user_question, district)

    # Generic "附近地点" — try parks first then mention restaurants
    park_reply, park_trace = _answer_parks(user_question, district)
    if park_trace and park_trace[0].get("result_count", 0) > 0:
        return park_reply, park_trace
    return _answer_restaurants(user_question, district)


def run_dev_fallback(user_question: str) -> tuple[str, list[dict]]:
    intent = classify_intent(user_question)

    if intent == "out_of_scope":
        return (
            "这个问题超出了 PawPlan 目前的范围。"
            "我可以回答香港宠物友善相关的护理/规则问题，或查询宠物公园与获准带狗食肆。"
            "例如：「带狗散步怎样防中暑？」或「沙田有没有宠物公园？」",
            [],
        )

    if intent == "place":
        return _answer_place(user_question)

    return _answer_knowledge(user_question)
