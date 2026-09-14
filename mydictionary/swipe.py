"""Deterministic curated Mini App practice, with transactional replay and undo."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from uuid import UUID, uuid4

from sqlalchemy import select

from mydictionary import storage
from mydictionary.content import target_text
from mydictionary.miniapp import MiniAppAccessDenied
from mydictionary.storage import (
    AnalyticsEvent, MiniAppSwipeSession, User, UserProgress, WordProgress,
    WORD_PROGRESS_FIELDS, vocabulary_id_for,
)
from vocabulary_topics import transcription_for


# These are the deterministic bot's mark_correct/mark_wrong and XP contract.
SRS_INTERVALS = (1, 3, 7, 14, 30, 60)
LEVEL_THRESHOLDS = (0, 100, 300, 600, 1000, 1500, 2500, 4000, 6000)
MAX_OPERATIONS = 100  # Includes undone operations, keeping replay receipts bounded.
REQUEST_KEYS = {
    "deck": {"mode"},
    "rate": {"session_id", "operation_id", "word_index", "knew"},
    "undo": {"session_id", "operation_id"},
    "complete": {"session_id"},
}


class SwipeError(ValueError):
    def __init__(self, status: int, error: str = "invalid_transition"):
        super().__init__(error)
        self.status = status
        self.error = error


def _object(pairs):
    if len({key for key, _ in pairs}) != len(pairs):
        raise ValueError("Duplicate keys")
    return dict(pairs)


def parse_request(action: str, raw: bytes, mimetype: str) -> dict:
    """Reject extras, duplicates and type coercion at the signed boundary."""
    try:
        if mimetype != "application/json" or not raw or len(raw) > 512:
            raise ValueError("Invalid body")
        body = json.loads(raw.decode("utf-8"), object_pairs_hook=_object)
        if type(body) is not dict or set(body) != REQUEST_KEYS[action]:
            raise ValueError("Invalid keys")
        if action == "deck":
            if type(body["mode"]) is not str or body["mode"] not in {"mix", "forgotten", "new"}:
                raise ValueError("Invalid mode")
        else:
            for key in ("session_id", "operation_id"):
                if key in body:
                    value = body[key]
                    if type(value) is not str or len(value) != 36:
                        raise ValueError("Invalid UUID")
                    body[key] = str(UUID(value))
            if action == "rate" and (
                type(body["knew"]) is not bool
                or type(body["word_index"]) is not int
                or body["word_index"] < 0
            ):
                raise ValueError("Invalid rating")
        return body
    except (ValueError, UnicodeDecodeError, KeyError):
        raise SwipeError(400, "invalid_request") from None


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


@contextmanager
def _transaction(store, user_id):
    with store.Session.begin() as session:
        # SQLite ignores FOR UPDATE; reserve the writer before taking snapshots.
        if store.engine.dialect.name == "sqlite":
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        user = session.scalar(select(User).where(
            User.telegram_user_id == user_id
        ).with_for_update())
        if user is None or user.access_status != "active" or user.privacy_status != "active":
            raise MiniAppAccessDenied("Mini App access denied")
        profile = session.scalar(select(UserProgress).where(
            UserProgress.telegram_user_id == user_id
        ).with_for_update())
        if profile is None:
            raise MiniAppAccessDenied("Mini App access denied")
        yield session, user, profile


def _pack(catalog, user, profile):
    pack = catalog.get(str(profile.active_pack_id or ""))
    if (
        pack is None or profile.active_lang != pack.target_language
        or pack not in catalog.compatible_packs(user.native_language or "ru", user.role)
    ):
        raise SwipeError(409, "pack_unavailable")
    return pack


def _available(session, user_id, session_id, now):
    row = session.scalar(select(MiniAppSwipeSession).where(
        MiniAppSwipeSession.session_id == session_id,
        MiniAppSwipeSession.telegram_user_id == user_id,
    ).with_for_update())
    if row is None:
        raise SwipeError(404, "session_unavailable")
    if _aware(row.created_at) + timedelta(days=7) <= now:
        raise SwipeError(409, "session_expired")
    return row


def _state_response(row, state):
    operations = [state["operations"][oid] for oid in state["ratings"]]
    known = sum(operation["knew"] for operation in operations)
    return {
        "session_id": row.session_id, "queue": list(state["queue"]),
        "reviewed": len(operations), "known": known,
        "again": len(operations) - known,
        "undo_operation_id": state["ratings"][-1] if state["ratings"] else None,
    }


def _encode(state):
    return json.dumps(state, separators=(",", ":"), sort_keys=True)


def _require_current_content(row, state, words):
    """Saved indices must still identify the originally issued content."""
    initial_indices = json.loads(row.initial_indices_json)
    content_ids = state.get("content_ids", [])
    if len(initial_indices) != len(content_ids) or any(
        index >= len(words) or vocabulary_id_for(words[index]) != content_id
        for index, content_id in zip(initial_indices, content_ids)
    ):
        raise SwipeError(409, "content_changed")


def deck(store, *, user_id, catalog, mode):
    now = _aware(storage.utcnow())
    with _transaction(store, user_id) as (session, user, profile):
        pack = _pack(catalog, user, profile)
        words = catalog.words(pack)
        rows = session.scalars(select(WordProgress).where(
            WordProgress.telegram_user_id == user_id,
            WordProgress.language == pack.storage_key,
        )).all()
        progress = {row.vocabulary_id: row for row in rows}
        new, due, mistakes = [], [], []
        for index, word in enumerate(words):
            row = progress.get(vocabulary_id_for(word))
            if row is None:
                new.append(index)
                continue
            is_due = False
            if row.next_review:
                try:
                    is_due = _aware(datetime.fromisoformat(row.next_review)) <= now
                except ValueError:
                    pass
            if is_due:
                due.append(index)
            elif not row.last_seen and not row.correct_count and not row.wrong_count:
                new.append(index)
            elif row.wrong_count > 0 and row.correct_count < 3:
                mistakes.append(index)
        forgotten = due + mistakes
        if mode == "new":
            queue = new[:10]
        elif mode == "forgotten":
            queue = forgotten[:10]
        else:
            selected_f, selected_n = forgotten[:7], new[:3]
            capacity = 10 - len(selected_f) - len(selected_n)
            extra_f = forgotten[len(selected_f):len(selected_f) + capacity]
            selected_f += extra_f
            capacity -= len(extra_f)
            selected_n += new[len(selected_n):len(selected_n) + capacity]
            queue = []
            while selected_f or selected_n:
                queue += selected_f[:2]
                selected_f = selected_f[2:]
                queue += selected_n[:1]
                selected_n = selected_n[1:]
        cards = []
        for index in queue:
            word = words[index]
            aligned = catalog.meaning_entry(word, meaning_language=user.native_language or "ru", target_pack=pack, role=user.role)
            cards.append({
                "word_index": index, "target": target_text(word),
                "meaning": word["meaning"] if (user.native_language or "ru") == "ru" else target_text(aligned),
                "transcription": transcription_for(word, pack.target_language),
                "kind": "new" if index in new else "forgotten",
            })
        session_id = None
        if queue:
            session_id = str(uuid4())
            session.add(MiniAppSwipeSession(
                session_id=session_id, telegram_user_id=user_id,
                pack_id=pack.pack_id, language=pack.storage_key,
                initial_indices_json=_encode(queue),
                state_json=_encode({"queue": queue, "ratings": [], "operations": {}, "mode": mode,
                    "content_ids": [vocabulary_id_for(words[index]) for index in queue]}),
                created_at=now,
            ))
        return {
            "session_id": session_id, "pack_id": pack.pack_id,
            "language": pack.target_language, "tts_locale": pack.pronunciation.tts_locale,
            "mode": mode, "cards": cards, "queue": queue,
            "counts": {"new": len(new), "forgotten": len(forgotten), "total": len(new) + len(forgotten)},
        }


def _snapshot(word):
    if word is None:
        return None
    values = {field: getattr(word, field) for field in WORD_PROGRESS_FIELDS}
    values["updated_at"] = _aware(word.updated_at).isoformat()
    return values


def _level(profile):
    profile.level = max(1, sum(profile.xp >= threshold for threshold in LEVEL_THRESHOLDS))


def _xp(profile, amount, now):
    today = now.date().isoformat()
    if profile.today_date != today:
        profile.today_xp = 0
        profile.today_date = today
    profile.xp += amount
    profile.today_xp += amount
    _level(profile)


def _daily_activity(profile, now):
    today = now.date().isoformat()
    if profile.last_activity_date == today:
        return
    yesterday = (now - timedelta(days=1)).date().isoformat()
    profile.streak = profile.streak + 1 if profile.last_activity_date == yesterday else 1
    profile.last_activity_date = today
    profile.streak_best = max(profile.streak_best, profile.streak)
    profile.today_xp = 0
    profile.today_date = today
    _xp(profile, 15 * profile.streak, now)


def mutate(store, *, user_id, catalog, action, session_id, **body):
    now = _aware(storage.utcnow())
    with _transaction(store, user_id) as (session, user, profile):
        row = _available(session, user_id, session_id, now)
        pack = _pack(catalog, user, profile)
        if pack.pack_id != row.pack_id or pack.storage_key != row.language:
            raise SwipeError(409, "pack_changed")
        state = json.loads(row.state_json)
        if action == "complete":
            if state["queue"]:
                raise SwipeError(409)
            response = _state_response(row, state)
            if row.completed_at is None:
                profile.sessions += 1
                _xp(profile, 25, now)
                row.completed_at = now
                session.add(AnalyticsEvent(
                    event_id=str(uuid4()), telegram_user_id=user_id,
                    event_name="block_completed", source="miniapp", session_id=row.session_id,
                    properties_json=_encode({"pack_id": pack.pack_id, "language": pack.target_language,
                        "mode": state["mode"], "word_count": len(json.loads(row.initial_indices_json)),
                        "correct_count": response["known"], "wrong_count": response["again"]}),
                    occurred_at=now,
                ))
            return {"completed": True, "reviewed": response["reviewed"], "known": response["known"],
                "again": response["again"], "earned_xp": response["known"] * 10 + response["again"] * 2 + 25}
        if row.completed_at is not None:
            raise SwipeError(409, "session_completed")
        oid = body["operation_id"]
        operation = state["operations"].get(oid)
        words = catalog.words(pack)
        _require_current_content(row, state, words)
        if action == "rate":
            index, knew = body["word_index"], body["knew"]
            if index >= len(words):
                raise SwipeError(400, "invalid_request")
            if operation is not None:
                if operation["word_index"] != index or operation["knew"] != knew:
                    raise SwipeError(409, "operation_conflict")
                return _state_response(row, state)
            if not state["queue"] or state["queue"][0] != index or len(state["operations"]) >= MAX_OPERATIONS:
                raise SwipeError(409)
        else:
            if operation is None:
                raise SwipeError(409)
            if operation["undone"]:
                return _state_response(row, state)
            if not state["ratings"] or state["ratings"][-1] != oid:
                raise SwipeError(409)
            if now - _aware(datetime.fromisoformat(operation["rated_at"])) > timedelta(minutes=10):
                raise SwipeError(409, "undo_expired")
            index, knew = operation["word_index"], operation["knew"]
        word = session.scalar(select(WordProgress).where(
            WordProgress.telegram_user_id == user_id, WordProgress.language == row.language,
            WordProgress.vocabulary_id == vocabulary_id_for(words[index]),
        ).with_for_update())
        if action == "undo":
            if _snapshot(word) != operation["after"]:
                raise SwipeError(409, "progress_changed")
            prior = operation["before"]
            if prior is None:
                session.delete(word)
            else:
                for field in WORD_PROGRESS_FIELDS:
                    setattr(word, field, prior[field])
                # Restoring SRS is still a new mutation. Never resurrect an older
                # version token that another session could mistake for fresh.
                word.updated_at = now
            state["queue"] = operation["queue_before"]
            state["ratings"].pop()
            operation["undone"] = True
            if prior is not None:
                # Only this session's prior receipt can inherit the restored
                # freshness token. Other sessions remain stale after this undo.
                for previous_id in reversed(state["ratings"]):
                    previous = state["operations"][previous_id]
                    if previous["word_index"] == index:
                        if previous["after"] == prior:
                            previous["after"]["updated_at"] = _aware(word.updated_at).isoformat()
                        break
            amount = 10 if knew else 2
            profile.xp -= amount
            if profile.today_date == operation["activity_date"]:
                profile.today_xp -= amount
            if knew:
                profile.total_correct -= 1
            else:
                profile.total_wrong -= 1
            _level(profile)
        else:
            prior = _snapshot(word)
            if word is None:
                word = WordProgress(telegram_user_id=user_id, language=row.language,
                    vocabulary_id=vocabulary_id_for(words[index]), term=target_text(words[index]),
                    word_index=index, correct_count=0, wrong_count=0, interval=1)
                session.add(word)
            operation = {"word_index": index, "knew": knew, "before": prior,
                "queue_before": list(state["queue"]), "rated_at": now.isoformat(),
                "activity_date": now.date().isoformat(), "undone": False}
            if knew:
                word.correct_count += 1
                word.interval = SRS_INTERVALS[min(word.correct_count, len(SRS_INTERVALS)) - 1]
                profile.total_correct += 1
            else:
                word.correct_count = max(0, word.correct_count - 1)
                word.wrong_count += 1
                word.interval = 1
                profile.total_wrong += 1
            word.last_seen = now.isoformat()
            word.next_review = (now + timedelta(days=word.interval)).isoformat()
            word.updated_at = now
            operation["after"] = _snapshot(word)
            state["queue"].pop(0)
            previous_again = any(not state["operations"][old]["knew"] and state["operations"][old]["word_index"] == index for old in state["ratings"])
            if not knew and not previous_again:
                state["queue"].insert(min(2, len(state["queue"])), index)
            state["operations"][oid] = operation
            state["ratings"].append(oid)
            _daily_activity(profile, now)
            _xp(profile, 10 if knew else 2, now)
        profile.updated_at = now
        row.state_json = _encode(state)
        return _state_response(row, state)
