#!/usr/bin/env python3
"""MAX Context Bot — multilingual word quiz Telegram bot."""

import asyncio
import json
import random
import logging
import os
import time
import sys
from datetime import datetime, timedelta
from pathlib import Path

import yaml
from telegram import Bot, BotCommand, Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.error import Conflict
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, PollAnswerHandler, filters, ContextTypes
)

from tts import get_audio
from vocabulary_topics import (
    TOPIC_LABELS,
    topic_counts,
    topics_for_word,
    transcription_for,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
DATA_DIR = Path(os.environ.get("DATA_DIR", str(BASE_DIR)))

# Config: env vars first, then config.yaml fallback
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ALLOWED_USER = os.environ.get("ALLOWED_USER_ID")

if not BOT_TOKEN:
    CONFIG = yaml.safe_load((BASE_DIR / "config.yaml").read_text())
    BOT_TOKEN = CONFIG["telegram"]["bot_token"]
    ALLOWED_USER = ALLOWED_USER or CONFIG["telegram"]["allowed_user_id"]

ALLOWED_USER = int(ALLOWED_USER)

# ---------------------------------------------------------------------------
# Data layer — multi-language
# ---------------------------------------------------------------------------

LANG_FILES = {
    "en": "words.json",
    "vi": "words_vi.json",
    "ja": "words_ja.json",
}
LANG_LABELS = {
    "en": "🇬🇧 English",
    "vi": "🇻🇳 Tiếng Việt",
    "ja": "🇯🇵 日本語",
}
LANG_FLAGS = {"en": "🇬🇧", "vi": "🇻🇳", "ja": "🇯🇵"}

def _words_path(lang: str) -> Path:
    """Return path to word file — DATA_DIR if exists there, else BASE_DIR (and copy on first write)."""
    data_path = DATA_DIR / LANG_FILES[lang]
    base_path = BASE_DIR / LANG_FILES[lang]
    if not data_path.exists() and data_path != base_path:
        import shutil
        data_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(base_path, data_path)
    return data_path

def load_words(lang: str) -> list[dict]:
    with open(_words_path(lang), "r", encoding="utf-8") as f:
        return json.load(f)

def save_words_lang(lang: str):
    p = _words_path(lang)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(DICTS[lang], f, ensure_ascii=False, indent=2)

PROGRESS_DEFAULTS = {
    "total_correct": 0, "total_wrong": 0, "sessions": 0,
    "xp": 0, "level": 1,
    "streak": 0, "streak_best": 0, "last_activity_date": None,
    "today_xp": 0, "today_date": None,
    "active_lang": "en",
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

def save_progress(prog: dict):
    p = DATA_DIR / "progress.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(prog, f, ensure_ascii=False, indent=2)

DICTS: dict[str, list[dict]] = {lang: load_words(lang) for lang in LANG_FILES}
PROGRESS: dict = load_progress()

def W() -> list[dict]:
    """Return the active word list."""
    return DICTS[PROGRESS["active_lang"]]

def save_words(words: list[dict]):
    """Save the active word list."""
    save_words_lang(PROGRESS["active_lang"])

# ---------------------------------------------------------------------------
# XP / Levels / Streaks
# ---------------------------------------------------------------------------

XP_CORRECT = 10
XP_WRONG = 2
XP_SESSION = 25       # completing a block
XP_STREAK_BONUS = 15  # per streak day, awarded once daily

LEVELS = [
    (0,    "Novice"),
    (100,  "Learner"),
    (300,  "Student"),
    (600,  "Scholar"),
    (1000, "Linguist"),
    (1500, "Polyglot"),
    (2500, "Sage"),
    (4000, "Master"),
    (6000, "Legend"),
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
        parts.append(f"+{streak_bonus} streak bonus")
    lvl, title, _ = get_level(PROGRESS["xp"])
    parts.append(f"[Lv.{lvl} {title}]")
    return " | ".join(parts)

def get_example(idx: int) -> str:
    """Return example sentence if available."""
    ex = W()[idx].get("example")
    return f"\n💡 _{ex}_" if ex else ""

def get_pronunciation(idx: int) -> str:
    """Return pronunciation for a prompt without revealing the translation."""
    word = W()[idx]
    transcription = transcription_for(word, PROGRESS["active_lang"])
    if not transcription:
        return ""
    if PROGRESS["active_lang"] == "ja":
        return f"\n🔤 {transcription}"
    return f" {transcription}"

def format_word_label(idx: int) -> str:
    """Format a question prompt without exposing the Russian answer."""
    w = W()[idx]
    flag = LANG_FLAGS.get(PROGRESS["active_lang"], "")
    pronunciation = get_pronunciation(idx)
    return f"{flag} *{w['en']}*{pronunciation}"


def format_word_details(idx: int) -> str:
    """Format a revealed card: Russian first, foreign word, transcription."""
    word = W()[idx]
    lang = PROGRESS["active_lang"]
    flag = LANG_FLAGS.get(lang, "")
    lines = [f"🇷🇺 *{word['ru']}*", f"{flag} *{word['en']}*"]
    transcription = transcription_for(word, lang)
    if transcription:
        lines.append(f"🔤 {transcription}")
    return "\n".join(lines)


def format_plain_word_prompt(idx: int) -> str:
    """Format a compact prompt for Telegram surfaces without Markdown."""
    word = W()[idx]
    lang = PROGRESS["active_lang"]
    flag = LANG_FLAGS.get(lang, "")
    transcription = transcription_for(word, lang)
    suffix = f" ({transcription})" if transcription else ""
    return f"{flag} {word['en']}{suffix}"

def get_lang_keyboard():
    """Return one-time ReplyKeyboardMarkup with language buttons."""
    return ReplyKeyboardMarkup(
        [[LANG_LABELS["en"], LANG_LABELS["vi"]], [LANG_LABELS["ja"]]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

LANG_SWITCH_TEXTS = {label: code for code, label in LANG_LABELS.items()}

FORVO_LANG_CODES = {"en": "en", "vi": "vi", "ja": "ja"}

def forvo_button(idx: int) -> InlineKeyboardButton:
    """Return an inline button linking to Forvo pronunciation page."""
    word = W()[idx]
    lang = FORVO_LANG_CODES.get(PROGRESS["active_lang"], "en")
    url = f"https://forvo.com/word/{word['en'].replace(' ', '_')}/#{lang}"
    return InlineKeyboardButton("🔊 Forvo", url=url)

async def send_pronunciation(chat_id: int, idx: int, context: ContextTypes.DEFAULT_TYPE):
    """Generate and send voice pronunciation for the word at idx."""
    try:
        word = W()[idx]
        lang = PROGRESS["active_lang"]
        audio = await get_audio(word["en"], lang)
        try:
            await context.bot.send_voice(chat_id=chat_id, voice=audio)
        except Exception:
            audio.seek(0)
            await context.bot.send_audio(chat_id=chat_id, audio=audio, title=word["en"])
    except Exception as e:
        logger.warning(f"TTS failed for word {idx}: {e}")

def adaptive_mode(idx: int) -> str:
    """Pick quiz type based on word strength. Weak → quiz (recognition), strong → type (recall)."""
    w = W()[idx]
    if w["correct_count"] >= 3:
        return "type"
    return "quiz"

def build_quiz_options(idx: int) -> tuple[list[str], int]:
    """Build 4 options for a quiz question. Returns (options, correct_index)."""
    correct_ru = W()[idx]["ru"]
    distractors = set()
    attempts = 0
    while len(distractors) < 3 and attempts < 50:
        r = random.choice(W())
        if r["ru"] != correct_ru:
            distractors.add(r["ru"])
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
    save_words(W())
    save_progress(PROGRESS)
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
    save_words(W())
    save_progress(PROGRESS)
    return XP_WRONG, streak_bonus

# ---------------------------------------------------------------------------
# Auth decorator
# ---------------------------------------------------------------------------

def auth(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id != ALLOWED_USER:
            await update.effective_message.reply_text("Access denied.")
            return
        return await func(update, context)
    return wrapper

# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

@auth
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📚 *MAX Context Bot*\n"
        f"Словарь: {LANG_LABELS[PROGRESS['active_lang']]}\n\n"
        "/learn — Блок 10 слов\n"
        "/smart — Адаптивный режим\n"
        "/poll — Нативный квиз (таймер)\n"
        "/quiz — Тест с вариантами\n"
        "/type — Написать перевод\n"
        "/flash — Карточки\n"
        "/stats — Статистика\n"
        "/lang — Сменить язык",
        parse_mode="Markdown",
        reply_markup=get_lang_keyboard(),
    )

cmd_help = cmd_start

@auth
async def cmd_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch active language."""
    current = PROGRESS["active_lang"]
    buttons = []
    for lang_code, label in LANG_LABELS.items():
        marker = " ✓" if lang_code == current else ""
        total = len(DICTS[lang_code])
        learned = sum(1 for w in DICTS[lang_code] if w["correct_count"] >= 3)
        buttons.append([InlineKeyboardButton(
            f"{label} ({learned}/{total}){marker}",
            callback_data=f"lang:{lang_code}"
        )])
    await update.message.reply_text(
        f"Текущий словарь: *{LANG_LABELS[current]}*\n\nВыбери язык:",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown"
    )

@auth
async def lang_switch_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = query.data.split(":")[1]
    PROGRESS["active_lang"] = lang
    save_progress(PROGRESS)
    total = len(DICTS[lang])
    await query.edit_message_text(
        f"Словарь переключён на *{LANG_LABELS[lang]}* ({total} слов)",
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
    idx = pick_word()
    word = W()[idx]

    # Build 4 options: 1 correct + 3 distractors
    correct_ru = word["ru"]
    distractors = set()
    attempts = 0
    while len(distractors) < 3 and attempts < 50:
        r = random.choice(W())
        if r["ru"] != correct_ru:
            distractors.add(r["ru"])
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
        f"{format_word_label(idx)}\n\nChoose the correct translation:",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown"
    )
    await send_pronunciation(update.message.chat_id, idx, context)

@auth
async def quiz_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

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
        [forvo_button(idx), InlineKeyboardButton("Next ➡️", callback_data="next_quiz")]
    ])
    await query.edit_message_text(text, reply_markup=next_btn, parse_mode="Markdown")
    await send_pronunciation(query.message.chat_id, idx, context)

@auth
async def next_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    idx = pick_word()
    word = W()[idx]

    correct_ru = word["ru"]
    distractors = set()
    attempts = 0
    while len(distractors) < 3 and attempts < 50:
        r = random.choice(W())
        if r["ru"] != correct_ru:
            distractors.add(r["ru"])
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
    idx = pick_word()
    context.user_data["type_idx"] = idx
    word = W()[idx]
    await update.message.reply_text(
        f"{format_word_label(idx)}\n\nType the Russian translation:",
        parse_mode="Markdown"
    )
    await send_pronunciation(update.message.chat_id, idx, context)

@auth
async def handle_lang_switch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle language switch via persistent keyboard buttons."""
    text = update.message.text
    lang = LANG_SWITCH_TEXTS.get(text)
    if lang is None:
        return
    PROGRESS["active_lang"] = lang
    save_progress(PROGRESS)
    total = len(DICTS[lang])
    await update.message.reply_text(
        f"Словарь переключён на *{LANG_LABELS[lang]}* ({total} слов)",
        parse_mode="Markdown",
        reply_markup=get_lang_keyboard(),
    )

@auth
async def handle_type_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check typed translation — works for both single and block mode."""
    import re
    clean = lambda s: re.sub(r'[^\w\s]', '', s).strip()

    # Ignore language switch button presses
    if update.message.text in LANG_SWITCH_TEXTS:
        return

    idx = context.user_data.get("type_idx")
    if idx is None:
        return  # Not in type mode

    word = W()[idx]
    answer = update.message.text.strip().lower()
    correct = word["ru"].strip().lower()
    is_correct = clean(answer) == clean(correct)

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
        [forvo_button(idx), InlineKeyboardButton("Next ➡️", callback_data="next_type")]
    ])
    await update.message.reply_text(text, reply_markup=next_btn, parse_mode="Markdown")
    await send_pronunciation(update.message.chat_id, idx, context)

@auth
async def next_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    idx = pick_word()
    context.user_data["type_idx"] = idx
    word = W()[idx]
    await query.edit_message_text(
        f"{format_word_label(idx)}\n\nType the Russian translation:",
        parse_mode="Markdown"
    )
    await send_pronunciation(query.message.chat_id, idx, context)

@auth
async def cmd_flash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Flashcard mode."""
    idx = pick_word()
    word = W()[idx]
    btn = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Show translation 👁", callback_data=f"flash_show:{idx}")]]
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
    idx = int(query.data.split(":")[1])
    word = W()[idx]

    buttons = InlineKeyboardMarkup([
        [forvo_button(idx)],
        [
            InlineKeyboardButton("✅ Knew it", callback_data=f"flash_knew:{idx}"),
            InlineKeyboardButton("❌ Didn't know", callback_data=f"flash_didnt:{idx}"),
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
    idx = int(query.data.split(":")[1])
    xp, sb = mark_correct(idx)

    new_idx = pick_word(exclude_idx=idx)
    word = W()[new_idx]
    btn = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Show translation 👁", callback_data=f"flash_show:{new_idx}")]]
    )
    await query.edit_message_text(
        f"✅ Got it! {format_xp_line(xp, sb)}\n\n{format_word_label(new_idx)}",
        reply_markup=btn,
        parse_mode="Markdown"
    )

@auth
async def flash_didnt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    idx = int(query.data.split(":")[1])
    xp, sb = mark_wrong(idx)

    new_idx = pick_word(exclude_idx=idx)
    word = W()[new_idx]
    btn = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Show translation 👁", callback_data=f"flash_show:{new_idx}")]]
    )
    await query.edit_message_text(
        f"❌ Will repeat! {format_xp_line(xp, sb)}\n\n{format_word_label(new_idx)}",
        reply_markup=btn,
        parse_mode="Markdown"
    )

@auth
async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    weak_text = "\n".join(f"  • {w['ru']} — {w['en']}" for w in weak) if weak else "  Пока нет"

    # Overdue
    now = datetime.now().isoformat()
    overdue = sum(1 for w in W() if w["next_review"] and w["next_review"] <= now)

    lvl, title, next_xp = get_level(PROGRESS["xp"])
    xp_line = f"{PROGRESS['xp']} XP"
    if next_xp:
        xp_line += f" ({next_xp - PROGRESS['xp']} to Lv.{lvl + 1})"
    streak = PROGRESS.get("streak", 0)
    streak_best = PROGRESS.get("streak_best", 0)
    today_xp = PROGRESS.get("today_xp", 0)

    await update.message.reply_text(
        f"📊 *Статистика* ({LANG_LABELS[PROGRESS['active_lang']]})\n\n"
        f"📈 *Lv.{lvl} {title}* — {xp_line}\n"
        f"🔥 Streak: {streak} дн. (рекорд: {streak_best})\n"
        f"💰 Сегодня: +{today_xp} XP\n\n"
        f"📚 Слов: {total} | Изучено: {seen} | Выучено (3+): {learned}\n"
        f"⏰ На повторение: {overdue}\n\n"
        f"✅ Правильных: {tc} | ❌ Ошибок: {tw}\n"
        f"🎯 Точность: {accuracy:.1f}%\n\n"
        f"*Слабые слова:*\n{weak_text}",
        parse_mode="Markdown"
    )

# ---------------------------------------------------------------------------
# /smart — Adaptive mode (auto quiz vs type)
# ---------------------------------------------------------------------------

@auth
async def cmd_smart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adaptive mode: weak words → quiz, strong words → type."""
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
            is_right = "1" if opt == word["ru"] else "0"
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
            is_right = "1" if opt == word["ru"] else "0"
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
    idx = pick_word()
    word = W()[idx]
    options, correct_pos = build_quiz_options(idx)

    msg = await update.message.reply_poll(
        question=f"{format_plain_word_prompt(idx)} — перевод?",
        options=options,
        type="quiz",
        correct_option_id=correct_pos,
        explanation=word.get("example", f"{word['ru']} — {word['en']}"),
        open_period=15,
        is_anonymous=False,
    )
    context.bot_data.setdefault("poll_map", {})[msg.poll.id] = (idx, correct_pos)

async def poll_answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle native poll answers — track XP and SR."""
    answer = update.poll_answer
    if answer.user.id != ALLOWED_USER:
        return

    poll_map = context.bot_data.get("poll_map", {})
    poll_data = poll_map.get(answer.poll_id)
    if poll_data is None:
        return

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
        explanation=new_word.get("example", f"{new_word['ru']} — {new_word['en']}"),
        open_period=15,
        is_anonymous=False,
    )
    poll_map[msg.poll.id] = (new_idx, new_correct)

# ---------------------------------------------------------------------------
# Block learning mode (/learn)
# ---------------------------------------------------------------------------

def activate_block_language(user_data: dict):
    """Keep block indices bound to the language used to create the block."""
    lang = user_data.get("block_lang")
    if lang in DICTS and PROGRESS["active_lang"] != lang:
        PROGRESS["active_lang"] = lang
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


def format_study_list(indices: list[int]) -> str:
    lines = []
    for n, idx in enumerate(indices, 1):
        w = W()[idx]
        lang = PROGRESS["active_lang"]
        flag = LANG_FLAGS.get(lang, "")
        lines.append(f"{n}. 🇷🇺 *{w['ru']}*")
        lines.append(f"   {flag} *{w['en']}*")
        transcription = transcription_for(w, lang)
        if transcription:
            lines.append(f"   🔤 {transcription}")
    return "\n".join(lines)


def build_topic_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Build a topic picker for one language using actual dictionary counts."""
    counts = topic_counts(DICTS[lang], lang)
    rows = [[InlineKeyboardButton(
        f"🌐 Все слова ({len(DICTS[lang])})",
        callback_data=f"ltopic:{lang}:all",
    )]]
    topic_buttons = [
        InlineKeyboardButton(
            f"{TOPIC_LABELS[topic]} ({count})",
            callback_data=f"ltopic:{lang}:{topic}",
        )
        for topic, count in counts.items()
    ]
    rows.extend([button] for button in topic_buttons)
    return InlineKeyboardMarkup(rows)


def topic_title(topic: str | None) -> str:
    return TOPIC_LABELS.get(topic, "🌐 Все слова")


def reset_block_state(user_data: dict, indices: list[int], lang: str, topic: str | None):
    user_data["block_indices"] = indices
    user_data["block_pos"] = 0
    user_data["block_correct"] = 0
    user_data["block_wrong"] = []
    user_data["block_mode"] = None
    user_data["block_typing"] = False
    user_data["block_lang"] = lang
    user_data["block_topic"] = topic


def format_block_intro(indices: list[int], topic: str | None) -> str:
    return (
        f"📖 *{topic_title(topic)}*\n"
        f"Запомни {len(indices)} слов:\n\n{format_study_list(indices)}"
    )


def build_study_buttons(indices: list[int]) -> InlineKeyboardMarkup:
    """Build inline keyboard with 🔊 buttons for each word + mode buttons."""
    # Audio buttons in rows of 5
    audio_row1 = [InlineKeyboardButton(f"🔊 {n}", callback_data=f"lplay:{idx}")
                  for n, idx in enumerate(indices[:5], 1)]
    audio_row2 = [InlineKeyboardButton(f"🔊 {n}", callback_data=f"lplay:{idx}")
                  for n, idx in enumerate(indices[5:], 6)]
    mode_row = [
        InlineKeyboardButton("Quiz ❓", callback_data="bmode:quiz"),
        InlineKeyboardButton("Type ✍️", callback_data="bmode:type"),
        InlineKeyboardButton("Flash 👁", callback_data="bmode:flash"),
    ]
    rows = [audio_row1]
    if audio_row2:
        rows.append(audio_row2)
    rows.append(mode_row)
    rows.append([InlineKeyboardButton("Темы 📚", callback_data="btopics")])
    return InlineKeyboardMarkup(rows)


@auth
async def cmd_learn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = PROGRESS["active_lang"]
    context.user_data["block_lang"] = lang
    await update.message.reply_text(
        f"📚 *{LANG_LABELS[lang]}*\n\nВыбери тему:",
        reply_markup=build_topic_keyboard(lang),
        parse_mode="Markdown",
    )


@auth
async def learn_topic_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a block from the selected language and topic."""
    query = update.callback_query
    await query.answer()
    _, lang, topic_id = query.data.split(":", 2)
    if lang not in DICTS:
        return
    topic = None if topic_id == "all" else topic_id
    if topic and topic not in TOPIC_LABELS:
        return

    PROGRESS["active_lang"] = lang
    save_progress(PROGRESS)
    indices = pick_block(topic=topic)
    reset_block_state(context.user_data, indices, lang, topic)
    if not indices:
        await query.edit_message_text(
            "В этой теме пока нет слов.",
            reply_markup=build_topic_keyboard(lang),
        )
        return
    await query.edit_message_text(
        format_block_intro(indices, topic),
        reply_markup=build_study_buttons(indices),
        parse_mode="Markdown",
    )


@auth
async def block_topics_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Return from a block to the topic picker."""
    query = update.callback_query
    await query.answer()
    lang = context.user_data.get("block_lang", PROGRESS["active_lang"])
    await query.edit_message_text(
        f"📚 *{LANG_LABELS[lang]}*\n\nВыбери тему:",
        reply_markup=build_topic_keyboard(lang),
        parse_mode="Markdown",
    )


@auth
async def learn_play_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Play pronunciation for a word from the study list."""
    query = update.callback_query
    await query.answer()
    activate_block_language(context.user_data)
    idx = int(query.data.split(":")[1])
    await send_pronunciation(query.message.chat_id, idx, context)


@auth
async def block_mode_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    mode = query.data.split(":")[1]
    ud = context.user_data
    activate_block_language(ud)
    ud["block_mode"] = mode
    ud["block_pos"] = 0
    ud["block_correct"] = 0
    ud["block_wrong"] = []
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
    word = W()[idx]
    mode = ud["block_mode"]
    progress_text = f"({pos + 1}/{len(indices)})"

    if mode == "quiz":
        correct_ru = word["ru"]
        distractors = set()
        attempts = 0
        while len(distractors) < 3 and attempts < 50:
            r = random.choice(W())
            if r["ru"] != correct_ru:
                distractors.add(r["ru"])
            attempts += 1
        options = list(distractors) + [correct_ru]
        random.shuffle(options)

        buttons = []
        for opt in options:
            is_right = "1" if opt == correct_ru else "0"
            cb = f"bquiz:{idx}:{is_right}"
            buttons.append([InlineKeyboardButton(opt, callback_data=cb)])

        await query.edit_message_text(
            f"{progress_text} {format_word_label(idx)}\n\nВыбери перевод:",
            reply_markup=InlineKeyboardMarkup(buttons),
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
        btn = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Показать 👁", callback_data=f"bflash_show:{idx}")]]
        )
        await query.edit_message_text(
            f"{progress_text} {format_word_label(idx)}",
            reply_markup=btn,
            parse_mode="Markdown"
        )
        await send_pronunciation(query.message.chat_id, idx, context)


async def block_advance(query_or_msg, context: ContextTypes.DEFAULT_TYPE, idx: int, correct: bool):
    """Record answer and advance to next word."""
    ud = context.user_data
    activate_block_language(ud)
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


async def block_send_question_msg(message, context: ContextTypes.DEFAULT_TYPE):
    """Send next block question as a new message (for type mode)."""
    ud = context.user_data
    activate_block_language(ud)
    indices = ud["block_indices"]
    pos = ud["block_pos"]

    if pos >= len(indices):
        await block_summary_msg(message, context)
        return

    idx = indices[pos]
    word = W()[idx]
    mode = ud["block_mode"]
    progress_text = f"({pos + 1}/{len(indices)})"

    if mode == "quiz":
        correct_ru = word["ru"]
        distractors = set()
        attempts = 0
        while len(distractors) < 3 and attempts < 50:
            r = random.choice(W())
            if r["ru"] != correct_ru:
                distractors.add(r["ru"])
            attempts += 1
        options = list(distractors) + [correct_ru]
        random.shuffle(options)
        buttons = []
        for opt in options:
            is_right = "1" if opt == correct_ru else "0"
            cb = f"bquiz:{idx}:{is_right}"
            buttons.append([InlineKeyboardButton(opt, callback_data=cb)])
        await message.reply_text(
            f"{progress_text} {format_word_label(idx)}\n\nВыбери перевод:",
            reply_markup=InlineKeyboardMarkup(buttons),
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
        btn = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Показать 👁", callback_data=f"bflash_show:{idx}")]]
        )
        await message.reply_text(
            f"{progress_text} {format_word_label(idx)}",
            reply_markup=btn,
            parse_mode="Markdown"
        )
        await send_pronunciation(message.chat_id, idx, context)


def format_block_summary(ud) -> str:
    total = len(ud["block_indices"])
    correct = ud["block_correct"]
    wrong_indices = ud["block_wrong"]
    # Award session completion bonus
    award_xp(XP_SESSION)
    save_progress(PROGRESS)
    xp_earned = correct * XP_CORRECT + len(wrong_indices) * XP_WRONG + XP_SESSION
    lvl, title, next_xp = get_level(PROGRESS["xp"])

    text = f"📊 *Результат: {correct}/{total}*"
    if wrong_indices:
        text += "\n\n❌ Ошибки:"
        for idx in wrong_indices:
            w = W()[idx]
            lang = PROGRESS["active_lang"]
            text += f"\n  • 🇷🇺 *{w['ru']}*"
            text += f"\n    {LANG_FLAGS.get(lang, '')} *{w['en']}*"
            transcription = transcription_for(w, lang)
            if transcription:
                text += f"\n    🔤 {transcription}"
    else:
        text += "\n\n🎉 Без ошибок!"

    text += f"\n\n💰 +{xp_earned} XP за блок | Всего: {PROGRESS['xp']} XP"
    text += f"\n📈 Lv.{lvl} {title}"
    if next_xp:
        text += f" ({next_xp - PROGRESS['xp']} XP до след.)"
    if PROGRESS["streak"] > 0:
        text += f"\n🔥 Streak: {PROGRESS['streak']} дн."
    return text


async def block_summary(query, context: ContextTypes.DEFAULT_TYPE):
    ud = context.user_data
    activate_block_language(ud)
    text = format_block_summary(ud)
    rows = []
    if ud["block_wrong"]:
        rows.append([InlineKeyboardButton("Повторить ошибки 🔄", callback_data="bretry")])
    rows.append([
        InlineKeyboardButton("Следующий блок ➡️", callback_data="bnext"),
        InlineKeyboardButton("Темы 📚", callback_data="btopics"),
    ])
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(rows),
        parse_mode="Markdown"
    )


async def block_summary_msg(message, context: ContextTypes.DEFAULT_TYPE):
    ud = context.user_data
    activate_block_language(ud)
    text = format_block_summary(ud)
    rows = []
    if ud["block_wrong"]:
        rows.append([InlineKeyboardButton("Повторить ошибки 🔄", callback_data="bretry")])
    rows.append([
        InlineKeyboardButton("Следующий блок ➡️", callback_data="bnext"),
        InlineKeyboardButton("Темы 📚", callback_data="btopics"),
    ])
    ud["block_typing"] = False
    ud["type_idx"] = None
    await message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(rows),
        parse_mode="Markdown"
    )


@auth
async def block_quiz_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    idx = int(parts[1])
    correct = parts[2] == "1"
    await block_advance(query, context, idx, correct)


@auth
async def block_flash_show_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    activate_block_language(context.user_data)
    idx = int(query.data.split(":")[1])
    word = W()[idx]
    buttons = InlineKeyboardMarkup([
        [forvo_button(idx)],
        [
            InlineKeyboardButton("Знал ✅", callback_data=f"bflash_knew:{idx}"),
            InlineKeyboardButton("Не знал ❌", callback_data=f"bflash_didnt:{idx}"),
        ]
    ])
    await query.edit_message_text(
        format_word_details(idx),
        reply_markup=buttons,
        parse_mode="Markdown"
    )
    await send_pronunciation(query.message.chat_id, idx, context)


@auth
async def block_flash_rate_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    idx = int(data.split(":")[1])
    correct = data.startswith("bflash_knew")
    await block_advance(query, context, idx, correct)


@auth
async def block_retry_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ud = context.user_data
    activate_block_language(ud)
    ud["block_indices"] = list(ud["block_wrong"])
    ud["block_pos"] = 0
    ud["block_correct"] = 0
    ud["block_wrong"] = []
    await block_send_question(query, context)


@auth
async def block_next_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ud = context.user_data
    activate_block_language(ud)
    topic = ud.get("block_topic")
    previous_indices = set(ud.get("block_indices", []))
    indices = pick_block(topic=topic, exclude_indices=previous_indices)
    reset_block_state(ud, indices, PROGRESS["active_lang"], topic)
    await query.edit_message_text(
        format_block_intro(indices, topic),
        reply_markup=build_study_buttons(indices),
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def manual_polling():
    """Manual polling loop that handles Conflict gracefully."""
    app = Application.builder().token(BOT_TOKEN).build()

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

    # Language switch callback
    app.add_handler(CallbackQueryHandler(lang_switch_cb, pattern=r"^lang:"))

    # Smart mode callbacks
    app.add_handler(CallbackQueryHandler(smart_quiz_cb, pattern=r"^smart:"))
    app.add_handler(CallbackQueryHandler(next_smart_cb, pattern=r"^next_smart$"))

    # Poll answer handler
    app.add_handler(PollAnswerHandler(poll_answer_handler))

    # Block learning callbacks
    app.add_handler(CallbackQueryHandler(learn_topic_cb, pattern=r"^ltopic:"))
    app.add_handler(CallbackQueryHandler(block_topics_cb, pattern=r"^btopics$"))
    app.add_handler(CallbackQueryHandler(learn_play_cb, pattern=r"^lplay:"))
    app.add_handler(CallbackQueryHandler(block_mode_cb, pattern=r"^bmode:"))
    app.add_handler(CallbackQueryHandler(block_quiz_cb, pattern=r"^bquiz:"))
    app.add_handler(CallbackQueryHandler(block_flash_show_cb, pattern=r"^bflash_show:"))
    app.add_handler(CallbackQueryHandler(block_flash_rate_cb, pattern=r"^bflash_knew:"))
    app.add_handler(CallbackQueryHandler(block_flash_rate_cb, pattern=r"^bflash_didnt:"))
    app.add_handler(CallbackQueryHandler(block_retry_cb, pattern=r"^bretry$"))
    app.add_handler(CallbackQueryHandler(block_next_cb, pattern=r"^bnext$"))

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
        filters.TEXT & filters.Regex(r"^(🇬🇧 English|🇻🇳 Tiếng Việt|🇯🇵 日本語)$"),
        handle_lang_switch
    ))

    # Text handler for type-in mode (must be last)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_type_answer))

    # Initialize without starting the built-in updater
    await app.initialize()
    await app.start()
    await app.bot.delete_webhook(drop_pending_updates=True)
    await app.bot.set_my_commands([
        BotCommand("start", "Главное меню"),
        BotCommand("learn", "Блок 10 слов"),
        BotCommand("smart", "Адаптивный режим"),
        BotCommand("poll", "Нативный квиз (таймер)"),
        BotCommand("quiz", "Тест с вариантами"),
        BotCommand("type", "Написать перевод"),
        BotCommand("flash", "Карточки"),
        BotCommand("lang", "Сменить язык"),
        BotCommand("stats", "Статистика"),
        BotCommand("help", "Помощь"),
    ])
    logger.info("Bot commands menu registered")

    offset = None
    logger.info("Manual polling started")

    try:
        while True:
            try:
                updates = await app.bot.get_updates(
                    offset=offset, timeout=10, allowed_updates=Update.ALL_TYPES
                )
                for update in updates:
                    offset = update.update_id + 1
                    await app.process_update(update)
            except Conflict:
                logger.warning("Conflict — another instance polling. Waiting 30s...")
                await asyncio.sleep(30)
            except Exception as e:
                if "Conflict" in str(e):
                    logger.warning("Conflict — waiting 30s...")
                    await asyncio.sleep(30)
                else:
                    logger.error(f"Polling error: {e}")
                    await asyncio.sleep(5)
    finally:
        await app.stop()
        await app.shutdown()

def main():
    langs = ", ".join(f"{l}: {len(DICTS[l])}" for l in DICTS)
    logger.info(f"Bot starting — {langs}")
    asyncio.run(manual_polling())

if __name__ == "__main__":
    main()
