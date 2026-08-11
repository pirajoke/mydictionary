#!/usr/bin/env python3
"""MY DICTIONARY multilingual word-learning Telegram bot."""

import asyncio
from collections.abc import Iterator, MutableMapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
import json
import random
import re
import secrets
import logging
import os
import time
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

import yaml
from telegram import (
    Bot,
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.error import Conflict, TelegramError
from telegram.helpers import escape_markdown
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes,
    MessageHandler, PollAnswerHandler, PreCheckoutQueryHandler, filters
)

from tts import get_audio
from vocabulary_topics import (
    topic_counts,
    topics_for_word,
    transcription_for,
)
from mydictionary.ai_tutor import (
    AIConfigurationError,
    AIProviderError,
    AIUsageRecoveryError,
    AITutorService,
    AITutorSettings,
    TutorContext,
    TutorWord,
    build_openai_tutor_service,
    render_tutor_answer,
)
from mydictionary.admin_store import AdminStore
from mydictionary.assistant_speech import build_mirror_speech_renderer
from mydictionary.billing import (
    BillingConfigurationError,
    BillingService,
    BillingSettings,
    BillingValidationError,
    TelegramStarsGateway,
)
from mydictionary.bot_profile import render_start_text
from mydictionary.catalog import ContentPack, load_catalog
from mydictionary.content import (
    answer_matches,
    example_meaning_text,
    example_target_text,
    meaning_display_text,
    meaning_text,
    speech_text,
    target_text,
)
from mydictionary.config import mirror_voice_output_enabled
from mydictionary.legacy import import_legacy_user
from mydictionary.mirror_assistant import (
    MIRROR_ADMIN_DEFAULTS,
    MIRROR_STYLE_LABELS,
    MirrorMemorySettings,
    append_mirror_turn,
    build_mirror_progress_summary,
    build_mirror_provider_payload,
    classify_mirror_intent,
    grounded_progress_snapshot,
    normalize_mirror_style,
    recent_mirror_dialogue,
    render_mirror_capabilities,
    render_mirror_greeting,
)
from mydictionary.readiness import BotHeartbeat, heartbeat_path
from mydictionary.runtime_secrets import load_runtime_secret_files
from mydictionary.privacy import erase_user_learning_data
from mydictionary.safety import PersistentRateLimiter, SafetySettings
from mydictionary.storage import (
    ACCESS_STATUSES,
    AIQuotaExceeded,
    DatabaseStore,
    WORD_PROGRESS_DEFAULTS,
    vocabulary_id_for,
)
from mydictionary.telegram_runtime import TelegramRuntimeSettings
from mydictionary.voice_tutor import (
    VoiceConfigurationError,
    VoiceProviderError,
    VoiceSessionError,
    VoiceSessionState,
    VoiceTutorService,
    VoiceTutorSettings,
    VoiceUsageRecoveryError,
    VoiceWord,
    build_openai_voice_service,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
# Telegram API URLs contain the bot token. Keep request-level HTTPX logging out
# of production logs while retaining application lifecycle and error messages.
logging.getLogger("httpx").setLevel(logging.WARNING)

BASE_DIR = Path(__file__).parent
DATA_DIR = Path(os.environ.get("DATA_DIR", str(BASE_DIR)))
WELCOME_BANNER_PATH = BASE_DIR / "assets" / "mydictionary-welcome.jpg"

# Config: owner-only token file, then env vars, then config.yaml fallback.
_runtime_environment = load_runtime_secret_files(os.environ)
for _secret_name in ("BOT_TOKEN", "TELEGRAM_TEST_USER_ID"):
    if (
        _runtime_environment.get(_secret_name)
        and not os.environ.get(_secret_name)
    ):
        os.environ[_secret_name] = _runtime_environment[_secret_name]
BOT_TOKEN = os.environ.get("BOT_TOKEN")
LEGACY_USER_ID_RAW = os.environ.get("ALLOWED_USER_ID")

if not BOT_TOKEN and (BASE_DIR / "config.yaml").exists():
    CONFIG = yaml.safe_load((BASE_DIR / "config.yaml").read_text())
    BOT_TOKEN = CONFIG["telegram"]["bot_token"]
    LEGACY_USER_ID_RAW = (
        LEGACY_USER_ID_RAW or CONFIG["telegram"].get("allowed_user_id")
    )

LEGACY_USER_ID = int(LEGACY_USER_ID_RAW) if LEGACY_USER_ID_RAW else None
# Compatibility alias for operational scripts that still inspect this value.
ALLOWED_USER = LEGACY_USER_ID


def _configured_user_ids() -> set[int]:
    values = os.environ.get("ALLOWED_USER_IDS", "").split(",")
    result = {int(value.strip()) for value in values if value.strip()}
    if LEGACY_USER_ID is not None:
        result.add(LEGACY_USER_ID)
    return result


ALLOWED_USER_IDS = _configured_user_ids()


def _configured_admin_ids() -> set[int]:
    values = os.environ.get("ADMIN_TELEGRAM_USER_IDS", "").split(",")
    result = {int(value.strip()) for value in values if value.strip()}
    if LEGACY_USER_ID is not None:
        result.add(LEGACY_USER_ID)
    return result


ADMIN_USER_IDS = _configured_admin_ids()


def _configured_access_mode() -> str:
    mode = os.environ.get("BOT_ACCESS_MODE", "allowlist").strip().lower()
    if mode not in {"allowlist", "pilot", "public"}:
        raise RuntimeError(
            "BOT_ACCESS_MODE must be 'allowlist', 'pilot', or 'public'"
        )
    return mode


BOT_ACCESS_MODE = _configured_access_mode()
AI_SETTINGS = AITutorSettings.from_env()
MIRROR_MEMORY_SETTINGS = MirrorMemorySettings.from_env(
    ai_consent_version=AI_SETTINGS.consent_version
)
BILLING_SETTINGS = BillingSettings.from_env()
SAFETY_SETTINGS = SafetySettings.from_env()
VOICE_SETTINGS = VoiceTutorSettings.from_env()
TELEGRAM_RUNTIME = TelegramRuntimeSettings.from_env()
TELEGRAM_RUNTIME.validate_billing_process(
    billing_enabled=BILLING_SETTINGS.enabled,
    terms_version=BILLING_SETTINGS.terms_version,
)
BOT_HEARTBEAT = BotHeartbeat(
    heartbeat_path(DATA_DIR),
    release_sha=os.environ.get("RELEASE_SHA", BASE_DIR.resolve().name),
    access_mode=BOT_ACCESS_MODE,
)

# ---------------------------------------------------------------------------
# Data layer — multi-language
# ---------------------------------------------------------------------------

CATALOG = load_catalog(BASE_DIR)
# Legacy JSON import namespaces stay fixed as new packs are added to the catalog.
LEGACY_LANG_FILES = {
    "en": "words.json",
    "vi": "words_vi.json",
    "ja": "words_ja.json",
}

PROGRESS_DEFAULTS = {
    "total_correct": 0, "total_wrong": 0, "sessions": 0,
    "xp": 0, "level": 1,
    "streak": 0, "streak_best": 0, "last_activity_date": None,
    "today_xp": 0, "today_date": None,
    "active_lang": "en",
    "active_pack_id": None,
}

def load_progress() -> dict:
    p = DATA_DIR / "progress.json"
    if not p.exists():
        # Fallback: copy from BASE_DIR if exists there
        base_p = BASE_DIR / "progress.json"
        if base_p.exists() and p != base_p:
            import shutil
            p.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(base_p, p)
    data = {}
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    for k, v in PROGRESS_DEFAULTS.items():
        data.setdefault(k, v)
    return data

PACK_DICTS: dict[str, list[dict]] = {
    pack.pack_id: [dict(word, **WORD_PROGRESS_DEFAULTS) for word in CATALOG.words(pack)]
    for pack in CATALOG.packs
}
_FALLBACK_PROGRESS: dict = load_progress()
_STORE: DatabaseStore | None = None
_AI_TUTOR: AITutorService | None = None
_BILLING: BillingService | None = None
_VOICE_TUTOR: VoiceTutorService | None = None
LAST_PRONUNCIATION_MESSAGES_KEY = "last_pronunciation_messages"


def database_url() -> str:
    configured = os.environ.get("DATABASE_URL", "").strip()
    if configured:
        if configured.startswith("postgres://"):
            return configured.replace("postgres://", "postgresql+psycopg://", 1)
        if configured.startswith("postgresql://"):
            return configured.replace(
                "postgresql://", "postgresql+psycopg://", 1
            )
        return configured
    allow_sqlite = os.environ.get("ALLOW_SQLITE_DEV", "false").strip().lower()
    if allow_sqlite not in {"1", "true", "yes", "on"}:
        raise RuntimeError(
            "DATABASE_URL is required; set ALLOW_SQLITE_DEV=true only for local use"
        )
    sqlite_path = (DATA_DIR / "mydictionary.db").resolve()
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{sqlite_path}"


def get_store() -> DatabaseStore:
    global _STORE
    if _STORE is None:
        _STORE = DatabaseStore(database_url())
    return _STORE


def get_bot_profile() -> dict[str, str]:
    """Load admin-editable bot text without caching runtime changes."""
    return AdminStore(get_store()).get_settings()


def get_ai_tutor_service() -> AITutorService:
    global _AI_TUTOR
    if _AI_TUTOR is None:
        _AI_TUTOR = build_openai_tutor_service(get_store(), AI_SETTINGS)
    return _AI_TUTOR


def get_billing_service() -> BillingService:
    global _BILLING
    if _BILLING is None:
        _BILLING = BillingService(get_store(), BILLING_SETTINGS)
    return _BILLING


def get_voice_tutor_service() -> VoiceTutorService:
    global _VOICE_TUTOR
    if _VOICE_TUTOR is None:
        _VOICE_TUTOR = build_openai_voice_service(get_store(), VOICE_SETTINGS)
    return _VOICE_TUTOR


@dataclass
class LearnerRuntime:
    user_id: int
    store: DatabaseStore
    progress: dict
    role: str = "learner"
    access_status: str = "pending"
    onboarding_completed: bool = False
    words_by_lang: dict[str, list[dict]] = field(default_factory=dict)

    def words(self, language_or_pack: str) -> list[dict]:
        pack = CATALOG.get(language_or_pack)
        if pack is None:
            if (
                language_or_pack == self.progress.get("active_lang")
                and self.progress.get("active_pack_id")
            ):
                active_pack = CATALOG.get(self.progress["active_pack_id"])
                if (
                    active_pack
                    and active_pack.target_language == language_or_pack
                ):
                    pack = active_pack
            pack = pack or CATALOG.pack_for_language(language_or_pack, self.role)
        if pack is None or not pack.visible_to(self.role):
            raise PermissionError("Content pack is not available to this user")
        if pack.pack_id not in self.words_by_lang:
            stored = self.store.load_word_progress(self.user_id, pack.storage_key)
            words = [dict(word) for word in PACK_DICTS[pack.pack_id]]
            for word in words:
                values = stored.get(vocabulary_id_for(word))
                if values is not None:
                    word.update(values)
            self.words_by_lang[pack.pack_id] = words
        return self.words_by_lang[pack.pack_id]


_ACTIVE_RUNTIME: ContextVar[LearnerRuntime | None] = ContextVar(
    "active_learner_runtime", default=None
)


class ProgressProxy(MutableMapping):
    """Dict-compatible view of the learner bound to the current update."""

    def __init__(self, fallback: dict):
        self.fallback = fallback

    def _data(self) -> dict:
        runtime = _ACTIVE_RUNTIME.get()
        return runtime.progress if runtime else self.fallback

    def __getitem__(self, key):
        return self._data()[key]

    def __setitem__(self, key, value):
        self._data()[key] = value

    def __delitem__(self, key):
        del self._data()[key]

    def __iter__(self) -> Iterator:
        return iter(self._data())

    def __len__(self) -> int:
        return len(self._data())


PROGRESS = ProgressProxy(_FALLBACK_PROGRESS)


def W(language: str | None = None) -> list[dict]:
    """Return vocabulary content overlaid with the active user's progress."""
    selected = language
    if selected is None:
        active_pack = CATALOG.get(PROGRESS.get("active_pack_id"))
        selected = (
            active_pack.pack_id
            if (
                active_pack
                and active_pack.target_language == PROGRESS["active_lang"]
            )
            else PROGRESS["active_lang"]
        )
    runtime = _ACTIVE_RUNTIME.get()
    if runtime:
        return runtime.words(selected)
    pack = CATALOG.get(selected) or CATALOG.pack_for_language(selected, "admin")
    if pack is None:
        raise KeyError(f"Unknown content pack or language: {selected}")
    return PACK_DICTS[pack.pack_id]


def visible_packs() -> tuple[ContentPack, ...]:
    runtime = _ACTIVE_RUNTIME.get()
    return CATALOG.visible_packs(runtime.role if runtime else "admin")


def visible_pack_for_language(language: str) -> ContentPack | None:
    runtime = _ACTIVE_RUNTIME.get()
    role = runtime.role if runtime else "admin"
    return CATALOG.pack_for_language(language, role)


def active_content_pack() -> ContentPack:
    pack = CATALOG.get(PROGRESS.get("active_pack_id"))
    if (
        pack is None
        or pack.target_language != PROGRESS["active_lang"]
        or pack not in visible_packs()
    ):
        pack = visible_pack_for_language(PROGRESS["active_lang"])
    if pack is None:
        raise PermissionError("No active content pack")
    return pack


def activate_content_pack(pack: ContentPack, *, source: str) -> None:
    runtime = _ACTIVE_RUNTIME.get()
    if runtime is None or not pack.visible_to(runtime.role):
        raise PermissionError("Content pack is not available to this user")
    runtime.store.activate_pack(
        runtime.user_id,
        pack_id=pack.pack_id,
        language=pack.target_language,
        source=source,
    )
    PROGRESS["active_pack_id"] = pack.pack_id
    PROGRESS["active_lang"] = pack.target_language


def record_product_event(
    event_name: str,
    *,
    properties: dict | None = None,
    session_id: str | None = None,
    source: str | None = None,
) -> None:
    """Record analytics without allowing telemetry failures to break learning."""
    runtime = _ACTIVE_RUNTIME.get()
    if runtime is None:
        return
    try:
        runtime.store.record_event(
            runtime.user_id,
            event_name,
            properties=properties,
            session_id=session_id,
            source=source,
        )
    except Exception as exc:
        logger.warning("Product analytics failed for %s: %s", event_name, exc)


def save_progress(prog: MutableMapping):
    runtime = _ACTIVE_RUNTIME.get()
    if runtime:
        runtime.store.save_profile(runtime.user_id, dict(prog))
        return
    p = DATA_DIR / "progress.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(dict(prog), f, ensure_ascii=False, indent=2)


def save_answer_state(index: int) -> None:
    runtime = _ACTIVE_RUNTIME.get()
    if runtime:
        pack = CATALOG.get(PROGRESS.get("active_pack_id"))
        if pack is None or pack.target_language != PROGRESS["active_lang"]:
            pack = visible_pack_for_language(PROGRESS["active_lang"])
            if pack is None:
                raise PermissionError("Content pack is not available to this user")
            PROGRESS["active_pack_id"] = pack.pack_id
        runtime.store.save_learning_state(
            runtime.user_id,
            dict(PROGRESS),
            pack.storage_key,
            index,
            W()[index],
        )
        return

    # Compatibility fallback for direct, non-Telegram use during migration.
    save_progress(PROGRESS)


def _runtime_for_user(telegram_user) -> LearnerRuntime:
    store = get_store()
    user_id = int(telegram_user.id)
    configured_role = "admin" if user_id in ADMIN_USER_IDS else None
    store.ensure_user(telegram_user, role=configured_role)
    if LEGACY_USER_ID is not None and user_id == LEGACY_USER_ID:
        import_legacy_user(
            store,
            user_id,
            DATA_DIR,
            BASE_DIR,
            LEGACY_LANG_FILES,
            PROGRESS_DEFAULTS,
        )
    product = store.product_profile(user_id)
    role = product["role"]
    if role == "admin" and (
        product["onboarding_completed_at"] is None
        or product["active_pack_id"] is None
    ):
        pack = (
            CATALOG.pack_for_language(product["active_lang"], "admin")
            or CATALOG.require("pirajoke-en-personal")
        )
        store.activate_pack(
            user_id,
            pack_id=pack.pack_id,
            language=pack.target_language,
            source="admin_bootstrap",
        )
        store.update_product_profile(
            user_id,
            native_language=product["native_language"] or "ru",
            learning_goal=product["learning_goal"] or "personal",
            daily_word_goal=product["daily_word_goal"] or 10,
            complete_onboarding=True,
        )
        product = store.product_profile(user_id)
    return LearnerRuntime(
        user_id=user_id,
        store=store,
        progress=store.load_profile(user_id, PROGRESS_DEFAULTS),
        role=product["role"],
        access_status=product["access_status"],
        onboarding_completed=product["onboarding_completed_at"] is not None,
    )


@contextmanager
def learner_scope(telegram_user):
    """Bind one learner to all legacy helper functions for one update."""
    token = _ACTIVE_RUNTIME.set(_runtime_for_user(telegram_user))
    try:
        yield _ACTIVE_RUNTIME.get()
    finally:
        _ACTIVE_RUNTIME.reset(token)

# ---------------------------------------------------------------------------
# XP / Levels / Streaks
# ---------------------------------------------------------------------------

XP_CORRECT = 10
XP_WRONG = 2
XP_SESSION = 25       # completing a block
XP_STREAK_BONUS = 15  # per streak day, awarded once daily

LEVELS = [
    (0,    "Новичок"),
    (100,  "Ученик"),
    (300,  "Студент"),
    (600,  "Знаток"),
    (1000, "Лингвист"),
    (1500, "Полиглот"),
    (2500, "Мудрец"),
    (4000, "Мастер"),
    (6000, "Легенда"),
]

def get_level(xp: int) -> tuple[int, str, int]:
    """Return (level_num, title, xp_for_next)."""
    for i in range(len(LEVELS) - 1, -1, -1):
        if xp >= LEVELS[i][0]:
            next_xp = LEVELS[i + 1][0] if i + 1 < len(LEVELS) else None
            return i + 1, LEVELS[i][1], next_xp
    return 1, LEVELS[0][1], LEVELS[1][0]

def update_streak():
    """Update streak based on today's date. Returns streak bonus XP (0 if already claimed today)."""
    today = datetime.now().strftime("%Y-%m-%d")
    bonus = 0

    if PROGRESS["last_activity_date"] == today:
        return 0  # already active today, no bonus

    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    if PROGRESS["last_activity_date"] == yesterday:
        PROGRESS["streak"] += 1
    elif PROGRESS["last_activity_date"] is None:
        PROGRESS["streak"] = 1
    else:
        PROGRESS["streak"] = 1  # streak broken

    PROGRESS["last_activity_date"] = today
    PROGRESS["streak_best"] = max(PROGRESS["streak_best"], PROGRESS["streak"])
    PROGRESS["today_xp"] = 0
    PROGRESS["today_date"] = today

    bonus = XP_STREAK_BONUS * PROGRESS["streak"]
    PROGRESS["xp"] += bonus
    PROGRESS["today_xp"] += bonus
    return bonus

def award_xp(amount: int) -> int:
    """Add XP, return new total."""
    today = datetime.now().strftime("%Y-%m-%d")
    if PROGRESS.get("today_date") != today:
        PROGRESS["today_xp"] = 0
        PROGRESS["today_date"] = today
    PROGRESS["xp"] += amount
    PROGRESS["today_xp"] += amount
    lvl, _, _ = get_level(PROGRESS["xp"])
    PROGRESS["level"] = lvl
    return PROGRESS["xp"]

def format_xp_line(xp_earned: int, streak_bonus: int = 0) -> str:
    """Format XP feedback line."""
    parts = [f"+{xp_earned} XP"]
    if streak_bonus > 0:
        parts.append(f"+{streak_bonus} за серию")
    lvl, title, _ = get_level(PROGRESS["xp"])
    parts.append(f"[Уровень {lvl} · {title}]")
    return " | ".join(parts)

def get_example(idx: int) -> str:
    """Return example sentence if available."""
    word = W()[idx]
    target_example = example_target_text(word)
    meaning_example = example_meaning_text(word)
    if not target_example:
        return ""
    example = target_example
    if meaning_example:
        example = f"{target_example} — {meaning_example}"
    return f"\n💡 _{escape_markdown(example)}_"


def _content_pack(pack_or_language: ContentPack | str | None = None) -> ContentPack:
    if isinstance(pack_or_language, ContentPack):
        return pack_or_language
    if pack_or_language:
        pack = CATALOG.get(pack_or_language) or visible_pack_for_language(
            pack_or_language
        )
        if pack is not None:
            return pack
    return active_content_pack()


def _directional_text(value: str, direction: str) -> str:
    """Keep RTL target text isolated inside mixed-direction Telegram messages."""
    if direction == "rtl":
        return f"\u2067{value}\u2069"
    return value


def format_target_word(
    word: dict, pack_or_language: ContentPack | str | None = None
) -> str:
    """Format a readable target-language word with its transcription."""
    pack = _content_pack(pack_or_language)
    transcription = transcription_for(word, pack.target_language)
    target = _directional_text(target_text(word), pack.direction)
    position = pack.pronunciation.transcription_position
    if transcription and position == "before":
        return f"{transcription} ({target})"
    if transcription and position == "after":
        return f"{target} {transcription}"
    return target

def format_word_label(idx: int) -> str:
    """Format a question prompt without exposing the Russian answer."""
    w = W()[idx]
    pack = active_content_pack()
    return f"{pack.flag} *{escape_markdown(format_target_word(w, pack))}*"


def format_word_details(idx: int) -> str:
    """Format a revealed card: meaning first, then target and transcription."""
    word = W()[idx]
    pack = active_content_pack()
    lines = [
        f"{pack.meaning_flag} *{escape_markdown(meaning_display_text(word))}*",
        f"{pack.flag} *{escape_markdown(format_target_word(word, pack))}*",
    ]
    return "\n".join(lines)


def card_topic_visual(idx: int) -> str:
    """Use the content taxonomy as a lightweight visual cue on every card."""
    topics = topics_for_word(W()[idx], PROGRESS["active_lang"])
    label = CATALOG.topic_labels.get(topics[0], "✨") if topics else "✨"
    return label.split(" ", 1)[0]


def card_progress_text(user_data: dict) -> str:
    total = max(1, len(user_data.get("block_indices", [])))
    current = min(total, int(user_data.get("block_pos", 0)) + 1)
    filled = max(1, (current * 5 + total - 1) // total)
    return f"{'▰' * filled}{'▱' * (5 - filled)}"


def format_learning_card_front(user_data: dict, idx: int) -> str:
    total = len(user_data.get("block_indices", []))
    position = int(user_data.get("block_pos", 0)) + 1
    return (
        f"{card_topic_visual(idx)}\n\n"
        f"*Карточка {position} из {total}*  ·  {card_progress_text(user_data)}\n\n"
        f"{format_word_label(idx)}\n\n"
        "Сначала вспомни значение."
    )


def format_learning_card_back(user_data: dict, idx: int) -> str:
    total = len(user_data.get("block_indices", []))
    position = int(user_data.get("block_pos", 0)) + 1
    return (
        f"{card_topic_visual(idx)}\n\n"
        f"*Карточка {position} из {total}*  ·  {card_progress_text(user_data)}\n\n"
        f"{format_word_details(idx)}{get_example(idx)}"
    )


def format_plain_word_prompt(idx: int) -> str:
    """Format a compact prompt for Telegram surfaces without Markdown."""
    word = W()[idx]
    pack = active_content_pack()
    return f"{pack.flag} {format_target_word(word, pack)}"

def get_lang_keyboard():
    """Return one-time ReplyKeyboardMarkup with language buttons."""
    buttons = [pack.label for pack in visible_packs()]
    rows = [buttons[index:index + 2] for index in range(0, len(buttons), 2)]
    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def language_picker_keyboard() -> InlineKeyboardMarkup:
    current_pack_id = PROGRESS.get("active_pack_id")
    rows = []
    for pack in visible_packs():
        marker = " ✓" if pack.pack_id == current_pack_id else ""
        learned = sum(
            1 for word in W(pack.pack_id) if word["correct_count"] >= 3
        )
        rows.append([
            InlineKeyboardButton(
                f"{pack.label} ({learned}/{pack.entry_count}){marker}",
                callback_data=f"lang:{pack.pack_id}",
            )
        ])
    return InlineKeyboardMarkup(rows)

PACK_SWITCH_TEXTS = {pack.label: pack.pack_id for pack in CATALOG.packs}
PACK_SWITCH_PATTERN = r"^(?:" + "|".join(
    re.escape(label) for label in PACK_SWITCH_TEXTS
) + r")$"

def forvo_button(idx: int) -> InlineKeyboardButton:
    """Return an inline button linking to Forvo pronunciation page."""
    word = W()[idx]
    pack = active_content_pack()
    encoded_word = quote(target_text(word).replace(" ", "_"), safe="")
    url = f"https://forvo.com/word/{encoded_word}/#{pack.target_language}"
    return InlineKeyboardButton("🔊 Forvo", url=url)


async def replace_previous_pronunciation(
    chat_id: int,
    sent_message,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Keep at most one bot pronunciation message per user and chat."""
    message_id = getattr(sent_message, "message_id", None)
    if (
        not isinstance(message_id, int)
        or isinstance(message_id, bool)
        or message_id <= 0
    ):
        return
    user_data = getattr(context, "user_data", None)
    if not isinstance(user_data, MutableMapping):
        return
    messages = user_data.get(LAST_PRONUNCIATION_MESSAGES_KEY)
    if not isinstance(messages, MutableMapping):
        messages = {}
        user_data[LAST_PRONUNCIATION_MESSAGES_KEY] = messages
    chat_key = str(chat_id)
    previous_message_id = messages.get(chat_key)
    if (
        not isinstance(previous_message_id, int)
        or isinstance(previous_message_id, bool)
        or previous_message_id <= 0
        or previous_message_id == message_id
    ):
        messages[chat_key] = message_id
        return
    newest_message_id = max(previous_message_id, message_id)
    obsolete_message_id = min(previous_message_id, message_id)
    messages[chat_key] = newest_message_id
    try:
        await context.bot.delete_message(
            chat_id=chat_id,
            message_id=obsolete_message_id,
        )
    except TelegramError as exc:
        logger.info(
            "Previous pronunciation could not be deleted: error_type=%s",
            type(exc).__name__,
        )


async def send_pronunciation_audio(
    *,
    chat_id: int,
    audio,
    title: str,
    context: ContextTypes.DEFAULT_TYPE,
):
    """Send TTS as voice/audio and retire the preceding pronunciation."""
    try:
        sent_message = await context.bot.send_voice(chat_id=chat_id, voice=audio)
    except Exception:
        if hasattr(audio, "seek"):
            audio.seek(0)
        sent_message = await context.bot.send_audio(
            chat_id=chat_id,
            audio=audio,
            title=title,
        )
    await replace_previous_pronunciation(chat_id, sent_message, context)
    return sent_message


async def send_pronunciation(chat_id: int, idx: int, context: ContextTypes.DEFAULT_TYPE):
    """Generate and send voice pronunciation for the word at idx."""
    if not callable(getattr(context.bot, "send_voice", None)):
        return
    try:
        word = W()[idx]
        pack = active_content_pack()
        audio = await get_audio(
            speech_text(word),
            voice=pack.pronunciation.tts_voice,
            rate=pack.pronunciation.tts_rate,
            cache_namespace=f"{pack.pack_id}:v{pack.content_version}",
        )
        await send_pronunciation_audio(
            chat_id=chat_id,
            audio=audio,
            title=target_text(word),
            context=context,
        )
    except Exception as exc:
        logger.warning(
            "TTS failed for word %s: error_type=%s", idx, type(exc).__name__
        )

def adaptive_mode(idx: int) -> str:
    """Pick quiz type based on word strength. Weak → quiz (recognition), strong → type (recall)."""
    w = W()[idx]
    if w["correct_count"] >= 3:
        return "type"
    return "quiz"

def build_quiz_options(idx: int) -> tuple[list[str], int]:
    """Build 4 options for a quiz question. Returns (options, correct_index)."""
    correct_ru = meaning_text(W()[idx])
    distractors = set()
    attempts = 0
    while len(distractors) < 3 and attempts < 50:
        r = random.choice(W())
        candidate = meaning_text(r)
        if candidate != correct_ru:
            distractors.add(candidate)
        attempts += 1
    options = list(distractors) + [correct_ru]
    random.shuffle(options)
    correct_pos = options.index(correct_ru)
    return options, correct_pos

# ---------------------------------------------------------------------------
# Spaced repetition helpers
# ---------------------------------------------------------------------------

def pick_word(exclude_idx: int | None = None) -> int:
    """Pick next word: overdue first, then new, then random."""
    now = datetime.now().isoformat()
    overdue = []
    new_words = []
    for i, w in enumerate(W()):
        if i == exclude_idx:
            continue
        if w["next_review"] is None and w["correct_count"] == 0:
            new_words.append(i)
        elif w["next_review"] and w["next_review"] <= now:
            overdue.append(i)

    if overdue:
        return random.choice(overdue)
    if new_words:
        return random.choice(new_words)
    # All reviewed — pick least recently seen
    candidates = [(i, w) for i, w in enumerate(W()) if i != exclude_idx]
    candidates.sort(key=lambda x: x[1].get("last_seen") or "")
    return candidates[0][0] if candidates else 0

def mark_correct(idx: int) -> tuple[int, int]:
    """Mark word correct. Returns (xp_earned, streak_bonus)."""
    w = W()[idx]
    w["correct_count"] += 1
    w["last_seen"] = datetime.now().isoformat()
    intervals = [1, 3, 7, 14, 30, 60]
    level = min(w["correct_count"], len(intervals)) - 1
    w["interval"] = intervals[max(level, 0)]
    w["next_review"] = (datetime.now() + timedelta(days=w["interval"])).isoformat()
    PROGRESS["total_correct"] += 1
    streak_bonus = update_streak()
    award_xp(XP_CORRECT)
    save_answer_state(idx)
    return XP_CORRECT, streak_bonus

def mark_wrong(idx: int) -> tuple[int, int]:
    """Mark word wrong. Returns (xp_earned, streak_bonus)."""
    w = W()[idx]
    w["wrong_count"] += 1
    w["last_seen"] = datetime.now().isoformat()
    w["interval"] = 1
    w["next_review"] = (datetime.now() + timedelta(days=1)).isoformat()
    w["correct_count"] = max(0, w["correct_count"] - 1)
    PROGRESS["total_wrong"] += 1
    streak_bonus = update_streak()
    award_xp(XP_WRONG)
    save_answer_state(idx)
    return XP_WRONG, streak_bonus

# ---------------------------------------------------------------------------
# Auth decorator
# ---------------------------------------------------------------------------

def access_decision(
    *,
    mode: str,
    configured: bool,
    stored_role: str | None,
    stored_status: str | None,
    is_start: bool,
) -> str:
    """Return a fail-closed action for one incoming Telegram update."""
    if stored_role == "admin":
        return "allow"
    if stored_status is not None and stored_status not in ACCESS_STATUSES:
        return "blocked"
    if stored_status == "blocked":
        return "blocked"
    if configured:
        return "allow"
    if mode == "allowlist":
        return "deny"
    if mode == "public":
        return "allow"
    if mode == "pilot" and stored_status == "active":
        return "allow"
    if mode == "pilot" and is_start:
        return "waitlist"
    return "pending"


async def reject_access(update: Update, text: str) -> None:
    query = getattr(update, "callback_query", None)
    if query is not None:
        await query.answer(text[:200], show_alert=True)
        return
    message = getattr(update, "effective_message", None)
    if message is not None:
        await message.reply_text(text)


def auth(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        telegram_user = getattr(update, "effective_user", None)
        if telegram_user is None and getattr(update, "poll_answer", None):
            telegram_user = update.poll_answer.user
        if telegram_user is None:
            return
        user_id = int(telegram_user.id)
        configured = user_id in ALLOWED_USER_IDS or user_id in ADMIN_USER_IDS
        store = get_store()
        stored = store.access_profile(user_id)
        decision = access_decision(
            mode=BOT_ACCESS_MODE,
            configured=configured,
            stored_role=stored["role"] if stored else None,
            stored_status=stored["access_status"] if stored else None,
            is_start=func.__name__ == "cmd_start",
        )
        if decision == "waitlist":
            source = start_source(getattr(context, "args", None))
            first_request = stored is None
            store.ensure_user(telegram_user, acquisition_source=source)
            store.record_event(user_id, "start_received", source=source)
            if first_request:
                store.record_event(
                    user_id,
                    "pilot_waitlist_joined",
                    source=source,
                )
            await reject_access(
                update,
                "Заявка на участие в бесплатном пилоте принята. "
                "После одобрения администратора открой /start ещё раз.",
            )
            return
        if decision == "blocked":
            await reject_access(
                update,
                "Доступ к MY DICTIONARY заблокирован. Обратись в поддержку.",
            )
            return
        if decision == "pending":
            await reject_access(
                update,
                "Доступ к пилоту ещё не одобрен. Статус можно проверить через /start.",
            )
            return
        if decision == "deny":
            await reject_access(
                update,
                "MY DICTIONARY пока доступен только участникам закрытого тестирования.",
            )
            return
        with learner_scope(telegram_user) as runtime:
            if runtime.access_status != "active":
                runtime.store.activate_user_access(runtime.user_id)
                runtime.access_status = "active"
            if SAFETY_SETTINGS.enabled and runtime.role != "admin":
                scope, policy = SAFETY_SETTINGS.for_handler(func.__name__)
                rate_decision = PersistentRateLimiter(runtime.store).consume(
                    user_id=runtime.user_id,
                    scope=scope,
                    policy=policy,
                )
                if not rate_decision.allowed:
                    await reject_access(
                        update,
                        "Слишком много действий подряд. "
                        f"Попробуй снова через {rate_decision.retry_after_seconds} сек.",
                    )
                    return
            if (
                runtime.role != "admin"
                and not runtime.onboarding_completed
                and func.__name__ not in {"cmd_start", "onboarding_cb"}
            ):
                query = getattr(update, "callback_query", None)
                if query is not None:
                    await query.answer()
                message = getattr(update, "effective_message", None)
                if message is not None:
                    await send_onboarding_intro(message)
                return
            return await func(update, context)
    return wrapper

# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

@auth
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    runtime = _ACTIVE_RUNTIME.get()
    source = start_source(getattr(context, "args", None))
    runtime.store.update_product_profile(
        runtime.user_id, acquisition_source=source
    )
    record_product_event("start_received", source=source)
    if runtime.role != "admin" and not runtime.onboarding_completed:
        await send_onboarding_intro(update.message)
        return
    await send_start_message(
        update.message,
        context,
        first_name=getattr(update.effective_user, "first_name", None),
    )


def start_source(args) -> str:
    if not args:
        return "direct"
    candidate = str(args[0]).strip().lower()
    if not candidate or len(candidate) > 32:
        return "direct"
    if not candidate.isascii() or not candidate[0].isalnum() or not all(
        char.isalnum() or char in {"-", "_"} for char in candidate
    ):
        return "direct"
    return candidate


def onboarding_intro_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(
            "Попробовать бесплатно ✨", callback_data="onboarding:begin"
        )]]
    )


async def send_onboarding_intro(message) -> None:
    await message.reply_text(
        "MY DICTIONARY — короткие уроки со словами, карточками и "
        "произношением прямо в Telegram. Базовые наборы бесплатны.\n\n"
        "Два коротких шага — и первый урок готов.",
        reply_markup=onboarding_intro_keyboard(),
    )


ONBOARDING_GOALS = {
    "basics": "Базовая лексика",
    "travel": "Путешествия",
    "conversation": "Разговорная речь",
    "work": "Работа и учёба",
}


def onboarding_pack_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(
                f"{pack.label} · {pack.entry_count} слов",
                callback_data=f"onboarding:pack:{pack.pack_id}",
            )]
            for pack in CATALOG.visible_packs("learner")
        ]
    )


def onboarding_pace_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(
                "5 карточек · легко", callback_data="onboarding:pace:5"
            )],
            [InlineKeyboardButton(
                "10 карточек · обычно", callback_data="onboarding:pace:10"
            )],
            [InlineKeyboardButton(
                "20 карточек · интенсивно", callback_data="onboarding:pace:20"
            )],
        ]
    )


@auth
async def onboarding_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split(":")
    runtime = _ACTIVE_RUNTIME.get()
    if runtime.role == "admin" or runtime.onboarding_completed:
        await query.answer("Настройка уже завершена.")
        return
    await query.answer()
    if parts == ["onboarding", "begin"]:
        record_product_event("onboarding_started")
        runtime.store.update_product_profile(
            runtime.user_id,
            native_language="ru",
            learning_goal="basics",
        )
        record_product_event(
            "onboarding_native_selected",
            properties={"language": "ru"},
            source="default",
        )
        record_product_event(
            "onboarding_goal_selected",
            properties={"goal": "basics"},
            source="default",
        )
        await query.edit_message_text(
            "Шаг 1 из 2. Какой язык хочешь учить?",
            reply_markup=onboarding_pack_keyboard(),
        )
        return
    # Compatibility for buttons sent by the previous onboarding version.
    if len(parts) == 3 and parts[1] == "native" and parts[2] == "ru":
        runtime.store.update_product_profile(
            runtime.user_id,
            native_language=parts[2],
            learning_goal="basics",
        )
        record_product_event(
            "onboarding_native_selected", properties={"language": parts[2]}
        )
        await query.edit_message_text(
            "Шаг 1 из 2. Какой язык хочешь учить?",
            reply_markup=onboarding_pack_keyboard(),
        )
        return
    if len(parts) == 3 and parts[1] == "pack":
        pack = CATALOG.get(parts[2])
        if pack is None or not pack.visible_to("learner"):
            await query.edit_message_text("Этот набор недоступен. Начни настройку заново.")
            return
        activate_content_pack(pack, source="onboarding")
        context.user_data["onboarding_pack_id"] = pack.pack_id
        record_product_event(
            "onboarding_pack_selected",
            properties={
                "pack_id": pack.pack_id,
                "language": pack.target_language,
            },
        )
        await query.edit_message_text(
            "Шаг 2 из 2. Сколько карточек удобно проходить в день?",
            reply_markup=onboarding_pace_keyboard(),
        )
        return
    # Compatibility for an in-flight goal step from the previous version.
    if len(parts) == 3 and parts[1] == "goal" and parts[2] in ONBOARDING_GOALS:
        runtime.store.update_product_profile(
            runtime.user_id, learning_goal=parts[2]
        )
        record_product_event(
            "onboarding_goal_selected", properties={"goal": parts[2]}
        )
        await query.edit_message_text(
            "Шаг 2 из 2. Сколько карточек удобно проходить в день?",
            reply_markup=onboarding_pace_keyboard(),
        )
        return
    if len(parts) == 3 and parts[1] == "pace" and parts[2] in {"5", "10", "20"}:
        product = runtime.store.product_profile(runtime.user_id)
        pack = CATALOG.get(
            context.user_data.get("onboarding_pack_id")
            or product["active_pack_id"]
        )
        if pack is None or not pack.visible_to("learner"):
            await query.edit_message_text("Выбери учебный набор заново через /start.")
            return
        runtime.store.update_product_profile(
            runtime.user_id,
            daily_word_goal=int(parts[2]),
            complete_onboarding=True,
        )
        runtime.onboarding_completed = True
        record_product_event(
            "onboarding_completed",
            properties={
                "pack_id": pack.pack_id,
                "language": pack.target_language,
                "daily_word_goal": int(parts[2]),
            },
        )
        await query.edit_message_text(
            f"Готово ✨ Подключён набор «{pack.title}». "
            "Первый урок уже ждёт тебя."
        )
        await send_start_message(
            query.message,
            context,
            first_name=getattr(update.effective_user, "first_name", None),
        )
        return
    await query.edit_message_text("Шаг настройки устарел. Отправь /start.")


def start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(
                "▶️ Урок на сегодня", callback_data="start:daily"
            )],
            [
                InlineKeyboardButton("🔁 Повторить", callback_data="start:review"),
                InlineKeyboardButton("📚 Темы", callback_data="start:topics"),
            ],
            [
                InlineKeyboardButton("📊 Прогресс", callback_data="start:stats"),
                InlineKeyboardButton("⚙️ Настройки", callback_data="start:settings"),
            ],
        ]
    )


def settings_keyboard(product: dict) -> InlineKeyboardMarkup:
    current_pack_id = PROGRESS.get("active_pack_id")
    language_rows = []
    for pack in visible_packs():
        marker = " ✓" if pack.pack_id == current_pack_id else ""
        language_rows.append([
            InlineKeyboardButton(
                f"{pack.label}{marker}", callback_data=f"lang:{pack.pack_id}"
            )
        ])
    pace = int(product.get("daily_word_goal") or 10)
    pace_row = [
        InlineKeyboardButton(
            f"{count}{' ✓' if count == pace else ''}",
            callback_data=f"settings:pace:{count}",
        )
        for count in (5, 10, 20)
    ]
    selected_style = str(product.get("mirror_style") or "teacher")
    style_rows = [
        [
            InlineKeyboardButton(
                f"{label}{' ✓' if style == selected_style else ''}",
                callback_data=f"settings:mirror:{style}",
            )
        ]
        for style, label in MIRROR_STYLE_LABELS.items()
    ]
    return InlineKeyboardMarkup(language_rows + [pace_row] + style_rows)


def settings_text(current: ContentPack, product: Mapping[str, Any]) -> str:
    style = str(product.get("mirror_style") or "teacher")
    style_label = MIRROR_STYLE_LABELS.get(style, MIRROR_STYLE_LABELS["teacher"])
    return (
        f"⚙️ *Настройки*\n\n"
        f"Язык: *{current.title}*\n"
        f"Карточек в уроке: *{product['daily_word_goal']}*\n"
        f"Стиль AI: *{style_label}*\n\n"
        "Выбери язык, ритм или стиль ответа:"
    )


async def send_start_message(message, context, *, first_name: str | None) -> None:
    profile = get_bot_profile()
    text = render_start_text(profile, first_name)
    if WELCOME_BANNER_PATH.exists():
        try:
            with WELCOME_BANNER_PATH.open("rb") as photo:
                await message.reply_photo(
                    photo=photo,
                    caption=text,
                    reply_markup=start_keyboard(),
                )
            return
        except Exception as exc:
            logger.warning("Welcome banner failed; using text fallback: %s", exc)
    await message.reply_text(text, reply_markup=start_keyboard())


@auth
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(get_bot_profile()["bot_help_text"])


@auth
async def cmd_privacy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    store = get_store()
    voice_consent = store.has_consent(
        int(update.effective_user.id),
        consent_type="voice_processing",
        document_version=VOICE_SETTINGS.consent_version,
    )
    ai_consent = bool(
        AI_SETTINGS.consent_version
        and store.has_consent(
            int(update.effective_user.id),
            consent_type="ai_processing",
            document_version=AI_SETTINGS.consent_version,
        )
    )
    if MIRROR_MEMORY_SETTINGS.enabled:
        mirror_memory_text = (
            "Контекст Mirror: до 20 последних реплик, "
            f"хранение {MIRROR_MEMORY_SETTINGS.retention_days} дней."
        )
    else:
        mirror_memory_text = "Долговременный контекст Mirror: выключен."
    await update.effective_message.reply_text(
        "Приватность MY DICTIONARY\n\n"
        "Учебная история, события продукта и AI-запросы удаляются по "
        "ограниченным срокам хранения. Ты можешь стереть свои учебные данные "
        "сразу. Платёжные и аудиторские записи сохраняются для возвратов, "
        "сверки и защиты от мошенничества. После удаления доступ будет заблокирован.\n\n"
        + (
            "AI-согласие: принято."
            if ai_consent
            else "AI-согласие: не выдано."
        )
        + f"\n{mirror_memory_text}",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "Удалить мои учебные данные",
                        callback_data="privacy:request",
                    )
                ],
                [
                    InlineKeyboardButton(
                        (
                            "Отозвать согласие на обработку голоса"
                            if voice_consent
                            else "Согласие на обработку голоса не выдано"
                        ),
                        callback_data=(
                            "privacy:voice_revoke"
                            if voice_consent
                            else "privacy:voice_status"
                        ),
                    )
                ],
                [
                    InlineKeyboardButton(
                        (
                            "AI-согласие принято — отозвать"
                            if ai_consent
                            else "AI-согласие не выдано"
                        ),
                        callback_data=(
                            "privacy:ai_revoke"
                            if ai_consent
                            else "privacy:ai_status"
                        ),
                    )
                ],
            ]
        ),
    )


@auth
async def privacy_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    action = query.data.split(":", 1)[1]
    if action == "voice_status":
        await query.answer(
            "Согласие можно выдать при запуске /voice.", show_alert=True
        )
        return
    if action == "voice_revoke":
        changed = get_store().revoke_consent(
            int(update.effective_user.id), consent_type="voice_processing"
        )
        context.user_data.pop("pending_voice_consent", None)
        if VOICE_SETTINGS.enabled:
            get_voice_tutor_service().stop_session(int(update.effective_user.id))
        record_product_event(
            "voice_consent_revoked",
            properties={"consent_type": "voice_processing"},
        )
        await query.answer("Согласие отозвано.")
        await query.edit_message_text(
            "Согласие на обработку голоса отозвано. Активная голосовая "
            f"сессия остановлена. Изменено записей: {changed}."
        )
        return
    if action == "ai_status":
        await query.answer(
            "Согласие можно выдать при запуске /ai.", show_alert=True
        )
        return
    if action == "ai_revoke":
        changed = get_store().revoke_consent(
            int(update.effective_user.id), consent_type="ai_processing"
        )
        context.user_data.pop("pending_ai_consent", None)
        record_product_event(
            "ai_consent_revoked",
            properties={"consent_type": "ai_processing"},
        )
        await query.answer("Согласие отозвано.")
        await query.edit_message_text(
            "Согласие на обработку AI отозвано. Новые AI-запросы не будут "
            f"отправлены до повторного согласия. Изменено записей: {changed}."
        )
        return
    if action == "request":
        await query.answer()
        await query.edit_message_text(
            "Удалить учебный профиль, прогресс, аналитику и историю AI? "
            "Восстановить эти данные будет нельзя.",
            reply_markup=InlineKeyboardMarkup(
                [[
                    InlineKeyboardButton(
                        "Подтвердить удаление",
                        callback_data="privacy:confirm",
                    ),
                    InlineKeyboardButton("Отмена", callback_data="privacy:cancel"),
                ]]
            ),
        )
        return
    if action == "cancel":
        await query.answer("Удаление отменено.")
        await query.edit_message_text("Учебные данные не изменены.")
        return
    if action != "confirm":
        await query.answer("Неизвестное действие.", show_alert=True)
        return
    runtime = _ACTIVE_RUNTIME.get()
    result = erase_user_learning_data(
        runtime.store,
        user_id=runtime.user_id,
        actor="telegram-self-service",
    )
    context.user_data.clear()
    await query.answer("Данные удалены.")
    await query.edit_message_text(
        "Учебные данные удалены. Сохранён только обязательный платёжный и "
        f"аудиторский след. Номер операции: {result.user_reference}."
    )


@auth
async def start_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data.split(":", 1)[1]
    chat_id = query.message.chat_id
    if action in {"daily"}:
        await start_home_lesson(query, context, lesson_kind="daily")
        return
    if action == "review":
        await start_home_lesson(query, context, lesson_kind="review")
        return
    if action in {"topics", "learn"}:
        invalidate_block_session(context.user_data)
        pack = active_content_pack()
        context.user_data["block_lang"] = pack.target_language
        context.user_data["block_pack_id"] = pack.pack_id
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"📚 *{pack.label}*\n\nВыбери тему:",
            reply_markup=build_topic_keyboard(pack),
            parse_mode="Markdown",
        )
        return
    if action in {"settings", "lang"}:
        current = active_content_pack()
        runtime = _ACTIVE_RUNTIME.get()
        product = runtime.store.product_profile(runtime.user_id)
        await context.bot.send_message(
            chat_id=chat_id,
            text=settings_text(current, product),
            reply_markup=settings_keyboard(product),
            parse_mode="Markdown",
        )
        return
    if action == "stats":
        await context.bot.send_message(
            chat_id=chat_id,
            text=format_stats_text(),
            parse_mode="Markdown",
        )
        return
    if action == "about":
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "Как проходит обучение\n\n"
                "1. Нажми «Урок на сегодня».\n"
                "2. Вспомни значение слова и открой карточку.\n"
                "3. Отметь «Знаю» или «Не знаю».\n"
                "4. Бот сохранит ответ и сам назначит повторение."
            ),
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("▶️ Начать урок", callback_data="start:daily")]]
            ),
        )


@auth
async def settings_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        _, setting, value = query.data.split(":")
    except ValueError:
        await query.answer("Настройка устарела.", show_alert=True)
        return
    runtime = _ACTIVE_RUNTIME.get()
    if setting == "pace" and value in {"5", "10", "20"}:
        await query.answer("Ритм сохранён")
        product = runtime.store.update_product_profile(
            runtime.user_id, daily_word_goal=int(value)
        )
        record_product_event(
            "daily_goal_updated", properties={"daily_word_goal": int(value)}
        )
    elif setting == "mirror" and value in MIRROR_STYLE_LABELS:
        saved = runtime.store.set_mirror_style(runtime.user_id, value)
        await query.answer(f"Стиль: {MIRROR_STYLE_LABELS[saved]}")
        product = runtime.store.product_profile(runtime.user_id)
    else:
        await query.answer("Настройка недоступна.", show_alert=True)
        return
    current = active_content_pack()
    await query.edit_message_text(
        settings_text(current, product),
        reply_markup=settings_keyboard(product),
        parse_mode="Markdown",
    )


def active_tutor_context(user_data: dict) -> TutorContext | None:
    """Build AI context only from the currently valid learning block."""
    if not user_data.get("block_session"):
        return None
    indices = user_data.get("block_all_indices", [])
    pack = CATALOG.get(user_data.get("block_pack_id", ""))
    language = user_data.get("block_lang")
    if (
        not indices
        or pack is None
        or pack.target_language != language
        or pack not in visible_packs()
    ):
        return None
    source_words = W(pack.pack_id)
    words = []
    for index in indices:
        if not isinstance(index, int) or not 0 <= index < len(source_words):
            return None
        word = source_words[index]
        words.append(
            TutorWord(
                term=target_text(word),
                transcription=transcription_for(word, language),
                meaning_ru=meaning_text(word),
                example_target=example_target_text(word) or None,
            )
        )
    return TutorContext(
        language=language,
        topic=user_data.get("block_topic"),
        words=tuple(words),
    )


def build_mirror_learning_context(
    profile: Mapping[str, Any],
    user_data: dict,
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Return bounded active vocabulary without persisting dialogue text."""
    tutor_context = active_tutor_context(user_data)
    if tutor_context is not None:
        source_words = W(str(user_data.get("block_pack_id") or ""))
        source_indices = user_data.get("block_all_indices", [])
        return {
            "language": tutor_context.language,
            "pack_id": user_data.get("block_pack_id"),
            "topic": tutor_context.topic,
            "source": "active_block",
            "words": [
                {
                    "target": word.term,
                    "transcription": word.transcription,
                    "meaning_ru": meaning_display_text(source_words[index]),
                    "example": word.example_target or "",
                }
                for word, index in zip(
                    tutor_context.words[:12], source_indices[:12], strict=True
                )
            ],
        }

    role = str(profile.get("role") or "learner")
    language = str(profile.get("active_lang") or snapshot.get("language") or "")
    pack = CATALOG.get(str(profile.get("active_pack_id") or ""))
    if pack is None and language:
        pack = CATALOG.pack_for_language(language, role)
    if pack is None or not pack.visible_to(role):
        return {"language": language, "source": "profile", "words": []}

    weak = {
        str(term).strip().casefold()
        for term in snapshot.get("weak_terms", [])
        if str(term).strip()
    }
    words = CATALOG.words(pack)
    words.sort(key=lambda word: target_text(word).casefold() not in weak)
    return {
        "language": pack.target_language,
        "pack_id": pack.pack_id,
        "source": "active_pack",
        "words": [
            {
                "target": target_text(word),
                "transcription": transcription_for(word, pack.target_language),
                "meaning_ru": meaning_display_text(word),
                "example": example_target_text(word),
            }
            for word in words[:12]
        ],
    }


def _voice_word(
    word: dict, language: str, *, mode: str = "pronunciation"
) -> VoiceWord:
    focus_target = target_text(word)
    focus_transcription = transcription_for(word, language)
    if mode == "conversation":
        practice_target = example_target_text(word) or focus_target
        practice_meaning = example_meaning_text(word) or meaning_text(word)
        return VoiceWord(
            vocabulary_id=vocabulary_id_for(word),
            target=practice_target,
            speech=practice_target,
            transcription="",
            meaning_ru=practice_meaning,
            focus_target=focus_target,
            focus_transcription=focus_transcription,
        )
    return VoiceWord(
        vocabulary_id=vocabulary_id_for(word),
        target=focus_target,
        speech=speech_text(word),
        transcription=focus_transcription,
        meaning_ru=meaning_text(word),
        focus_target=focus_target,
        focus_transcription=focus_transcription,
    )


def active_voice_block(
    user_data: dict, *, mode: str = "pronunciation"
) -> tuple[ContentPack, list[tuple[int, VoiceWord]]] | None:
    if not user_data.get("block_session"):
        return None
    pack = CATALOG.get(user_data.get("block_pack_id", ""))
    indices = user_data.get("block_all_indices", [])
    if pack is None or pack not in visible_packs() or not indices:
        return None
    words = W(pack.pack_id)
    result = []
    for index in indices:
        if not isinstance(index, int) or not 0 <= index < len(words):
            return None
        result.append(
            (
                index,
                _voice_word(words[index], pack.target_language, mode=mode),
            )
        )
    return pack, result


def restore_voice_block(
    state: VoiceSessionState,
) -> tuple[ContentPack, list[tuple[int, VoiceWord]]]:
    pack = CATALOG.get(state.pack_id)
    if (
        pack is None
        or pack.target_language != state.language
        or pack not in visible_packs()
    ):
        raise VoiceSessionError("Voice content pack is unavailable")
    if PROGRESS.get("active_pack_id") != pack.pack_id:
        activate_content_pack(pack, source="voice_restore")
    source = W(pack.pack_id)
    by_id = {
        vocabulary_id_for(word): (
            index,
            _voice_word(word, pack.target_language, mode=state.mode),
        )
        for index, word in enumerate(source)
    }
    try:
        ordered = [by_id[vocabulary_id] for vocabulary_id in state.vocabulary_ids]
    except KeyError as exc:
        raise VoiceSessionError("Voice session content changed") from exc
    return pack, ordered


def voice_prompt_text(
    pack: ContentPack,
    word: VoiceWord,
    *,
    position: int,
    total: int,
    mode: str,
) -> str:
    target = _directional_text(word.target, pack.direction)
    reading = f" {word.transcription}" if word.transcription else ""
    title = "Разговорная практика" if mode == "conversation" else "Голосовая практика"
    focus = ""
    if mode == "conversation" and word.focus_target:
        focus = (
            f"\nКлючевое слово: {word.focus_target}"
            f" {word.focus_transcription or ''}"
        ).rstrip()
    return (
        f"{title} {position}/{total}\n\n"
        f"🇷🇺 {word.meaning_ru}\n"
        f"{pack.flag} {target}{reading}{focus}\n\n"
        "Прослушай эталон ниже, затем отправь голосовое сообщение."
    )


async def send_voice_prompt(
    *,
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    pack: ContentPack,
    indexed_word: tuple[int, VoiceWord],
    position: int,
    total: int,
    mode: str = "pronunciation",
) -> None:
    index, word = indexed_word
    await context.bot.send_message(
        chat_id=chat_id,
        text=voice_prompt_text(
            pack, word, position=position, total=total, mode=mode
        ),
    )
    await send_voice_reference(
        chat_id=chat_id,
        context=context,
        pack=pack,
        indexed_word=indexed_word,
        mode=mode,
    )


async def send_voice_reference(
    *,
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    pack: ContentPack,
    indexed_word: tuple[int, VoiceWord],
    mode: str,
) -> None:
    index, word = indexed_word
    if mode == "pronunciation":
        await send_pronunciation(chat_id, index, context)
        return
    try:
        audio = await get_audio(
            word.speech,
            voice=pack.pronunciation.tts_voice,
            rate=pack.pronunciation.tts_rate,
            cache_namespace=f"{pack.pack_id}:conversation:v{pack.content_version}",
        )
        await send_pronunciation_audio(
            chat_id=chat_id,
            audio=audio,
            title=word.target,
            context=context,
        )
    except Exception as exc:
        logger.warning(
            "Conversation TTS failed: error_type=%s", type(exc).__name__
        )


def voice_feedback_text(result) -> str:
    labels = {
        "exact": "Текст распознан как ожидаемое слово.",
        "close": "Распознавание близко к ожидаемому слову.",
        "retry": "Распознавание не совпало. Прослушай эталон и попробуй ещё раз в новой сессии.",
    }
    feedback = result.feedback
    lines = [
        f"Распознано: {feedback.transcript}",
        f"Значение: {feedback.expected.meaning_ru}",
    ]
    if (
        feedback.expected.focus_target
        and feedback.expected.focus_target != feedback.expected.target
    ):
        lines.extend(
            [
                f"Фраза: {feedback.expected.target}",
                f"Ключевое слово: {feedback.expected.focus_target}",
                f"Транскрипция слова: {feedback.expected.focus_transcription or ''}",
            ]
        )
    else:
        lines.extend(
            [
                f"Слово: {feedback.expected.target}",
                f"Транскрипция: {feedback.expected.transcription}",
            ]
        )
    lines.extend(["", labels[feedback.code]])
    if (
        feedback.matched is not None
        and feedback.matched.vocabulary_id != feedback.expected.vocabulary_id
    ):
        lines.append(
            f"Похоже на другое слово блока: {feedback.matched.target} — "
            f"{feedback.matched.meaning_ru}."
        )
    lines.extend(
        [
            "Это сравнение текста распознавания, а не акустическая оценка акцента.",
            f"AI-кредиты: {result.available_credits}",
        ]
    )
    return "\n".join(lines)


async def start_voice_mode(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    mode: str,
) -> None:
    message = update.effective_message
    if not VOICE_SETTINGS.enabled:
        await message.reply_text("Голосовой тренажёр пока выключен.")
        return
    block = active_voice_block(context.user_data, mode=mode)
    if block is None:
        await message.reply_text(
            "Сначала выбери тему и создай блок из 10 слов через /learn."
        )
        return
    user_id = int(update.effective_user.id)
    if not get_store().has_consent(
        user_id,
        consent_type="voice_processing",
        document_version=VOICE_SETTINGS.consent_version,
    ):
        context.user_data["pending_voice_consent"] = {
            "mode": mode,
            "block_session": context.user_data.get("block_session"),
            "expires_at": int(time.time()) + 600,
        }
        await message.reply_text(
            "Согласие на обработку голоса\n\n"
            f"{VOICE_SETTINGS.processing_notice}\n\n"
            f"Версия: {VOICE_SETTINGS.consent_version}",
            reply_markup=InlineKeyboardMarkup(
                [[
                    InlineKeyboardButton(
                        "Согласен и начать",
                        callback_data="voiceconsent:accept",
                    ),
                    InlineKeyboardButton(
                        "Отмена", callback_data="voiceconsent:cancel"
                    ),
                ]]
            ),
        )
        return
    await launch_voice_mode(update, context, mode=mode)


async def launch_voice_mode(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    mode: str,
) -> None:
    message = update.effective_message
    block = active_voice_block(context.user_data, mode=mode)
    if block is None:
        await message.reply_text(
            "Блок устарел. Выбери тему и создай новый блок через /learn."
        )
        return
    pack, indexed_words = block
    state = get_voice_tutor_service().start_session(
        user_id=int(update.effective_user.id),
        pack_id=pack.pack_id,
        language=pack.target_language,
        topic=context.user_data.get("block_topic"),
        block_session_id=context.user_data.get("block_session"),
        mode=mode,
        words=[word for _, word in indexed_words],
    )
    record_product_event(
        "voice_session_started",
        properties={
            "pack_id": pack.pack_id,
            "language": pack.target_language,
            "topic": state.topic or "all",
            "word_count": len(indexed_words),
            "mode": mode,
        },
        session_id=context.user_data.get("block_session"),
    )
    await send_voice_prompt(
        chat_id=update.effective_chat.id,
        context=context,
        pack=pack,
        indexed_word=indexed_words[0],
        position=1,
        total=len(indexed_words),
        mode=mode,
    )


@auth
async def voice_consent_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not VOICE_SETTINGS.enabled:
        context.user_data.pop("pending_voice_consent", None)
        await query.answer("Голосовая практика пока выключена.", show_alert=True)
        return
    action = query.data.split(":", 1)[1]
    if action == "cancel":
        context.user_data.pop("pending_voice_consent", None)
        await query.answer("Голосовая практика отменена.")
        await query.edit_message_reply_markup(reply_markup=None)
        return
    pending = context.user_data.pop("pending_voice_consent", None)
    if (
        action != "accept"
        or not isinstance(pending, dict)
        or int(pending.get("expires_at", 0)) < int(time.time())
        or pending.get("block_session") != context.user_data.get("block_session")
        or pending.get("mode") not in {"pronunciation", "conversation"}
    ):
        await query.answer("Запрос устарел. Запусти /voice снова.", show_alert=True)
        return
    user_id = int(update.effective_user.id)
    changed = get_store().grant_consent(
        user_id,
        consent_type="voice_processing",
        document_version=VOICE_SETTINGS.consent_version,
        source="telegram",
    )
    if changed:
        record_product_event(
            "voice_consent_accepted",
            properties={
                "consent_type": "voice_processing",
                "document_version": VOICE_SETTINGS.consent_version,
            },
        )
    await query.answer("Согласие сохранено.")
    await query.edit_message_reply_markup(reply_markup=None)
    await launch_voice_mode(update, context, mode=pending["mode"])


@auth
async def cmd_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_voice_mode(update, context, mode="pronunciation")


@auth
async def cmd_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_voice_mode(update, context, mode="conversation")


@auth
async def cmd_voice_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stopped = get_voice_tutor_service().stop_session(int(update.effective_user.id))
    await update.message.reply_text(
        "Голосовая сессия остановлена. Транскрипт: /voice_transcript."
        if stopped
        else "Активной голосовой сессии нет."
    )


@auth
async def cmd_voice_transcript(update: Update, context: ContextTypes.DEFAULT_TYPE):
    service = get_voice_tutor_service()
    state = service.latest_session(int(update.effective_user.id))
    if state is None:
        await update.message.reply_text("Голосовых сессий пока нет.")
        return
    pack, words = restore_voice_block(state)
    by_id = {word.vocabulary_id: word for _, word in words}
    turns = service.turns(
        user_id=int(update.effective_user.id), session_id=state.session_id
    )
    lines = [
        f"Транскрипт голосовой сессии · {pack.label}",
        f"Статус: {state.status}",
        "",
    ]
    for position, turn in enumerate(turns, 1):
        expected = by_id.get(turn["expected_vocabulary_id"])
        lines.extend(
            [
                f"{position}. 🇷🇺 {expected.meaning_ru if expected else 'слово из блока'}",
                f"   {pack.flag} {expected.target if expected else turn['expected_vocabulary_id']}",
                f"   Распознано: {str(turn['transcript'])[:300]}",
                f"   Результат: {turn['feedback_code']}",
            ]
        )
    if not turns:
        lines.append("Сохранённых реплик нет или срок хранения истёк.")
    rendered = "\n".join(lines)
    for start in range(0, len(rendered), 3900):
        await update.message.reply_text(rendered[start:start + 3900])


@auth
async def voice_message_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    if not VOICE_SETTINGS.enabled:
        await update.message.reply_text("Голосовой тренажёр пока выключен.")
        return
    if not get_store().has_consent(
        int(update.effective_user.id),
        consent_type="voice_processing",
        document_version=VOICE_SETTINGS.consent_version,
    ):
        await update.message.reply_text(
            "Согласие на обработку голоса отсутствует или устарело. "
            "Запусти /voice и подтверди актуальные условия."
        )
        return
    voice = update.message.voice
    duration = int(getattr(voice, "duration", 0) or 0)
    file_size = getattr(voice, "file_size", None)
    if (
        duration < 1
        or duration > VOICE_SETTINGS.max_duration_seconds
        or file_size is None
        or int(file_size) <= 0
        or int(file_size) > VOICE_SETTINGS.max_audio_bytes
    ):
        await update.message.reply_text(
            "Голосовое не принято: длительность или размер вне допустимого лимита."
        )
        return
    service = get_voice_tutor_service()
    state = service.active_session(int(update.effective_user.id))
    if state is None:
        await update.message.reply_text(
            "Сначала запусти практику командой /voice после выбора блока."
        )
        return
    try:
        pack, indexed_words = restore_voice_block(state)
        expected_indexed = indexed_words[state.next_position]
        telegram_file = await context.bot.get_file(voice.file_id)
        downloaded = await telegram_file.download_as_bytearray()
        if not downloaded or len(downloaded) > VOICE_SETTINGS.max_audio_bytes:
            raise ValueError("Downloaded voice exceeds size limit")
        result = await service.process_turn(
            user_id=int(update.effective_user.id),
            audio=bytes(downloaded),
            duration_seconds=duration,
            words=[word for _, word in indexed_words],
        )
    except AIQuotaExceeded:
        await update.message.reply_text(
            "AI-кредиты закончились. Проверь /ai_stats или открой /buy."
        )
        return
    except VoiceUsageRecoveryError:
        logger.exception("Voice credit reservation recovery failed")
        await update.message.reply_text(
            "Не удалось подтвердить возврат AI-кредита. Проверь /ai_stats."
        )
        return
    except (VoiceProviderError, VoiceSessionError, ValueError) as exc:
        logger.warning("Voice turn rejected: error_type=%s", type(exc).__name__)
        await update.message.reply_text(
            "Не удалось безопасно обработать голосовое. AI-кредит не списан."
        )
        return
    except (TelegramError, VoiceConfigurationError) as exc:
        logger.warning("Voice service unavailable: error_type=%s", type(exc).__name__)
        await update.message.reply_text("Голосовой тренажёр временно недоступен.")
        return
    except Exception as exc:
        logger.warning("Voice request failed: error_type=%s", type(exc).__name__)
        await update.message.reply_text(
            "Голосовой тренажёр временно недоступен. AI-кредит не списан."
        )
        return
    await update.message.reply_text(voice_feedback_text(result))
    await send_voice_reference(
        chat_id=update.effective_chat.id,
        context=context,
        pack=pack,
        indexed_word=expected_indexed,
        mode=state.mode,
    )
    record_product_event(
        "voice_turn_completed",
        properties={
            "pack_id": pack.pack_id,
            "language": pack.target_language,
            "mode": result.feedback.code,
            "word_index": expected_indexed[0],
        },
        session_id=state.session_id,
    )
    if result.session_status == "completed":
        await update.message.reply_text(
            "Голосовой блок завершён. Открой /voice_transcript, чтобы увидеть все реплики."
        )
        return
    await send_voice_prompt(
        chat_id=update.effective_chat.id,
        context=context,
        pack=pack,
        indexed_word=indexed_words[result.next_position],
        position=result.next_position + 1,
        total=len(indexed_words),
        mode=state.mode,
    )


async def send_ai_tutor_answer(
    message, context, question: str, *, user_id: int
) -> None:
    if not AI_SETTINGS.enabled:
        await message.reply_text("AI-репетитор пока выключен.")
        return
    tutor_context = active_tutor_context(context.user_data)
    if tutor_context is None:
        await message.reply_text("Сначала выбери тему и создай блок через /learn.")
        return
    try:
        result = await get_ai_tutor_service().ask(
            user_id=int(user_id),
            question=question,
            context=tutor_context,
        )
    except AIQuotaExceeded:
        await message.reply_text(
            "AI-кредиты закончились. Проверь баланс через /ai_stats или открой /buy."
        )
        return
    except AIConfigurationError:
        logger.exception("AI tutor configuration error")
        await message.reply_text("AI-репетитор временно недоступен.")
        return
    except AIUsageRecoveryError:
        logger.exception("AI tutor credit reservation recovery failed")
        await message.reply_text(
            "Не удалось подтвердить возврат AI-кредита. Проверь /ai_stats."
        )
        return
    except (AIProviderError, ValueError) as exc:
        logger.warning("AI tutor rejected response: %s", type(exc).__name__)
        await message.reply_text(
            "Не удалось подготовить безопасный ответ. AI-кредит не списан."
        )
        return
    except Exception as exc:
        logger.warning("AI tutor request failed: %s", type(exc).__name__)
        await message.reply_text(
            "AI-репетитор временно недоступен. AI-кредит не списан."
        )
        return
    rendered = render_tutor_answer(result)
    while rendered:
        if len(rendered) <= 4000:
            chunk, rendered = rendered, ""
        else:
            split_at = rendered.rfind("\n\n", 0, 4000)
            if split_at < 1:
                split_at = 4000
            chunk, rendered = rendered[:split_at], rendered[split_at:].lstrip()
        await message.reply_text(chunk)


async def request_ai_tutor_answer(
    message,
    context,
    question: str,
    *,
    user_id: int,
    request_kind: str,
) -> None:
    """Require current, versioned processing consent before any AI work."""
    if not AI_SETTINGS.enabled:
        await message.reply_text("AI-репетитор пока выключен.")
        return
    consent_version = AI_SETTINGS.consent_version
    processing_notice = AI_SETTINGS.processing_notice
    if not consent_version or not processing_notice:
        await message.reply_text("AI-репетитор временно недоступен.")
        return
    if get_store().has_consent(
        int(user_id),
        consent_type="ai_processing",
        document_version=consent_version,
    ):
        await send_ai_tutor_answer(
            message, context, question, user_id=int(user_id)
        )
        return
    context.user_data["pending_ai_consent"] = {
        "request_kind": request_kind,
        "question": question,
        "block_session": context.user_data.get("block_session"),
        "expires_at": int(time.time()) + 600,
    }
    await message.reply_text(
        "Согласие на обработку AI\n\n"
        f"{processing_notice}\n\n"
        f"Версия: {consent_version}",
        reply_markup=InlineKeyboardMarkup(
            [[
                InlineKeyboardButton(
                    "Согласен и продолжить",
                    callback_data="aiconsent:accept",
                ),
                InlineKeyboardButton("Отмена", callback_data="aiconsent:cancel"),
            ]]
        ),
    )


async def send_mirror_response(
    message,
    text: str,
    *,
    mode: str,
    voice_enabled: bool,
    speech_consented: bool,
    voice_renderer=None,
) -> None:
    """Deliver Mirror text/audio without touching the pronunciation cache."""
    safe_text = str(text).strip()
    selected = mode if mode in {"text", "voice", "both"} else "text"
    if selected == "text":
        await message.reply_text(safe_text)
        return
    if not voice_enabled or not speech_consented or voice_renderer is None:
        if selected == "both":
            await message.reply_text(safe_text)
            await message.reply_text("Голосовой ответ сейчас недоступен.")
        else:
            await message.reply_text(
                f"{safe_text}\n\nГолосовой ответ сейчас недоступен."
            )
        return
    if selected == "both":
        await message.reply_text(safe_text)
    try:
        audio = await voice_renderer(safe_text)
        if hasattr(audio, "seek"):
            audio.seek(0)
        await message.reply_voice(audio)
    except Exception as exc:
        logger.warning(
            "Mirror voice delivery failed: error_type=%s", type(exc).__name__
        )
        if selected == "voice":
            await message.reply_text(
                f"{safe_text}\n\nГолосовой ответ сейчас недоступен."
            )
        else:
            await message.reply_text("Голосовой ответ сейчас недоступен.")


def _mirror_mode(store, user_id: int) -> str:
    try:
        mode = store.get_mirror_response_mode(user_id)
    except Exception:
        return "text"
    return mode if mode in {"text", "voice", "both"} else "text"


def _mirror_style(store, user_id: int) -> str:
    try:
        return normalize_mirror_style(store.get_mirror_style(user_id))
    except (AttributeError, TypeError, ValueError):
        return "teacher"


@auth
async def cmd_mirror_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = " ".join(getattr(context, "args", [])).strip().lower()
    try:
        saved = get_store().set_mirror_response_mode(
            int(update.effective_user.id), mode
        )
    except ValueError:
        await update.message.reply_text(
            "Выбери формат ответа: /response text, /response voice или /response both."
        )
        return
    await update.message.reply_text(f"Формат ответов Mirror: {saved}.")


@auth
async def mirror_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route free text after every existing exercise-answer state."""
    type_idx = context.user_data.get("type_idx")
    active_type_answer = type_idx is not None and (
        not context.user_data.get("block_typing")
        or (
            context.user_data.get("block_mode") == "type"
            and bool(context.user_data.get("block_session"))
            and current_block_index(context.user_data) == type_idx
        )
    )
    if active_type_answer:
        if not hasattr(update.message, "chat_id"):
            update.message.chat_id = int(update.effective_chat.id)
        handler = getattr(handle_type_answer, "__wrapped__", handle_type_answer)
        await handler(update, context)
        return

    store = get_store()
    user_id = int(update.effective_user.id)
    profile = store.product_profile(user_id)
    if profile.get("access_status") != "active":
        await update.message.reply_text("Доступ к Mirror сейчас недоступен.")
        return
    if not profile.get("onboarding_completed_at"):
        await update.message.reply_text("Сначала заверши настройку через /start.")
        return

    question = str(update.message.text or "").strip()
    mirror_profile = get_bot_profile()
    response_style = _mirror_style(store, user_id)
    intent = classify_mirror_intent(question)
    if intent == "greeting":
        role = str(profile.get("role") or "learner")
        active_pack = CATALOG.get(str(profile.get("active_pack_id") or ""))
        if active_pack is None:
            active_pack = CATALOG.pack_for_language(
                str(profile.get("active_lang") or ""), role
            )
        response = render_mirror_greeting(
            active_language=(
                active_pack.target_language
                if active_pack is not None
                else str(profile.get("active_lang") or "")
            ),
            active_pack_title=active_pack.title if active_pack is not None else None,
            has_active_block=active_tutor_context(context.user_data) is not None,
        )
    elif intent == "capabilities":
        response = render_mirror_capabilities(
            mirror_profile.get(
                "mirror_capabilities_text",
                MIRROR_ADMIN_DEFAULTS["mirror_capabilities_text"],
            ),
            locale=getattr(update.effective_user, "language_code", None),
        )
    elif intent == "progress":
        response = build_mirror_progress_summary(store, user_id)
    else:
        consent_version = AI_SETTINGS.consent_version or "unversioned"
        try:
            consented = store.has_consent(
                user_id,
                consent_type="ai_processing",
                document_version=consent_version,
            )
        except (TypeError, ValueError):
            consented = False
        if not consented:
            await update.message.reply_text(
                "Для объясняющего AI-ответа нужно актуальное согласие через /ai."
            )
            return
        try:
            snapshot = (
                grounded_progress_snapshot(store, user_id)
                if isinstance(store, DatabaseStore)
                else {
                    "language": profile.get("active_lang"),
                    "active_pack_id": profile.get("active_pack_id"),
                    "accuracy_percent": None,
                    "due_count": None,
                    "weak_terms": [],
                }
            )
            if MIRROR_MEMORY_SETTINGS.enabled:
                try:
                    dialogue = store.get_mirror_dialogue(user_id, limit=20)
                except Exception as exc:
                    logger.warning(
                        "Mirror memory read failed: error_type=%s",
                        type(exc).__name__,
                    )
                    dialogue = recent_mirror_dialogue(context.user_data)
            else:
                dialogue = recent_mirror_dialogue(context.user_data)
            payload = build_mirror_provider_payload(
                question=question,
                admin_guidance=mirror_profile.get(
                    "mirror_persona_guidance",
                    MIRROR_ADMIN_DEFAULTS["mirror_persona_guidance"],
                ),
                grounded_snapshot=snapshot,
                learning_context=build_mirror_learning_context(
                    profile,
                    context.user_data,
                    snapshot,
                ),
                recent_dialogue=dialogue,
                response_style=response_style,
            )
            service = get_ai_tutor_service()
            if isinstance(service, AITutorService) and hasattr(service, "ask_mirror"):
                result = await service.ask_mirror(user_id=user_id, payload=payload)
            else:
                result = await service.ask(
                    user_id=user_id,
                    question=question,
                    mirror_payload=payload,
                )
            response = str(result).strip()
            if not response:
                raise ValueError("Empty Mirror response")
        except AIQuotaExceeded:
            await update.message.reply_text(
                "AI-кредиты закончились. Проверь баланс через /ai_stats."
            )
            return
        except Exception as exc:
            logger.warning("Mirror AI failed: error_type=%s", type(exc).__name__)
            await update.message.reply_text(
                "Не удалось подготовить безопасный ответ. Учебный ответ не был придуман."
            )
            return

    mode = _mirror_mode(store, user_id)
    try:
        voice_enabled = mirror_voice_output_enabled()
    except ValueError:
        voice_enabled = False
    speech_consented = False
    voice_renderer = None
    if voice_enabled and mode in {"voice", "both"}:
        try:
            speech_consented = store.has_consent(
                user_id,
                consent_type="voice_processing",
                document_version=VOICE_SETTINGS.consent_version,
            )
        except (TypeError, ValueError):
            speech_consented = False
        if speech_consented:
            try:
                voice_renderer = build_mirror_speech_renderer()
            except Exception as exc:
                logger.warning(
                    "Mirror speech renderer unavailable: error_type=%s",
                    type(exc).__name__,
                )
    await send_mirror_response(
        update.message,
        response,
        mode=mode,
        voice_enabled=voice_enabled,
        speech_consented=speech_consented,
        voice_renderer=voice_renderer,
    )
    if intent == "learning_question" and MIRROR_MEMORY_SETTINGS.enabled:
        try:
            store.append_mirror_exchange(
                user_id,
                question=question,
                answer=response,
                retention_days=MIRROR_MEMORY_SETTINGS.retention_days,
            )
        except Exception as exc:
            logger.warning(
                "Mirror memory write failed: error_type=%s", type(exc).__name__
            )
    append_mirror_turn(context.user_data, role="user", text=question)
    append_mirror_turn(context.user_data, role="assistant", text=response)


@auth
async def ai_consent_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not AI_SETTINGS.enabled:
        context.user_data.pop("pending_ai_consent", None)
        await query.answer("AI-репетитор пока выключен.", show_alert=True)
        return
    parts = str(query.data).split(":", 1)
    action = parts[1] if len(parts) == 2 else ""
    if action == "cancel":
        context.user_data.pop("pending_ai_consent", None)
        await query.answer("AI-запрос отменён.")
        await query.edit_message_reply_markup(reply_markup=None)
        return
    pending = context.user_data.pop("pending_ai_consent", None)
    try:
        expires_at = int(pending.get("expires_at", 0)) if isinstance(pending, dict) else 0
    except (TypeError, ValueError):
        expires_at = 0
    if (
        action != "accept"
        or not isinstance(pending, dict)
        or expires_at < int(time.time())
        or pending.get("block_session") != context.user_data.get("block_session")
        or pending.get("request_kind") not in {"command", "active_block"}
    ):
        await query.answer("Запрос устарел. Запусти /ai снова.", show_alert=True)
        return
    user_id = int(update.effective_user.id)
    get_store().grant_consent(
        user_id,
        consent_type="ai_processing",
        document_version=AI_SETTINGS.consent_version,
        source="telegram",
    )
    await query.answer("Согласие сохранено.")
    await query.edit_message_reply_markup(reply_markup=None)
    question = str(pending.get("question") or "").strip()
    if not question:
        question = "Объясни главные связи между словами этого блока."
    await send_ai_tutor_answer(
        query.message,
        context,
        question,
        user_id=user_id,
    )


@auth
async def cmd_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = " ".join(getattr(context, "args", [])).strip()
    if not question:
        question = "Объясни главные связи между словами этого блока."
    await request_ai_tutor_answer(
        update.message,
        context,
        question,
        user_id=int(update.effective_user.id),
        request_kind="command",
    )


@auth
async def cmd_ai_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    summary = get_store().ai_usage_summary(
        int(update.effective_user.id),
        initial_credits=AI_SETTINGS.initial_credits,
    )
    await update.message.reply_text(
        "AI-использование\n\n"
        f"Доступно кредитов: {summary['available_credits']}\n"
        f"Зарезервировано: {summary['reserved_credits']}\n"
        f"Использовано: {summary['spent_credits']}\n"
        f"Запросы: {summary['completed_requests']} успешно, "
        f"{summary['failed_requests']} с возвратом"
    )


@auth
async def cmd_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not BILLING_SETTINGS.enabled:
        await update.message.reply_text("Покупка AI-кредитов пока недоступна.")
        return
    record_product_event("buy_opened", source="command")
    if not get_store().has_consent(
        int(update.effective_user.id),
        consent_type="billing_terms",
        document_version=BILLING_SETTINGS.terms_version,
    ):
        await send_billing_terms(update.message)
        return
    await send_billing_products(update.message)


def billing_terms_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton(
                "Принимаю и начать сразу",
                callback_data="billing:accept_terms",
            )
        ]]
    )


async def send_billing_terms(message) -> None:
    instruction = (
        "Нажимая кнопку, ты подтверждаешь, что прочитал и принимаешь условия."
        if BILLING_SETTINGS.enabled
        else "Покупка AI-кредитов сейчас выключена."
    )
    seller = (
        "\n".join(
            (
                f"Продавец: {BILLING_SETTINGS.seller_legal_name}",
                f"Адрес: {BILLING_SETTINGS.seller_address}",
                f"Email: {BILLING_SETTINGS.seller_email}",
                f"Телефон: {BILLING_SETTINGS.seller_phone}",
                f"Поддержка платежей: {BILLING_SETTINGS.support_contact}",
            )
        )
        if BILLING_SETTINGS.seller_legal_name
        else "Реквизиты продавца ещё не опубликованы."
    )
    consent = (
        "Я принимаю условия и прошу начать оказание цифровой услуги сразу "
        "после оплаты. Я понимаю, что после полного предоставления услуги "
        "право на отказ может быть утрачено в предусмотренных законом случаях."
    )
    await message.reply_text(
        "Условия покупки AI-кредитов\n\n"
        f"{BILLING_SETTINGS.terms_text}\n\n"
        f"{seller}\n\n"
        f"Версия: {BILLING_SETTINGS.terms_version}\n"
        f"{consent}\n\n"
        f"{instruction}",
        reply_markup=(billing_terms_keyboard() if BILLING_SETTINGS.enabled else None),
    )


async def send_billing_products(message) -> None:
    products = await asyncio.to_thread(get_billing_service().active_products)
    if not products:
        await message.reply_text("Пакеты AI-кредитов пока не опубликованы.")
        return
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    f"{product['title']} · {product['price_xtr']} ⭐",
                    callback_data=f"buy:{product['product_id']}",
                )
            ]
            for product in products
        ]
    )
    heading = (
        "Тестовая среда Telegram Stars. Выбери тестовый пакет AI-кредитов:"
        if TELEGRAM_RUNTIME.is_test
        else "Выбери пакет AI-кредитов:"
    )
    await message.reply_text(heading, reply_markup=keyboard)


@auth
async def billing_consent_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not BILLING_SETTINGS.enabled:
        await query.answer("Покупка AI-кредитов пока выключена.", show_alert=True)
        return
    if query.data != "billing:accept_terms":
        await query.answer("Неизвестное действие.", show_alert=True)
        return
    changed = get_store().grant_consent(
        int(update.effective_user.id),
        consent_type="billing_terms",
        document_version=BILLING_SETTINGS.terms_version,
        source="telegram",
    )
    if changed:
        record_product_event(
            "billing_terms_accepted",
            properties={
                "consent_type": "billing_terms",
                "document_version": BILLING_SETTINGS.terms_version,
            },
        )
    await query.answer("Условия приняты.")
    await query.edit_message_reply_markup(reply_markup=None)
    await send_billing_products(query.message)


@auth
async def buy_product_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not get_store().has_consent(
        int(update.effective_user.id),
        consent_type="billing_terms",
        document_version=BILLING_SETTINGS.terms_version,
    ):
        await send_billing_terms(query.message)
        return
    product_id = query.data.split(":", 1)[1]
    try:
        order = await asyncio.to_thread(
            get_billing_service().create_order,
            user_id=int(update.effective_user.id),
            product_id=product_id,
        )
    except (BillingConfigurationError, BillingValidationError, ValueError):
        logger.warning("Stars invoice creation rejected for product=%s", product_id)
        await query.message.reply_text("Этот пакет сейчас недоступен.")
        return
    await context.bot.send_invoice(
        **{
            "chat_id": query.message.chat_id,
            "title": order.title,
            "description": (
                f"[TEST] {order.description}"[:255]
                if TELEGRAM_RUNTIME.is_test
                else order.description
            ),
            "payload": order.payload,
            "currency": "XTR",
            "prices": [
                LabeledPrice(
                    label=f"{order.credits} AI-кредитов",
                    amount=order.amount_xtr,
                )
            ],
            **(
                {"subscription_period": order.subscription_period_seconds}
                if order.subscription_period_seconds
                else {}
            ),
        }
    )


async def pre_checkout_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.pre_checkout_query
    try:
        await asyncio.wait_for(
            asyncio.to_thread(
                get_billing_service().validate_pre_checkout,
                user_id=int(query.from_user.id),
                payload=query.invoice_payload,
                currency=query.currency,
                total_amount=query.total_amount,
            ),
            timeout=8,
        )
    except Exception as exc:
        logger.warning(
            "Stars pre-checkout rejected: error_type=%s", type(exc).__name__
        )
        await query.answer(
            ok=False,
            error_message="Не удалось подтвердить цену. Создай новый счёт через /buy.",
        )
        return
    await query.answer(ok=True)


async def successful_payment_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    payment = update.message.successful_payment
    try:
        result = await asyncio.to_thread(
            get_billing_service().fulfill_successful_payment,
            user_id=int(update.effective_user.id),
            payload=payment.invoice_payload,
            currency=payment.currency,
            total_amount=payment.total_amount,
            telegram_payment_charge_id=payment.telegram_payment_charge_id,
            provider_payment_charge_id=payment.provider_payment_charge_id,
            is_recurring=bool(getattr(payment, "is_recurring", False)),
            is_first_recurring=bool(
                getattr(payment, "is_first_recurring", False)
            ),
            subscription_expiration_date=getattr(
                payment, "subscription_expiration_date", None
            ),
        )
    except Exception as exc:
        logger.error("Stars fulfillment failed: error_type=%s", type(exc).__name__)
        await update.message.reply_text(
            "Платёж получен, но начисление требует проверки. Напиши /paysupport."
        )
        return
    if result.created:
        prefix = "Тестовая " if TELEGRAM_RUNTIME.is_test else ""
        await update.message.reply_text(
            f"{prefix}оплата подтверждена. "
            f"Начислено {result.credits} AI-кредитов.\n"
            f"Доступно: {result.available_credits}."
        )
    else:
        await update.message.reply_text(
            f"Этот платёж уже учтён. Доступно: {result.available_credits}."
        )


async def cmd_terms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_billing_terms(update.message)


async def cmd_paysupport(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = BILLING_SETTINGS.support_contact
    if contact:
        await update.message.reply_text(
            "Поддержка по платежам\n\n"
            f"Контакт: {contact}\n"
            f"Продавец: {BILLING_SETTINGS.seller_legal_name}\n"
            f"Email: {BILLING_SETTINGS.seller_email}\n"
            f"Телефон: {BILLING_SETTINGS.seller_phone}"
        )
    else:
        await update.message.reply_text("Платежи пока выключены.")


@auth
async def cmd_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subscriptions = await asyncio.to_thread(
        get_billing_service().subscriptions_for_user,
        int(update.effective_user.id),
    )
    if not subscriptions:
        await update.message.reply_text("Активных Stars-подписок пока нет.")
        return
    for subscription in subscriptions:
        cancelled = subscription["status"] == "cancelled"
        action = "restore" if cancelled else "cancel"
        label = "Возобновить" if cancelled else "Отключить автопродление"
        period_end = subscription["current_period_end"].strftime("%Y-%m-%d")
        await update.message.reply_text(
            "Stars-подписка\n"
            f"Статус: {subscription['status']}\n"
            f"Оплачено до: {period_end}",
            reply_markup=InlineKeyboardMarkup(
                [[
                    InlineKeyboardButton(
                        label,
                        callback_data=(
                            f"sub:{action}:{subscription['subscription_id']}"
                        ),
                    )
                ]]
            ),
        )


@auth
async def subscription_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, action, subscription_id = query.data.split(":", 2)
    is_canceled = action == "cancel"
    try:
        await get_billing_service().set_subscription_autorenew(
            subscription_id=subscription_id,
            user_id=int(update.effective_user.id),
            is_canceled=is_canceled,
            gateway=TelegramStarsGateway(context.bot),
        )
    except Exception as exc:
        logger.warning(
            "Stars subscription update failed: error_type=%s",
            type(exc).__name__,
        )
        await query.answer("Не удалось изменить подписку.", show_alert=True)
        return
    await query.answer("Настройка подписки обновлена.")
    await query.message.reply_text(
        "Автопродление отключено до конца оплаченного периода."
        if is_canceled
        else "Автопродление подписки снова включено."
    )


@auth
async def cmd_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch active language."""
    invalidate_block_session(context.user_data)
    current = active_content_pack()
    await update.message.reply_text(
        f"Текущий набор: *{current.title}*\n\nВыбери язык:",
        reply_markup=language_picker_keyboard(),
        parse_mode="Markdown"
    )

@auth
async def lang_switch_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    invalidate_block_session(context.user_data)
    requested = query.data.split(":", 1)[1]
    pack = CATALOG.get(requested) or visible_pack_for_language(requested)
    if pack is None or pack not in visible_packs():
        await query.edit_message_text("Этот набор недоступен.")
        return
    activate_content_pack(pack, source="catalog")
    record_product_event(
        "language_switched",
        properties={
            "pack_id": pack.pack_id,
            "language": pack.target_language,
        },
    )
    await query.edit_message_text(
        f"Подключён набор *{pack.title}* ({pack.entry_count} слов)",
        parse_mode="Markdown"
    )
    # Send persistent keyboard
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="🔄",
        reply_markup=get_lang_keyboard(),
    )

@auth
async def cmd_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a quiz question with 4 options."""
    invalidate_block_session(context.user_data)
    idx = pick_word()
    word = W()[idx]

    # Build 4 options: 1 correct + 3 distractors
    correct_ru = meaning_text(word)
    distractors = set()
    attempts = 0
    while len(distractors) < 3 and attempts < 50:
        r = random.choice(W())
        candidate = meaning_text(r)
        if candidate != correct_ru:
            distractors.add(candidate)
        attempts += 1

    options = list(distractors) + [correct_ru]
    random.shuffle(options)

    buttons = []
    for opt in options:
        cb = f"quiz:{idx}:{'1' if opt == correct_ru else '0'}:{opt}"
        # Telegram callback_data max 64 bytes — truncate if needed
        if len(cb.encode()) > 64:
            short = opt[:15]
            cb = f"quiz:{idx}:{'1' if opt == correct_ru else '0'}:{short}"
        buttons.append([InlineKeyboardButton(opt, callback_data=cb)])

    await update.message.reply_text(
        f"{format_word_label(idx)}\n\nВыбери правильный перевод:",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown"
    )
    await send_pronunciation(update.message.chat_id, idx, context)

@auth
async def quiz_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    invalidate_block_session(context.user_data)

    parts = query.data.split(":", 3)
    idx = int(parts[1])
    is_correct = parts[2] == "1"
    word = W()[idx]

    if is_correct:
        xp, sb = mark_correct(idx)
        text = f"✅ Правильно!\n{format_word_details(idx)}{get_example(idx)}\n{format_xp_line(xp, sb)}"
    else:
        xp, sb = mark_wrong(idx)
        text = f"❌ Ошибка!\n{format_word_details(idx)}{get_example(idx)}\n{format_xp_line(xp, sb)}"

    next_btn = InlineKeyboardMarkup([
        [forvo_button(idx), InlineKeyboardButton("Дальше ➡️", callback_data="next_quiz")]
    ])
    await query.edit_message_text(text, reply_markup=next_btn, parse_mode="Markdown")
    await send_pronunciation(query.message.chat_id, idx, context)

@auth
async def next_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    invalidate_block_session(context.user_data)

    idx = pick_word()
    word = W()[idx]

    correct_ru = meaning_text(word)
    distractors = set()
    attempts = 0
    while len(distractors) < 3 and attempts < 50:
        r = random.choice(W())
        candidate = meaning_text(r)
        if candidate != correct_ru:
            distractors.add(candidate)
        attempts += 1

    options = list(distractors) + [correct_ru]
    random.shuffle(options)

    buttons = []
    for opt in options:
        cb = f"quiz:{idx}:{'1' if opt == correct_ru else '0'}:{opt}"
        if len(cb.encode()) > 64:
            short = opt[:15]
            cb = f"quiz:{idx}:{'1' if opt == correct_ru else '0'}:{short}"
        buttons.append([InlineKeyboardButton(opt, callback_data=cb)])

    await query.edit_message_text(
        f"{format_word_label(idx)}\n\nВыбери правильный перевод:",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown"
    )
    await send_pronunciation(query.message.chat_id, idx, context)

@auth
async def cmd_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start type-in mode."""
    invalidate_block_session(context.user_data)
    idx = pick_word()
    context.user_data["type_idx"] = idx
    word = W()[idx]
    await update.message.reply_text(
        f"{format_word_label(idx)}\n\nНапиши перевод по-русски:",
        parse_mode="Markdown"
    )
    await send_pronunciation(update.message.chat_id, idx, context)

@auth
async def handle_lang_switch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle language switch via persistent keyboard buttons."""
    text = update.message.text
    pack = CATALOG.get(PACK_SWITCH_TEXTS.get(text, ""))
    if pack is None or pack not in visible_packs():
        return
    invalidate_block_session(context.user_data)
    activate_content_pack(pack, source="reply_keyboard")
    record_product_event(
        "language_switched",
        properties={
            "pack_id": pack.pack_id,
            "language": pack.target_language,
        },
    )
    await update.message.reply_text(
        f"Подключён набор *{pack.title}* ({pack.entry_count} слов)",
        parse_mode="Markdown",
        reply_markup=get_lang_keyboard(),
    )

@auth
async def handle_type_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check typed translation — works for both single and block mode."""
    # Ignore language switch button presses
    if update.message.text in PACK_SWITCH_TEXTS:
        return

    idx = context.user_data.get("type_idx")
    if idx is None:
        return  # Not in type mode

    word = W()[idx]
    answer = update.message.text.strip().lower()
    is_correct = answer_matches(word, answer)

    # Block type mode
    if context.user_data.get("block_typing"):
        if is_correct:
            text = f"✅\n{format_word_details(idx)}"
        else:
            text = f"❌\n{format_word_details(idx)}\nТвой ответ: _{answer}_"
        await update.message.reply_text(text, parse_mode="Markdown")
        await send_pronunciation(update.message.chat_id, idx, context)
        context.user_data["type_idx"] = None
        await block_advance(update.message, context, idx, is_correct)
        return

    # Smart type mode
    if context.user_data.get("smart_mode"):
        context.user_data["smart_mode"] = False
        context.user_data["type_idx"] = None
        if is_correct:
            xp, sb = mark_correct(idx)
            text = f"✅\n{format_word_details(idx)}{get_example(idx)}\n{format_xp_line(xp, sb)}"
        else:
            xp, sb = mark_wrong(idx)
            text = f"❌\n{format_word_details(idx)}\nТвой ответ: _{answer}_{get_example(idx)}\n{format_xp_line(xp, sb)}"
        next_btn = InlineKeyboardMarkup([
            [forvo_button(idx), InlineKeyboardButton("Дальше ➡️", callback_data="next_smart")]
        ])
        await update.message.reply_text(text, reply_markup=next_btn, parse_mode="Markdown")
        await send_pronunciation(update.message.chat_id, idx, context)
        return

    # Regular type mode
    if is_correct:
        xp, sb = mark_correct(idx)
        text = f"✅ Правильно!\n{format_word_details(idx)}{get_example(idx)}\n{format_xp_line(xp, sb)}"
    else:
        xp, sb = mark_wrong(idx)
        text = f"❌ Ошибка!\n{format_word_details(idx)}\nТвой ответ: _{answer}_{get_example(idx)}\n{format_xp_line(xp, sb)}"

    context.user_data["type_idx"] = None

    next_btn = InlineKeyboardMarkup([
        [forvo_button(idx), InlineKeyboardButton("Дальше ➡️", callback_data="next_type")]
    ])
    await update.message.reply_text(text, reply_markup=next_btn, parse_mode="Markdown")
    await send_pronunciation(update.message.chat_id, idx, context)

@auth
async def next_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    invalidate_block_session(context.user_data)

    idx = pick_word()
    context.user_data["type_idx"] = idx
    word = W()[idx]
    await query.edit_message_text(
        f"{format_word_label(idx)}\n\nНапиши перевод по-русски:",
        parse_mode="Markdown"
    )
    await send_pronunciation(query.message.chat_id, idx, context)

@auth
async def cmd_flash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Flashcard mode."""
    invalidate_block_session(context.user_data)
    idx = pick_word()
    word = W()[idx]
    btn = InlineKeyboardMarkup(
        [[InlineKeyboardButton("👁 Показать значение", callback_data=f"flash_show:{idx}")]]
    )
    await update.message.reply_text(
        f"{format_word_label(idx)}",
        reply_markup=btn,
        parse_mode="Markdown"
    )
    await send_pronunciation(update.message.chat_id, idx, context)

@auth
async def flash_show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    invalidate_block_session(context.user_data)
    idx = int(query.data.split(":")[1])
    word = W()[idx]

    buttons = InlineKeyboardMarkup([
        [forvo_button(idx)],
        [
            InlineKeyboardButton("😵 Не знаю", callback_data=f"flash_didnt:{idx}"),
            InlineKeyboardButton("✅ Знаю", callback_data=f"flash_knew:{idx}"),
        ]
    ])
    await query.edit_message_text(
        format_word_details(idx),
        reply_markup=buttons,
        parse_mode="Markdown"
    )
    await send_pronunciation(query.message.chat_id, idx, context)

@auth
async def flash_knew(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    invalidate_block_session(context.user_data)
    idx = int(query.data.split(":")[1])
    xp, sb = mark_correct(idx)

    new_idx = pick_word(exclude_idx=idx)
    word = W()[new_idx]
    btn = InlineKeyboardMarkup(
        [[InlineKeyboardButton("👁 Показать значение", callback_data=f"flash_show:{new_idx}")]]
    )
    await query.edit_message_text(
        f"✅ Отлично! {format_xp_line(xp, sb)}\n\n{format_word_label(new_idx)}",
        reply_markup=btn,
        parse_mode="Markdown"
    )

@auth
async def flash_didnt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    invalidate_block_session(context.user_data)
    idx = int(query.data.split(":")[1])
    xp, sb = mark_wrong(idx)

    new_idx = pick_word(exclude_idx=idx)
    word = W()[new_idx]
    btn = InlineKeyboardMarkup(
        [[InlineKeyboardButton("👁 Показать значение", callback_data=f"flash_show:{new_idx}")]]
    )
    await query.edit_message_text(
        f"🔁 Ещё повторим! {format_xp_line(xp, sb)}\n\n{format_word_label(new_idx)}",
        reply_markup=btn,
        parse_mode="Markdown"
    )

@auth
async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(format_stats_text(), parse_mode="Markdown")


def format_stats_text() -> str:
    total = len(W())
    learned = sum(1 for w in W() if w["correct_count"] >= 3)
    seen = sum(1 for w in W() if w["last_seen"] is not None)
    tc = PROGRESS["total_correct"]
    tw = PROGRESS["total_wrong"]
    accuracy = (tc / (tc + tw) * 100) if (tc + tw) > 0 else 0

    # Weak words (wrong > correct)
    weak = sorted(
        [w for w in W() if w["wrong_count"] > w["correct_count"] and w["last_seen"]],
        key=lambda w: w["wrong_count"] - w["correct_count"],
        reverse=True
    )[:10]
    weak_text = (
        "\n".join(
            f"  • {meaning_text(word)} — {target_text(word)}" for word in weak
        )
        if weak
        else "  Пока нет"
    )

    # Overdue
    now = datetime.now().isoformat()
    overdue = sum(1 for w in W() if w["next_review"] and w["next_review"] <= now)

    lvl, title, next_xp = get_level(PROGRESS["xp"])
    xp_line = f"{PROGRESS['xp']} XP"
    if next_xp:
        xp_line += f" ({next_xp - PROGRESS['xp']} до уровня {lvl + 1})"
    streak = PROGRESS.get("streak", 0)
    streak_best = PROGRESS.get("streak_best", 0)
    today_xp = PROGRESS.get("today_xp", 0)

    return (
        f"📊 *Статистика* ({active_content_pack().label})\n\n"
        f"📈 *Уровень {lvl} · {title}* — {xp_line}\n"
        f"🔥 Серия: {streak} дн. (рекорд: {streak_best})\n"
        f"⭐ Сегодня: +{today_xp} XP\n\n"
        f"📚 Слов: {total} | Изучено: {seen} | Выучено (3+): {learned}\n"
        f"⏰ На повторение: {overdue}\n\n"
        f"✅ Правильных: {tc} | ❌ Ошибок: {tw}\n"
        f"🎯 Точность: {accuracy:.1f}%\n\n"
        f"*Слабые слова:*\n{weak_text}"
    )

# ---------------------------------------------------------------------------
# /smart — Adaptive mode (auto quiz vs type)
# ---------------------------------------------------------------------------

@auth
async def cmd_smart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adaptive mode: weak words → quiz, strong words → type."""
    invalidate_block_session(context.user_data)
    idx = pick_word()
    mode = adaptive_mode(idx)
    word = W()[idx]

    if mode == "type":
        context.user_data["type_idx"] = idx
        context.user_data["smart_mode"] = True
        await update.message.reply_text(
            f"✍️ {format_word_label(idx)}\n\nНапиши перевод:",
            parse_mode="Markdown"
        )
    else:
        options, correct_pos = build_quiz_options(idx)
        buttons = []
        for opt in options:
            is_right = "1" if opt == meaning_text(word) else "0"
            cb = f"smart:{idx}:{is_right}"
            buttons.append([InlineKeyboardButton(opt, callback_data=cb)])
        await update.message.reply_text(
            f"❓ {format_word_label(idx)}\n\nВыбери перевод:",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown"
        )

@auth
async def smart_quiz_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    invalidate_block_session(context.user_data)
    parts = query.data.split(":")
    idx = int(parts[1])
    is_correct = parts[2] == "1"
    word = W()[idx]

    if is_correct:
        xp, sb = mark_correct(idx)
        text = f"✅\n{format_word_details(idx)}{get_example(idx)}\n{format_xp_line(xp, sb)}"
    else:
        xp, sb = mark_wrong(idx)
        text = f"❌\n{format_word_details(idx)}{get_example(idx)}\n{format_xp_line(xp, sb)}"

    next_btn = InlineKeyboardMarkup([
        [forvo_button(idx), InlineKeyboardButton("Дальше ➡️", callback_data="next_smart")]
    ])
    await query.edit_message_text(text, reply_markup=next_btn, parse_mode="Markdown")
    await send_pronunciation(query.message.chat_id, idx, context)

@auth
async def next_smart_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    invalidate_block_session(context.user_data)

    idx = pick_word()
    mode = adaptive_mode(idx)
    word = W()[idx]

    if mode == "type":
        context.user_data["type_idx"] = idx
        context.user_data["smart_mode"] = True
        await query.edit_message_text(
            f"✍️ {format_word_label(idx)}\n\nНапиши перевод:",
            parse_mode="Markdown"
        )
    else:
        options, _ = build_quiz_options(idx)
        buttons = []
        for opt in options:
            is_right = "1" if opt == meaning_text(word) else "0"
            cb = f"smart:{idx}:{is_right}"
            buttons.append([InlineKeyboardButton(opt, callback_data=cb)])
        await query.edit_message_text(
            f"❓ {format_word_label(idx)}\n\nВыбери перевод:",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown"
        )

# ---------------------------------------------------------------------------
# /poll — Native Telegram quiz polls with timer
# ---------------------------------------------------------------------------

@auth
async def cmd_poll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a native Telegram quiz poll with 15s timer."""
    invalidate_block_session(context.user_data)
    idx = pick_word()
    word = W()[idx]
    options, correct_pos = build_quiz_options(idx)

    msg = await update.message.reply_poll(
        question=f"{format_plain_word_prompt(idx)} — перевод?",
        options=options,
        type="quiz",
        correct_option_id=correct_pos,
        explanation=example_target_text(word)
        or f"{meaning_text(word)} — {target_text(word)}",
        open_period=15,
        is_anonymous=False,
    )
    context.bot_data.setdefault("poll_map", {})[msg.poll.id] = (
        int(update.effective_user.id),
        active_content_pack().pack_id,
        idx,
        correct_pos,
    )

@auth
async def poll_answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle native poll answers — track XP and SR."""
    answer = update.poll_answer

    poll_map = context.bot_data.get("poll_map", {})
    poll_data = poll_map.get(answer.poll_id)
    if poll_data is None:
        return

    invalidate_block_session(context.user_data)
    if len(poll_data) == 4:
        poll_user_id, pack_or_language, idx, correct_pos = poll_data
        if int(poll_user_id) != int(answer.user.id):
            return
        pack = CATALOG.get(pack_or_language) or visible_pack_for_language(
            pack_or_language
        )
        if pack is None or pack not in visible_packs():
            poll_map.pop(answer.poll_id, None)
            return
        runtime = _ACTIVE_RUNTIME.get()
        if runtime is not None and (
            PROGRESS.get("active_pack_id") != pack.pack_id
            or PROGRESS.get("active_lang") != pack.target_language
        ):
            activate_content_pack(pack, source="poll_restore")
        elif runtime is None:
            PROGRESS["active_pack_id"] = pack.pack_id
            PROGRESS["active_lang"] = pack.target_language
    else:
        # Compatibility with poll state created before the multi-user migration.
        idx, correct_pos = poll_data

    if answer.option_ids and answer.option_ids[0] == correct_pos:
        mark_correct(idx)
    else:
        mark_wrong(idx)

    poll_map.pop(answer.poll_id, None)

    # Auto-send next poll
    new_idx = pick_word()
    new_word = W()[new_idx]
    opts, new_correct = build_quiz_options(new_idx)
    msg = await context.bot.send_poll(
        chat_id=answer.user.id,
        question=f"{format_plain_word_prompt(new_idx)} — перевод?",
        options=opts,
        type="quiz",
        correct_option_id=new_correct,
        explanation=example_target_text(new_word)
        or f"{meaning_text(new_word)} — {target_text(new_word)}",
        open_period=15,
        is_anonymous=False,
    )
    poll_map[msg.poll.id] = (
        int(answer.user.id),
        active_content_pack().pack_id,
        new_idx,
        new_correct,
    )

# ---------------------------------------------------------------------------
# Block learning mode (/learn)
# ---------------------------------------------------------------------------

def activate_block_language(user_data: dict):
    """Keep block indices bound to the language used to create the block."""
    lang = user_data.get("block_lang")
    pack = CATALOG.get(user_data.get("block_pack_id", ""))
    runtime = _ACTIVE_RUNTIME.get()
    if pack is None or pack.target_language != lang:
        return
    role = runtime.role if runtime is not None else "admin"
    if not pack.visible_to(role):
        return
    if runtime is not None and PROGRESS.get("active_pack_id") != pack.pack_id:
        activate_content_pack(pack, source="block_restore")
        return
    if (
        PROGRESS.get("active_pack_id") != pack.pack_id
        or PROGRESS["active_lang"] != pack.target_language
    ):
        PROGRESS["active_pack_id"] = pack.pack_id
        PROGRESS["active_lang"] = pack.target_language
        save_progress(PROGRESS)


def pick_block(
    size: int = 10,
    topic: str | None = None,
    exclude_indices: set[int] | None = None,
) -> list[int]:
    """Pick a themed block with SR priority: overdue → new → random."""
    now = datetime.now().isoformat()
    overdue, new_words, rest = [], [], []
    for i, w in enumerate(W()):
        if topic and topic not in topics_for_word(w, PROGRESS["active_lang"]):
            continue
        if w["next_review"] is None and w["correct_count"] == 0:
            new_words.append(i)
        elif w["next_review"] and w["next_review"] <= now:
            overdue.append(i)
        else:
            rest.append(i)

    random.shuffle(overdue)
    random.shuffle(new_words)
    random.shuffle(rest)
    pool = overdue + new_words + rest
    if exclude_indices:
        fresh_pool = [idx for idx in pool if idx not in exclude_indices]
        if len(fresh_pool) >= min(size, len(pool)):
            pool = fresh_pool
    return pool[:size]


def due_word_indices(size: int = 20) -> list[int]:
    """Return words whose spaced-repetition date has arrived."""
    now = datetime.now().isoformat()
    due = [
        (index, word["next_review"])
        for index, word in enumerate(W())
        if word.get("next_review") and word["next_review"] <= now
    ]
    due.sort(key=lambda item: item[1])
    return [index for index, _ in due[:size]]


def daily_lesson_size() -> int:
    runtime = _ACTIVE_RUNTIME.get()
    if runtime is None:
        return 5
    product = runtime.store.product_profile(runtime.user_id)
    size = int(product.get("daily_word_goal") or 5)
    return size if size in {5, 10, 20} else 5


async def start_home_lesson(query, context, *, lesson_kind: str) -> None:
    """Start the primary daily or due-only lesson from the home screen."""
    invalidate_block_session(context.user_data)
    pack = active_content_pack()
    size = daily_lesson_size()
    if lesson_kind == "review":
        indices = due_word_indices(size)
        if not indices:
            record_product_event(
                "review_empty",
                properties={
                    "pack_id": pack.pack_id,
                    "language": pack.target_language,
                },
            )
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=(
                    "🎉 На сегодня всё повторено.\n\n"
                    "Можно пройти новый урок — бот сам добавит свежие слова."
                ),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "▶️ Начать новый урок", callback_data="start:daily"
                    )
                ]]),
            )
            return
    else:
        indices = pick_block(size=size)
    if not indices:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="В этом наборе пока нет доступных слов.",
        )
        return

    reset_block_state(
        context.user_data,
        indices,
        pack.target_language,
        None,
        pack.pack_id,
        lesson_kind=lesson_kind,
    )
    start_block_attempt(context.user_data, "flash")
    event_properties = {
        "pack_id": pack.pack_id,
        "language": pack.target_language,
        "lesson_kind": lesson_kind,
        "word_count": len(indices),
    }
    record_product_event(
        "lesson_started",
        properties=event_properties,
        session_id=context.user_data["block_session"],
        source="home",
    )
    record_product_event(
        "block_started",
        properties={**event_properties, "topic": "all"},
        session_id=context.user_data["block_session"],
        source="home",
    )
    record_product_event(
        "block_mode_started",
        properties={**event_properties, "mode": "flash"},
        session_id=context.user_data["block_session"],
        source="home",
    )
    await block_send_question_msg(query.message, context)


