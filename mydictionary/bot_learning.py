"""Durable native Telegram blocks sharing the canonical SRS and XP records."""

from datetime import timedelta
import hashlib
import json
import re
import secrets

from sqlalchemy import select

from mydictionary import storage
from mydictionary.content import target_text
from mydictionary.miniapp import MiniAppAccessDenied
from mydictionary.storage import BotLearningSession, PROFILE_FIELDS, WordProgress, vocabulary_id_for
from mydictionary.swipe import (
    SRS_INTERVALS, SwipeError, _aware, _daily_activity, _pack, _snapshot,
    _transaction, _xp,
)

MAX_WORDS = 100
MAX_TYPED_UPDATE_IDS = 256
STATE_KEYS = {
    "block_all_indices", "block_indices", "block_pos", "block_correct",
    "block_wrong", "block_mode", "block_typing", "block_lang", "block_pack_id",
    "block_topic", "block_session", "block_completion_tracked",
    "lesson_kind", "lesson_completion_tracked", "type_idx",
    "quick_mode_pending_start", "block_reward_granted", "block_storage_session",
}
BOOLEAN_KEYS = {
    "block_typing", "block_completion_tracked", "lesson_completion_tracked",
    "quick_mode_pending_start", "block_reward_granted",
}


class BotLearningError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = self.error = code


def _encode(value):
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _bounded(state, pack, words):
    result = {key: value for key, value in state.items() if key in STATE_KEYS}
    try:
        token = result["block_session"]
        if type(token) is not str or not re.fullmatch(r"[0-9a-f]{8}|[0-9a-f]{16}", token):
            raise ValueError
        if result["block_pack_id"] != pack.pack_id or result["block_lang"] != pack.target_language:
            raise ValueError
        for key in ("block_indices", "block_all_indices"):
            values = result[key]
            if (type(values) is not list or not 0 < len(values) <= MAX_WORDS
                or len(set(values)) != len(values)
                or any(type(index) is not int or not 0 <= index < len(words) for index in values)):
                raise ValueError
        indices = result["block_indices"]
        if not set(indices) <= set(result["block_all_indices"]):
            raise ValueError
        pos, correct, wrong = result["block_pos"], result["block_correct"], result["block_wrong"]
        if (type(pos) is not int or not 0 <= pos <= len(indices)
            or type(correct) is not int or not 0 <= correct <= pos
            or type(wrong) is not list or len(wrong) > MAX_WORDS
            or any(type(index) is not int or index not in indices[:pos] for index in wrong)
            or correct + len(wrong) != pos):
            raise ValueError
        if result.get("block_mode") not in {None, "flash", "quiz", "type"}:
            raise ValueError
        for key in BOOLEAN_KEYS:
            if key in result and type(result[key]) is not bool:
                raise ValueError
        for key in ("block_topic", "lesson_kind", "block_storage_session"):
            if key in result and result[key] is not None and (
                type(result[key]) is not str or len(result[key]) > 128
            ):
                raise ValueError
        if result.get("type_idx") is not None and (
            type(result["type_idx"]) is not int or result["type_idx"] not in indices
        ):
            raise ValueError
        if len(_encode(result)) > 8192:
            raise ValueError
    except (KeyError, ValueError, TypeError):
        raise BotLearningError("invalid_state") from None
    return json.loads(_encode(result))


def _content(words, indices):
    # The digest detects editorial changes too; the saved state never contains text.
    values = [{key: value for key, value in words[index].items()
               if key not in storage.WORD_PROGRESS_FIELDS} for index in indices]
    return hashlib.sha256(_encode(values).encode()).hexdigest()


def _word(session, user_id, pack, word):
    return session.scalar(select(WordProgress).where(
        WordProgress.telegram_user_id == user_id,
        WordProgress.language == pack.storage_key,
        WordProgress.vocabulary_id == vocabulary_id_for(word),
    ).with_for_update())


def _valid(row, saved, words, now):
    indices = saved.get("state", {}).get("block_all_indices", [])
    return (_aware(row.created_at) + timedelta(days=7) > now
            and bool(indices)
            and all(type(index) is int and 0 <= index < len(words) for index in indices)
            and saved.get("content_hash") == _content(words, indices))


def _response(row, saved):
    state = json.loads(_encode(saved["state"]))
    state["block_storage_session"] = row.session_id
    state["block_reward_granted"] = saved["completed"]
    return state


