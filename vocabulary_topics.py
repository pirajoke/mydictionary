"""Topic and transcription metadata independent from mutable learning progress."""

from collections import Counter


TOPIC_LABELS = {
    "greetings": "👋 Приветствия",
    "communication": "💬 Общение",
    "people": "👥 Люди и семья",
    "food": "🍽 Еда и напитки",
    "home": "🏠 Дом и быт",
    "travel": "🧭 Места и поездки",
    "time": "🕒 Время и числа",
    "work": "📚 Работа и учёба",
    "business": "💼 Бизнес и финансы",
    "health": "🩺 Здоровье и тело",
    "nature": "🌿 Природа и наука",
    "technology": "💻 Технологии",
    "actions": "🏃 Действия",
    "descriptions": "🎨 Описания и эмоции",
    "general": "📦 Разное",
}


JA_ROMAJI = {
    "こんにちは": "konnichiwa",
    "おはよう": "ohayou",
    "こんばんは": "konbanwa",
    "さようなら": "sayounara",
    "ありがとう": "arigatou",
    "すみません": "sumimasen",
    "ごめんなさい": "gomennasai",
    "お願いします": "onegaishimasu",
    "はい": "hai",
    "いいえ": "iie",
    "私": "watashi",
    "あなた": "anata",
    "人": "hito",
    "友達": "tomodachi",
    "家族": "kazoku",
    "父": "chichi",
    "母": "haha",
    "兄": "ani",
    "姉": "ane",
    "子供": "kodomo",
    "名前": "namae",
    "先生": "sensei",
    "学生": "gakusei",
    "学校": "gakkou",
    "会社": "kaisha",
    "家": "ie",
    "部屋": "heya",
    "店": "mise",
    "駅": "eki",
    "国": "kuni",
    "日本": "nihon",
    "水": "mizu",
    "お茶": "ocha",
    "ご飯": "gohan",
    "パン": "pan",
    "肉": "niku",
    "魚": "sakana",
    "野菜": "yasai",
    "果物": "kudamono",
    "りんご": "ringo",
    "今日": "kyou",
    "明日": "ashita",
    "昨日": "kinou",
    "今": "ima",
    "朝": "asa",
    "昼": "hiru",
    "夜": "yoru",
    "時間": "jikan",
    "日": "hi",
    "週": "shuu",
    "月": "tsuki",
    "年": "toshi",
    "一": "ichi",
    "二": "ni",
    "三": "san",
    "四": "yon",
    "五": "go",
    "六": "roku",
    "七": "nana",
    "八": "hachi",
    "九": "kyuu",
    "十": "juu",
    "大きい": "ookii",
    "小さい": "chiisai",
    "新しい": "atarashii",
    "古い": "furui",
    "良い": "ii",
    "悪い": "warui",
    "高い": "takai",
    "安い": "yasui",
    "暑い": "atsui",
    "寒い": "samui",
    "忙しい": "isogashii",
    "楽しい": "tanoshii",
    "好き": "suki",
    "行く": "iku",
    "来る": "kuru",
    "見る": "miru",
    "聞く": "kiku",
    "話す": "hanasu",
    "読む": "yomu",
    "書く": "kaku",
    "食べる": "taberu",
    "飲む": "nomu",
    "買う": "kau",
    "使う": "tsukau",
    "分かる": "wakaru",
    "知る": "shiru",
    "ある": "aru",
    "いる": "iru",
    "する": "suru",
    "寝る": "neru",
    "起きる": "okiru",
    "働く": "hataraku",
    "勉強する": "benkyou suru",
    "ここ": "koko",
    "そこ": "soko",
    "どこ": "doko",
    "何": "nani",
    "どう": "dou",
}


def _terms(value: str) -> frozenset[str]:
    return frozenset(value.split("|"))


