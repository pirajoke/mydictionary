"""Editable Telegram profile text with conservative platform limits."""

from __future__ import annotations

from typing import Mapping


BOT_PROFILE_DEFAULTS = {
    "bot_name": "MY DICTIONARY",
    "bot_short_description": (
        "Слова по темам: перевод, транскрипция, произношение и тесты."
    ),
    "bot_description": (
        "MY DICTIONARY помогает учить слова на восьми языках тематическими "
        "блоками. В каждой карточке есть русский перевод, оригинальное "
        "написание, латинская транскрипция и произношение."
    ),
    "bot_start_text": (
        "Привет, {name}!\n\n"
        "MY DICTIONARY — тренажёр слов для регулярного обучения в Telegram.\n\n"
        "Выбирай английский, французский, немецкий, японский, арабский, "
        "китайский, русский или испанский язык, затем тему и блок из 10 "
        "связанных слов. После изучения выбирай тест с четырьмя "
        "вариантами или письменный режим только по этому блоку.\n\n"
        "Каждое слово показывается в одном порядке:\n"
        "1. значение по-русски;\n"
        "2. написание на выбранном языке;\n"
        "3. латинская транскрипция;\n"
        "4. голосовое произношение.\n\n"
        "Прогресс, XP, серия занятий и слова для повторения сохраняются отдельно "
        "для каждого ученика."
    ),
    "bot_help_text": (
        "MY DICTIONARY\n\n"
        "/start — главное меню\n"
        "/learn — блок из 10 слов, тест и письменный режим\n"
        "/lang — выбрать язык\n"
        "/stats — личный прогресс\n"
        "/ai — AI-репетитор, кредиты и голос\n"
        "/privacy — данные и приватность\n"
        "/help — помощь"
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


def render_start_text(profile: Mapping[str, str], first_name: str | None) -> str:
    name = (first_name or "").strip() or "друг"
    return str(profile["bot_start_text"]).replace("{name}", name)