def format_study_list(indices: list[int]) -> str:
    lines = []
    pack = active_content_pack()
    for n, idx in enumerate(indices, 1):
        w = W()[idx]
        target = escape_markdown(format_target_word(w, pack))
        meaning = escape_markdown(meaning_display_text(w))
        lines.append(f"{n}. *{target}* — {meaning}")
    return "\n".join(lines)


def build_topic_keyboard(pack_or_language: ContentPack | str) -> InlineKeyboardMarkup:
    """Build a topic picker for one language using actual dictionary counts."""
    if isinstance(pack_or_language, ContentPack):
        pack = pack_or_language
    else:
        pack = CATALOG.get(pack_or_language) or visible_pack_for_language(
            pack_or_language
        )
    if pack is None or pack not in visible_packs():
        raise PermissionError("Content pack is not available to this user")
    words = PACK_DICTS[pack.pack_id]
    counts = topic_counts(
        words,
        pack.target_language,
        topic_labels=CATALOG.topic_labels,
    )
    rows = [[InlineKeyboardButton(
        f"🌐 Все слова ({len(words)})",
        callback_data=f"ltopic:{pack.pack_id}:all",
    )]]
    topic_buttons = [
        InlineKeyboardButton(
            f"{CATALOG.topic_labels[topic]} ({count})",
            callback_data=f"ltopic:{pack.pack_id}:{topic}",
        )
        for topic, count in counts.items()
    ]
    rows.extend(
        topic_buttons[index:index + 2]
        for index in range(0, len(topic_buttons), 2)
    )
    return InlineKeyboardMarkup(rows)


