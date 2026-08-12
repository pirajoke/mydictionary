"""Editable Telegram profile text with conservative platform limits."""

from __future__ import annotations

from typing import Mapping

from .localization import normalize_locale, translate


BOT_PROFILE_DEFAULTS = {
    "bot_name": "MY DICTIONARY",
    "bot_short_description": (
        "Короткий урок каждый день: карточки, произношение и повторение."
    ),
    "bot_description": (
        "MY DICTIONARY помогает учить слова прямо в Telegram. Открой урок на "
        "сегодня, пройди карточки с произношением и повтори слова в нужный момент. "
        "Доступны 8 языковых наборов с русскими значениями."
    ),
    "bot_start_text": (
        "Привет, {name}! 👋\n\n"
        "Твой короткий урок уже готов. Открывай по одной карточке, слушай "
        "произношение и отмечай, какие слова знаешь.\n\n"
        "Бот сам подберёт новые слова и вовремя вернёт их на повторение. "
        "Прогресс, XP и серия занятий сохраняются автоматически."
    ),
    "bot_help_text": (
        "MY DICTIONARY\n\n"
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