def load(store, *, user_id, catalog):
    """Restore only the currently selected, compatible pack's unexpired block."""
    try:
        with _transaction(store, user_id) as (session, user, profile):
            pack = _pack(catalog, user, profile)
            row = session.get(BotLearningSession, (user_id, pack.pack_id))
            if row is None:
                return None
            saved = json.loads(row.state_json)
            words = catalog.words(pack)
            if not _valid(row, saved, words, _aware(storage.utcnow())):
                return None
            _bounded(saved["state"], pack, words)
            return _response(row, saved)
    except MiniAppAccessDenied:
        raise BotLearningError("access_denied") from None
    except SwipeError:
        return None
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def save(store, *, user_id, catalog, state):
    """Acknowledge presentation saves without replacing issued SRS snapshots.

    False means a newer receipt won and the caller must not issue its stale
    token. Navigation without an active block is an acknowledged no-op.
    """
    if not state.get("block_session"):
        return True  # Navigation is not erasure; the per-pack block stays resumable.
    now = _aware(storage.utcnow())
    try:
        with _transaction(store, user_id) as (session, user, profile):
            pack = _pack(catalog, user, profile)
            words = catalog.words(pack)
            bounded = _bounded(state, pack, words)
            row = session.get(BotLearningSession, (user_id, pack.pack_id))
            old = json.loads(row.state_json) if row else None
            if row and bounded.get("block_storage_session") not in {None, row.session_id}:
                return False
            continuing = bool(row and _valid(row, old, words, now)
                and old["state"]["block_indices"] == bounded["block_indices"]
                and old["state"]["block_all_indices"] == bounded["block_all_indices"]
                and old["state"]["block_pos"] == bounded["block_pos"]
                and (row.session_id == bounded["block_session"] or bounded["block_pos"] > 0))
            if row and row.session_id == bounded["block_session"] and not continuing:
                return False  # A stale render/auth finally must not rewind an accepted rating.
            if continuing:
                saved = old
                for key in ("block_correct", "block_wrong"):
                    bounded[key] = old["state"][key]
                for key in ("block_completion_tracked", "lesson_completion_tracked"):
                    bounded[key] = bool(bounded.get(key) or old["state"].get(key))
                saved["state"] = bounded
            else:
                if bounded["block_pos"] != 0:
                    raise BotLearningError("invalid_state")
                saved = {"state": bounded, "completed": False,
                    "content_hash": _content(words, bounded["block_all_indices"]),
                    "typed_update_ids": (old.get("typed_update_ids", [])[-MAX_TYPED_UPDATE_IDS:]
                        if old and _aware(row.created_at) + timedelta(days=7) > now else []),
                    "snapshots": {str(index): _snapshot(_word(session, user_id, pack, words[index]))
                                  for index in bounded["block_indices"]}}
            if row is None:
                row = BotLearningSession(telegram_user_id=user_id, pack_id=pack.pack_id)
                session.add(row)
            if not continuing:
                row.created_at = now
            row.session_id = bounded["block_session"]
            row.updated_at = now
            bounded["block_storage_session"] = row.session_id
            bounded["block_reward_granted"] = saved["completed"]
            row.state_json = _encode(saved)
            state["block_storage_session"] = row.session_id
            state["block_reward_granted"] = saved["completed"]
        return True
    except MiniAppAccessDenied:
        raise BotLearningError("access_denied") from None
    except SwipeError as error:
        raise BotLearningError(error.error) from None


def rate(store, *, user_id, catalog, state, word_index, knew):
    """Atomically rate one issued card, advance its block and award completion once."""
    now = _aware(storage.utcnow())
    try:
        with _transaction(store, user_id) as (session, user, profile):
            pack = _pack(catalog, user, profile)
            row = session.get(BotLearningSession, (user_id, pack.pack_id))
            if row is None or row.session_id != state.get("block_session"):
                raise BotLearningError("session_unavailable")
            saved = json.loads(row.state_json)
            words = catalog.words(pack)
            if not _valid(row, saved, words, now):
                raise BotLearningError("session_unavailable")
            update_id = state.get("native_answer_update_id")
            if update_id is not None:
                if type(update_id) is not int or not 0 < update_id <= 2**63 - 1:
                    raise BotLearningError("invalid_state")
                if update_id in saved.get("typed_update_ids", []):
                    raise BotLearningError("answer_already_recorded")
            current = saved["state"]
            pos = current["block_pos"]
            if (type(knew) is not bool or type(word_index) is not int
                or type(state.get("block_pos")) is not int
                or state.get("block_pos") != pos or pos >= len(current["block_indices"])
                or current["block_indices"][pos] != word_index or saved["completed"]):
                raise BotLearningError("invalid_transition")
            word = _word(session, user_id, pack, words[word_index])
            if _snapshot(word) != saved["snapshots"][str(word_index)]:
                raise BotLearningError("progress_changed")
            if word is None:
                word = WordProgress(telegram_user_id=user_id, language=pack.storage_key,
                    vocabulary_id=vocabulary_id_for(words[word_index]),
                    term=target_text(words[word_index]), word_index=word_index,
                    correct_count=0, wrong_count=0, interval=1)
                session.add(word)
            previous_xp = profile.xp
            _daily_activity(profile, now)
            streak_bonus = profile.xp - previous_xp
            amount = 10 if knew else 2
            if knew:
                word.correct_count += 1
                word.interval = SRS_INTERVALS[min(word.correct_count, len(SRS_INTERVALS)) - 1]
                profile.total_correct += 1
                current["block_correct"] += 1
            else:
                word.correct_count = max(0, word.correct_count - 1)
                word.wrong_count += 1
                word.interval = 1
                profile.total_wrong += 1
                current["block_wrong"].append(word_index)
            word.last_seen = now.isoformat()
            word.next_review = (now + timedelta(days=word.interval)).isoformat()
            word.updated_at = now
            _xp(profile, amount, now)
            current["block_pos"] += 1
            current["block_typing"] = False
            current["type_idx"] = None
            if current["block_pos"] == len(current["block_indices"]):
                saved["completed"] = True
                profile.sessions += 1
                _xp(profile, 25, now)
            # A receipt commits a new callback generation along with position.
            # An old button can never acquire a fresh position after a restart.
            row.session_id = current["block_session"] = secrets.token_hex(4)
            profile.updated_at = row.updated_at = now
            if update_id is not None:
                saved["typed_update_ids"] = (
                    saved.get("typed_update_ids", []) + [update_id]
                )[-MAX_TYPED_UPDATE_IDS:]
            row.state_json = _encode(saved)
            return {"state": _response(row, saved),
                    "profile": {key: getattr(profile, key) for key in PROFILE_FIELDS},
                    "word": {key: getattr(word, key) for key in storage.WORD_PROGRESS_FIELDS},
                    "xp_earned": amount, "streak_bonus": streak_bonus}
    except MiniAppAccessDenied:
        raise BotLearningError("access_denied") from None
    except SwipeError as error:
        raise BotLearningError(error.error) from None
