"""Locked swipe contract: public signed HTTP API, durable state and UI semantics."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text

os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN_ABCDEFGHIJKLMNOP")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot
from mydictionary import miniapp
from mydictionary.admin import create_app
from mydictionary.privacy import RetentionPolicy, apply_retention, erase_user_learning_data
from mydictionary.storage import AnalyticsEvent, DatabaseStore, User, UserProgress, WordProgress, vocabulary_id_for

ROOT = Path(__file__).resolve().parents[1]
USER_ID, OTHER_ID = 739001, 739002
HEAD = "0023_miniapp_swipe_sessions"
NODE = shutil.which("node") or "/Users/mark/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"


class MiniAppSwipeV1ApiTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="miniapp-swipe-test-")
        self.store = DatabaseStore(f"sqlite:///{Path(self.temporary.name) / 'test.sqlite3'}")
        self.pack = bot.CATALOG.require("en-basics-100")
        self.words = bot.CATALOG.words(self.pack)
        self.now = datetime.now(timezone.utc)
        for user_id in (USER_ID, OTHER_ID):
            self.store.ensure_user_id(user_id)
            with self.store.Session.begin() as session:
                user = session.get(User, user_id)
                user.access_status = user.privacy_status = "active"
                user.native_language = "ru"
            self.store.activate_pack(user_id, pack_id=self.pack.pack_id, language="en", source="test")
        self.app = self.make_app()
        self.client = self.app.test_client()
        self.limiter = patch("mydictionary.admin.PersistentRateLimiter.consume", return_value=SimpleNamespace(allowed=True, retry_after_seconds=0))
        self.limiter.start()

    def tearDown(self):
        self.limiter.stop()
        self.store.close()
        self.temporary.cleanup()

    def make_app(self, **overrides):
        return create_app({
            "TESTING": True, "SECRET_KEY": "s" * 40,
            "ADMIN_USERNAME": "owner", "ADMIN_PASSWORD": "test-password",
            "MINIAPP_ENABLED": True,
            "MINIAPP_PUBLIC_URL": "https://mydictionary.example.test/miniapp",
            "MINIAPP_BOT_USERNAME": "mydictionary_test_bot",
            "BOT_TOKEN_FILE": "/protected/bot-token",
            "AI_TUTOR_ENABLED": False, "VOICE_TUTOR_ENABLED": False,
            "TELEGRAM_STARS_ENABLED": False, **overrides,
        }, database_store=self.store)

    def post(self, action, body, *, user_id=USER_ID, client=None):
        with patch.object(miniapp, "verify_init_data", return_value={"user_id": user_id, "display_name": "Test", "language_code": "en"}):
            response = (client or self.client).post(f"/miniapp/api/swipe/{action}", json=body, headers={"X-Telegram-Init-Data": "signed"})
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")
        return response

    def deck(self, mode="new", **kwargs):
        response = self.post("deck", {"mode": mode}, **kwargs)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def rate(self, deck, knew, *, word_index=None, operation_id=None):
        return self.post("rate", {
            "session_id": deck["session_id"], "operation_id": operation_id or str(uuid4()),
            "word_index": deck["queue"][0] if word_index is None else word_index, "knew": knew,
        })

    def seed(self, index, *, correct=0, wrong=0, due=False, user_id=USER_ID):
        with self.store.Session.begin() as session:
            key = (user_id, self.pack.storage_key, vocabulary_id_for(self.words[index]))
            row = session.get(WordProgress, key)
            if row is None:
                row = WordProgress(telegram_user_id=user_id, language=self.pack.storage_key, vocabulary_id=key[2], term=self.words[index]["target"], word_index=index)
                session.add(row)
            row.correct_count, row.wrong_count, row.interval = correct, wrong, 7
            row.last_seen = (self.now - timedelta(days=2)).isoformat() if correct or wrong else None
            row.next_review = (self.now + timedelta(days=-1 if due else 30)).isoformat()

    def only_new(self, count):
        for index in range(count, len(self.words)):
            self.seed(index, correct=3)

    def profile(self):
        with self.store.Session() as session:
            row = session.get(UserProgress, USER_ID)
            return {name: getattr(row, name) for name in ("total_correct", "total_wrong", "sessions", "xp", "level", "streak", "streak_best", "last_activity_date", "today_xp", "today_date")}

    def word_state(self, index):
        with self.store.Session() as session:
            row = session.get(WordProgress, (USER_ID, self.pack.storage_key, vocabulary_id_for(self.words[index])))
            if row is None:
                return None
            return {name: getattr(row, name) for name in ("correct_count", "wrong_count", "interval", "last_seen", "next_review")}

    def finish(self, deck):
        state = deck
        while state["queue"]:
            response = self.rate(state, True)
            self.assertEqual(response.status_code, 200, response.get_json())
            state = response.get_json()
        return state

    def test_ac1_deck_has_real_native_meanings_pool_counts_and_stable_interleaving(self):
        for index in range(12, len(self.words)):
            self.seed(index, correct=3)
        for index in range(2, 10):
            self.seed(index, correct=3 if index % 2 == 0 else 1, wrong=1, due=index % 2 == 0)
        self.seed(10)  # A pre-created row without an actual rating is still new.
        deck = self.deck("mix")
        self.assertEqual(set(deck), {"session_id", "pack_id", "language", "tts_locale", "mode", "cards", "queue", "counts"})
        UUID(deck["session_id"])
        self.assertEqual(deck["pack_id"], self.pack.pack_id)
        self.assertEqual(deck["language"], "en")
        self.assertEqual(deck["tts_locale"], self.pack.pronunciation.tts_locale)
        self.assertEqual(deck["counts"], {"new": 4, "forgotten": 8, "total": 12})
        self.assertEqual(deck["queue"], [2, 4, 0, 6, 8, 1, 3, 5, 10, 7])
        self.assertEqual([card["word_index"] for card in deck["cards"]], deck["queue"])
        for card in deck["cards"]:
            word = self.words[card["word_index"]]
            self.assertEqual(set(card), {"word_index", "target", "meaning", "transcription", "kind"})
            self.assertEqual(card["target"], word["target"])
            self.assertEqual(card["meaning"], word["meaning"])
            self.assertEqual(card["kind"], "new" if card["word_index"] in (0, 1, 10) else "forgotten")
        with self.store.Session.begin() as session:
            session.get(User, USER_ID).native_language = "fr"
        french = self.deck("new")
        for card in french["cards"]:
            aligned = bot.CATALOG.meaning_entry(self.words[card["word_index"]], meaning_language="fr", target_pack=self.pack, role="learner")
            self.assertEqual(card["meaning"], aligned["target"])

    def test_ac1_mode_shortages_fill_without_learned_nondue_or_custom_fillers(self):
        self.only_new(2)
        self.seed(2, correct=1, wrong=1)
        self.store.upsert_custom_vocabulary(USER_ID, target_language="en", meaning_language="ru", entries=[SimpleNamespace(target="unrelated-custom", meaning="custom", transcription="", source_kind="text")])
        for mode, expected in (("new", [0, 1]), ("forgotten", [2]), ("mix", [2, 0, 1])):
            with self.subTest(mode=mode):
                deck = self.deck(mode)
                self.assertEqual(deck["queue"], expected)
                self.assertEqual(deck["counts"], {"new": 2, "forgotten": 1, "total": 3})

    def test_ac2_correct_srs_intervals_answer_xp_levels_and_daily_bonus(self):
        self.only_new(1)
        # A due card remains eligible at every mastery stage.
        for correct, interval in enumerate((1, 3, 7, 14, 30, 60, 60)):
            self.seed(0, correct=correct, due=True)
            before = self.profile()
            deck = self.deck("forgotten")
            response = self.rate(deck, True)
            self.assertEqual(response.status_code, 200, response.get_json())
            state = self.word_state(0)
            self.assertEqual(state["correct_count"], correct + 1)
            self.assertEqual(state["wrong_count"], 0)
            self.assertEqual(state["interval"], interval)
            seen = datetime.fromisoformat(state["last_seen"])
            review = datetime.fromisoformat(state["next_review"])
            self.assertEqual(review - seen, timedelta(days=interval))
            after = self.profile()
            self.assertEqual(after["total_correct"], before["total_correct"] + 1)
            self.assertEqual(after["xp"] - before["xp"], 25 if correct == 0 else 10)
            self.assertEqual(after["level"], bot.get_level(after["xp"])[0])
            self.assertEqual(after["streak"], 1)
            self.assertEqual(after["today_xp"], after["xp"])
        with self.store.Session.begin() as session:
            session.get(UserProgress, USER_ID).xp = 95
        # No new pool remains: level assertion uses a due card instead.
        self.seed(0, correct=7, due=True)
        deck = self.deck("forgotten")
        self.assertEqual(self.rate(deck, True).status_code, 200)
        self.assertEqual(self.profile()["level"], 2)

    def test_ac2_ac3_again_lowers_mastery_and_reinserts_once_after_two_cards(self):
        self.only_new(3)
        self.seed(0, correct=2, wrong=2, due=True)
        deck = self.deck("mix")
        self.assertEqual(deck["queue"], [0, 1, 2])
        response = self.rate(deck, False)
        self.assertEqual(response.status_code, 200)
        state = response.get_json()
        self.assertEqual(state["queue"], [1, 2, 0])
        self.assertEqual((state["reviewed"], state["known"], state["again"]), (1, 0, 1))
        progress = self.word_state(0)
        self.assertEqual((progress["correct_count"], progress["wrong_count"], progress["interval"]), (1, 3, 1))
        self.assertEqual(datetime.fromisoformat(progress["next_review"]) - datetime.fromisoformat(progress["last_seen"]), timedelta(days=1))
        self.assertEqual(self.profile()["total_wrong"], 1)
        self.assertEqual(self.profile()["xp"], 17)
        for _ in range(2):
            response = self.rate(state, True)
            self.assertEqual(response.status_code, 200)
            state = response.get_json()
        response = self.rate(state, False)
        self.assertEqual(response.status_code, 200)
        state = response.get_json()
        self.assertEqual(state["queue"], [])
        self.assertEqual((state["reviewed"], state["known"], state["again"]), (4, 2, 2))
        self.assertEqual(self.word_state(0)["correct_count"], 0)

    def test_ac3_err1_only_authoritative_queue_head_can_be_rated(self):
        self.only_new(2)
        deck = self.deck()
        before = self.profile()
        response = self.rate(deck, True, word_index=1)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.profile(), before)
        self.assertIsNone(self.word_state(1))

    def test_ac4_operation_replay_returns_current_state_and_conflict_is_nonmutating(self):
        self.only_new(2)
        deck = self.deck()
        operation_id = str(uuid4())
        first = self.rate(deck, True, operation_id=operation_id)
        self.assertEqual(first.status_code, 200)
        second = self.rate(first.get_json(), True)
        self.assertEqual(second.status_code, 200)
        before = self.profile()
        replay = self.rate(deck, True, operation_id=operation_id)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.get_json(), second.get_json())
        conflict = self.rate(deck, False, operation_id=operation_id)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(self.profile(), before)

    def test_ac4_undo_new_row_is_idempotent_and_preserves_daily_bonus(self):
        self.only_new(2)
        deck = self.deck()
        operation_id = str(uuid4())
        rating = self.rate(deck, True, operation_id=operation_id)
        self.assertEqual(rating.status_code, 200)
        self.assertEqual(rating.get_json()["undo_operation_id"], operation_id)
        body = {"session_id": deck["session_id"], "operation_id": operation_id}
        undo = self.post("undo", body)
        self.assertEqual(undo.status_code, 200)
        self.assertEqual(undo.get_json()["queue"], deck["queue"])
        self.assertEqual((undo.get_json()["reviewed"], undo.get_json()["known"], undo.get_json()["again"]), (0, 0, 0))
        self.assertIsNone(self.word_state(0))
        profile = self.profile()
        self.assertEqual((profile["xp"], profile["today_xp"], profile["total_correct"], profile["streak"]), (15, 15, 0, 1))
        replay = self.post("undo", body)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.get_json(), undo.get_json())
        self.assertEqual(self.profile(), profile)

    def test_ac4_undo_restores_existing_state_and_wrong_answer_totals(self):
        self.only_new(1)
        self.seed(0, correct=2, wrong=1, due=True)
        before_word = self.word_state(0)
        deck = self.deck("forgotten")
        operation_id = str(uuid4())
        rating = self.rate(deck, False, operation_id=operation_id)
        self.assertEqual(rating.status_code, 200)
        undo = self.post("undo", {"session_id": deck["session_id"], "operation_id": operation_id})
        self.assertEqual(undo.status_code, 200)
        self.assertEqual(self.word_state(0), before_word)
        self.assertEqual((self.profile()["total_wrong"], self.profile()["xp"]), (0, 15))

    def test_ac4_undo_rejects_old_operation_and_intervening_same_word_answer(self):
        self.only_new(2)
        first_deck, second_deck = self.deck(), self.deck()
        first_operation = str(uuid4())
        response = self.rate(first_deck, True, operation_id=first_operation)
        self.assertEqual(response.status_code, 200)
        second = self.rate(second_deck, True)
        self.assertEqual(second.status_code, 200)
        before = (self.profile(), self.word_state(0))
        conflict = self.post("undo", {"session_id": first_deck["session_id"], "operation_id": first_operation})
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual((self.profile(), self.word_state(0)), before)
        other_operation = str(uuid4())
        response = self.rate(response.get_json(), True, operation_id=other_operation)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.post("undo", {"session_id": first_deck["session_id"], "operation_id": first_operation}).status_code, 409)

    def test_ac4_same_word_again_know_undo_stack_restores_untracked_state_and_answer_totals(self):
        self.only_new(1)
        deck = self.deck("new")
        again_operation, know_operation = str(uuid4()), str(uuid4())
        again = self.rate(deck, False, operation_id=again_operation)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.get_json()["queue"], [0])
        know = self.rate(again.get_json(), True, operation_id=know_operation)
        self.assertEqual(know.status_code, 200)
        self.assertEqual(know.get_json()["queue"], [])
        undo_know = self.post("undo", {"session_id": deck["session_id"], "operation_id": know_operation})
        self.assertEqual(undo_know.status_code, 200)
        self.assertEqual(undo_know.get_json()["queue"], [0])
        self.assertEqual(undo_know.get_json()["undo_operation_id"], again_operation)
        undo_again = self.post("undo", {"session_id": deck["session_id"], "operation_id": again_operation})
        self.assertEqual(undo_again.status_code, 200)
        state = undo_again.get_json()
        self.assertEqual(state["queue"], deck["queue"])
        self.assertEqual((state["reviewed"], state["known"], state["again"]), (0, 0, 0))
        self.assertIsNone(state["undo_operation_id"])
        self.assertIsNone(self.word_state(0))
        profile = self.profile()
        self.assertEqual((profile["total_correct"], profile["total_wrong"], profile["xp"], profile["today_xp"], profile["streak"]), (0, 0, 15, 15, 1))

    def test_ac5_complete_is_empty_queue_only_idempotent_and_privacy_safe(self):
        self.only_new(2)
        deck = self.deck()
        self.assertEqual(self.post("complete", {"session_id": deck["session_id"]}).status_code, 409)
        final = self.finish(deck)
        response = self.post("complete", {"session_id": deck["session_id"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"completed": True, "reviewed": 2, "known": 2, "again": 0, "earned_xp": 45})
        before = self.profile()
        self.assertEqual((before["sessions"], before["xp"]), (1, 60))
        replay = self.post("complete", {"session_id": deck["session_id"]})
        self.assertEqual(replay.get_json(), response.get_json())
        self.assertEqual(self.profile(), before)
        self.assertEqual(self.rate(deck, True).status_code, 409)
        with self.store.Session() as session:
            events = session.scalars(select(AnalyticsEvent).where(AnalyticsEvent.telegram_user_id == USER_ID, AnalyticsEvent.event_name == "block_completed")).all()
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].source, "miniapp")
            properties = json.loads(events[0].properties_json)
            self.assertFalse({"target", "meaning", "term", "message", "answer", "user_id", "telegram_user_id"} & set(properties))
        # V2 permits correction of the final answer after completion. Keep the
        # first answer and daily bonus, reversing only the last rating and block.
        undo_body = {"session_id": deck["session_id"], "operation_id": final["undo_operation_id"]}
        undo = self.post("undo", undo_body)
        self.assertEqual(undo.status_code, 200, undo.get_json())
        self.assertEqual(undo.get_json()["queue"], [deck["queue"][-1]])
        self.assertEqual((undo.get_json()["reviewed"], undo.get_json()["known"], undo.get_json()["again"]), (1, 1, 0))
        corrected = self.profile()
        self.assertEqual((corrected["sessions"], corrected["xp"], corrected["today_xp"], corrected["total_correct"]), (0, 25, 25, 1))
        self.assertEqual(self.word_state(deck["queue"][0])["correct_count"], 1)
        self.assertIsNone(self.word_state(deck["queue"][-1]))
        self.assertEqual(self.post("undo", undo_body).get_json(), undo.get_json())
        self.assertEqual(self.profile(), corrected)
        with self.store.Session() as session:
            names = session.scalars(select(AnalyticsEvent.event_name).where(AnalyticsEvent.telegram_user_id == USER_ID)).all()
            self.assertEqual(names.count("block_completed"), 0)
            self.assertEqual(names.count("swipe_completion_undone"), 1)

    def test_ec1_empty_pool_has_no_session_or_xp(self):
        self.only_new(0)
        before = self.profile()
        for mode in ("mix", "new", "forgotten"):
            deck = self.deck(mode)
            self.assertEqual(deck["cards"], [])
            self.assertEqual(deck["queue"], [])
            self.assertIsNone(deck["session_id"])
            self.assertEqual(deck["counts"], {"new": 0, "forgotten": 0, "total": 0})
        self.assertEqual(self.profile(), before)
        self.assertEqual(self.post("complete", {"session_id": str(uuid4())}).status_code, 404)

    def test_ec1_one_and_two_card_again_queues_are_bounded(self):
        for count in (1, 2):
            with self.subTest(count=count):
                for index in range(len(self.words)):
                    self.seed(index, correct=0 if index < count else 3)
                deck = self.deck()
                ratings = 0
                while deck["queue"]:
                    response = self.rate(deck, False)
                    self.assertEqual(response.status_code, 200)
                    deck = response.get_json()
                    ratings += 1
                    self.assertLessEqual(len(deck["queue"]), count)
                    self.assertLessEqual(ratings, count * 2)
                self.assertEqual(ratings, count * 2)

    def test_ec3_content_reorder_rejects_rate_and_undo_without_retargeting_progress(self):
        self.only_new(3)
        catalog_type = type(bot.CATALOG)
        original_words = catalog_type.words

        def reordered_words(catalog, pack):
            words = original_words(catalog, pack)
            if pack.pack_id == self.pack.pack_id:
                first, second = swapped_indices
                words[first], words[second] = words[second], words[first]
            return words

        for action in ("rate", "undo"):
            with self.subTest(action=action):
                # Isolate each subcase even when the preceding RED request writes.
                with self.store.Session.begin() as session:
                    for index in range(3):
                        row = session.get(WordProgress, (USER_ID, self.pack.storage_key, vocabulary_id_for(self.words[index])))
                        if row is not None:
                            session.delete(row)
                deck = self.deck("new")
                operation_id = str(uuid4())
                swapped_indices = (0, 1) if action == "rate" else (1, 2)
                if action == "undo":
                    rating = self.rate(deck, True, operation_id=operation_id)
                    self.assertEqual(rating.status_code, 200)
                before = (self.profile(), *(self.word_state(index) for index in range(3)))
                with patch.object(catalog_type, "words", reordered_words):
                    if action == "rate":
                        response = self.rate(deck, True, operation_id=operation_id)
                    else:
                        response = self.post("undo", {"session_id": deck["session_id"], "operation_id": operation_id})
                self.assertEqual(response.status_code, 409)
                self.assertEqual((self.profile(), *(self.word_state(index) for index in range(3))), before)

    def test_err1_disabled_absent_invalid_expired_auth_and_access_denied(self):
        bodies = {"deck": {"mode": "new"}, "rate": {"session_id": str(uuid4()), "operation_id": str(uuid4()), "word_index": 0, "knew": True}, "undo": {"session_id": str(uuid4()), "operation_id": str(uuid4())}, "complete": {"session_id": str(uuid4())}}
        disabled = self.make_app(MINIAPP_ENABLED=False).test_client()
        for action, body in bodies.items():
            with self.subTest(action=action):
                self.assertEqual(self.post(action, body, client=disabled).status_code, 404)
                self.assertEqual(self.client.post(f"/miniapp/api/swipe/{action}", json=body).status_code, 401)
                for label in ("invalid", "expired"):
                    with patch.object(miniapp, "verify_init_data", side_effect=miniapp.MiniAppAuthenticationError(label)):
                        self.assertEqual(self.client.post(f"/miniapp/api/swipe/{action}", json=body, headers={"X-Telegram-Init-Data": "invalid"}).status_code, 401)
        for access, privacy in (("pending", "active"), ("active", "erased")):
            with self.store.Session.begin() as session:
                user = session.get(User, USER_ID)
                user.access_status, user.privacy_status = access, privacy
            for action, body in bodies.items():
                self.assertEqual(self.post(action, body).status_code, 403)

    def test_err1_json_exact_keys_uuid_boolean_index_and_unknown_session(self):
        deck = self.deck()
        sid, oid = deck["session_id"], str(uuid4())
        valid = {"session_id": sid, "operation_id": oid, "word_index": 0, "knew": True}
        cases = [("deck", {}), ("deck", {"mode": "NEW"}), ("deck", {"mode": 0}), ("deck", {"mode": "new", "extra": True}), ("deck", []), ("rate", {**valid, "extra": 0}), ("rate", {**valid, "session_id": "no"}), ("rate", {**valid, "operation_id": 1}), ("rate", {**valid, "operation_id": "not-a-uuid"}), ("rate", {**valid, "knew": 1}), ("rate", {**valid, "knew": "true"}), ("rate", {**valid, "word_index": True}), ("rate", {**valid, "word_index": "0"}), ("rate", {**valid, "word_index": -1}), ("rate", {**valid, "word_index": len(self.words)}), ("undo", {"session_id": sid, "operation_id": "bad"}), ("undo", {"session_id": sid, "operation_id": oid, "extra": True}), ("complete", {"session_id": sid, "extra": 0}), ("complete", {"session_id": None})]
        before = self.profile()
        for action, body in cases:
            with self.subTest(action=action, body=body):
                self.assertEqual(self.post(action, body).status_code, 400)
        with patch.object(miniapp, "verify_init_data", return_value={"user_id": USER_ID, "display_name": "Test", "language_code": "en"}):
            self.assertEqual(self.client.post("/miniapp/api/swipe/deck", data="{", content_type="application/json", headers={"X-Telegram-Init-Data": "signed"}).status_code, 400)
        unknown = str(uuid4())
        for action, body in (("rate", {**valid, "session_id": unknown}), ("undo", {"session_id": unknown, "operation_id": oid}), ("complete", {"session_id": unknown})):
            self.assertEqual(self.post(action, body).status_code, 404)
        self.assertEqual(self.profile(), before)

    def test_err1_throttled_storage_failure_and_no_broad_csrf_exemption(self):
        with patch("mydictionary.admin.PersistentRateLimiter.consume", return_value=SimpleNamespace(allowed=False, retry_after_seconds=9)):
            response = self.post("deck", {"mode": "new"})
            self.assertEqual(response.status_code, 429)
            self.assertGreaterEqual(int(response.headers["Retry-After"]), 1)
        with patch("mydictionary.admin.PersistentRateLimiter.consume", side_effect=RuntimeError("storage unavailable")):
            response = self.post("deck", {"mode": "new"})
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.get_json(), {"error": "temporarily_unavailable"})
        self.assertEqual(self.client.post("/miniapp/api/swipe/not-a-route", json={}).status_code, 400)
        self.assertEqual(self.client.post("/users", json={}).status_code, 400)

    def test_err2_cross_owner_session_ids_never_disclose_or_mutate(self):
        self.only_new(1)
        deck = self.deck()
        before = self.profile()
        for action, body in (("rate", {"session_id": deck["session_id"], "operation_id": str(uuid4()), "word_index": 0, "knew": True}), ("undo", {"session_id": deck["session_id"], "operation_id": str(uuid4())}), ("complete", {"session_id": deck["session_id"]})):
            response = self.post(action, body, user_id=OTHER_ID)
            self.assertEqual(response.status_code, 404)
            self.assertNotIn(deck["session_id"], response.get_data(as_text=True))
        self.assertEqual(self.profile(), before)
        self.assertIsNone(self.word_state(0))

    def test_err1_err2_pack_switch_missing_hidden_incompatible_and_expired_are_nonmutating(self):
        self.only_new(1)
        deck = self.deck()
        before = self.profile()
        incompatible = bot.CATALOG.require("fr-basics-100")
        with self.store.Session.begin() as session:
            session.get(UserProgress, USER_ID).active_pack_id = incompatible.pack_id
        self.assertEqual(self.rate(deck, True).status_code, 409)
        self.assertIsNone(self.word_state(0))
        self.assertEqual(self.profile()["xp"], before["xp"])
        for pack_id, native in (("missing-pack", "ru"), ("en-basics-100", "en")):
            with self.store.Session.begin() as session:
                session.get(UserProgress, USER_ID).active_pack_id = pack_id
                session.get(User, USER_ID).native_language = native
            self.assertIn(self.post("deck", {"mode": "new"}).status_code, (400, 409))
        with self.store.Session.begin() as session:
            session.get(UserProgress, USER_ID).active_pack_id = self.pack.pack_id
            session.get(User, USER_ID).native_language = "ru"
        with patch("mydictionary.catalog.ContentPack.visible_to", return_value=False):
            self.assertIn(self.post("deck", {"mode": "new"}).status_code, (400, 409))
            self.assertEqual(self.rate(deck, True).status_code, 409)
        self.assertIn("miniapp_swipe_sessions", inspect(self.store.engine).get_table_names())
        with self.store.engine.begin() as connection:
            connection.execute(text("UPDATE miniapp_swipe_sessions SET created_at = :old"), {"old": self.now - timedelta(days=8)})
        self.assertEqual(self.rate(deck, True).status_code, 409)
        self.assertEqual(self.profile()["xp"], before["xp"])

    def test_ac4_undo_window_expires_after_ten_minutes_without_overwrite(self):
        self.only_new(1)
        deck = self.deck()
        oid = str(uuid4())
        self.assertEqual(self.rate(deck, True, operation_id=oid).status_code, 200)
        before = (self.profile(), self.word_state(0))
        # Patch the established project clock, not the new module's internals.
        with patch("mydictionary.storage.utcnow", return_value=datetime.now(timezone.utc) + timedelta(minutes=11)):
            response = self.post("undo", {"session_id": deck["session_id"], "operation_id": oid})
        self.assertEqual(response.status_code, 409)
        self.assertEqual((self.profile(), self.word_state(0)), before)

    def test_ec2_additive_migration_downgrade_erasure_and_retention_isolate_owners(self):
        self.seed(0, correct=2, wrong=1)
        before = self.word_state(0)
        first, second = self.deck("new"), self.deck("new", user_id=OTHER_ID)
        tables = set(inspect(self.store.engine).get_table_names())
        self.assertIn("miniapp_swipe_sessions", tables)
        with self.store.engine.connect() as connection:
            self.assertEqual(connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one(), HEAD)
            rows = connection.execute(text("SELECT * FROM miniapp_swipe_sessions")).mappings().all()
            self.assertEqual(len(rows), 2)
            serialized = json.dumps([dict(row) for row in rows], default=str, ensure_ascii=False)
            for card in first["cards"]:
                self.assertNotIn(card["target"], serialized)
                self.assertNotIn(card["meaning"], serialized)
            self.assertNotIn("signed", serialized)
        erase_user_learning_data(self.store, USER_ID, actor="test")
        with self.store.engine.connect() as connection:
            self.assertEqual(connection.execute(text("SELECT COUNT(*) FROM miniapp_swipe_sessions")).scalar_one(), 1)
        # Another learner still owns a usable session after the erasure.
        response = self.post("rate", {"session_id": second["session_id"], "operation_id": str(uuid4()), "word_index": second["queue"][0], "knew": True}, user_id=OTHER_ID)
        self.assertEqual(response.status_code, 200)
        third = self.deck("new", user_id=OTHER_ID)
        with self.store.engine.begin() as connection:
            # Expire only the first remaining session, preserving the recent one.
            pk = inspect(self.store.engine).get_pk_constraint("miniapp_swipe_sessions")["constrained_columns"][0]
            connection.execute(text(f'UPDATE miniapp_swipe_sessions SET created_at = :old WHERE "{pk}" = :sid'), {"old": self.now - timedelta(days=8), "sid": second["session_id"]})
        apply_retention(self.store, RetentionPolicy.from_env({}), now=self.now)
        with self.store.engine.connect() as connection:
            self.assertEqual(connection.execute(text("SELECT COUNT(*) FROM miniapp_swipe_sessions")).scalar_one(), 1)
        self.assertEqual(self.post("complete", {"session_id": second["session_id"]}, user_id=OTHER_ID).status_code, 404)
        self.assertEqual(self.post("rate", {"session_id": third["session_id"], "operation_id": str(uuid4()), "word_index": third["queue"][0], "knew": True}, user_id=OTHER_ID).status_code, 200)
        config = Config(str(ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(ROOT / "migrations"))
        config.set_main_option("sqlalchemy.url", str(self.store.engine.url))
        command.downgrade(config, "0022_custom_vocab_translation")
        self.assertEqual(set(inspect(self.store.engine).get_table_names()), tables - {"miniapp_swipe_sessions"})
        with self.store.Session() as session:
            self.assertIsNotNone(session.get(WordProgress, (OTHER_ID, self.pack.storage_key, vocabulary_id_for(self.words[0]))))
        command.upgrade(config, "head")
        self.assertIn("miniapp_swipe_sessions", inspect(self.store.engine).get_table_names())


class MiniAppSwipeV1UiTest(unittest.TestCase):
    def test_ac6_existing_bottom_navigation_is_byte_for_byte_unchanged(self):
        html = (ROOT / "mydictionary/templates/miniapp.html").read_bytes()
        nav = re.search(rb'<nav class="bottom-nav"[\s\S]*?</nav>', html).group(0)
        # Locked from the 3,386 raw navigation bytes in BASE, not the current
        # template; remains verifiable under CI's history-free shallow checkout.
        # BASE: d8d98a41b22f5fe236cd57991c5794fb28607c40
        baseline_sha256 = "ee945fcfc4e0ccc7193c80953b3081448ae7b5bb32c82fe3d3b7e1bcbbe8a355"

        def assert_baseline_bytes(candidate):
            self.assertEqual(hashlib.sha256(candidate).hexdigest(), baseline_sha256)

        assert_baseline_bytes(nav)
        insertion = nav.index(b">") + 1
        with self.assertRaises(AssertionError):
            assert_baseline_bytes(nav[:insertion] + b" " + nav[insertion:])

    def test_ac6_ac7_semantic_surface_accessibility_and_no_content_injection(self):
        html = (ROOT / "mydictionary/templates/miniapp.html").read_text(encoding="utf-8")
        css = (ROOT / "mydictionary/static/miniapp.css").read_text(encoding="utf-8")
        words = html[html.index('<section id="panel-words"'):html.index('<section id="panel-credits"')]
        self.assertIn('id="swipe-trainer"', words)
        for mode in ("mix", "forgotten", "new"):
            tag = re.search(rf'<button\b[^>]*data-swipe-mode="{mode}"[^>]*>', words)
            self.assertIsNotNone(tag, mode)
            self.assertIn('type="button"', tag.group(0))
            self.assertIn("aria-pressed", tag.group(0))
            self.assertNotIn('role="tab"', tag.group(0))
        for element_id in ("swipe-reveal", "swipe-again", "swipe-know", "swipe-undo", "swipe-retry"):
            self.assertRegex(words, rf'<button\b[^>]*id="{element_id}"[^>]*>')
        self.assertRegex(words, r'<[^>]*id="swipe-status"[^>]*aria-live="polite"')
        self.assertRegex(words, r'<[^>]*id="swipe-card"[^>]*tabindex="0"')
        self.assertIn("miniapp-swipe.js", html)
        js_path = ROOT / "mydictionary/static/miniapp-swipe.js"
        self.assertTrue(js_path.is_file(), "swipe JS must provide real request-driven interactions")
        js = js_path.read_text(encoding="utf-8")
        self.assertNotRegex(js, r"\.(?:innerHTML|outerHTML)\s*=")
        self.assertNotIn("insertAdjacentHTML", js)
        self.assertNotIn("localStorage", js)
        self.assertIn("textContent", js)
        self.assertRegex(css, r"\.swipe[^{}]*:focus-visible")
        self.assertIn("prefers-reduced-motion", css)
        self.assertRegex(css, r"\.swipe[^{}]*\{[^}]*min-width:\s*0")
        self.assertRegex(css, r"\.swipe[^{}]*\{[^}]*overflow-wrap:\s*anywhere")
        app_js = (ROOT / "mydictionary/static/miniapp.js").read_text(encoding="utf-8")
        self.assertRegex(app_js, r"LexiSwipe\.configure\(data\)")

    def test_ac6_ac7_real_card_flip_grade_retry_undo_speech_locale_and_failure_harness(self):
        run = subprocess.run([NODE, str(ROOT / "tests/browser/miniapp-swipe.cjs")], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()
