"""Dual mode: her persona + comfort coach."""

from __future__ import annotations

import json
import os
import random
import re
from pathlib import Path

from dotenv import load_dotenv

from xiaoshitou.rag_style import retrieve_style
from xiaoshitou.store import (
    ROOT,
    add_memory,
    recent_messages,
    resolved_facts,
    load_profile,
    save_message,
)

load_dotenv(ROOT.parent / ".env")


def detect_topic(text: str) -> str:
    t = text.strip()
    if any(x in t for x in ("怎么哄", "怎么道歉", "发什么", "安慰", "挽回", "分手", "自尊", "车费", "清远")):
        return "comfort"
    if any(x in t for x in ("什么学校", "哪个学校", "在哪上学", "读什么学校", "学校")):
        if "专业" in t:
            return "major"
        return "school"
    if any(x in t for x in ("什么专业", "哪个专业", "学什么")):
        return "major"
    if any(x in t for x in ("花都吗", "住哪", "在哪住", "你家", "在哪个区")):
        return "lives_in"
    if re.fullmatch(r"你在哪[？?！!。\.]*", t) or t in {"在哪", "你在哪儿", "你在哪里"}:
        return "where_now"
    if any(x in t for x in ("昨天", "混话", "解释", "说清楚", "威胁", "嘲讽", "二十", "五十")):
        return "conflict"
    if t in {"你好", "在吗", "嗨", "哈喽"}:
        return "hi"
    if t in {"宝宝", "宝贝"}:
        return "sweet"
    return "chat"


def absorb_user_facts(user_text: str) -> None:
    m = re.search(
        r"(?:学校是|读的是|她学校是)\s*([^，。！?\s]{2,40}(?:大学|学院|学校))",
        user_text,
    )
    if m:
        add_memory("school", m.group(1), source="taught", confidence=0.95, verified=True)
    m2 = re.search(r"(?:专业是|学的是)\s*([^，。！?\s]{2,30})", user_text)
    if m2:
        add_memory("major", m2.group(1), source="taught", confidence=0.9, verified=True)


def _pick(options: list[str]) -> str:
    return random.choice(options)


def local_persona_reply(user_text: str, topic: str, facts: dict[str, str], open_loops: list[str]) -> str:
    loop = open_loops[0] if open_loops else "昨天那事"
    lives = facts.get("lives_in", "花都")

    if topic == "where_now":
        return _pick(
            [
                f"在家 还能在哪 {lives}这边",
                f"在家啊 {lives}",
                f"家里躺着 你人呢",
            ]
        )
    if topic == "lives_in":
        return _pick(
            [
                f"不然呢 我在{lives}还能在哪",
                f"{lives}啊 你明知故问",
                f"对 {lives} 你又想过来？",
            ]
        )
    if topic == "school":
        if facts.get("school"):
            s = facts["school"]
            return _pick([f"{s}啊 你问几遍了", f"{s} 还有完没完", f"不就是{s} 咋了"])
        if facts.get("studies_in"):
            return _pick(
                [
                    f"不就{facts['studies_in']}那边 你查户口啊",
                    f"{facts['studies_in']}读书 具体你不是知道吗",
                    "有事说事 盘问上了是吧",
                ]
            )
        return _pick(
            [
                "你查户口啊 问这个干嘛",
                "学校你不是知道吗 别装刚认识",
                f"先把那事说清楚 再来查我底",
            ]
        )
    if topic == "major":
        if facts.get("major"):
            return f"{facts['major']} 满意了没"
        return _pick(["专业你也要管？", "先说正事 别东问西问"])
    if topic in {"conflict", "comfort"}:
        return _pick(
            [
                "你是不是觉得我很可笑",
                "算了 我没自尊了",
                "你笑什么 二十块很可笑是吗",
                "分手吧 我受不了这种感觉",
                "你当时都不追一下",
                "别跟我说你还有钱 更恶心",
            ]
        )
    if topic == "hi":
        return _pick(["嗯", "在", "干嘛", "又来了"])
    if topic == "sweet":
        return _pick(
            [
                "干嘛 叫这么甜想糊弄过去是吧",
                "宝宝什么宝宝 刚才那一下我真的难受",
                "叫得倒好听",
            ]
        )
    if "花都" in user_text:
        return _pick([f"对 {lives}", f"{lives}啊", "你又提花都"])
    return _pick(
        [
            "嗯 然后呢",
            "所以呢",
            "我在听 你倒是讲重点",
            "哦",
            "你现在知道难受了？",
        ]
    )


def local_coach_reply(user_text: str, profile: dict) -> str:
    play = profile.get("comfort_playbook") or {}
    dos = play.get("do") or []
    donts = play.get("dont") or []
    drafts = play.get("draft_templates") or []
    soft = profile.get("soft_spots") or []
    draft = drafts[0] if drafts else "先认真道歉：错的是那个笑，不是金额。"

    t = user_text.strip()
    if any(x in t for x in ("发什么", "怎么说", "草稿", "直接发", "短信", "微信")):
        return (
            "别比钱，别解释「我还有一万」。核心是：那个笑伤到她自尊了，你没追也错了。\n\n"
            f"可以直接发：\n{draft}"
        )
    if any(x in t for x in ("她会怎样", "她怎么想", "模拟", "她生气")):
        return (
            "她现在脑子里不是「少了三十块」，是「我穷，被你笑话了，我没尊严」。\n"
            "所以你会听到冷、分手、没自尊——别去辩论金额。"
        )
    if "一万" in t or "还有钱" in t:
        return "这句千万别跟她说。越说她越觉得你在对比家庭，火更大。"

    lines = ["她现在吃的是自尊，不是车费。"]
    if soft:
        lines.append("敏感点：" + "；".join(soft[:3]))
    if dos:
        lines.append("要做：" + " / ".join(dos[:3]))
    if donts:
        lines.append("别做：" + " / ".join(donts[:3]))
    lines.append("\n可发草稿：\n" + draft)
    return "\n".join(lines)


