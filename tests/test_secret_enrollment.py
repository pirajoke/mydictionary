import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from mydictionary.secret_enrollment import (
    SecretEnrollmentError,
    SecretEnrollmentSettings,
    load_provider_api_key,
)


class SecretEnrollmentTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(
            prefix="mydictionary-secret-enrollment-"
        )
        self.root = Path(self.temporary.name)
        os.chmod(self.root, 0o700)
        self.now = datetime.now(timezone.utc)

    def tearDown(self):
        self.temporary.cleanup()

    def settings(self, destination: Path) -> SecretEnrollmentSettings:
        return SecretEnrollmentSettings.from_mapping(
            {
                "AI_KEY_ENROLLMENT_ENABLED": "true",
                "AI_KEY_ENROLLMENT_PATH": str(destination),
                "AI_KEY_ENROLLMENT_EXPIRES_AT": (
                    self.now + timedelta(minutes=30)
                ).isoformat(),
            },
            now=self.now,
        )

    def groq_settings(self, destination: Path) -> SecretEnrollmentSettings:
        return SecretEnrollmentSettings.from_mapping(
            {
                "GROQ_KEY_ENROLLMENT_ENABLED": "true",
                "GROQ_KEY_ENROLLMENT_PATH": str(destination),
                "GROQ_KEY_ENROLLMENT_EXPIRES_AT": (
                    self.now + timedelta(minutes=30)
                ).isoformat(),
            },
            now=self.now,
            provider="groq",
        )

    def test_configuration_requires_absolute_bounded_window(self):
        with self.assertRaisesRegex(SecretEnrollmentError, "must be absolute"):
            SecretEnrollmentSettings.from_mapping(
                {
                    "AI_KEY_ENROLLMENT_ENABLED": "true",
                    "AI_KEY_ENROLLMENT_PATH": "relative.key",
                    "AI_KEY_ENROLLMENT_EXPIRES_AT": (
                        self.now + timedelta(minutes=30)
                    ).isoformat(),
                },
                now=self.now,
            )
        with self.assertRaisesRegex(SecretEnrollmentError, "cannot exceed"):
            SecretEnrollmentSettings.from_mapping(
                {
                    "AI_KEY_ENROLLMENT_ENABLED": "true",
                    "AI_KEY_ENROLLMENT_PATH": str(self.root / "key"),
                    "AI_KEY_ENROLLMENT_EXPIRES_AT": (
                        self.now + timedelta(hours=2)
                    ).isoformat(),
                },
                now=self.now,
            )

    def test_symlink_target_is_consumed_without_touching_destination(self):
        victim = self.root / "victim"
        victim.write_text("unchanged", encoding="utf-8")
        link = self.root / "openai.key"
        link.symlink_to(victim)
        settings = self.settings(link)

        self.assertEqual(settings.status(now=self.now), "consumed")
        with self.assertRaisesRegex(SecretEnrollmentError, "consumed"):
            settings.enroll("sk-proj-" + "A" * 48, now=self.now)
        self.assertEqual(victim.read_text(encoding="utf-8"), "unchanged")

    def test_group_writable_directory_and_whitespace_fail_closed(self):
        unsafe = self.root / "unsafe"
        unsafe.mkdir()
        os.chmod(unsafe, 0o770)
        unsafe_settings = self.settings(unsafe / "openai.key")
        with self.assertRaisesRegex(SecretEnrollmentError, "must not be"):
            unsafe_settings.enroll("sk-proj-" + "A" * 48, now=self.now)
        self.assertFalse((unsafe / "openai.key").exists())

        safe_settings = self.settings(self.root / "openai.key")
        with self.assertRaisesRegex(SecretEnrollmentError, "format"):
            safe_settings.enroll(" sk-proj-" + "B" * 48, now=self.now)
        self.assertFalse((self.root / "openai.key").exists())

    def test_concurrent_submissions_create_exactly_one_secret(self):
        destination = self.root / "openai.key"
        settings = self.settings(destination)
        candidates = ("sk-proj-" + "A" * 48, "sk-proj-" + "B" * 48)

        def submit(value: str) -> str:
            try:
                settings.enroll(value, now=self.now)
            except SecretEnrollmentError:
                return "rejected"
            return "accepted"

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(submit, candidates))

        self.assertEqual(outcomes.count("accepted"), 1)
        self.assertEqual(outcomes.count("rejected"), 1)
        self.assertIn(destination.read_text(encoding="ascii"), candidates)
        self.assertEqual(destination.stat().st_mode & 0o777, 0o600)

    def test_groq_enrollment_is_independent_and_provider_specific(self):
        destination = self.root / "groq-voice.key"
        settings = self.groq_settings(destination)
        secret = "gsk_" + "G" * 48

        with self.assertRaisesRegex(SecretEnrollmentError, "Groq"):
            settings.enroll("sk-proj-" + "A" * 48, now=self.now)
        fingerprint = settings.enroll(secret, now=self.now)

        self.assertEqual(len(fingerprint), 12)
        self.assertEqual(destination.read_text(encoding="ascii"), secret)
        self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.settings(self.root / "openai.key").status(), "ready")

    def test_provider_key_file_must_be_private_regular_and_unambiguous(self):
        destination = self.root / "groq-voice.key"
        secret = "gsk_" + "K" * 48
        destination.write_text(secret, encoding="ascii")
        os.chmod(destination, 0o600)

        self.assertEqual(
            load_provider_api_key(
                {"GROQ_API_KEY_FILE": str(destination)},
                provider="groq",
            ),
            secret,
        )
        with self.assertRaisesRegex(SecretEnrollmentError, "mutually exclusive"):
            load_provider_api_key(
                {
                    "GROQ_API_KEY": secret,
                    "GROQ_API_KEY_FILE": str(destination),
                },
                provider="groq",
            )

        os.chmod(destination, 0o640)
        with self.assertRaisesRegex(SecretEnrollmentError, "permissions"):
            load_provider_api_key(
                {"GROQ_API_KEY_FILE": str(destination)},
                provider="groq",
            )

        victim = self.root / "victim"
        victim.write_text(secret, encoding="ascii")
        os.chmod(victim, 0o600)
        link = self.root / "groq-link.key"
        link.symlink_to(victim)
        with self.assertRaisesRegex(SecretEnrollmentError, "regular"):
            load_provider_api_key(
                {"GROQ_API_KEY_FILE": str(link)},
                provider="groq",
            )


if __name__ == "__main__":
    unittest.main()