def topic_title(topic: str | None) -> str:
    return CATALOG.topic_labels.get(topic, "🌐 Все слова")


BLOCK_STALE_TEXT = "Эта кнопка устарела. Используй последнее сообщение блока."
BLOCK_MODES = {"quiz", "type", "flash"}


def new_block_session_id() -> str:
    """Return a short token that binds Telegram callbacks to one block state."""
    return secrets.token_hex(4)


def invalidate_block_session(user_data: dict):
    """Leave block mode and make every previously rendered block button stale."""
    user_data["block_session"] = None
    user_data["block_mode"] = None
    user_data["block_typing"] = False
    user_data["type_idx"] = None
    user_data["smart_mode"] = False


def reset_block_state(
    user_data: dict,
    indices: list[int],
    lang: str,
    topic: str | None,
    pack_id: str | None = None,
    *,
    lesson_kind: str | None = None,
):
    user_data["block_all_indices"] = list(indices)
    user_data["block_indices"] = list(indices)
    user_data["block_pos"] = 0
    user_data["block_correct"] = 0
    user_data["block_wrong"] = []
    user_data["block_mode"] = None
    user_data["block_typing"] = False
    user_data["smart_mode"] = False
    user_data["block_lang"] = lang
    if pack_id is None:
        candidate = CATALOG.get(PROGRESS.get("active_pack_id"))
        if candidate is None or candidate.target_language != lang:
            candidate = visible_pack_for_language(lang)
        pack_id = candidate.pack_id if candidate else None
    user_data["block_pack_id"] = pack_id
    user_data["block_topic"] = topic
    user_data["block_session"] = new_block_session_id()
    user_data["block_completion_tracked"] = False
    user_data["lesson_kind"] = lesson_kind
    user_data["lesson_completion_tracked"] = False