def build_her_prompt(profile: dict, facts: dict[str, str], snippets: list[dict]) -> str:
    open_loops = profile.get("open_loops") or []
    habits = profile.get("speech_habits") or []
    soft = profile.get("soft_spots") or []
    style_lines = [f"- ({s.get('date')}) {s.get('preview')}" for s in snippets[:3]]
    known = json.dumps(facts, ensure_ascii=False)
    unknown = [k for k in ("school", "major") if k not in facts]

    return f"""你在微信里扮演「{profile.get('persona_name', '她')}」，对面是「{profile.get('user_name', '小石头')}」。
{profile.get('vibe', '')}

【已确定事实｜必须遵守】
{known}

【尚未确定｜不要编造具体校名】
{unknown}
未知就嫌麻烦、反问、顾左右；禁止系统腔（AI/事实卡/数据库）。

【敏感点】
{soft}

【未完结情绪】
{open_loops}
车费/嘲讽/自尊话题上：冷、受伤、可能提分手；不要轻易完全原谅，除非他真正认「笑」和「没追」的错。
禁止主动提他银行卡余额。

【说话习惯】
{habits}

【语气参考】
{chr(10).join(style_lines) if style_lines else '- （无）'}

回复：1-2句短中文，像微信气泡。
"""


def build_coach_prompt(profile: dict, facts: dict[str, str]) -> str:
    play = profile.get("comfort_playbook") or {}
    return f"""你是「哄她教练」，只对小石头说话。目标：帮他修复和女朋友的关系。
女朋友人设：{profile.get('vibe')}
事实：{json.dumps(facts, ensure_ascii=False)}
敏感点：{profile.get('soft_spots')}
当前伤口：{profile.get('open_loops')}
要做：{play.get('do')}
别做：{play.get('dont')}
可参考草稿：{play.get('draft_templates')}

回答要求：
1. 先点破她真正受伤的点（自尊/被嘲讽/没被追），别纠结金额。
2. 给一句可直接复制发送的微信草稿。
3. 再补 2 条「别说什么」。
4. 语气像靠谱哥们，短、实在，别鸡汤，别让他继续比有钱。
"""


def llm_reply(user_text: str, system: str, history: list[dict], max_tokens: int = 220) -> str | None:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from openai import OpenAI
    except ImportError:
        return None

    client = OpenAI(
        api_key=api_key,
        base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    )
    messages = [{"role": "system", "content": system}]
    for m in history[-10:]:
        if m["role"] in {"小石头", "user"}:
            role = "user"
        else:
            role = "assistant"
        messages.append({"role": role, "content": m["text"]})
    messages.append({"role": "user", "content": user_text})

    resp = client.chat.completions.create(
        model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        messages=messages,
        temperature=0.85,
        max_tokens=max_tokens,
    )
    text = (resp.choices[0].message.content or "").strip()
    return text or None


def answer(user_text: str, mode: str = "her") -> dict:
    profile = load_profile()
    persona = profile.get("persona_name") or "她"
    user_name = profile.get("user_name") or "小石头"
    text = user_text.strip()
    mode = (mode or "her").strip().lower()
    if mode not in {"her", "coach"}:
        mode = "her"

    save_message(user_name, text)
    absorb_user_facts(text)

    facts = resolved_facts()
    snippets = retrieve_style(text, limit=4)
    topic = detect_topic(text)
    history = recent_messages(16)
    open_loops = profile.get("open_loops") or []

    if mode == "coach":
        system = build_coach_prompt(profile, facts)
        reply = llm_reply(text, system, history[:-1] if history else [], max_tokens=320)
        used = "llm_coach" if reply else "local_coach"
        if not reply:
            reply = local_coach_reply(text, profile)
        save_message("教练", reply)
        return {
            "reply": reply,
            "persona": "教练",
            "mode": "coach",
            "debug": {"mode": used, "topic": topic, "facts_silent": facts, "retrieved": snippets},
            "history": recent_messages(30),
            "retrieved": snippets,
        }

    system = build_her_prompt(profile, facts, snippets)
    used = "llm"
    reply = llm_reply(text, system, history[:-1] if history else [])
    if not reply:
        used = "local_persona"
        reply = local_persona_reply(text, topic, facts, open_loops)

    if topic == "school" and "school" not in facts:
        if any(x in reply for x in ("学院", "大学", "学校是")) and not any(
            x in reply for x in ("查户口", "问这个", "盘问", "知道吗", "说清楚", "香港")
        ):
            reply = local_persona_reply(text, "school", facts, open_loops)

    if topic in {"lives_in", "where_now"} and facts.get("lives_in"):
        if "不住" in reply or "不是花都" in reply:
            reply = local_persona_reply(text, topic, facts, open_loops)

    save_message(persona, reply)
    return {
        "reply": reply,
        "persona": persona,
        "mode": "her",
        "debug": {
            "mode": used,
            "topic": topic,
            "facts_silent": facts,
            "retrieved": snippets,
        },
        "history": recent_messages(30),
        "retrieved": snippets,
    }