LANG_TOPIC_TERMS = {
    "ja": {
        "greetings": _terms(
            "こんにちは|おはよう|こんばんは|さようなら|ありがとう|すみません|"
            "ごめんなさい|お願いします|はい|いいえ"
        ),
        "communication": _terms(
            "名前|見る|聞く|話す|読む|書く|分かる|知る|何|どう|お願いします"
        ),
        "people": _terms(
            "私|あなた|人|友達|家族|父|母|兄|姉|子供|名前|先生|学生"
        ),
        "food": _terms(
            "水|お茶|ご飯|パン|肉|魚|野菜|果物|りんご|食べる|飲む|買う"
        ),
        "home": _terms("家|部屋|店|ある|いる|ここ|そこ"),
        "travel": _terms("駅|国|日本|行く|来る|ここ|そこ|どこ"),
        "time": _terms(
            "今日|明日|昨日|今|朝|昼|夜|時間|日|週|月|年|一|二|三|四|五|六|七|八|九|十"
        ),
        "work": _terms("先生|学生|学校|会社|忙しい|読む|書く|働く|勉強する"),
        "actions": _terms(
            "行く|来る|見る|聞く|話す|読む|書く|食べる|飲む|買う|使う|分かる|"
            "知る|ある|いる|する|寝る|起きる|働く|勉強する"
        ),
        "descriptions": _terms(
            "大きい|小さい|新しい|古い|良い|悪い|高い|安い|暑い|寒い|忙しい|楽しい|好き"
        ),
    },
    "vi": {
        "greetings": _terms("xin chào|tạm biệt|cảm ơn|xin lỗi|vâng|không"),
        "communication": _terms(
            "biết|hiểu|nói|nghe|đọc|viết|bao nhiêu|ở đâu|khi nào|tại sao|gì|ai|thế nào"
        ),
        "people": _terms("tôi|bạn|anh|chị|chúng tôi|họ|người|bạn bè|gia đình|con"),
        "food": _terms("ăn|uống|nước|cơm|phở|cà phê|ngon|nhà hàng|đói|khát"),
        "home": _terms("nhà|chợ|đường"),
        "travel": _terms("đi|đến|về|đường|xe|máy bay|khách sạn|nhà hàng|bệnh viện|ở đâu"),
        "time": _terms(
            "một|hai|ba|bốn|năm|mười|bao nhiêu|khi nào|hôm nay|ngày mai|hôm qua|"
            "bây giờ|giờ|ngày|tuần|tháng"
        ),
        "work": _terms("làm|học|dạy|trường|tiền|bán|mua"),
        "actions": _terms(
            "muốn|cần|biết|hiểu|nói|nghe|đọc|viết|ăn|uống|đi|đến|về|làm|mua|bán|"
            "thích|yêu|sống|học|dạy|cho|lấy|tìm|đợi|giúp"
        ),
        "descriptions": _terms(
            "tốt|xấu|đẹp|lớn|nhỏ|mới|cũ|nóng|lạnh|ngon|đắt|trẻ|nhanh|chậm|nhiều|"
            "ít|đẹp trai|vui|buồn|mệt|đói|khát"
        ),
    },
}