def start_block_attempt(user_data: dict, mode: str, indices: list[int] | None = None):
    """Start a fresh attempt and invalidate buttons from the previous block state."""
    attempt_indices = indices if indices is not None else user_data["block_all_indices"]
    user_data["block_indices"] = list(attempt_indices)
    user_data["block_pos"] = 0
    user_data["block_correct"] = 0
    user_data["block_wrong"] = []
    user_data["block_mode"] = mode
    user_data["block_typing"] = False
    user_data["type_idx"] = None
    user_data["smart_mode"] = False
    user_data["block_session"] = new_block_session_id()
    user_data["block_completion_tracked"] = False


def current_block_index(user_data: dict) -> int | None:
    indices = user_data.get("block_indices", [])
    pos = user_data.get("block_pos", 0)
    if not 0 <= pos < len(indices):
        return None
    return indices[pos]


def block_is_complete(user_data: dict) -> bool:
    indices = user_data.get("block_indices", [])
    return bool(indices) and user_data.get("block_pos", 0) >= len(indices)


async def reject_block_callback(query):
    await query.answer(BLOCK_STALE_TEXT, show_alert=True)


async def validate_block_callback(
    query,
    user_data: dict,
    session_id: str,
    *,
    mode: str | None = None,
    current_idx: int | None = None,
    member_idx: int | None = None,
    require_complete: bool = False,
) -> bool:
    """Answer a callback and reject buttons that no longer match active block state."""
    valid = bool(session_id) and session_id == user_data.get("block_session")
    if mode is not None:
        valid = valid and user_data.get("block_mode") == mode
    if current_idx is not None:
        valid = valid and current_block_index(user_data) == current_idx
    if member_idx is not None:
        valid = valid and member_idx in user_data.get("block_all_indices", [])
    if require_complete:
        valid = valid and block_is_complete(user_data)

    if not valid:
        await reject_block_callback(query)
        return False

    await query.answer()
    return True


