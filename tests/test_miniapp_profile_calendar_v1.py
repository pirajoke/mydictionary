from datetime import date, datetime, timezone
import hashlib
import hmac
import importlib
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlencode
import unittest

from sqlalchemy import func, select


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN_ABCDEFGHIJKLMNOP")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot
from mydictionary.storage import AnalyticsEvent, DatabaseStore, User, UserProgress


TOKEN = "123456:TESTTOKEN_ABCDEFGHIJKLMNOP"
INTERFACE_LOCALES = {"en", "fr", "de", "ja", "ar", "zh", "ru", "es"}
PROFILE_COPY_KEYS = {
    "streak_days",
    "best_streak_short",
    "calendar_activity",
    "calendar_today",
    "calendar_active_day",
    "previous_month",
    "next_month",
    "share_profile",
}


def miniapp_module():
    return importlib.import_module("mydictionary.miniapp")


def signed_init_data(*, photo_url=None, auth_date=1_800_000_000):
    user = {
        "id": 7001,
        "first_name": "Mila",
        "language_code": "fr",
    }
    if photo_url is not None:
        user["photo_url"] = photo_url
    fields = {
        "auth_date": str(auth_date),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps(user, ensure_ascii=False, separators=(",", ":")),
    }
    data_check = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(
        secret, data_check.encode(), hashlib.sha256
    ).hexdigest()
    return urlencode(fields)


class MiniAppProfileIdentityContractTest(unittest.TestCase):
    def test_ac1_signed_telegram_photo_is_allowlisted_and_unsafe_urls_fall_back(self):
        miniapp = miniapp_module()
        safe = "https://t.me/i/userpic/320/signed-avatar.jpg"
        verified = miniapp.verify_init_data(
            signed_init_data(photo_url=safe),
            bot_token=TOKEN,
            now=1_800_000_100,
        )
        self.assertEqual(verified["photo_url"], safe)

        unsafe_values = (
            "http://t.me/i/userpic/320/avatar.jpg",
            "https://evil.example/avatar.jpg",
            "https://user:password@t.me/avatar.jpg",
            "https://t.me/" + ("x" * 600),
        )
        for value in unsafe_values:
            with self.subTest(value=value[:40]):
                identity = miniapp.verify_init_data(
                    signed_init_data(photo_url=value),
                    bot_token=TOKEN,
                    now=1_800_000_100,
                )
                self.assertNotIn("photo_url", identity)


class MiniAppActivityCalendarContractTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="miniapp-calendar-")
        self.addCleanup(self.temporary.cleanup)
        self.store = DatabaseStore(
            f"sqlite:///{Path(self.temporary.name) / 'calendar.sqlite3'}"
        )
        self.addCleanup(self.store.close)
        self.user_id = 7301
        fixed = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
        with self.store.Session.begin() as session:
            session.add(
                User(
                    telegram_user_id=self.user_id,
                    first_name="Mila",
                    language_code="fr",
                    role="learner",
                    access_status="active",
                    privacy_status="active",
                    updated_at=fixed,
                    created_at=fixed,
                )
            )
            session.add(
                UserProgress(
                    telegram_user_id=self.user_id,
                    streak=4,
                    streak_best=11,
                    last_activity_date="2026-08-29",
                    active_lang="fr",
                    active_pack_id="fr-basics-100",
                )
            )
            for event_id, event_name, occurred_at in (
                ("activity-1", "block_started", datetime(2026, 8, 2, 10, tzinfo=timezone.utc)),
                ("activity-2", "block_completed", datetime(2026, 8, 3, 11, tzinfo=timezone.utc)),
                ("activity-3", "word_audio_played", datetime(2026, 8, 3, 12, tzinfo=timezone.utc)),
                ("activity-4", "start_received", datetime(2026, 7, 15, 9, tzinfo=timezone.utc)),
                ("too-old", "block_completed", datetime(2025, 7, 1, 9, tzinfo=timezone.utc)),
            ):
                session.add(
                    AnalyticsEvent(
                        event_id=event_id,
                        telegram_user_id=self.user_id,
                        event_name=event_name,
                        occurred_at=occurred_at,
                    )
                )

    def _snapshot(self):
        with self.store.Session() as session:
            learner = session.get(User, self.user_id)
            return {
                "updated_at": learner.updated_at,
                "users": session.scalar(select(func.count()).select_from(User)),
                "progress": session.scalar(
                    select(func.count()).select_from(UserProgress)
                ),
                "events": session.scalar(
                    select(func.count()).select_from(AnalyticsEvent)
                ),
            }

    def test_ac2_ec1_real_activity_dates_are_unique_bounded_and_read_only(self):
        miniapp = miniapp_module()
        before = self._snapshot()
        payload = miniapp.build_bootstrap(
            self.store,
            user_id=self.user_id,
            display_name="Mila",
            avatar_url="https://t.me/i/userpic/320/signed-avatar.jpg",
            locale="fr",
            catalog=bot.CATALOG,
            products=[],
            checkout_enabled=False,
            ai_enabled=True,
            voice_enabled=True,
            observed_date=date(2026, 8, 29),
        )
        after = self._snapshot()

        calendar = payload["progress"]["calendar"]
        self.assertEqual(after, before)
        self.assertEqual(calendar["today"], "2026-08-29")
        self.assertEqual(
            calendar["activity_days"],
            ["2026-07-15", "2026-08-02", "2026-08-03", "2026-08-29"],
        )
        self.assertEqual(len(calendar["activity_days"]), len(set(calendar["activity_days"])))
        self.assertLessEqual(len(calendar["activity_days"]), 370)
        self.assertTrue(all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) for day in calendar["activity_days"]))
        self.assertEqual(payload["profile"]["avatar_url"], "https://t.me/i/userpic/320/signed-avatar.jpg")
        serialized = json.dumps(calendar, sort_keys=True)
        for forbidden in ("event_name", "session_id", "telegram", "user_id", "prompt", "message"):
            self.assertNotIn(forbidden, serialized.casefold())

    def test_ec2_err1_empty_history_and_unsafe_avatar_are_honest(self):
        miniapp = miniapp_module()
        with self.store.Session.begin() as session:
            session.query(AnalyticsEvent).delete()
            progress = session.get(UserProgress, self.user_id)
            progress.last_activity_date = None
            progress.streak = 0
        payload = miniapp.build_bootstrap(
            self.store,
            user_id=self.user_id,
            display_name="Mila",
            avatar_url="https://evil.example/avatar.png",
            locale="fr",
            catalog=bot.CATALOG,
            products=[],
            checkout_enabled=False,
            ai_enabled=True,
            voice_enabled=True,
            observed_date=date(2026, 8, 29),
        )
        self.assertEqual(payload["progress"]["calendar"]["activity_days"], [])
        self.assertEqual(payload["progress"]["streak"], 0)
        self.assertNotIn("avatar_url", payload["profile"])


