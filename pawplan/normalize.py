"""District and cuisine normalization for PawPlan HK."""

from __future__ import annotations

DISTRICT_ALIASES: dict[str, str] = {
    # English FEHD / common variants
    "sha tin": "Sha Tin",
    "shatin": "Sha Tin",
    "mong kok": "Mong Kok",
    "mongkok": "Mong Kok",
    "yau tsim": "Yau Tsim Mong",
    "yau tsim mong": "Yau Tsim Mong",
    "tsim sha tsui": "Yau Tsim Mong",
    "jordan": "Yau Tsim Mong",
    "yau ma tei": "Yau Tsim Mong",
    "central/western": "Central/Western",
    "central & western": "Central/Western",
    "central and western": "Central/Western",
    "central": "Central/Western",
    "western": "Central/Western",
    "wan chai": "Wan Chai",
    "wanchai": "Wan Chai",
    "eastern": "Eastern",
    "southern": "Southern",
    "sham shui po": "Sham Shui Po",
    "kowloon city": "Kowloon City",
    "wong tai sin": "Wong Tai Sin",
    "kwun tong": "Kwun Tong",
    "tsuen wan": "Tsuen Wan",
    "tuen mun": "Tuen Mun",
    "yuen long": "Yuen Long",
    "north": "North",
    "tai po": "Tai Po",
    "sai kung": "Sai Kung",
    "islands": "Islands",
    "kwai tsing": "Kwai Tsing",
    # Chinese
    "沙田": "Sha Tin",
    "旺角": "Mong Kok",
    "尖沙咀": "Yau Tsim Mong",
    "油尖旺": "Yau Tsim Mong",
    "佐敦": "Yau Tsim Mong",
    "油麻地": "Yau Tsim Mong",
    "中西区": "Central/Western",
    "中西區": "Central/Western",
    "中环": "Central/Western",
    "中環": "Central/Western",
    "湾仔": "Wan Chai",
    "灣仔": "Wan Chai",
    "东区": "Eastern",
    "東區": "Eastern",
    "南区": "Southern",
    "南區": "Southern",
    "深水埗": "Sham Shui Po",
    "九龙城": "Kowloon City",
    "九龍城": "Kowloon City",
    "黄大仙": "Wong Tai Sin",
    "黃大仙": "Wong Tai Sin",
    "观塘": "Kwun Tong",
    "觀塘": "Kwun Tong",
    "荃湾": "Tsuen Wan",
    "荃灣": "Tsuen Wan",
    "屯门": "Tuen Mun",
    "屯門": "Tuen Mun",
    "元朗": "Yuen Long",
    "北区": "North",
    "北區": "North",
    "大埔": "Tai Po",
    "西贡": "Sai Kung",
    "西貢": "Sai Kung",
    "离岛": "Islands",
    "離島": "Islands",
    "葵青": "Kwai Tsing",
    "铜锣湾": "Wan Chai",
    "銅鑼灣": "Wan Chai",
}

CANONICAL_DISTRICTS = sorted(set(DISTRICT_ALIASES.values()))

CUISINE_ALIASES: dict[str, str] = {
    "dim_sum": "dim_sum",
    "dim sum": "dim_sum",
    "yum cha": "dim_sum",
    "点心": "dim_sum",
    "飲茶": "dim_sum",
    "饮茶": "dim_sum",
    "粵式点心": "dim_sum",
    "粤式点心": "dim_sum",
    "cantonese": "cantonese",
    "粤菜": "cantonese",
    "粵菜": "cantonese",
    "广东菜": "cantonese",
    "chinese": "chinese",
    "中菜": "chinese",
    "中餐": "chinese",
    "french": "french",
    "法国": "french",
    "法國": "french",
    "法餐": "french",
    "spanish": "spanish",
    "西班牙": "spanish",
    "tapas": "spanish",
    "japanese": "japanese",
    "日本": "japanese",
    "日料": "japanese",
    "寿司": "japanese",
    "壽司": "japanese",
    "korean": "korean",
    "韩国": "korean",
    "韓國": "korean",
    "韩餐": "korean",
    "thai": "thai",
    "泰国": "thai",
    "泰國": "thai",
    "泰餐": "thai",
    "italian": "italian",
    "意大利": "italian",
    "pizza": "italian",
    "cafe": "cafe",
    "coffee": "cafe",
    "咖啡": "cafe",
    "咖啡馆": "cafe",
    "western": "western",
    "西餐": "western",
    "bakery": "bakery",
    "面包": "bakery",
    "麵包": "bakery",
    "unknown": "unknown",
}