def build_block_quiz_options(indices: list[int], idx: int) -> list[str]:
    """Build quiz options exclusively from the active block attempt."""
    correct_ru = meaning_text(W()[idx])
    distractors = list({
        meaning_text(W()[candidate])
        for candidate in indices
        if candidate != idx and meaning_text(W()[candidate]) != correct_ru
    })
    random.shuffle(distractors)
    options = distractors[:3] + [correct_ru]
    random.shuffle(options)
    return options


def build_block_quiz_keyboard(user_data: dict, idx: int) -> InlineKeyboardMarkup:
    correct_ru = meaning_text(W()[idx])
    session_id = user_data["block_session"]
    buttons = []
    for option in build_block_quiz_options(user_data["block_all_indices"], idx):
        is_right = "1" if option == correct_ru else "0"
        callback_data = f"bquiz:{session_id}:{idx}:{is_right}"
        buttons.append([InlineKeyboardButton(option, callback_data=callback_data)])
    return InlineKeyboardMarkup(buttons)


def card_event_properties(user_data: dict, idx: int) -> dict:
    return {
        "pack_id": active_content_pack().pack_id,
        "language": PROGRESS["active_lang"],
        "lesson_kind": user_data.get("lesson_kind") or "topic_block",
        "mode": user_data.get("block_mode") or "unknown",
        "position": int(user_data.get("block_pos", 0)) + 1,
        "word_count": len(user_data.get("block_indices", [])),
        "word_index": idx,
    }


