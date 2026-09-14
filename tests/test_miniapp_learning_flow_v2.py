"""Locked learning-flow v2 contract, exercised through authenticated HTTP."""
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import select, text

import test_miniapp_swipe_v1 as fixture
from mydictionary.storage import AnalyticsEvent, User, UserProgress


class MiniAppLearningFlowV2Test(unittest.TestCase):
    # Reuse the established signed-request/database fixture without collecting
    # the v1 tests a second time through TestCase inheritance.
    setUp = fixture.MiniAppSwipeV1ApiTest.setUp
    tearDown = fixture.MiniAppSwipeV1ApiTest.tearDown
    make_app = fixture.MiniAppSwipeV1ApiTest.make_app
    post = fixture.MiniAppSwipeV1ApiTest.post
    deck = fixture.MiniAppSwipeV1ApiTest.deck
    rate = fixture.MiniAppSwipeV1ApiTest.rate
    seed = fixture.MiniAppSwipeV1ApiTest.seed
    only_new = fixture.MiniAppSwipeV1ApiTest.only_new
    profile = fixture.MiniAppSwipeV1ApiTest.profile
    word_state = fixture.MiniAppSwipeV1ApiTest.word_state
    finish = fixture.MiniAppSwipeV1ApiTest.finish

    def events(self):
        with self.store.Session() as session:
            return [(event.event_name, json.loads(event.properties_json)) for event in
                    session.scalars(select(AnalyticsEvent).where(
                        AnalyticsEvent.telegram_user_id == fixture.USER_ID)).all()]

    def status(self):
        response = self.post("status", {})
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def resume(self, deck):
        response = self.post("resume", {"session_id": deck["session_id"]})
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def completed_one(self):
        self.only_new(1)
        deck = self.deck()
        operation_id = str(uuid4())
        self.assertEqual(self.rate(deck, True, operation_id=operation_id).status_code, 200)
        response = self.post("complete", {"session_id": deck["session_id"]})
        self.assertEqual(response.status_code, 200)
        return deck, operation_id

    def test_ac3_status_counts_are_read_only_and_review_does_not_fall_back(self):
        self.only_new(2)
        before = self.profile(), self.events()
        status = self.status()
        self.assertEqual(status["counts"], {"new": 2, "forgotten": 0, "total": 2})
        self.assertIsNone(status["resume"])
        self.assertEqual(self.status(), status)
        self.assertEqual((self.profile(), self.events()), before)
        with self.store.engine.connect() as connection:
            self.assertEqual(connection.execute(text("SELECT COUNT(*) FROM miniapp_swipe_sessions")).scalar_one(), 0)
        review = self.deck("forgotten")
        self.assertEqual(review["cards"], [])
        self.assertIsNone(review["session_id"])

    def test_ac3_ac4_resume_retains_original_deck_queue_counts_and_latest_session(self):
        self.only_new(3)
        old = self.deck("new")
        deck = self.deck("mix")
        self.assertNotEqual(old["session_id"], deck["session_id"])
        operation_id = str(uuid4())
        rating = self.rate(deck, False, operation_id=operation_id)
        self.assertEqual(rating.status_code, 200)
        rated = rating.get_json()
        before = self.profile(), [self.word_state(i) for i in range(3)]
        status = self.status()
        self.assertEqual(status["resume"]["session_id"], deck["session_id"])
        resumed = self.resume(deck)
        for field in ("session_id", "pack_id", "language", "mode", "cards"):
            self.assertEqual(resumed[field], deck[field])
        for field in ("queue", "reviewed", "known", "again", "undo_operation_id"):
            self.assertEqual(resumed[field], rated[field])
        self.assertEqual((self.profile(), [self.word_state(i) for i in range(3)]), before)

    def test_ac3_pending_empty_queue_can_resume_and_complete_once(self):
        self.only_new(1)
        deck = self.deck()
        final = self.finish(deck)
        before = self.profile()
        self.assertEqual(self.status()["resume"]["session_id"], deck["session_id"])
        resumed = self.resume(deck)
        self.assertEqual(resumed["queue"], [])
        self.assertEqual(resumed["undo_operation_id"], final["undo_operation_id"])
        self.assertEqual(self.profile(), before)
        body = {"session_id": deck["session_id"]}
        self.assertEqual(self.post("complete", body).status_code, 200)
        completed = self.profile()
        self.assertEqual(self.post("complete", body).status_code, 200)
        self.assertEqual(self.profile(), completed)
        self.assertIsNone(self.status()["resume"])

    def test_ac4_err2_pack_switch_hides_resume_until_switching_back(self):
        self.only_new(2)
        deck = self.deck()
        french = fixture.bot.CATALOG.require("fr-basics-100")
        self.store.activate_pack(fixture.USER_ID, pack_id=french.pack_id, language="fr", source="test")
        before = self.profile()
        self.assertIsNone(self.status()["resume"])
        self.assertEqual(self.post("resume", {"session_id": deck["session_id"]}).status_code, 409)
        self.assertEqual(self.profile(), before)
        self.store.activate_pack(fixture.USER_ID, pack_id=self.pack.pack_id, language="en", source="test")
        self.assertEqual(self.status()["resume"]["session_id"], deck["session_id"])
        self.assertEqual(self.resume(deck)["cards"], deck["cards"])

    def test_ac3_resume_foreign_expired_and_changed_content_fail_closed(self):
        self.only_new(2)
        deck = self.deck()
        body = {"session_id": deck["session_id"]}
        before = self.profile()
        foreign = self.post("resume", body, user_id=fixture.OTHER_ID)
        self.assertEqual(foreign.status_code, 404)
        self.assertNotIn(deck["session_id"], foreign.get_data(as_text=True))
        catalog_type = type(fixture.bot.CATALOG)
        original_words = catalog_type.words

        def reordered(catalog, pack):
            words = original_words(catalog, pack)
            if pack.pack_id == self.pack.pack_id:
                words[0], words[1] = words[1], words[0]
            return words

        with patch.object(catalog_type, "words", reordered):
            self.assertEqual(self.post("resume", body).status_code, 409)
            self.assertIsNone(self.status()["resume"])
        with self.store.engine.begin() as connection:
            connection.execute(text("UPDATE miniapp_swipe_sessions SET created_at = :old"),
                               {"old": self.now - timedelta(days=8)})
        self.assertEqual(self.post("resume", body).status_code, 409)
        self.assertIsNone(self.status()["resume"])
        self.assertEqual(self.profile(), before)

    def test_ac5_completed_last_answer_undo_replay_and_recomplete_preserve_awards(self):
        deck, operation_id = self.completed_one()
        completed = self.profile()
        body = {"session_id": deck["session_id"], "operation_id": operation_id}
        undo = self.post("undo", body)
        self.assertEqual(undo.status_code, 200, undo.get_json())
        self.assertEqual(undo.get_json()["queue"], [0])
        self.assertIsNone(self.word_state(0))
        undone = self.profile()
        self.assertEqual((undone["sessions"], undone["xp"], undone["total_correct"]), (0, 15, 0))
        self.assertEqual(self.post("undo", body).get_json(), undo.get_json())
        self.assertEqual(self.profile(), undone)
        names = [name for name, _ in self.events()]
        self.assertEqual(names.count("block_completed"), 0)
        self.assertEqual(names.count("swipe_completion_undone"), 1)
        self.assertEqual(self.post("complete", {"session_id": deck["session_id"]}).status_code, 409)
        self.assertEqual(self.rate(undo.get_json(), True).status_code, 200)
        for _ in range(2):
            self.assertEqual(self.post("complete", {"session_id": deck["session_id"]}).status_code, 200)
        self.assertEqual(self.profile(), completed)
        names = [name for name, _ in self.events()]
        self.assertEqual(names.count("block_completed"), 1)
        self.assertEqual(names.count("swipe_completion_undone"), 1)

    def test_ac5_newer_session_blocks_completed_undo_without_mutation(self):
        deck, operation_id = self.completed_one()
        # Make a distinct new word available; an empty deck is not a session.
        self.seed(1, correct=0)
        newer = self.deck()
        self.assertIsNotNone(newer["session_id"])
        before = self.profile(), self.word_state(0), self.events()
        response = self.post("undo", {"session_id": deck["session_id"], "operation_id": operation_id})
        self.assertEqual(response.status_code, 409)
        self.assertEqual((self.profile(), self.word_state(0), self.events()), before)

    def test_ac5_completed_undo_expires_after_ten_minutes(self):
        deck, operation_id = self.completed_one()
        before = self.profile(), self.word_state(0), self.events()
        with patch("mydictionary.storage.utcnow", return_value=datetime.now(timezone.utc) + timedelta(minutes=11)):
            response = self.post("undo", {"session_id": deck["session_id"], "operation_id": operation_id})
        self.assertEqual(response.status_code, 409)
        self.assertEqual((self.profile(), self.word_state(0), self.events()), before)

    def test_ac5_err2_completed_undo_preserves_unrelated_later_profile_work(self):
        deck, operation_id = self.completed_one()
        with self.store.Session.begin() as session:
            profile = session.get(UserProgress, fixture.USER_ID)
            profile.xp += 7
            profile.today_xp += 7
            profile.total_wrong += 1
        response = self.post("undo", {"session_id": deck["session_id"], "operation_id": operation_id})
        self.assertEqual(response.status_code, 200, response.get_json())
        profile = self.profile()
        self.assertEqual((profile["xp"], profile["today_xp"], profile["total_wrong"], profile["sessions"]), (22, 22, 1, 0))

    def test_ac9_started_resumed_events_are_versioned_private_and_replay_safe(self):
        self.only_new(2)
        deck = self.deck()
        for _ in range(2):
            self.resume(deck)
        events = self.events()
        self.assertEqual(sum(name == "swipe_started" for name, _ in events), 1)
        self.assertEqual(sum(name == "swipe_resumed" for name, _ in events), 1)
        forbidden = {"target", "meaning", "term", "answer", "prompt", "name", "display_name", "initData", "init_data", "telegram_user_id", "user_id"}
        for name, properties in events:
            if name not in ("swipe_started", "swipe_resumed"):
                continue
            self.assertTrue(any(key in properties for key in ("version", "schema_version", "event_version")), properties)
            self.assertFalse(forbidden.intersection(properties), properties)
            serialized = json.dumps(properties, ensure_ascii=False)
            for card in deck["cards"]:
                self.assertNotIn('"' + card["target"] + '"', serialized)
                self.assertNotIn(card["meaning"], serialized)
            self.assertNotIn("signed", serialized)
        before = self.events()
        self.status()
        self.assertEqual(self.events(), before)

    def test_ac9_event_language_preserves_target_language_not_storage_namespace(self):
        self.only_new(1)
        deck = self.deck()
        self.resume(deck)
        rated = self.rate(deck, True)
        self.assertEqual(rated.status_code, 200, rated.get_json())
        completed = self.post("complete", {"session_id": deck["session_id"]})
        self.assertEqual(completed.status_code, 200, completed.get_json())
        events = [(name, props) for name, props in self.events()
                  if name in {"swipe_started", "swipe_resumed", "block_completed"}]
        self.assertEqual({name for name, _ in events}, {"swipe_started", "swipe_resumed", "block_completed"})
        for name, properties in events:
            with self.subTest(event=name):
                self.assertEqual(properties["language"], "en")
                self.assertEqual(properties["pack_id"], "en-basics-100")

    def test_ac7_editorial_russian_notes_follow_native_language_without_hiding_german_forms(self):
        self.pack = fixture.bot.CATALOG.require("de-basics-100")
        self.words = fixture.bot.CATALOG.words(self.pack)
        # Additive synthetic editorial fixtures keep the UI/backend release
        # independent of the separately reviewed German editorial publication.
        additions = {
            "hand": {"example_target": "Das Kind hält meine Hand.",
                     "example_meaning": "Ребёнок держит меня за руку.",
                     "part_of_speech": "noun",
                     "grammar": {"article": "die", "plural": "Hände", "note": "Кисть руки."}},
            "listen": {"example_target": "Ich höre dir zu.",
                       "example_meaning": "Я тебя слушаю.",
                       "part_of_speech": "verb",
                       "grammar": {"present": "er hört zu", "preterite": "er hörte zu",
                                   "perfect": "er hat zugehört", "note": "Управление: Dativ."}},
        }
        self.words = [dict(word, **additions.get(word.get("entry_id"), {})) for word in self.words]
        catalog_type = type(fixture.bot.CATALOG)
        original_words = catalog_type.words

        def with_editorial_fixture(catalog, pack):
            return self.words if pack.pack_id == self.pack.pack_id else original_words(catalog, pack)

        editorial_patch = patch.object(catalog_type, "words", with_editorial_fixture)
        editorial_patch.start()
        self.addCleanup(editorial_patch.stop)
        selected = {index for index, word in enumerate(self.words)
                    if word.get("entry_id") in {"hand", "listen"}}
        self.assertEqual(len(selected), 2)
        self.store.activate_pack(fixture.USER_ID, pack_id=self.pack.pack_id, language="de", source="test")
        for index in range(len(self.words)):
            if index not in selected:
                self.seed(index, correct=3)
        for native in ("ru", "fr"):
            with self.subTest(native=native):
                with self.store.Session.begin() as session:
                    session.get(User, fixture.USER_ID).native_language = native
                deck = self.deck()
                self.assertEqual(len(deck["cards"]), 2)
                for card in deck["cards"]:
                    source = self.words[card["word_index"]]
                    self.assertEqual(card["example"]["target"], source["example_target"])
                    if native == "ru":
                        self.assertEqual(card["grammar"]["note"], source["grammar"]["note"])
                        self.assertEqual(card["example"]["meaning"], source["example_meaning"])
                    else:
                        self.assertNotIn("note", card["grammar"])
                        self.assertNotIn("notes", card["grammar"])
                        self.assertNotIn("meaning", card["example"])
                    for key, value in source["grammar"].items():
                        if key not in {"note", "notes"}:
                            self.assertEqual(card["grammar"][key], value)
                self.assertEqual(self.resume(deck)["cards"], deck["cards"])

    def test_err1_new_endpoints_require_auth_access_strict_bodies_and_limits(self):
        endpoints = {"status": {}, "resume": {"session_id": str(uuid4())}}
        for action, body in endpoints.items():
            with self.subTest(action=action):
                self.assertEqual(self.client.post(f"/miniapp/api/swipe/{action}", json=body).status_code, 401)
                with patch.object(fixture.miniapp, "verify_init_data", side_effect=fixture.miniapp.MiniAppAuthenticationError("expired")):
                    self.assertEqual(self.client.post(f"/miniapp/api/swipe/{action}", json=body, headers={"X-Telegram-Init-Data": "expired"}).status_code, 401)
                with patch("mydictionary.admin.PersistentRateLimiter.consume", return_value=SimpleNamespace(allowed=False, retry_after_seconds=9)):
                    response = self.post(action, body)
                    self.assertEqual(response.status_code, 429)
                    self.assertGreaterEqual(int(response.headers["Retry-After"]), 1)
        for action, body in (("status", {"mode": "new"}), ("status", []), ("resume", {}), ("resume", {"session_id": "bad"}), ("resume", {"session_id": str(uuid4()), "extra": True})):
            with self.subTest(action=action, body=body):
                self.assertEqual(self.post(action, body).status_code, 400)
        for access, privacy in (("pending", "active"), ("active", "erased")):
            with self.store.Session.begin() as session:
                user = session.get(User, fixture.USER_ID)
                user.access_status, user.privacy_status = access, privacy
            for action, body in endpoints.items():
                self.assertEqual(self.post(action, body).status_code, 403)


if __name__ == "__main__":
    unittest.main()
