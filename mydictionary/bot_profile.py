"""Editable Telegram profile text with conservative platform limits."""

from __future__ import annotations

from typing import Mapping

from .localization import normalize_locale, translate


BOT_PROFILE_DEFAULTS = {
    "bot_name": "Lexi",
    "bot_short_description": "Короткие уроки и умные повторения с Lexi 🦊",
    "bot_description": (
        "Учи слова, тренируй произношение и повторяй вовремя вместе с Lexi 🦊"
    ),
    "bot_start_text": (
        "Привет, {name}! Я Lexi 🦊\n\n"
        "Твой короткий урок уже готов. Открывай по одной карточке, слушай "
        "произношение и отмечай, какие слова знаешь.\n\n"
        "Бот сам подберёт новые слова и вовремя вернёт их на повторение. "
        "Прогресс, XP и серия занятий сохраняются автоматически."
    ),
    "bot_help_text": (
        "Lexi\n\n"
        "/start — урок на сегодня и главное меню\n"
        "/learn — выбрать язык и тему\n"
        "/stats — посмотреть прогресс\n"
        "/lang — сменить язык\n"
        "/ai — AI-репетитор, кредиты и голос\n"
        "/privacy — данные и приватность\n"
        "/help — помощь\n\n"
        "В уроке нажми «Показать значение», затем оцени слово. Бот сохранит "
        "ответ и назначит следующее повторение."
    ),
}

BOT_PROFILE_LOCALIZED = {
    "en": {
        "bot_short_description": "Short lessons and smart reviews with Lexi 🦊",
        "bot_description": (
            "Learn words, practise pronunciation and review at the right time "
            "with Lexi 🦊"
        ),
    },
    "fr": {
        "bot_short_description": "Leçons courtes et révisions futées avec Lexi 🦊",
        "bot_description": (
            "Apprends des mots, travaille ta prononciation et révise au bon "
            "moment avec Lexi 🦊"
        ),
    },
    "de": {
        "bot_short_description": "Kurze Lektionen und clevere Wiederholungen mit Lexi 🦊",
        "bot_description": (
            "Lerne Wörter, übe die Aussprache und wiederhole zur richtigen "
            "Zeit mit Lexi 🦊"
        ),
    },
    "ja": {
        "bot_short_description": "Lexiと短いレッスン、かしこく復習 🦊",
        "bot_description": (
            "Lexiと単語を学び、発音を練習し、最適なタイミングで復習しよう 🦊"
        ),
    },
    "ar": {
        "bot_short_description": "دروس قصيرة ومراجعة ذكية مع Lexi 🦊",
        "bot_description": (
            "تعلّم الكلمات، تدرّب على النطق وراجع في الوقت المناسب مع Lexi 🦊"
        ),
    },
    "zh": {
        "bot_short_description": "和 Lexi 一起短时学习、智能复习 🦊",
        "bot_description": "和 Lexi 一起学单词、练发音，并在合适的时间复习 🦊",
    },
    "ru": {
        "bot_short_description": BOT_PROFILE_DEFAULTS["bot_short_description"],
        "bot_description": BOT_PROFILE_DEFAULTS["bot_description"],
    },
    "es": {
        "bot_short_description": "Lecciones cortas y repasos inteligentes con Lexi 🦊",
        "bot_description": (
            "Aprende palabras, practica la pronunciación y repasa a tiempo "
            "con Lexi 🦊"
        ),
    },
}

BOT_PROFILE_LIMITS = {
    "bot_name": 64,
    "bot_short_description": 120,
    "bot_description": 512,
    "bot_start_text": 1024,
    "bot_help_text": 4096,
}


def validate_bot_profile(values: Mapping[str, str]) -> dict[str, str]:
    result = dict(BOT_PROFILE_DEFAULTS)
    for key, limit in BOT_PROFILE_LIMITS.items():
        if key not in values:
            continue
        value = str(values[key]).strip()
        if not value:
            raise ValueError(f"{key} cannot be empty")
        if len(value) > limit:
            raise ValueError(f"{key} exceeds {limit} characters")
        result[key] = value
    return result


def localized_bot_profile(
    profile: Mapping[str, str], locale: str
) -> dict[str, str]:
    """Return Telegram profile copy for a supported interface locale."""
    selected = normalize_locale(locale)
    if selected == "ru":
        return {
            "bot_short_description": str(profile["bot_short_description"]),
            "bot_description": str(profile["bot_description"]),
        }
    return dict(BOT_PROFILE_LOCALIZED[selected])


def render_start_text(
    profile: Mapping[str, str],
    first_name: str | None,
    *,
    locale: str = "ru",
) -> str:
    selected = normalize_locale(locale, fallback="ru")
    fallback_names = {
        "en": "friend",
        "fr": "ami",
        "de": "Freund",
        "ja": "友だち",
        "ar": "صديقي",
        "zh": "朋友",
        "ru": "друг",
        "es": "amigo",
    }
    name = (first_name or "").strip() or fallback_names[selected]
    if selected == "ru":
        return str(profile["bot_start_text"]).replace("{name}", name)
    return translate("start_text", selected, name=name)