EN_TOPIC_KEYWORDS = {
    "communication": (
        "cover the topic", "twang", "glance", "define", "remind", "yell", "babble",
        "request", "claim", "rumor", "eloquent", "complain", "confess", "summarize",
        "respond", "utter", "reveal", "arguing", "poll", "plead", "proofread",
    ),
    "people": (
        "fraternity", "intern", "execs", "governor", "martyr", "relative", "darling",
        "crusader", "guard", "judge", "monk", "mentor", "bride", "coward", "participants",
    ),
    "food": (
        "candy", "nutritious", "shrimp", "buns", "nutrients", "gluten", "herbal",
        "garlic", "taste", "canteen", "cereal", "pilsner", "brew", "partake",
    ),
    "home": (
        "mug", "laundry", "faucet", "napkin", "envelope", "mansion", "ceiling", "tape",
        "glue", "strap", "leash", "lodge", "outfit", "lighters",
    ),
    "travel": (
        "entry", "vehicle", "van", "yacht", "reservation", "route", "cycle parking",
        "on-site", "field", "fire station", "asylums", "pitches",
    ),
    "time": (
        "ninth", "thirties", "schedule", "still", "expected", "noon", "current",
        "elapsed", "immediately", "currently", "recently", "ever", "lasting",
    ),
    "work": (
        "effort", "activity", "intern", "schedule", "requirements", "responsibilities",
        "lesson", "opportunity", "assignment", "mentor", "taught", "literacy", "conducted",
        "proofread", "available", "output", "parameters",
    ),
    "business": (
        "consumption", "exchange", "distribution", "revenue", "execs", "promote",
        "bargain", "solvency", "inflation", "distributers", "takeover", "acquisitions",
        "insurance", "purchase", "welfare", "accountancy", "trade-off", "concession",
        "benefits", "negotiation", "debt", "acquiring", "gross", "venture", "merger",
        "offer", "afford", "underwrite", "undersell", "underpay", "current account surplus",
    ),
    "health": (
        "pneumonia", "morgue", "cure", "inhale", "injured", "sweating", "tissue",
        "aid kit", "nerve", "cell", "anxiety", "medulla", "diazepam", "inoculation",
        "tinnitus", "fever", "spleen", "consciousness", "addiction", "craving",
    ),
    "nature": (
        "contaminate", "isosceles", "bushfire", "habitat", "environment", "drought",
        "surface", "rectangles", "globes", "fiber", "particle", "silt", "cesium",
        "scale", "projection", "flow", "strand", "velocity", "density", "oak", "sow",
    ),
    "technology": (
        "conduit", "cutting edge", "backup", "amp", "compilation", "parameters", "slider",
        "script", "output", "cipher", "barcode", "gears", "release", "reboot", "disable",
    ),
    "actions": (
        "carry on", "serve", "yield", "gather", "kidnap", "adopt", "forgive", "promote",
        "extend", "conform", "govern", "remind", "throw", "beg", "wind up", "haul",
        "figure out", "feed", "behave", "bury", "soothe", "dig", "borrow", "deal with",
        "accuse", "chase", "smash", "engrave", "step aside", "reject", "follow up",
        "introduce", "let off", "resist", "engage", "stay out", "reduce", "undo",
        "retire", "break down", "allow", "avoid", "catch up", "get off", "wipe out",
        "keep", "prevent", "solve", "undertake", "strive", "retrace",
    ),
    "descriptions": (
        "oddity", "vanity", "superior", "weary", "stubborn", "tense", "unreliable",
        "idle", "disingenuous", "embarrassed", "furious", "curious", "particular",
        "worthless", "wan", "thick", "thin", "stale", "unjust", "miserable", "vague",
        "harsh", "grateful", "sturdy", "jealous", "hilarious", "fragile", "deceitful",
        "gentle", "neutral", "significant", "irresistible", "impatient", "quirky",
        "innocent", "suspicious", "decent", "humble", "smooth", "strict", "bizarre",
        "sensitive", "attractive", "arrogant", "brash", "desperate", "restless",
        "precious", "adorable", "sober", "tough", "grouchy", "livid",
    ),
}


def transcription_for(word: dict, lang: str) -> str:
    """Return a learner-friendly pronunciation or transliteration."""
    if lang == "ja":
        return JA_ROMAJI.get(word["en"], "")
    if lang == "vi":
        return word.get("ipa", "")
    return ""


def topics_for_word(word: dict, lang: str) -> tuple[str, ...]:
    """Return one or more stable topic ids for a dictionary entry."""
    term = word["en"]
    topics = []

    for topic, terms in LANG_TOPIC_TERMS.get(lang, {}).items():
        if term in terms:
            topics.append(topic)

    if lang == "en":
        haystack = " ".join((term, word.get("ru", ""))).lower()
        for topic, keywords in EN_TOPIC_KEYWORDS.items():
            if any(keyword in haystack for keyword in keywords):
                topics.append(topic)

    if not topics:
        topics.append("general")

    return tuple(dict.fromkeys(topics))


def topic_counts(words: list[dict], lang: str) -> dict[str, int]:
    """Count entries for each topic in display order."""
    counts = Counter(
        topic
        for word in words
        for topic in topics_for_word(word, lang)
    )
    return {
        topic: counts[topic]
        for topic in TOPIC_LABELS
        if counts[topic]
    }