def track_card_shown(user_data: dict, idx: int) -> None:
    record_product_event(
        "card_shown",
        properties=card_event_properties(user_data, idx),
        session_id=user_data.get("block_session"),
    )


def format_block_intro(indices: list[int], topic: str | None) -> str:
    return (
        f"📖 *{topic_title(topic)}*\n"
        f"Запомни {len(indices)} слов:\n\n{format_study_list(indices)}"
    )


def build_study_buttons(indices: list[int], session_id: str) -> InlineKeyboardMarkup:
    """Build inline keyboard with 🔊 buttons for each word + mode buttons."""
    # Audio buttons in rows of 5
    audio_row1 = [InlineKeyboardButton(f"🔊 {n}", callback_data=f"lplay:{session_id}:{idx}")
                  for n, idx in enumerate(indices[:5], 1)]
    audio_row2 = [InlineKeyboardButton(f"🔊 {n}", callback_data=f"lplay:{session_id}:{idx}")
                  for n, idx in enumerate(indices[5:], 6)]
    mode_row = [
        InlineKeyboardButton(
            "Тест · 4 варианта",
            callback_data=f"bmode:{session_id}:quiz",
        ),
        InlineKeyboardButton(
            "Письменно",
            callback_data=f"bmode:{session_id}:type",
        ),
    ]
    rows = [audio_row1]
    if audio_row2:
        rows.append(audio_row2)
    rows.append(mode_row)
    if AI_SETTINGS.enabled:
        rows.append([
            InlineKeyboardButton(
                "AI-репетитор", callback_data=f"bai:{session_id}"
            )
        ])
    rows.append([InlineKeyboardButton("Темы 📚", callback_data=f"btopics:{session_id}")])
    return InlineKeyboardMarkup(rows)


