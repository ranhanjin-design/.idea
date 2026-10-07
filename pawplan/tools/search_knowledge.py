"""Keyword retrieval over curated knowledge documents."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DOCS = ROOT / "data" / "knowledge" / "midterm_docs.json"

TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def _tokenize(text: str) -> set[str]:
    text = (text or "").lower()
    parts = TOKEN_RE.findall(text)
    tokens: set[str] = set()
    for p in parts:
        tokens.add(p)
        # rough bigrams for Chinese 2-grams
        if re.search(r"[\u4e00-\u9fff]", p) and len(p) >= 2:
            for i in range(len(p) - 1):
                tokens.add(p[i : i + 2])
    return tokens


@lru_cache(maxsize=1)
def load_docs(path: str | None = None) -> list[dict]:
    doc_path = Path(path) if path else DEFAULT_DOCS
    data = json.loads(doc_path.read_text(encoding="utf-8"))
    return data


def search_knowledge(query: str, limit: int = 3) -> dict:
    """Return ranked knowledge snippets with sources. Never invents documents."""
    limit = max(1, min(int(limit), 5))
    q = (query or "").strip()
    if not q:
        return {"query": query, "count": 0, "documents": []}

    q_tokens = _tokenize(q)
    scored: list[tuple[float, dict]] = []

    for doc in load_docs():
        hay = " ".join(
            [
                doc.get("title_zh") or "",
                doc.get("title_en") or "",
                doc.get("summary_zh") or "",
                doc.get("content_zh") or "",
                " ".join(doc.get("tags") or []),
                doc.get("category") or "",
            ]
        )
        hay_l = hay.lower()
        score = 0.0

        # phrase hits
        for tag in doc.get("tags") or []:
            if tag and tag.lower() in q.lower():
                score += 3.0
            if tag and tag.lower() in hay_l and tag.lower() in q.lower():
                score += 1.0

        overlap = _tokenize(hay) & q_tokens
        score += len(overlap) * 1.2

        # title boost
        title = (doc.get("title_zh") or "") + " " + (doc.get("title_en") or "")
        for tok in q_tokens:
            if tok and tok in title.lower():
                score += 2.0

        if score > 0:
            scored.append((score, doc))

    scored.sort(key=lambda x: (-x[0], -float(x[1].get("confidence") or 0)))
    top = scored[:limit]

    documents = []
    for score, doc in top:
        documents.append(
            {
                "doc_id": doc["doc_id"],
                "category": doc.get("category"),
                "title_zh": doc.get("title_zh"),
                "summary_zh": doc.get("summary_zh"),
                "content_zh": doc.get("content_zh"),
                "source_name": doc.get("source_name"),
                "source_url": doc.get("source_url"),
                "last_verified_at": doc.get("last_verified_at"),
                "confidence": doc.get("confidence"),
                "score": round(score, 3),
            }
        )

    return {"query": q, "count": len(documents), "documents": documents}