CUISINE_LABELS: dict[str, tuple[str, str]] = {
    "dim_sum": ("点心", "Dim Sum"),
    "cantonese": ("粤菜", "Cantonese"),
    "chinese": ("中菜", "Chinese"),
    "french": ("法餐", "French"),
    "spanish": ("西班牙菜", "Spanish"),
    "japanese": ("日本菜", "Japanese"),
    "korean": ("韩国菜", "Korean"),
    "thai": ("泰国菜", "Thai"),
    "italian": ("意大利菜", "Italian"),
    "cafe": ("咖啡店", "Cafe"),
    "western": ("西餐", "Western"),
    "bakery": ("烘焙", "Bakery"),
    "unknown": ("未标注", "Unknown"),
}

# Keyword heuristics for cuisine enrichment from shop names.
CUISINE_NAME_HINTS: list[tuple[str, str, float]] = [
    ("dim sum", "dim_sum", 0.8),
    ("yum cha", "dim_sum", 0.8),
    ("tea house", "dim_sum", 0.7),
    ("tea restaurant", "dim_sum", 0.65),
    ("点心", "dim_sum", 0.85),
    ("飲茶", "dim_sum", 0.85),
    ("饮茶", "dim_sum", 0.85),
    ("茶楼", "dim_sum", 0.75),
    ("茶樓", "dim_sum", 0.75),
    ("cantonese", "cantonese", 0.75),
    ("粤", "cantonese", 0.65),
    ("粵", "cantonese", 0.65),
    ("french", "french", 0.8),
    ("法式", "french", 0.75),
    ("bistro", "western", 0.55),
    ("japanese", "japanese", 0.8),
    ("sushi", "japanese", 0.8),
    ("ramen", "japanese", 0.75),
    ("日本", "japanese", 0.75),
    ("寿司", "japanese", 0.8),
    ("壽司", "japanese", 0.8),
    ("拉面", "japanese", 0.7),
    ("拉麵", "japanese", 0.7),
    ("korean", "korean", 0.8),
    ("韩国", "korean", 0.75),
    ("韓國", "korean", 0.75),
    ("thai", "thai", 0.8),
    ("泰国", "thai", 0.75),
    ("泰國", "thai", 0.75),
    ("italian", "italian", 0.8),
    ("pizza", "italian", 0.75),
    ("pasta", "italian", 0.7),
    ("意大利", "italian", 0.75),
    ("coffee shop", "cafe", 0.85),
    ("cafe", "cafe", 0.7),
    ("coffee", "cafe", 0.75),
    ("arabica", "cafe", 0.85),
    ("starbucks", "cafe", 0.9),
    ("咖啡", "cafe", 0.8),
    ("bakery", "bakery", 0.8),
    ("面包", "bakery", 0.75),
    ("麵包", "bakery", 0.75),
    ("hot pot", "chinese", 0.7),
    ("火锅", "chinese", 0.75),
    ("火鍋", "chinese", 0.75),
    ("bbq", "chinese", 0.55),
    ("restaurant", "chinese", 0.35),
]


def normalize_district(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    key = raw.lower()
    if key in DISTRICT_ALIASES:
        return DISTRICT_ALIASES[key]
    if raw in DISTRICT_ALIASES:
        return DISTRICT_ALIASES[raw]
    # substring match for Chinese / mixed utterances
    for alias, canonical in DISTRICT_ALIASES.items():
        if alias in raw or alias in key:
            return canonical
    # already canonical?
    for canonical in CANONICAL_DISTRICTS:
        if raw.lower() == canonical.lower():
            return canonical
    return raw


def normalize_cuisine(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    key = raw.lower()
    if key in CUISINE_ALIASES:
        return CUISINE_ALIASES[key]
    if raw in CUISINE_ALIASES:
        return CUISINE_ALIASES[raw]
    for alias, code in CUISINE_ALIASES.items():
        if alias in raw or alias in key:
            return code
    return key.replace(" ", "_")


def infer_cuisine_from_name(name_en: str, name_zh: str) -> tuple[str, float]:
    blob = f"{name_en or ''} {name_zh or ''}".strip()
    if not blob:
        return "unknown", 0.1
    lower = blob.lower()
    best_code = "unknown"
    best_score = 0.1
    for needle, code, score in CUISINE_NAME_HINTS:
        if needle.lower() in lower or needle in blob:
            if score > best_score:
                best_code, best_score = code, score
    return best_code, best_score


def detect_district_in_text(text: str) -> str | None:
    """Find first district mentioned in free text (for agent fallback)."""
    if not text:
        return None
    # Prefer longer Chinese aliases first
    items = sorted(DISTRICT_ALIASES.items(), key=lambda kv: len(kv[0]), reverse=True)
    lower = text.lower()
    for alias, canonical in items:
        if alias in text or alias in lower:
            return canonical
    return None