class MiniAppProfileFrontendContractTest(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.html = (root / "mydictionary/templates/miniapp.html").read_text(encoding="utf-8")
        self.css = (root / "mydictionary/static/miniapp.css").read_text(encoding="utf-8")
        self.js = (root / "mydictionary/static/miniapp.js").read_text(encoding="utf-8")

    def test_ac1_ac3_profile_has_avatar_balance_primary_actions_and_ai_tab_entry(self):
        violations = []
        for token in (
            'id="profile-photo"',
            'id="profile-avatar-fallback"',
            'id="profile-credit-balance"',
            'data-action="continue"',
            'data-action="share"',
            'data-action="ai"',
        ):
            if token not in self.html:
                violations.append(token)
        if self.html.index('data-action="ai"') < self.html.index('id="panel-credits"'):
            violations.append("AI Tutor belongs in the credits tab, not the focused profile actions")
        for behavior in ("profile.avatar_url", "profile.display_name", "profile.credits"):
            if behavior not in self.js:
                violations.append(f"unbound:{behavior}")
        self.assertEqual(violations, [])

    def test_ac2_err2_calendar_renders_42_cells_with_localized_bounded_navigation(self):
        violations = []
        for token in (
            'id="streak-count"',
            'id="best-streak"',
            'id="calendar-month"',
            'id="calendar-grid"',
            'id="calendar-previous"',
            'id="calendar-next"',
            "function renderCalendar",
            "Intl.DateTimeFormat",
            "activity_days",
            "for (let index = 0; index < 42; index += 1)",
            "calendar.min_month",
            "calendar.max_month",
        ):
            if token not in f"{self.html}\n{self.js}":
                violations.append(token)
        if "aria-label" not in self.js or "calendar_today" not in self.js:
            violations.append("calendar-accessible-labels")
        self.assertEqual(violations, [])

    def test_ac4_ac6_bottom_navigation_uses_five_distinct_icon_discs_responsively(self):
        self.assertEqual(self.html.count('class="nav-icon '), 5)
        for tab in ("profile", "words", "credits", "languages", "settings"):
            with self.subTest(tab=tab):
                self.assertIn(f"nav-icon-{tab}", self.html)
        for contract in (
            ".nav-icon",
            "min-height: 44px",
            "env(safe-area-inset-bottom)",
            "@media (max-width: 359px)",
            "prefers-reduced-motion: reduce",
        ):
            with self.subTest(contract=contract):
                self.assertIn(contract, self.css)
        self.assertIn('"ArrowLeft"', self.js)
        self.assertIn('"ArrowRight"', self.js)
        self.assertIn("tabIndex", self.js)

    def test_ac5_new_profile_copy_is_complete_and_bound_in_all_locales(self):
        miniapp = miniapp_module()
        missing = {
            locale: sorted(PROFILE_COPY_KEYS - set(miniapp.MINIAPP_COPY[locale]))
            for locale in INTERFACE_LOCALES
            if PROFILE_COPY_KEYS - set(miniapp.MINIAPP_COPY[locale])
        }
        self.assertEqual(missing, {})
        combined = f"{self.html}\n{self.js}"
        unbound = [
            key
            for key in PROFILE_COPY_KEYS
            if not any(
                token in combined
                for token in (
                    f'data-i18n="{key}"',
                    f'data-i18n-aria-label="{key}"',
                    f"copy.{key}",
                    f'copy["{key}"]',
                )
            )
        ]
        self.assertEqual(unbound, [])
