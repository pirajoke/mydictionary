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
        "связанных слов. После изучения можно пройти тест, ввод или карточки "
        "только по этому блоку.\n\n"
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
        "/learn — выбрать тему и изучить блок из 10 слов\n"
        "/smart — адаптивная тренировка по всему словарю\n"
        "/quiz — тест с вариантами ответа\n"
        "/type — написать перевод\n"
        "/flash — карточки\n"
        "/stats — личная статистика\n"
        "/lang — сменить язык\n"
        "/ai — AI-репетитор по активному блоку\n"
        "/voice — произношение по активному блоку\n"
        "/conversation — разговорные фразы активного блока\n"
        "/voice_stop — остановить голосовую практику\n"
        "/voice_transcript — транскрипт голосовой практики\n"
        "/ai_stats — баланс AI-кредитов\n"
        "/buy — пакеты AI-кредитов за Telegram Stars\n"
        "/subscriptions — управление Stars-подписками\n"
        "/terms — условия AI-кредитов\n"
        "/paysupport — поддержка по платежам\n"
        "/privacy — хранение и удаление данных"
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
