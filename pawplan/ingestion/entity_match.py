"""Entity matching for FEHD restaurants vs complementary cuisine sources.

score = 0.45 * name_sim + 0.40 * address_sim + 0.15 * district_or_mall
Auto-merge >= 0.90; review queue 0.75-0.90; else skip.
Uses token/character Jaccard (stdlib only; avoids SequenceMatcher crashes).
"""

from __future__ import annotations

import re

from pawplan.normalize import normalize_district

AUTO_MERGE = 0.90
REVIEW_MIN = 0.75

_MALL_EN = re.compile(
    r"\b("
    r"[A-Za-z0-9'&.+\- ]{2,}?"
    r"(?:PLAZA|MALL|CENTRE|CENTER|ESTATE|HOTEL|TOWER|GARDEN|MARKET|ARCADE|PHASE)"
    r")\b",
    re.I,
)
_MALL_ZH = re.compile(
    r"([\u4e00-\u9fff]{1,12}(?:广场|廣場|商場|商场|中心|邨|村|酒店|城|花园|花園|街市))"
)
_NON_ALNUM = re.compile(r"[^a-z0-9\u4e00-\u9fff%+&]")
_WS = re.compile(r"\s+")


def fold_name(value: str | None) -> str:
    return _WS.sub(" ", (value or "").strip().lower())


def compact_name(value: str | None) -> str:
    return _NON_ALNUM.sub("", fold_name(value))


def _names_of(row: dict) -> list[str]:
    seen: list[str] = []
    for key in (
        "name_en",
        "name_zh",
        "name",
        "match_name_en",
        "match_name_zh",
    ):
        raw = row.get(key)
        if raw is None:
            continue
        text = f"{raw}".strip()
        if text and text not in seen:
            seen.append(text)
    return seen


def similarity(left: str | None, right: str | None) -> float:
    a = fold_name(str(left) if left is not None else "")
    b = fold_name(str(right) if right is not None else "")
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if len(a) > 180:
        a = a[:180]
    if len(b) > 180:
        b = b[:180]
    ca, cb = compact_name(a), compact_name(b)
    if ca and cb and ca == cb:
        return 1.0
    if ca and cb and (ca in cb or cb in ca) and min(len(ca), len(cb)) >= 4:
        return 0.96
    ta = {t for t in a.replace(",", " ").split() if len(t) >= 2}
    tb = {t for t in b.replace(",", " ").split() if len(t) >= 2}
    if ta and tb:
        return len(ta & tb) / len(ta | tb)
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def name_similarity(left: dict, right: dict) -> float:
    best = 0.0
    for a in _names_of(left):
        for b in _names_of(right):
            best = max(best, similarity(a, b))
            if best >= 0.999:
                return 1.0
    return best


def address_similarity(left: dict, right: dict) -> float:
    return similarity(left.get("address") or "", right.get("address") or "")


def _mall_tokens(address: str | None) -> set[str]:
    text = address or ""
    tokens = {m.group(1).strip().lower() for m in _MALL_EN.finditer(text)}
    tokens.update(m.group(1) for m in _MALL_ZH.finditer(text))
    return {t for t in tokens if len(t) >= 3}


def district_or_mall_score(left: dict, right: dict) -> float:
    ld = normalize_district(left.get("district")) if left.get("district") else None
    rd = normalize_district(right.get("district")) if right.get("district") else None
    district_hit = 1.0 if ld and rd and ld == rd else 0.0
    la, ra = _mall_tokens(left.get("address")), _mall_tokens(right.get("address"))
    if la and ra:
        overlap = la & ra
        union = la | ra
        mall_hit = len(overlap) / len(union) if union else 0.0
        if overlap:
            mall_hit = max(mall_hit, 0.7)
    else:
        mall_hit = 0.0
    return max(district_hit, mall_hit)


def match_score(left: dict, right: dict) -> float:
    return (
        0.45 * name_similarity(left, right)
        + 0.40 * address_similarity(left, right)
        + 0.15 * district_or_mall_score(left, right)
    )


def classify_match(score: float) -> str:
    if score >= AUTO_MERGE:
        return "auto_merge"
    if score >= REVIEW_MIN:
        return "review"
    return "skip"


def identity_match(left: dict, right: dict) -> bool:
    """Exact folded/compact name (en or zh) plus the same district."""
    ld = normalize_district(left.get("district")) if left.get("district") else None
    rd = normalize_district(right.get("district")) if right.get("district") else None
    if not ld or not rd or ld != rd:
        return False
    left_keys = {fold_name(n) for n in _names_of(left) if fold_name(n)}
    left_keys |= {compact_name(n) for n in _names_of(left) if compact_name(n)}
    for name in _names_of(right):
        folded = fold_name(name)
        compact = compact_name(name)
        if folded and folded in left_keys:
            return True
        if compact and compact in left_keys:
            return True
    return False


def best_match(
    candidate: dict,
    restaurants: list[dict],
    *,
    min_score: float = 0.0,
) -> tuple[dict | None, float, str]:
    best_row: dict | None = None
    best_score = 0.0
    for row in restaurants:
        if identity_match(candidate, row):
            return row, 1.0, "auto_merge"
        score = match_score(candidate, row)
        if score > best_score:
            best_row, best_score = row, score
    decision = classify_match(best_score)
    if best_score < min_score or decision == "skip":
        return None, best_score, "skip"
    return best_row, best_score, decision