@auth
async def cmd_learn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    invalidate_block_session(context.user_data)
    pack = active_content_pack()
    context.user_data["block_lang"] = pack.target_language
    context.user_data["block_pack_id"] = pack.pack_id
    await update.message.reply_text(
        f"📚 *{pack.label}*\n\nВыбери тему:",
        reply_markup=build_topic_keyboard(pack),
        parse_mode="Markdown",
    )


@auth
async def learn_topic_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a block from the selected language and topic."""
    query = update.callback_query
    await query.answer()
    try:
        _, requested_pack, topic_id = query.data.split(":", 2)
    except ValueError:
        await query.edit_message_text("Выбор темы устарел. Отправь /learn.")
        return
    pack = CATALOG.get(requested_pack) or visible_pack_for_language(requested_pack)
    if pack is None or pack not in visible_packs():
        await query.edit_message_text("Этот набор недоступен.")
        return
    topic = None if topic_id == "all" else topic_id
    if topic and topic not in CATALOG.topic_labels:
        return

    activate_content_pack(pack, source="learning")
    indices = pick_block(topic=topic)
    reset_block_state(
        context.user_data, indices, pack.target_language, topic, pack.pack_id
    )
    if not indices:
        await query.edit_message_text(
            "В этой теме пока нет слов.",
            reply_markup=build_topic_keyboard(pack),
        )
        return
    await query.edit_message_text(
        format_block_intro(indices, topic),
        reply_markup=build_study_buttons(indices, context.user_data["block_session"]),
        parse_mode="Markdown",
    )
    record_product_event(
        "block_started",
        properties={
            "pack_id": pack.pack_id,
            "language": pack.target_language,
            "topic": topic or "all",
            "word_count": len(indices),
        },
        session_id=context.user_data["block_session"],
    )


@auth
async def block_topics_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Return from a block to the topic picker."""
    query = update.callback_query
    parts = query.data.split(":")
    if len(parts) != 2:
        await reject_block_callback(query)
        return
    if not await validate_block_callback(query, context.user_data, parts[1]):
        return
    pack = CATALOG.get(context.user_data.get("block_pack_id", ""))
    if pack is None or pack not in visible_packs():
        pack = active_content_pack()
    invalidate_block_session(context.user_data)
    await query.edit_message_text(
        f"📚 *{pack.label}*\n\nВыбери тему:",
        reply_markup=build_topic_keyboard(pack),
        parse_mode="Markdown",
    )


@auth
async def learn_play_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send the selected word card, then play its pronunciation."""
    query = update.callback_query
    try:
        _, session_id, idx_text = query.data.split(":")
        idx = int(idx_text)
    except ValueError:
        await reject_block_callback(query)
        return
    if not await validate_block_callback(
        query, context.user_data, session_id, member_idx=idx
    ):
        return
    activate_block_language(context.user_data)
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=format_word_details(idx),
        parse_mode="Markdown",
    )
    record_product_event(
        "word_audio_played",
        properties={
            "pack_id": active_content_pack().pack_id,
            "language": PROGRESS["active_lang"],
            "word_index": idx,
        },
        session_id=context.user_data.get("block_session"),
    )
    await send_pronunciation(query.message.chat_id, idx, context)


@auth
async def block_ai_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Consent preflight that cannot call AI before normal access control."""
    query = update.callback_query
    parts = query.data.split(":")
    if (
        len(parts) != 2
        or parts[1] != context.user_data.get("block_session")
    ):
        await reject_block_callback(query)
        return
    user_id = int(update.effective_user.id)
    if (
        AI_SETTINGS.enabled
        and AI_SETTINGS.consent_version
        and not get_store().has_consent(
            user_id,
            consent_type="ai_processing",
            document_version=AI_SETTINGS.consent_version,
        )
    ):
        await query.answer()
        await request_ai_tutor_answer(
            query.message,
            context,
            "Объясни главные связи между словами этого блока.",
            user_id=user_id,
            request_kind="active_block",
        )
        return
    await _authorized_block_ai_cb.__wrapped__(update, context)


@auth
async def _authorized_block_ai_cb(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    parts = query.data.split(":")
    if not await validate_block_callback(query, context.user_data, parts[1]):
        return
    activate_block_language(context.user_data)
    question = "Объясни главные связи между словами этого блока."
    if AI_SETTINGS.enabled:
        await request_ai_tutor_answer(
            query.message,
            context,
            question,
            user_id=int(update.effective_user.id),
            request_kind="active_block",
        )
    else:
        await send_ai_tutor_answer(
            query.message,
            context,
            question,
            user_id=int(update.effective_user.id),
        )


@auth
async def block_voice_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split(":")
    if len(parts) != 2 or not await validate_block_callback(
        query, context.user_data, parts[1]
    ):
        return
    if not VOICE_SETTINGS.enabled:
        await query.answer("Голосовой тренажёр пока выключен.", show_alert=True)
        return
    mode = "conversation" if parts[0] == "bconversation" else "pronunciation"
    activate_block_language(context.user_data)
    await query.answer()
    await start_voice_mode(update, context, mode=mode)


@auth
async def block_mode_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        _, session_id, mode = query.data.split(":")
    except ValueError:
        await reject_block_callback(query)
        return
    ud = context.user_data
    if mode not in BLOCK_MODES:
        await reject_block_callback(query)
        return
    if not await validate_block_callback(query, ud, session_id):
        return
    activate_block_language(ud)
    start_block_attempt(ud, mode)
    record_product_event(
        "block_mode_started",
        properties={
            "pack_id": active_content_pack().pack_id,
            "language": PROGRESS["active_lang"],
            "mode": mode,
            "word_count": len(ud["block_indices"]),
        },
        session_id=ud["block_session"],
    )
    await block_send_question(query, context)


async def block_send_question(query, context: ContextTypes.DEFAULT_TYPE):
    ud = context.user_data
    activate_block_language(ud)
    indices = ud["block_indices"]
    pos = ud["block_pos"]

    if pos >= len(indices):
        await block_summary(query, context)
        return

    idx = indices[pos]
    mode = ud["block_mode"]
    progress_text = f"({pos + 1}/{len(indices)})"
    track_card_shown(ud, idx)

    if mode == "quiz":
        await query.edit_message_text(
            f"{progress_text} {format_word_label(idx)}\n\nВыбери перевод:",
            reply_markup=build_block_quiz_keyboard(ud, idx),
            parse_mode="Markdown"
        )
        await send_pronunciation(query.message.chat_id, idx, context)

    elif mode == "type":
        ud["type_idx"] = idx
        ud["block_typing"] = True
        await query.edit_message_text(
            f"{progress_text} {format_word_label(idx)}\n\nНапиши перевод:",
            parse_mode="Markdown"
        )
        await send_pronunciation(query.message.chat_id, idx, context)

    elif mode == "flash":
        session_id = ud["block_session"]
        btn = InlineKeyboardMarkup(
            [[InlineKeyboardButton(
                "👁 Показать значение",
                callback_data=f"bflash_show:{session_id}:{idx}",
            )]]
        )
        await query.edit_message_text(
            format_learning_card_front(ud, idx),
            reply_markup=btn,
            parse_mode="Markdown"
        )
        await send_pronunciation(query.message.chat_id, idx, context)


async def block_advance(query_or_msg, context: ContextTypes.DEFAULT_TYPE, idx: int, correct: bool):
    """Record answer and advance to next word."""
    ud = context.user_data
    activate_block_language(ud)
    if current_block_index(ud) != idx:
        return False
    if correct:
        mark_correct(idx)
        ud["block_correct"] += 1
    else:
        mark_wrong(idx)
        ud["block_wrong"].append(idx)

    ud["block_pos"] += 1

    if ud["block_pos"] >= len(ud["block_indices"]):
        # For type mode, summary must be sent as new message
        if hasattr(query_or_msg, 'edit_message_text'):
            await block_summary(query_or_msg, context)
        else:
            await block_summary_msg(query_or_msg, context)
        return

    # Send next question — need a query object for edit_message_text
    if hasattr(query_or_msg, 'edit_message_text'):
        await block_send_question(query_or_msg, context)
    else:
        await block_send_question_msg(query_or_msg, context)
    return True


async def block_send_question_msg(message, context: ContextTypes.DEFAULT_TYPE):
    """Send a block question as a new message."""
    ud = context.user_data
    activate_block_language(ud)
    indices = ud["block_indices"]
    pos = ud["block_pos"]

    if pos >= len(indices):
        await block_summary_msg(message, context)
        return

    idx = indices[pos]
    mode = ud["block_mode"]
    progress_text = f"({pos + 1}/{len(indices)})"
    track_card_shown(ud, idx)

    if mode == "quiz":
        await message.reply_text(
            f"{progress_text} {format_word_label(idx)}\n\nВыбери перевод:",
            reply_markup=build_block_quiz_keyboard(ud, idx),
            parse_mode="Markdown"
        )
        await send_pronunciation(message.chat_id, idx, context)

    elif mode == "type":
        ud["type_idx"] = idx
        ud["block_typing"] = True
        await message.reply_text(
            f"{progress_text} {format_word_label(idx)}\n\nНапиши перевод:",
            parse_mode="Markdown"
        )
        await send_pronunciation(message.chat_id, idx, context)

    elif mode == "flash":
        session_id = ud["block_session"]
        btn = InlineKeyboardMarkup(
            [[InlineKeyboardButton(
                "👁 Показать значение",
                callback_data=f"bflash_show:{session_id}:{idx}",
            )]]
        )
        await message.reply_text(
            format_learning_card_front(ud, idx),
            reply_markup=btn,
            parse_mode="Markdown"
        )
        await send_pronunciation(message.chat_id, idx, context)


def format_block_summary(ud) -> str:
    total = len(ud["block_indices"])
    correct = ud["block_correct"]
    wrong_indices = ud["block_wrong"]
    # Award session completion bonus
    PROGRESS["sessions"] += 1
    award_xp(XP_SESSION)
    save_progress(PROGRESS)
    xp_earned = correct * XP_CORRECT + len(wrong_indices) * XP_WRONG + XP_SESSION
    lvl, title, next_xp = get_level(PROGRESS["xp"])

    text = f"📊 *Результат: {correct}/{total}*"
    if wrong_indices:
        text += "\n\n❌ Ошибки:"
        pack = active_content_pack()
        for idx in wrong_indices:
            w = W()[idx]
            text += (
                f"\n  • {pack.meaning_flag} "
                f"*{escape_markdown(meaning_text(w))}*"
            )
            text += (
                f"\n    {pack.flag} "
                f"*{escape_markdown(format_target_word(w, pack))}*"
            )
    else:
        text += "\n\n🎉 Без ошибок!"

    text += f"\n\n⭐ +{xp_earned} XP за урок | Всего: {PROGRESS['xp']} XP"
    text += f"\n📈 Уровень {lvl} · {title}"
    if next_xp:
        text += f" ({next_xp - PROGRESS['xp']} XP до следующего)"
    if PROGRESS["streak"] > 0:
        text += f"\n🔥 Серия: {PROGRESS['streak']} дн."
    return text


def track_block_completion(user_data: dict) -> None:
    if user_data.get("block_completion_tracked"):
        return
    user_data["block_completion_tracked"] = True
    record_product_event(
        "block_completed",
        properties={
            "pack_id": active_content_pack().pack_id,
            "language": PROGRESS["active_lang"],
            "mode": user_data.get("block_mode") or "unknown",
            "word_count": len(user_data.get("block_indices", [])),
            "correct_count": user_data.get("block_correct", 0),
            "wrong_count": len(user_data.get("block_wrong", [])),
        },
        session_id=user_data.get("block_session"),
    )


def track_lesson_completion(user_data: dict) -> None:
    lesson_kind = user_data.get("lesson_kind")
    if not lesson_kind or user_data.get("lesson_completion_tracked"):
        return
    user_data["lesson_completion_tracked"] = True
    record_product_event(
        "lesson_completed",
        properties={
            "pack_id": active_content_pack().pack_id,
            "language": PROGRESS["active_lang"],
            "lesson_kind": lesson_kind,
            "word_count": len(user_data.get("block_indices", [])),
            "correct_count": user_data.get("block_correct", 0),
            "wrong_count": len(user_data.get("block_wrong", [])),
        },
        session_id=user_data.get("block_session"),
    )


def build_block_summary_keyboard(user_data: dict) -> InlineKeyboardMarkup:
    rows = []
    session_id = user_data["block_session"]
    if user_data["block_wrong"]:
        rows.append([InlineKeyboardButton(
            "🔄 Повторить ошибки", callback_data=f"bretry:{session_id}"
        )])
    if AI_SETTINGS.enabled:
        rows.append([
            InlineKeyboardButton("✨ AI-репетитор", callback_data=f"bai:{session_id}")
        ])
    if VOICE_SETTINGS.enabled:
        rows.append([
            InlineKeyboardButton(
                "🗣 Произношение", callback_data=f"bvoice:{session_id}"
            ),
            InlineKeyboardButton(
                "💬 Фразы", callback_data=f"bconversation:{session_id}"
            ),
        ])
    if user_data.get("lesson_kind"):
        rows.append([InlineKeyboardButton(
            "▶️ Ещё урок", callback_data="start:daily"
        )])
        rows.append([
            InlineKeyboardButton("📚 Темы", callback_data=f"btopics:{session_id}"),
            InlineKeyboardButton("⚙️ Настройки", callback_data="start:settings"),
        ])
    else:
        rows.append([
            InlineKeyboardButton("➡️ Следующий блок", callback_data=f"bnext:{session_id}"),
            InlineKeyboardButton("📚 Темы", callback_data=f"btopics:{session_id}"),
        ])
    return InlineKeyboardMarkup(rows)


async def block_summary(query, context: ContextTypes.DEFAULT_TYPE):
    ud = context.user_data
    activate_block_language(ud)
    text = format_block_summary(ud)
    track_block_completion(ud)
    track_lesson_completion(ud)
    await query.edit_message_text(
        text,
        reply_markup=build_block_summary_keyboard(ud),
        parse_mode="Markdown"
    )


async def block_summary_msg(message, context: ContextTypes.DEFAULT_TYPE):
    ud = context.user_data
    activate_block_language(ud)
    text = format_block_summary(ud)
    track_block_completion(ud)
    track_lesson_completion(ud)
    ud["block_typing"] = False
    ud["type_idx"] = None
    await message.reply_text(
        text,
        reply_markup=build_block_summary_keyboard(ud),
        parse_mode="Markdown"
    )


@auth
async def block_quiz_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        _, session_id, idx_text, correct_text = query.data.split(":")
        idx = int(idx_text)
    except ValueError:
        await reject_block_callback(query)
        return
    if correct_text not in {"0", "1"}:
        await reject_block_callback(query)
        return
    if not await validate_block_callback(
        query,
        context.user_data,
        session_id,
        mode="quiz",
        current_idx=idx,
    ):
        return
    correct = correct_text == "1"
    await block_advance(query, context, idx, correct)


@auth
async def block_flash_show_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        _, session_id, idx_text = query.data.split(":")
        idx = int(idx_text)
    except ValueError:
        await reject_block_callback(query)
        return
    if not await validate_block_callback(
        query,
        context.user_data,
        session_id,
        mode="flash",
        current_idx=idx,
    ):
        return
    user_data = context.user_data
    activate_block_language(user_data)
    record_product_event(
        "card_revealed",
        properties=card_event_properties(user_data, idx),
        session_id=session_id,
    )
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🔊 Слушать ещё", callback_data=f"bplay:{session_id}:{idx}"
            ),
            forvo_button(idx),
        ],
        [
            InlineKeyboardButton(
                "😵 Не знаю", callback_data=f"bflash_didnt:{session_id}:{idx}"
            ),
            InlineKeyboardButton(
                "✅ Знаю", callback_data=f"bflash_knew:{session_id}:{idx}"
            ),
        ]
    ])
    await query.edit_message_text(
        format_learning_card_back(user_data, idx),
        reply_markup=buttons,
        parse_mode="Markdown"
    )


