"""Style retrieval from sample WeChat-like turns."""

from __future__ import annotations

from xiaoshitou.store import load_chats


def retrieve_style(query: str, limit: int = 4) -> list[dict]:
    chats = load_chats()
    scored: list[tuple[float, dict]] = []
    for chat in chats:
        blob = " ".join(t["text"] for t in chat.get("turns") or [])
        score = 0.15
        for token in ("花都", "学校", "在哪", "昨天", "在家", "宝宝", "解释", "你好"):
            if token in query and token in blob:
                score += 2.2
        tags = chat.get("tags") or []
        if "conflict" in tags and any(x in query for x in ("昨天", "混话", "解释", "说清楚", "宝宝")):
            score += 1.8
        if "location" in tags and any(x in query for x in ("哪", "花都", "住", "在家")):
            score += 1.6
        if "tease" in tags:
            score += 0.4
        scored.append((score, chat))
    scored.sort(key=lambda x: -x[0])
    out = []
    for score, chat in scored[:limit]:
        preview = " / ".join(f"{t['role']}:{t['text']}" for t in chat.get("turns") or [])
        out.append(
            {
                "id": chat["id"],
                "date": chat.get("date"),
                "tags": chat.get("tags"),
                "score": round(score, 3),
                "turns": chat.get("turns"),
                "preview": preview,
            }
        )
    return out
