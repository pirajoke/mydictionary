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

# Telegram profile metadata can vary by the Telegram client language, but it
# cannot follow the per-chat interface language chosen inside Lexi. Keep every
# published language slot on the owner-selected Russian fallback instead.
BOT_PROFILE_LOCALIZED = {
    locale: {
        "bot_short_description": BOT_PROFILE_DEFAULTS["bot_short_description"],
        "bot_description": BOT_PROFILE_DEFAULTS["bot_description"],
    }
    for locale in ("ar", "de", "en", "es", "fr", "ja", "ru", "zh")
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
    """Return the fixed Russian Telegram profile for every language slot."""
    normalize_locale(locale)
    return {
        "bot_short_description": str(profile["bot_short_description"]),
        "bot_description": str(profile["bot_description"]),
    }


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