@auth
async def block_play_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        _, session_id, idx_text = query.data.split(":")
        idx = int(idx_text)
    except ValueError:
        await reject_block_callback(query)
        return
    if not await validate_block_callback(
        query,
        context.user_data,
        session_id,
        mode="flash",
        current_idx=idx,
    ):
        return
    activate_block_language(context.user_data)
    record_product_event(
        "card_audio_replayed",
        properties=card_event_properties(context.user_data, idx),
        session_id=session_id,
    )
    await send_pronunciation(query.message.chat_id, idx, context)


@auth
async def block_flash_rate_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    try:
        action, session_id, idx_text = data.split(":")
        idx = int(idx_text)
    except ValueError:
        await reject_block_callback(query)
        return
    if not await validate_block_callback(
        query,
        context.user_data,
        session_id,
        mode="flash",
        current_idx=idx,
    ):
        return
    correct = action == "bflash_knew"
    record_product_event(
        "card_rated",
        properties={
            **card_event_properties(context.user_data, idx),
            "rating": "known" if correct else "unknown",
        },
        session_id=session_id,
    )
    await block_advance(query, context, idx, correct)


@auth
async def block_retry_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    ud = context.user_data
    parts = query.data.split(":")
    if len(parts) != 2:
        await reject_block_callback(query)
        return
    if not await validate_block_callback(
        query, ud, parts[1], require_complete=True
    ):
        return
    activate_block_language(ud)
    wrong_indices = list(ud["block_wrong"])
    if not wrong_indices:
        return
    start_block_attempt(ud, ud["block_mode"], wrong_indices)
    record_product_event(
        "block_mode_started",
        properties={
            "pack_id": active_content_pack().pack_id,
            "language": PROGRESS["active_lang"],
            "mode": ud["block_mode"],
            "word_count": len(wrong_indices),
            "retry": True,
        },
        session_id=ud["block_session"],
    )
    await block_send_question(query, context)


@auth
async def block_next_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    ud = context.user_data
    parts = query.data.split(":")
    if len(parts) != 2:
        await reject_block_callback(query)
        return
    if not await validate_block_callback(
        query, ud, parts[1], require_complete=True
    ):
        return
    activate_block_language(ud)
    topic = ud.get("block_topic")
    previous_indices = set(ud.get("block_all_indices", []))
    indices = pick_block(topic=topic, exclude_indices=previous_indices)
    pack = active_content_pack()
    reset_block_state(
        ud, indices, pack.target_language, topic, pack.pack_id
    )
    await query.edit_message_text(
        format_block_intro(indices, topic),
        reply_markup=build_study_buttons(indices, ud["block_session"]),
        parse_mode="Markdown",
    )
    record_product_event(
        "block_started",
        properties={
            "pack_id": pack.pack_id,
            "language": pack.target_language,
            "topic": topic or "all",
            "word_count": len(indices),
        },
        session_id=ud["block_session"],
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_bot_commands(*, ai_enabled: bool) -> list[BotCommand]:
    """Return a stable, compact command menu; legacy handlers stay callable."""
    commands = [
        BotCommand("start", "Урок на сегодня"),
        BotCommand("learn", "Выбрать тему"),
        BotCommand("lang", "Сменить язык"),
        BotCommand("stats", "Мой прогресс"),
    ]
    if ai_enabled:
        commands.append(BotCommand("ai", "AI-репетитор"))
    commands.extend(
        [
            BotCommand("privacy", "Данные и приватность"),
            BotCommand("help", "Помощь"),
        ]
    )
    return commands


BOT_COMMANDS = build_bot_commands(ai_enabled=AI_SETTINGS.enabled)


async def sync_telegram_profile(telegram_bot) -> None:
    """Update optional Bot API metadata without blocking polling startup."""
    profile = get_bot_profile()
    operations = (
        ("commands", telegram_bot.set_my_commands, (BOT_COMMANDS,), {}),
        ("name", telegram_bot.set_my_name, (profile["bot_name"],), {}),
        (
            "short_description",
            telegram_bot.set_my_short_description,
            (profile["bot_short_description"],),
            {},
        ),
        (
            "description",
            telegram_bot.set_my_description,
            (profile["bot_description"],),
            {},
        ),
    )
    for operation, method, args, kwargs in operations:
        try:
            await method(*args, **kwargs)
        except TelegramError as exc:
            logger.warning(
                "Telegram profile sync skipped: operation=%s error_type=%s",
                operation,
                type(exc).__name__,
            )


TELEGRAM_NOTIFICATION_TEXTS = {
    "pilot_access_approved": (
        "Доступ к бесплатному пилоту MY DICTIONARY открыт. "
        "Отправь /start, выбери язык и начни первый блок."
    )
}


def _notification_retry_seconds(exc: Exception, attempts: int) -> int:
    retry_after = getattr(exc, "retry_after", None)
    if isinstance(retry_after, timedelta):
        return max(1, min(int(retry_after.total_seconds()) + 1, 3600))
    if isinstance(retry_after, (int, float)):
        return max(1, min(int(retry_after) + 1, 3600))
    return min(30 * (2 ** max(0, int(attempts) - 1)), 3600)


async def deliver_telegram_notifications(
    telegram_bot,
    store: DatabaseStore,
    *,
    limit: int = 10,
) -> int:
    """Deliver one leased outbox batch without exposing recipient data in logs."""
    claim = getattr(store, "claim_telegram_notifications", None)
    if not callable(claim):
        return 0
    notifications = claim(limit=limit)
    delivered = 0
    for notification in notifications:
        notification_id = notification["notification_id"]
        profile = store.access_profile(notification["telegram_user_id"])
        text = TELEGRAM_NOTIFICATION_TEXTS.get(notification["kind"])
        if not profile or profile["access_status"] != "active" or not text:
            store.cancel_telegram_notification(notification_id)
            continue
        try:
            await telegram_bot.send_message(
                chat_id=notification["telegram_user_id"],
                text=text,
            )
        except Exception as exc:
            status = store.retry_telegram_notification(
                notification_id,
                error_code=type(exc).__name__,
                retry_seconds=_notification_retry_seconds(
                    exc, notification["attempts"]
                ),
            )
            logger.warning(
                "Telegram notification delivery deferred: "
                "error_type=%s status=%s",
                type(exc).__name__,
                status,
            )
        else:
            if store.complete_telegram_notification(notification_id):
                delivered += 1
    return delivered


async def manual_polling():
    """Manual polling loop that handles Conflict gracefully."""
    BOT_HEARTBEAT.mark_starting()
    store = get_store()
    recovered_reservations = store.recover_stale_ai_usage(
        timeout_seconds=AI_SETTINGS.reservation_timeout_seconds
    )
    if recovered_reservations:
        logger.warning(
            "Recovered stale AI reservations: count=%s",
            recovered_reservations,
        )
    storage_mode = (
        "postgresql" if store.database_url.startswith("postgresql") else "sqlite"
    )
    logger.info(
        "Learner storage ready: mode=%s access=%s",
        storage_mode,
        BOT_ACCESS_MODE,
    )
    builder = Application.builder().token(BOT_TOKEN)
    app = TELEGRAM_RUNTIME.configure_builder(builder).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("quiz", cmd_quiz))
    app.add_handler(CommandHandler("type", cmd_type))
    app.add_handler(CommandHandler("flash", cmd_flash))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("learn", cmd_learn))
    app.add_handler(CommandHandler("smart", cmd_smart))
    app.add_handler(CommandHandler("poll", cmd_poll))
    app.add_handler(CommandHandler("lang", cmd_lang))
    app.add_handler(CommandHandler("ai", cmd_ai))
    app.add_handler(CommandHandler("voice", cmd_voice))
    app.add_handler(CommandHandler("conversation", cmd_conversation))
    app.add_handler(CommandHandler("voice_stop", cmd_voice_stop))
    app.add_handler(CommandHandler("voice_transcript", cmd_voice_transcript))
    app.add_handler(CommandHandler("ai_stats", cmd_ai_stats))
    app.add_handler(CommandHandler("buy", cmd_buy))
    app.add_handler(CommandHandler("subscriptions", cmd_subscriptions))
    app.add_handler(CommandHandler("terms", cmd_terms))
    app.add_handler(CommandHandler("paysupport", cmd_paysupport))
    app.add_handler(CommandHandler("privacy", cmd_privacy))
    app.add_handler(CommandHandler("response", cmd_mirror_response))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout_handler))
    app.add_handler(
        MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler)
    )
    app.add_handler(MessageHandler(filters.VOICE, voice_message_handler))

    # Welcome menu callbacks
    app.add_handler(CallbackQueryHandler(onboarding_cb, pattern=r"^onboarding:"))
    app.add_handler(CallbackQueryHandler(start_menu_cb, pattern=r"^start:"))
    app.add_handler(CallbackQueryHandler(billing_consent_cb, pattern=r"^billing:"))
    app.add_handler(
        CallbackQueryHandler(voice_consent_cb, pattern=r"^voiceconsent:")
    )
    app.add_handler(
        CallbackQueryHandler(ai_consent_cb, pattern=r"^aiconsent:")
    )
    app.add_handler(CallbackQueryHandler(buy_product_cb, pattern=r"^buy:"))
    app.add_handler(CallbackQueryHandler(subscription_cb, pattern=r"^sub:"))
    app.add_handler(CallbackQueryHandler(privacy_cb, pattern=r"^privacy:"))
    app.add_handler(CallbackQueryHandler(settings_cb, pattern=r"^settings:"))

    # Language switch callback
    app.add_handler(CallbackQueryHandler(lang_switch_cb, pattern=r"^lang:"))

    # Smart mode callbacks
    app.add_handler(CallbackQueryHandler(smart_quiz_cb, pattern=r"^smart:"))
    app.add_handler(CallbackQueryHandler(next_smart_cb, pattern=r"^next_smart$"))

    # Poll answer handler
    app.add_handler(PollAnswerHandler(poll_answer_handler))

    # Block learning callbacks
    app.add_handler(CallbackQueryHandler(learn_topic_cb, pattern=r"^ltopic:"))
    app.add_handler(CallbackQueryHandler(block_topics_cb, pattern=r"^btopics(?::|$)"))
    app.add_handler(CallbackQueryHandler(learn_play_cb, pattern=r"^lplay:"))
    app.add_handler(CallbackQueryHandler(block_ai_cb, pattern=r"^bai:"))
    app.add_handler(CallbackQueryHandler(block_voice_cb, pattern=r"^bvoice:"))
    app.add_handler(
        CallbackQueryHandler(block_voice_cb, pattern=r"^bconversation:")
    )
    app.add_handler(CallbackQueryHandler(block_mode_cb, pattern=r"^bmode:"))
    app.add_handler(CallbackQueryHandler(block_quiz_cb, pattern=r"^bquiz:"))
    app.add_handler(CallbackQueryHandler(block_play_cb, pattern=r"^bplay:"))
    app.add_handler(CallbackQueryHandler(block_flash_show_cb, pattern=r"^bflash_show:"))
    app.add_handler(CallbackQueryHandler(block_flash_rate_cb, pattern=r"^bflash_knew:"))
    app.add_handler(CallbackQueryHandler(block_flash_rate_cb, pattern=r"^bflash_didnt:"))
    app.add_handler(CallbackQueryHandler(block_retry_cb, pattern=r"^bretry(?::|$)"))
    app.add_handler(CallbackQueryHandler(block_next_cb, pattern=r"^bnext(?::|$)"))

    # Quiz callbacks
    app.add_handler(CallbackQueryHandler(quiz_callback, pattern=r"^quiz:"))
    app.add_handler(CallbackQueryHandler(next_quiz, pattern=r"^next_quiz$"))

    # Type callbacks
    app.add_handler(CallbackQueryHandler(next_type, pattern=r"^next_type$"))

    # Flash callbacks
    app.add_handler(CallbackQueryHandler(flash_show, pattern=r"^flash_show:"))
    app.add_handler(CallbackQueryHandler(flash_knew, pattern=r"^flash_knew:"))
    app.add_handler(CallbackQueryHandler(flash_didnt, pattern=r"^flash_didnt:"))

    # Language switch via persistent keyboard buttons
    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(PACK_SWITCH_PATTERN),
        handle_lang_switch,
    ))

    # Mirror delegates to every active exercise-answer state before free text.
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mirror_text_handler))

    # Initialize without starting the built-in updater
    await app.initialize()
    await app.start()
    await app.bot.delete_webhook(drop_pending_updates=True)
    await sync_telegram_profile(app.bot)
    logger.info("Bot command and profile sync completed")

    offset = None
    logger.info("Manual polling started")

    try:
        while True:
            try:
                updates = await app.bot.get_updates(
                    offset=offset, timeout=10, allowed_updates=Update.ALL_TYPES
                )
                BOT_HEARTBEAT.mark_ready()
                for update in updates:
                    offset = update.update_id + 1
                    await app.process_update(update)
                try:
                    delivered = await deliver_telegram_notifications(
                        app.bot,
                        store,
                    )
                    if delivered:
                        logger.info(
                            "Telegram notifications delivered: count=%s",
                            delivered,
                        )
                except Exception as exc:
                    logger.warning(
                        "Telegram notification delivery skipped: error_type=%s",
                        type(exc).__name__,
                    )
            except Conflict:
                BOT_HEARTBEAT.mark_starting()
                logger.warning("Conflict — another instance polling. Waiting 30s...")
                await asyncio.sleep(30)
            except Exception as e:
                BOT_HEARTBEAT.mark_starting()
                if "Conflict" in str(e):
                    logger.warning("Conflict — waiting 30s...")
                    await asyncio.sleep(30)
                else:
                    # Telegram exceptions can include the request URL and token.
                    logger.error(
                        "Telegram polling failed: error_type=%s",
                        type(e).__name__,
                    )
                    await asyncio.sleep(5)
    finally:
        BOT_HEARTBEAT.mark_stopped()
        await app.stop()
        await app.shutdown()
        store.close()

def main():
    packs = ", ".join(
        f"{pack.pack_id}: {pack.entry_count}" for pack in CATALOG.packs
    )
    logger.info("Bot starting — %s", packs)
    asyncio.run(manual_polling())

if __name__ == "__main__":
    main()
