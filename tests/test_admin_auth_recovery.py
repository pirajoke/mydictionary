import ast
import hashlib
import hmac
import inspect as python_inspect
import json
import os
import tempfile
import textwrap
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import MagicMock, patch

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text
from werkzeug.security import check_password_hash

from mydictionary.admin import create_app
from mydictionary.admin_auth import AdminAuthSettings
from mydictionary.admin_store import AdminStore
from mydictionary.storage import AdminAuditLog, DatabaseStore
from ops import mydictionary_admin as admin_launcher


OWNER_EMAIL = "owner@example.test"
PUBLIC_URL = "https://admin.example.test"
GOOGLE_CLIENT_ID = "admin-client.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET = "google-client-secret-value"
SMTP_PASSWORD = "smtp-password-value"


class RecordingMailer:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.messages = []

    def send_password_reset(self, *, recipient, reset_url):
        self.messages.append({"recipient": recipient, "reset_url": reset_url})
        if self.fail:
            raise RuntimeError("mail provider unavailable")


class ActivationObservingMailer:
    def __init__(self, store, *, session_secret):
        self.store = store
        self.session_secret = session_secret
        self.messages = []
        self.activation_during_delivery = []

    def send_password_reset(self, *, recipient, reset_url):
        self.messages.append({"recipient": recipient, "reset_url": reset_url})
        token = urlparse(reset_url).path.rsplit("/", 1)[-1]
        digest = hmac.new(
            self.session_secret.encode("utf-8"),
            token.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        try:
            with self.store.engine.connect() as connection:
                activated_at = connection.execute(
                    text(
                        "SELECT activated_at FROM admin_password_resets "
                        "WHERE token_digest = :digest"
                    ),
                    {"digest": digest},
                ).scalar_one()
        except Exception:
            activated_at = "missing-activation-contract"
        self.activation_during_delivery.append(activated_at)


class StubResponse:
    def __init__(self, payload=None, *, status_code=200, json_error=None):
        self.payload = payload or {}
        self.status_code = status_code
        self.json_error = json_error

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"provider status {self.status_code}")

    def json(self):
        if self.json_error is not None:
            raise self.json_error
        return dict(self.payload)


class StubGoogleHTTPClient:
    def __init__(self):
        self.post_calls = []
        self.get_calls = []
        self.post_error = None
        self.get_error = None
        self.token_payload = {
            "id_token": "private-id-token",
            "access_token": "private-access-token",
            "refresh_token": "private-refresh-token",
        }
        self.claims = {
            "aud": GOOGLE_CLIENT_ID,
            "iss": "https://accounts.google.com",
            "exp": str(int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp())),
            "nonce": "replace-after-start",
            "email_verified": "true",
            "email": OWNER_EMAIL,
        }
        self.token_json_error = None
        self.claim_json_error = None
        self.token_status_code = 200
        self.claim_status_code = 200

    def post(self, url, *, data, timeout):
        self.post_calls.append({"url": url, "data": dict(data), "timeout": timeout})
        if self.post_error is not None:
            raise self.post_error
        return StubResponse(
            self.token_payload,
            status_code=self.token_status_code,
            json_error=self.token_json_error,
        )

    def get(self, url, *, params, timeout):
        self.get_calls.append({"url": url, "params": dict(params), "timeout": timeout})
        if self.get_error is not None:
            raise self.get_error
        return StubResponse(
            self.claims,
            status_code=self.claim_status_code,
            json_error=self.claim_json_error,
        )


class DefaultGoogleTransportProbe(StubGoogleHTTPClient):
    """Accept both legacy GET and hardened POST tokeninfo calls for observation."""

    def post(self, url, *, data, timeout):
        self.post_calls.append({"url": url, "data": dict(data), "timeout": timeout})
        if self.post_error is not None:
            raise self.post_error
        if url == "https://oauth2.googleapis.com/tokeninfo":
            return StubResponse(
                self.claims,
                status_code=self.claim_status_code,
                json_error=self.claim_json_error,
            )
        return StubResponse(
            self.token_payload,
            status_code=self.token_status_code,
            json_error=self.token_json_error,
        )


class AdminAuthFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mydictionary-admin-auth-")
        self.root = Path(self.temporary.name)
        self.database_path = self.root / "admin-auth.db"
        self.store = DatabaseStore(f"sqlite:///{self.database_path}")
        self.google_secret_file = self.private_file(
            "google-client-secret", GOOGLE_CLIENT_SECRET
        )
        self.smtp_password_file = self.private_file("smtp-password", SMTP_PASSWORD)

    def tearDown(self):
        self.store.close()
        self.temporary.cleanup()

    def private_file(self, name, value, *, mode=0o600):
        path = self.root / name
        path.write_text(value, encoding="utf-8")
        os.chmod(path, mode)
        return path

    def base_config(self):
        return {
            "TESTING": True,
            "SECRET_KEY": "test-admin-auth-session-secret-at-least-32",
            "ADMIN_USERNAME": "owner",
            "ADMIN_PASSWORD": "test-password-123",
            "DATA_DIR": str(self.root),
            "SESSION_COOKIE_SECURE": True,
        }

    def reset_config(self, *, mailer=None):
        return {
            "ADMIN_EMAIL": OWNER_EMAIL,
            "ADMIN_PUBLIC_URL": PUBLIC_URL,
            "ADMIN_SMTP_HOST": "smtp.example.test",
            "ADMIN_SMTP_PORT": "587",
            "ADMIN_SMTP_USERNAME": "mailer@example.test",
            "ADMIN_SMTP_PASSWORD_FILE": str(self.smtp_password_file),
            "ADMIN_SMTP_FROM": "MY DICTIONARY <mailer@example.test>",
            "ADMIN_RESET_TOKEN_TTL_SECONDS": "900",
            "ADMIN_RESET_RATE_LIMIT_ATTEMPTS": "5",
            "ADMIN_RESET_MAILER": mailer or RecordingMailer(),
        }

    def google_config(self, *, http_client=None):
        return {
            "ADMIN_EMAIL": OWNER_EMAIL,
            "ADMIN_PUBLIC_URL": PUBLIC_URL,
            "ADMIN_GOOGLE_CLIENT_ID": GOOGLE_CLIENT_ID,
            "ADMIN_GOOGLE_CLIENT_SECRET_FILE": str(self.google_secret_file),
            "ADMIN_GOOGLE_HTTP_CLIENT": http_client or StubGoogleHTTPClient(),
        }

    def make_app(self, *, reset=False, google=False, overrides=None, mailer=None, http_client=None):
        config = self.base_config()
        if reset:
            config.update(self.reset_config(mailer=mailer))
        if google:
            config.update(self.google_config(http_client=http_client))
        if overrides:
            config.update(overrides)
        return create_app(config, database_store=self.store)

    @staticmethod
    def csrf(client):
        with client.session_transaction() as browser_session:
            return browser_session["csrf_token"]

    def request_reset(
        self,
        client,
        email,
        *,
        remote_addr="127.0.0.1",
        headers=None,
    ):
        client.get("/admin/login")
        client.get("/admin/forgot-password")
        return client.post(
            "/admin/forgot-password",
            data={"csrf_token": self.csrf(client), "email": email},
            environ_base={"REMOTE_ADDR": remote_addr},
            headers=headers,
        )

    def login(self, client):
        client.get("/admin/login")
        response = client.post(
            "/admin/login",
            data={
                "csrf_token": self.csrf(client),
                "username": "owner",
                "password": "test-password-123",
            },
        )
        self.assertEqual(response.status_code, 302)

    def reset_rows(self):
        inspector = inspect(self.store.engine)
        self.assertIn("admin_password_resets", inspector.get_table_names())
        with self.store.engine.connect() as connection:
            return [
                dict(row._mapping)
                for row in connection.execute(
                    text("SELECT * FROM admin_password_resets ORDER BY created_at")
                )
            ]

    def audit_payload(self):
        with self.store.Session() as database_session:
            rows = database_session.execute(select(AdminAuditLog)).scalars().all()
        return "\n".join(
            f"{row.actor} {row.action} {row.target_type} {row.target_id} {row.details_json}"
            for row in rows
        )

    def token_from_mail(self, mailer, index=-1):
        reset_url = mailer.messages[index]["reset_url"]
        parsed = urlparse(reset_url)
        self.assertEqual(f"{parsed.scheme}://{parsed.netloc}", PUBLIC_URL)
        self.assertTrue(parsed.path.startswith("/admin/reset-password/"))
        self.assertFalse(parsed.query)
        self.assertFalse(parsed.fragment)
        return parsed.path.rsplit("/", 1)[-1]


class AdminProviderHardeningTest(AdminAuthFixture):
    def default_smtp_mailer(self):
        config = self.reset_config()
        config["ADMIN_RESET_MAILER"] = None
        settings = AdminAuthSettings.from_mapping(config)
        self.assertTrue(settings.reset_enabled)
        self.assertIsNotNone(settings.reset_mailer)
        return settings.reset_mailer

    def test_default_smtp_mailer_uses_verified_default_tls_context(self):
        smtp_manager = MagicMock()
        smtp_client = MagicMock()
        smtp_manager.__enter__.return_value = smtp_client
        tls_context = object()
        with (
            patch(
                "ssl.create_default_context", return_value=tls_context
            ) as create_context,
            patch(
                "mydictionary.admin_auth.smtplib.SMTP",
                return_value=smtp_manager,
            ) as smtp_constructor,
        ):
            self.default_smtp_mailer().send_password_reset(
                recipient=OWNER_EMAIL,
                reset_url=PUBLIC_URL + "/admin/reset-password/opaque-token",
            )

        create_context.assert_called_once_with()
        smtp_constructor.assert_called_once_with(
            "smtp.example.test", 587, timeout=10
        )
        smtp_client.starttls.assert_called_once_with(context=tls_context)
        smtp_client.login.assert_called_once_with(
            "mailer@example.test", SMTP_PASSWORD
        )
        smtp_client.send_message.assert_called_once()

    def test_default_smtp_mailer_never_authenticates_or_sends_after_tls_failure(self):
        smtp_manager = MagicMock()
        smtp_client = MagicMock()
        smtp_manager.__enter__.return_value = smtp_client
        smtp_client.starttls.side_effect = RuntimeError("TLS negotiation failed")
        with patch(
            "mydictionary.admin_auth.smtplib.SMTP",
            return_value=smtp_manager,
        ):
            with self.assertRaisesRegex(RuntimeError, "TLS negotiation failed"):
                self.default_smtp_mailer().send_password_reset(
                    recipient=OWNER_EMAIL,
                    reset_url=PUBLIC_URL + "/admin/reset-password/opaque-token",
                )

        smtp_client.login.assert_not_called()
        smtp_client.send_message.assert_not_called()


class AdminResetLockOrderContractTest(unittest.TestCase):
    @staticmethod
    def lock_sequence(method):
        source = textwrap.dedent(python_inspect.getsource(method))
        tree = ast.parse(source)
        events = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            rendered = ast.unparse(node)
            if rendered.startswith("session.get(AdminCredential"):
                locked = any(
                    keyword.arg == "with_for_update"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is True
                    for keyword in node.keywords
                )
                if locked:
                    events.append((node.lineno, "credential"))
            elif (
                rendered.startswith("session.execute(")
                and "select(AdminPasswordReset)" in rendered
                and ".with_for_update()" in rendered
            ):
                events.append((node.lineno, "reset"))
        return [label for _, label in sorted(events)]

    def test_issue_and_consume_lock_credential_then_reset_in_identical_order(self):
        for label, method in (
            ("issue", AdminStore.issue_password_reset),
            ("consume", AdminStore.consume_password_reset),
        ):
            with self.subTest(operation=label):
                self.assertEqual(
                    self.lock_sequence(method),
                    ["credential", "reset"],
                )


class AdminAuthRecoveryTest(AdminAuthFixture):

    def test_login_surface_is_feature_gated_and_password_login_still_works(self):
        disabled = self.make_app()
        disabled_client = disabled.test_client()
        login = disabled_client.get("/admin/login")
        body = login.get_data(as_text=True)
        self.assertEqual(login.status_code, 200)
        self.assertNotIn('/admin/forgot-password', body)
        self.assertNotIn('/admin/google/login', body)
        self.assertEqual(disabled_client.get("/admin/forgot-password").status_code, 404)
        self.assertEqual(disabled_client.get("/admin/google/login").status_code, 404)
        self.assertEqual(disabled.config["SESSION_COOKIE_SAMESITE"], "Lax")
        self.assertTrue(disabled.config["SESSION_COOKIE_HTTPONLY"])
        self.assertTrue(disabled.config["SESSION_COOKIE_SECURE"])
        self.login(disabled_client)
        self.assertEqual(disabled_client.get("/admin").status_code, 200)

        configured = self.make_app(reset=True, google=True)
        configured_body = configured.test_client().get("/admin/login").get_data(as_text=True)
        self.assertIn('href="/admin/forgot-password"', configured_body)
        self.assertIn('href="/admin/google/login"', configured_body)

    def test_partial_contradictory_and_out_of_range_configuration_fails_startup(self):
        cases = {
            "email only": {"ADMIN_EMAIL": OWNER_EMAIL},
            "partial smtp": {
                "ADMIN_EMAIL": OWNER_EMAIL,
                "ADMIN_PUBLIC_URL": PUBLIC_URL,
                "ADMIN_SMTP_HOST": "smtp.example.test",
            },
            "partial google": {
                "ADMIN_EMAIL": OWNER_EMAIL,
                "ADMIN_PUBLIC_URL": PUBLIC_URL,
                "ADMIN_GOOGLE_CLIENT_ID": GOOGLE_CLIENT_ID,
            },
            "insecure public url": {
                **self.reset_config(),
                "ADMIN_PUBLIC_URL": "http://admin.example.test",
            },
            "public url query": {
                **self.reset_config(),
                "ADMIN_PUBLIC_URL": PUBLIC_URL + "/?next=https://evil.test",
            },
            "ttl too short": {
                **self.reset_config(),
                "ADMIN_RESET_TOKEN_TTL_SECONDS": "299",
            },
            "ttl too long": {
                **self.reset_config(),
                "ADMIN_RESET_TOKEN_TTL_SECONDS": "3601",
            },
        }
        for label, overrides in cases.items():
            with self.subTest(label=label), self.assertRaises(RuntimeError):
                self.make_app(overrides=overrides)

    def test_secret_files_must_be_absolute_private_regular_owned_nonempty_and_bounded(self):
        unsafe_paths = {}
        relative = Path("relative-secret")
        unsafe_paths["relative"] = relative
        world_readable = self.private_file("world-readable", "secret", mode=0o644)
        unsafe_paths["world-readable"] = world_readable
        empty = self.private_file("empty", "")
        unsafe_paths["empty"] = empty
        oversized = self.private_file("oversized", "x" * 1025)
        unsafe_paths["oversized"] = oversized
        directory = self.root / "secret-directory"
        directory.mkdir()
        os.chmod(directory, 0o600)
        unsafe_paths["directory"] = directory
        symlink = self.root / "secret-symlink"
        symlink.symlink_to(self.google_secret_file)
        unsafe_paths["symlink"] = symlink

        for label, path in unsafe_paths.items():
            with self.subTest(label=label), self.assertRaises(RuntimeError):
                self.make_app(
                    google=True,
                    overrides={"ADMIN_GOOGLE_CLIENT_SECRET_FILE": str(path)},
                )

        with patch("os.geteuid", return_value=os.geteuid() + 1):
            with self.assertRaises(RuntimeError):
                self.make_app(google=True)

        stricter = self.private_file("stricter-secret", "secret", mode=0o400)
        app = self.make_app(
            google=True,
            overrides={"ADMIN_GOOGLE_CLIENT_SECRET_FILE": str(stricter)},
        )
        self.assertEqual(app.test_client().get("/admin/google/login").status_code, 302)

    def test_smtp_secret_file_safety_uses_the_same_fail_closed_contract(self):
        unsafe = self.private_file("unsafe-smtp", SMTP_PASSWORD, mode=0o640)
        with self.assertRaises(RuntimeError):
            self.make_app(
                reset=True,
                overrides={"ADMIN_SMTP_PASSWORD_FILE": str(unsafe)},
            )

    def test_reset_request_is_csrf_protected_uniform_and_privacy_safe(self):
        mailer = RecordingMailer()
        app = self.make_app(reset=True, mailer=mailer)
        client = app.test_client()
        client.get("/admin/forgot-password")
        missing_csrf = client.post(
            "/admin/forgot-password", data={"email": OWNER_EMAIL}
        )
        self.assertEqual(missing_csrf.status_code, 400)
        self.assertEqual(mailer.messages, [])

        unknown = self.request_reset(client, "nobody@example.test")
        matching = self.request_reset(client, "  OwNeR@ExAmPlE.TeSt  ")
        self.assertEqual(unknown.status_code, 202)
        self.assertEqual(matching.status_code, 202)
        self.assertEqual(unknown.get_data(as_text=True), matching.get_data(as_text=True))
        response_body = matching.get_data(as_text=True)
        self.assertNotIn(OWNER_EMAIL, response_body.casefold())
        self.assertIn("Если адрес совпадает", response_body)
        self.assertEqual(len(mailer.messages), 1)
        self.assertEqual(mailer.messages[0]["recipient"], OWNER_EMAIL)

        token = self.token_from_mail(mailer)
        rows = self.reset_rows()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertIn("token_digest", row)
        self.assertRegex(str(row["token_digest"]), r"^[0-9a-f]{64}$")
        self.assertNotEqual(row["token_digest"], token)
        self.assertFalse({"email", "raw_token", "token"} & set(row))
        serialized_row = json.dumps(row, default=str)
        self.assertNotIn(token, serialized_row)
        self.assertNotIn(OWNER_EMAIL, serialized_row)
        serialized_audit = self.audit_payload()
        self.assertNotIn(token, serialized_audit)
        self.assertNotIn(OWNER_EMAIL, serialized_audit)

    def test_migration_creates_bounded_reset_schema_at_new_head(self):
        inspector = inspect(self.store.engine)
        self.assertIn("admin_password_resets", inspector.get_table_names())
        columns = {column["name"] for column in inspector.get_columns("admin_password_resets")}
        self.assertTrue(
            {
                "reset_id",
                "token_digest",
                "created_at",
                "expires_at",
                "activated_at",
                "used_at",
                "invalidated_at",
            }
            <= columns
        )
        self.assertFalse({"email", "raw_token", "token", "ip_address"} & columns)
        unique_sets = {
            tuple(item["column_names"])
            for item in inspector.get_unique_constraints("admin_password_resets")
        }
        unique_sets.update(
            tuple(item["column_names"])
            for item in inspector.get_indexes("admin_password_resets")
            if item.get("unique")
        )
        self.assertIn(("token_digest",), unique_sets)
        with self.store.engine.connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        self.assertEqual(revision, "0019_referral_program_v1")

    def test_migration_0017_downgrade_removes_reset_table_and_upgrade_restores_it(self):
        self.store.close()
        root = Path(__file__).resolve().parents[1]
        config = Config(str(root / "alembic.ini"))
        config.attributes["configure_logging"] = False
        config.set_main_option("script_location", str(root / "migrations"))
        config.set_main_option("sqlalchemy.url", f"sqlite:///{self.database_path}")

        command.downgrade(config, "0016_mirror_control_plane_v1")
        downgraded = DatabaseStore(
            f"sqlite:///{self.database_path}", migrate=False
        )
        try:
            self.assertNotIn(
                "admin_password_resets",
                inspect(downgraded.engine).get_table_names(),
            )
            with downgraded.engine.connect() as connection:
                revision = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
            self.assertEqual(revision, "0016_mirror_control_plane_v1")
        finally:
            downgraded.close()

        command.upgrade(config, "head")
        self.store = DatabaseStore(
            f"sqlite:///{self.database_path}", migrate=False
        )
        self.assertIn(
            "admin_password_resets", inspect(self.store.engine).get_table_names()
        )
        with self.store.engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
        self.assertEqual(revision, "0019_referral_program_v1")

    def test_reset_store_requires_explicit_activation_before_validity_or_consume(self):
        app = self.make_app(reset=True)
        admin_store = app.extensions["admin_store"]
        credential_before = admin_store.credential()
        digest = "a" * 64
        admin_store.issue_password_reset(token_digest=digest, ttl_seconds=900)
        issued_row = self.reset_rows()[0]
        self.assertIn("activated_at", issued_row)
        self.assertIsNone(issued_row["activated_at"])
        self.assertFalse(admin_store.password_reset_valid(token_digest=digest))
        self.assertIsNone(
            admin_store.consume_password_reset(
                token_digest=digest,
                password_hash="inactive-token-must-not-win",
            )
        )
        credential_after_rejected_consume = admin_store.credential()
        self.assertEqual(
            credential_after_rejected_consume.password_hash,
            credential_before.password_hash,
        )
        self.assertEqual(
            credential_after_rejected_consume.session_version,
            credential_before.session_version,
        )

        self.assertTrue(hasattr(admin_store, "activate_password_reset"))
        admin_store.activate_password_reset(token_digest=digest)
        activated_row = self.reset_rows()[0]
        self.assertIsNotNone(activated_row["activated_at"])
        self.assertTrue(admin_store.password_reset_valid(token_digest=digest))
        consumed = admin_store.consume_password_reset(
            token_digest=digest,
            password_hash="activated-token-password-hash",
        )
        self.assertIsNotNone(consumed)
        self.assertIsNotNone(self.reset_rows()[0]["used_at"])

    def test_successful_mail_activates_only_after_delivery_returns(self):
        session_secret = self.base_config()["SECRET_KEY"]
        mailer = ActivationObservingMailer(
            self.store, session_secret=session_secret
        )
        app = self.make_app(reset=True, mailer=mailer)
        client = app.test_client()
        response = self.request_reset(client, OWNER_EMAIL)
        self.assertEqual(len(mailer.messages), 1)
        token = self.token_from_mail(mailer)
        row = self.reset_rows()[0]
        link = client.get(f"/admin/reset-password/{token}")
        with self.subTest(contract="public response remains uniform"):
            self.assertEqual(response.status_code, 202)
        with self.subTest(contract="row inactive while mail transport runs"):
            self.assertEqual(mailer.activation_during_delivery, [None])
        with self.subTest(contract="row activated only after successful mail"):
            self.assertIn("activated_at", row)
            self.assertIsNotNone(row["activated_at"])
        with self.subTest(contract="activated link becomes usable"):
            self.assertEqual(link.status_code, 200)

    def test_mail_and_invalidation_failure_cannot_leave_issued_link_usable(self):
        mailer = RecordingMailer(fail=True)
        app = self.make_app(reset=True, mailer=mailer)
        app.config["PROPAGATE_EXCEPTIONS"] = False
        client = app.test_client()
        with patch.object(
            app.extensions["admin_store"],
            "invalidate_password_reset",
            side_effect=RuntimeError("invalidation database unavailable"),
        ):
            response = self.request_reset(client, OWNER_EMAIL)
        self.assertEqual(len(mailer.messages), 1)
        token = self.token_from_mail(mailer)
        row = self.reset_rows()[0]
        link = client.get(f"/admin/reset-password/{token}")
        with self.subTest(contract="public response remains uniform"):
            self.assertEqual(response.status_code, 202)
        with self.subTest(contract="failed delivery never activates row"):
            self.assertIn("activated_at", row)
            self.assertIsNone(row["activated_at"])
        with self.subTest(contract="failed-delivery link is unusable"):
            self.assertEqual(link.status_code, 400)

    def test_activation_failure_after_mail_keeps_link_inactive_and_response_uniform(self):
        mailer = RecordingMailer()
        app = self.make_app(reset=True, mailer=mailer)
        client = app.test_client()
        with patch.object(
            app.extensions["admin_store"],
            "activate_password_reset",
            create=True,
            side_effect=RuntimeError("activation database unavailable"),
        ) as activate:
            response = self.request_reset(client, OWNER_EMAIL)
        self.assertEqual(len(mailer.messages), 1)
        token = self.token_from_mail(mailer)
        row = self.reset_rows()[0]
        link = client.get(f"/admin/reset-password/{token}")
        with self.subTest(contract="activation attempted after mail"):
            activate.assert_called_once()
        with self.subTest(contract="public response remains uniform"):
            self.assertEqual(response.status_code, 202)
        with self.subTest(contract="row remains inactive"):
            self.assertIn("activated_at", row)
            self.assertIsNone(row["activated_at"])
        with self.subTest(contract="apparently delivered link is unusable"):
            self.assertEqual(link.status_code, 400)

    def test_reset_issue_database_failure_keeps_uniform_response_and_sends_nothing(self):
        mailer = RecordingMailer()
        app = self.make_app(reset=True, mailer=mailer)
        app.config["PROPAGATE_EXCEPTIONS"] = False
        client = app.test_client()
        unknown = self.request_reset(client, "unknown@example.test")
        self.assertEqual(unknown.status_code, 202)

        with patch.object(
            app.extensions["admin_store"],
            "issue_password_reset",
            side_effect=RuntimeError("database unavailable"),
        ):
            matching = self.request_reset(client, OWNER_EMAIL)

        self.assertEqual(matching.status_code, 202)
        self.assertEqual(
            matching.get_data(as_text=True), unknown.get_data(as_text=True)
        )
        self.assertEqual(mailer.messages, [])
        self.assertEqual(self.reset_rows(), [])
        audit = self.audit_payload()
        self.assertIn("admin_password_reset_issue_failed", audit)
        self.assertNotIn(OWNER_EMAIL, audit)

    def test_repeat_reset_invalidates_old_token_and_only_latest_can_complete(self):
        mailer = RecordingMailer()
        app = self.make_app(reset=True, mailer=mailer)
        client = app.test_client()
        self.request_reset(client, OWNER_EMAIL)
        self.assertEqual(len(mailer.messages), 1)
        old_token = self.token_from_mail(mailer)
        self.request_reset(client, OWNER_EMAIL)
        self.assertEqual(len(mailer.messages), 2)
        new_token = self.token_from_mail(mailer)
        self.assertNotEqual(old_token, new_token)
        rows = self.reset_rows()
        self.assertEqual(len(rows), 2)
        self.assertIsNotNone(rows[0]["invalidated_at"])
        self.assertIsNone(rows[1]["invalidated_at"])
        self.assertEqual(
            client.get(f"/admin/reset-password/{old_token}").status_code,
            400,
        )
        valid = client.get(f"/admin/reset-password/{new_token}")
        self.assertEqual(valid.status_code, 200)

    def test_valid_reset_changes_hash_consumes_token_and_invalidates_sessions(self):
        mailer = RecordingMailer()
        app = self.make_app(reset=True, mailer=mailer)
        old_session = app.test_client()
        self.login(old_session)
        credential_before = app.extensions["admin_store"].credential()

        reset_client = app.test_client()
        issued = self.request_reset(reset_client, OWNER_EMAIL)
        self.assertEqual(issued.status_code, 202)
        self.assertEqual(len(mailer.messages), 1)
        token = self.token_from_mail(mailer)
        reset_page = reset_client.get(f"/admin/reset-password/{token}")
        self.assertEqual(reset_page.status_code, 200)
        short = reset_client.post(
            f"/admin/reset-password/{token}",
            data={
                "csrf_token": self.csrf(reset_client),
                "password": "too-short",
                "password_confirm": "different",
            },
        )
        self.assertEqual(short.status_code, 400)
        self.assertEqual(
            app.extensions["admin_store"].credential().session_version,
            credential_before.session_version,
        )

        accepted = reset_client.post(
            f"/admin/reset-password/{token}",
            data={
                "csrf_token": self.csrf(reset_client),
                "password": "new-secure-password-456",
                "password_confirm": "new-secure-password-456",
                "next": "https://evil.example/steal",
            },
        )
        self.assertEqual(accepted.status_code, 303)
        self.assertEqual(accepted.headers["Location"], "/admin")
        credential_after = app.extensions["admin_store"].credential()
        self.assertEqual(
            credential_after.session_version,
            credential_before.session_version + 1,
        )
        self.assertTrue(
            check_password_hash(
                credential_after.password_hash, "new-secure-password-456"
            )
        )
        self.assertFalse(
            check_password_hash(credential_after.password_hash, "test-password-123")
        )
        self.assertEqual(old_session.get("/admin").headers["Location"], "/admin/login")
        self.assertEqual(
            reset_client.get(f"/admin/reset-password/{token}").status_code,
            400,
        )
        row = self.reset_rows()[0]
        self.assertIsNotNone(row["used_at"])

    def test_direct_credential_change_atomically_revokes_pending_reset_link(self):
        mailer = RecordingMailer()
        app = self.make_app(reset=True, mailer=mailer)
        reset_client = app.test_client()
        issued = self.request_reset(reset_client, OWNER_EMAIL)
        self.assertEqual(issued.status_code, 202)
        self.assertEqual(len(mailer.messages), 1)
        token = self.token_from_mail(mailer)
        generic_invalid = reset_client.get(
            "/admin/reset-password/not-a-real-token"
        )
        self.assertEqual(generic_invalid.status_code, 400)

        admin_client = app.test_client()
        self.login(admin_client)
        credential_before = app.extensions["admin_store"].credential()
        previous_version = credential_before.session_version
        direct_password = "direct-security-password-789"
        changed = admin_client.post(
            "/admin/security",
            data={
                "csrf_token": self.csrf(admin_client),
                "current_password": "test-password-123",
                "username": "owner-renamed",
                "password": direct_password,
            },
        )
        self.assertEqual(changed.status_code, 302)

        credential_after_direct_change = app.extensions["admin_store"].credential()
        expected_version = previous_version + 1
        self.assertEqual(credential_after_direct_change.username, "owner-renamed")
        self.assertEqual(
            credential_after_direct_change.session_version, expected_version
        )
        self.assertTrue(
            check_password_hash(
                credential_after_direct_change.password_hash, direct_password
            )
        )

        revoked_get = reset_client.get(f"/admin/reset-password/{token}")
        overwrite_attempt = reset_client.post(
            f"/admin/reset-password/{token}",
            data={
                "csrf_token": self.csrf(reset_client),
                "password": "reset-link-overwrite-456",
                "password_confirm": "reset-link-overwrite-456",
            },
        )
        row = self.reset_rows()[0]
        credential_final = app.extensions["admin_store"].credential()

        with self.subTest(contract="pending row invalidated, not consumed"):
            self.assertIsNotNone(row["invalidated_at"])
            self.assertIsNone(row["used_at"])
        with self.subTest(contract="GET is generic invalid link"):
            self.assertEqual(revoked_get.status_code, 400)
            self.assertEqual(
                revoked_get.get_data(as_text=True),
                generic_invalid.get_data(as_text=True),
            )
        with self.subTest(contract="POST cannot replay link"):
            self.assertEqual(overwrite_attempt.status_code, 400)
        with self.subTest(contract="direct credential remains authoritative"):
            self.assertEqual(credential_final.username, "owner-renamed")
            self.assertEqual(credential_final.session_version, expected_version)
            self.assertTrue(
                check_password_hash(credential_final.password_hash, direct_password)
            )
            self.assertFalse(
                check_password_hash(
                    credential_final.password_hash, "reset-link-overwrite-456"
                )
            )

    def test_unknown_expired_and_consumed_reset_links_share_generic_failure(self):
        mailer = RecordingMailer()
        app = self.make_app(reset=True, mailer=mailer)
        client = app.test_client()
        before = app.extensions["admin_store"].credential()
        unknown = client.get("/admin/reset-password/not-a-real-token")
        self.assertEqual(unknown.status_code, 400)

        self.request_reset(client, OWNER_EMAIL)
        token = self.token_from_mail(mailer)
        with self.store.engine.begin() as connection:
            connection.execute(
                text("UPDATE admin_password_resets SET expires_at = :past"),
                {"past": datetime.now(timezone.utc) - timedelta(seconds=1)},
            )
        expired = client.get(f"/admin/reset-password/{token}")
        self.assertEqual(expired.status_code, 400)
        self.assertEqual(unknown.get_data(as_text=True), expired.get_data(as_text=True))
        after = app.extensions["admin_store"].credential()
        self.assertEqual(before.password_hash, after.password_hash)
        self.assertEqual(before.session_version, after.session_version)

    def test_consumed_reset_link_matches_unknown_generic_failure_body(self):
        mailer = RecordingMailer()
        app = self.make_app(reset=True, mailer=mailer)
        client = app.test_client()
        unknown = client.get("/admin/reset-password/not-a-real-token")
        self.assertEqual(unknown.status_code, 400)
        self.request_reset(client, OWNER_EMAIL)
        token = self.token_from_mail(mailer)
        client.get(f"/admin/reset-password/{token}")
        accepted = client.post(
            f"/admin/reset-password/{token}",
            data={
                "csrf_token": self.csrf(client),
                "password": "consumed-reset-password-123",
                "password_confirm": "consumed-reset-password-123",
            },
        )
        self.assertEqual(accepted.status_code, 303)
        consumed = client.get(f"/admin/reset-password/{token}")
        self.assertEqual(consumed.status_code, 400)
        self.assertEqual(
            consumed.get_data(as_text=True), unknown.get_data(as_text=True)
        )

    def test_mail_failure_revokes_token_and_audits_without_secrets(self):
        mailer = RecordingMailer(fail=True)
        app = self.make_app(reset=True, mailer=mailer)
        client = app.test_client()
        response = self.request_reset(client, OWNER_EMAIL)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(len(mailer.messages), 1)
        token = self.token_from_mail(mailer)
        rows = self.reset_rows()
        self.assertTrue(
            not rows
            or all(row["invalidated_at"] is not None or row["used_at"] is not None for row in rows)
        )
        self.assertEqual(client.get(f"/admin/reset-password/{token}").status_code, 400)
        audit = self.audit_payload()
        self.assertIn("admin_password_reset_delivery_failed", audit)
        self.assertNotIn(token, audit)
        self.assertNotIn(OWNER_EMAIL, audit)

    def test_reset_limiter_creates_nothing_and_sends_nothing_when_blocked(self):
        mailer = RecordingMailer()
        app = self.make_app(
            reset=True,
            mailer=mailer,
            overrides={"ADMIN_RESET_RATE_LIMIT_ATTEMPTS": "2"},
        )
        client = app.test_client()
        self.assertEqual(self.request_reset(client, OWNER_EMAIL).status_code, 202)
        self.assertEqual(self.request_reset(client, OWNER_EMAIL).status_code, 202)
        rows_before = len(self.reset_rows())
        blocked = self.request_reset(client, OWNER_EMAIL)
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(len(mailer.messages), 2)
        self.assertEqual(len(self.reset_rows()), rows_before)

    def test_reset_source_uses_cloudflare_ip_only_from_loopback_without_persisting_it(self):
        trusted_app = self.make_app(
            reset=True,
            overrides={"ADMIN_RESET_RATE_LIMIT_ATTEMPTS": "1"},
        )
        trusted_client = trusted_app.test_client()
        first_cf_ip = "198.51.100.10"
        second_cf_ip = "203.0.113.20"
        first = self.request_reset(
            trusted_client,
            "unknown@example.test",
            remote_addr="127.0.0.1",
            headers={"CF-Connecting-IP": first_cf_ip},
        )
        second = self.request_reset(
            trusted_client,
            "unknown@example.test",
            remote_addr="127.0.0.1",
            headers={"CF-Connecting-IP": second_cf_ip},
        )
        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 202)

        untrusted_app = self.make_app(
            reset=True,
            overrides={"ADMIN_RESET_RATE_LIMIT_ATTEMPTS": "1"},
        )
        untrusted_client = untrusted_app.test_client()
        direct_peer = "192.0.2.44"
        untrusted_first = self.request_reset(
            untrusted_client,
            "unknown@example.test",
            remote_addr=direct_peer,
            headers={"CF-Connecting-IP": first_cf_ip},
        )
        untrusted_second = self.request_reset(
            untrusted_client,
            "unknown@example.test",
            remote_addr=direct_peer,
            headers={"CF-Connecting-IP": second_cf_ip},
        )
        self.assertEqual(untrusted_first.status_code, 202)
        self.assertEqual(untrusted_second.status_code, 429)

        persisted = self.audit_payload() + json.dumps(
            self.reset_rows(), default=str
        )
        visible = "\n".join(
            response.get_data(as_text=True)
            for response in (first, second, untrusted_first, untrusted_second)
        )
        for raw_ip in (first_cf_ip, second_cf_ip, direct_peer):
            self.assertNotIn(raw_ip, persisted)
            self.assertNotIn(raw_ip, visible)


class AdminGoogleAuthTest(AdminAuthFixture):
    def google_start(self, client):
        response = client.get("/admin/google/login")
        self.assertEqual(response.status_code, 302)
        parsed = urlparse(response.headers["Location"])
        self.assertEqual(
            f"{parsed.scheme}://{parsed.netloc}{parsed.path}",
            "https://accounts.google.com/o/oauth2/v2/auth",
        )
        return response, parse_qs(parsed.query)

    def google_session_values(self, client):
        with client.session_transaction() as browser_session:
            return (
                browser_session["google_oauth_state"],
                browser_session["google_oauth_nonce"],
            )

    def test_google_start_uses_oidc_fixed_callback_and_replaces_state_nonce(self):
        app = self.make_app(google=True)
        client = app.test_client()
        first, first_query = self.google_start(client)
        first_state, first_nonce = self.google_session_values(client)
        self.assertEqual(first_query["client_id"], [GOOGLE_CLIENT_ID])
        self.assertEqual(first_query["response_type"], ["code"])
        self.assertEqual(first_query["scope"], ["openid email"])
        self.assertEqual(first_query["redirect_uri"], [PUBLIC_URL + "/admin/google/callback"])
        self.assertEqual(first_query["state"], [first_state])
        self.assertEqual(first_query["nonce"], [first_nonce])
        self.assertNotIn(GOOGLE_CLIENT_SECRET, first.headers["Location"])
        self.assertGreaterEqual(len(first_state), 32)
        self.assertGreaterEqual(len(first_nonce), 32)

        _, second_query = self.google_start(client)
        second_state, second_nonce = self.google_session_values(client)
        self.assertNotEqual(first_state, second_state)
        self.assertNotEqual(first_nonce, second_nonce)
        self.assertEqual(second_query["state"], [second_state])
        self.assertEqual(second_query["nonce"], [second_nonce])

    def test_default_google_transport_posts_tokeninfo_token_in_body_only(self):
        transport = DefaultGoogleTransportProbe()
        with patch(
            "mydictionary.admin_auth.httpx.Client", return_value=transport
        ) as client_constructor:
            app = self.make_app(
                google=True,
                overrides={"ADMIN_GOOGLE_HTTP_CLIENT": None},
            )
        client_constructor.assert_called_once_with()
        client = app.test_client()
        self.google_start(client)
        state, nonce = self.google_session_values(client)
        transport.claims["nonce"] = nonce
        callback = client.get(
            "/admin/google/callback",
            query_string={"state": state, "code": "one-time-code"},
        )
        self.assertEqual(callback.status_code, 302)
        self.assertEqual(callback.headers["Location"], "/admin")

        tokeninfo_posts = [
            item
            for item in transport.post_calls
            if item["url"] == "https://oauth2.googleapis.com/tokeninfo"
        ]
        self.assertEqual(len(tokeninfo_posts), 1)
        self.assertEqual(
            tokeninfo_posts[0]["data"], {"id_token": "private-id-token"}
        )
        self.assertFalse(urlparse(tokeninfo_posts[0]["url"]).query)
        self.assertEqual(transport.get_calls, [])
        response_and_audit = callback.get_data(as_text=True) + self.audit_payload()
        self.assertNotIn("private-id-token", response_and_audit)

    def test_valid_google_callback_creates_normal_session_without_token_persistence(self):
        http_client = StubGoogleHTTPClient()
        app = self.make_app(google=True, http_client=http_client)
        client = app.test_client()
        _, query = self.google_start(client)
        state, nonce = self.google_session_values(client)
        http_client.claims["nonce"] = nonce
        http_client.claims["email"] = "  OwNeR@ExAmPlE.TeSt  "
        callback = client.get(
            "/admin/google/callback",
            query_string={
                "state": state,
                "code": "one-time-code",
                "next": "https://evil.example/steal",
            },
        )
        self.assertEqual(callback.status_code, 302)
        self.assertEqual(callback.headers["Location"], "/admin")
        self.assertEqual(len(http_client.post_calls), 1)
        self.assertEqual(len(http_client.get_calls), 1)
        exchange = http_client.post_calls[0]
        self.assertEqual(exchange["url"], "https://oauth2.googleapis.com/token")
        self.assertEqual(exchange["data"]["code"], "one-time-code")
        self.assertEqual(exchange["data"]["client_id"], GOOGLE_CLIENT_ID)
        self.assertEqual(exchange["data"]["client_secret"], GOOGLE_CLIENT_SECRET)
        self.assertEqual(exchange["data"]["redirect_uri"], query["redirect_uri"][0])
        self.assertEqual(exchange["data"]["grant_type"], "authorization_code")
        self.assertGreater(exchange["timeout"], 0)
        self.assertLessEqual(exchange["timeout"], 10)
        verification = http_client.get_calls[0]
        self.assertEqual(verification["url"], "https://oauth2.googleapis.com/tokeninfo")
        self.assertEqual(verification["params"], {"id_token": "private-id-token"})
        self.assertGreater(verification["timeout"], 0)
        self.assertLessEqual(verification["timeout"], 10)
        with client.session_transaction() as browser_session:
            self.assertEqual(browser_session["admin_username"], "owner")
            self.assertEqual(browser_session["session_version"], 1)
            self.assertNotIn("google_oauth_state", browser_session)
            self.assertNotIn("google_oauth_nonce", browser_session)
            serialized_session = repr(dict(browser_session))
        for secret in (
            "private-id-token",
            "private-access-token",
            "private-refresh-token",
            "one-time-code",
            OWNER_EMAIL,
        ):
            self.assertNotIn(secret, serialized_session)
            self.assertNotIn(secret, self.audit_payload())

    def test_google_callback_consumes_state_before_provider_attempt(self):
        http_client = StubGoogleHTTPClient()
        app = self.make_app(google=True, http_client=http_client)
        client = app.test_client()
        self.google_start(client)
        state, nonce = self.google_session_values(client)
        http_client.claims["nonce"] = nonce
        first = client.get(
            "/admin/google/callback", query_string={"state": state, "code": "code"}
        )
        self.assertEqual(first.status_code, 302)
        replay = client.get(
            "/admin/google/callback", query_string={"state": state, "code": "code"}
        )
        self.assertEqual(replay.status_code, 401)
        self.assertEqual(len(http_client.post_calls), 1)

    def test_missing_or_mismatched_oauth_state_and_missing_code_never_call_provider(self):
        for label, query_factory in (
            ("missing state", lambda state: {"code": "code"}),
            ("mismatched state", lambda state: {"state": "wrong", "code": "code"}),
            ("missing code", lambda state: {"state": state}),
        ):
            with self.subTest(label=label):
                http_client = StubGoogleHTTPClient()
                app = self.make_app(google=True, http_client=http_client)
                client = app.test_client()
                self.google_start(client)
                state, _ = self.google_session_values(client)
                response = client.get(
                    "/admin/google/callback", query_string=query_factory(state)
                )
                self.assertEqual(response.status_code, 401)
                self.assertNotIn("admin_username", self._session_dict(client))
                self.assertEqual(http_client.post_calls, [])
                self.assertEqual(http_client.get_calls, [])

    @staticmethod
    def _session_dict(client):
        with client.session_transaction() as browser_session:
            return dict(browser_session)

    def test_invalid_oidc_claims_fail_closed_with_generic_copy(self):
        now = datetime.now(timezone.utc)
        cases = {
            "audience": {"aud": "other-client"},
            "issuer": {"iss": "https://evil.example"},
            "expiry": {"exp": str(int((now - timedelta(seconds=1)).timestamp()))},
            "nonce": {"nonce": "wrong-nonce"},
            "verified boolean": {"email_verified": "false"},
            "verified missing": {"email_verified": None},
            "email": {"email": "other@example.test"},
        }
        bodies = []
        for label, replacement in cases.items():
            with self.subTest(label=label):
                http_client = StubGoogleHTTPClient()
                app = self.make_app(google=True, http_client=http_client)
                client = app.test_client()
                self.google_start(client)
                state, nonce = self.google_session_values(client)
                http_client.claims["nonce"] = nonce
                for key, value in replacement.items():
                    if value is None:
                        http_client.claims.pop(key, None)
                    else:
                        http_client.claims[key] = value
                response = client.get(
                    "/admin/google/callback",
                    query_string={"state": state, "code": "private-code"},
                )
                self.assertEqual(response.status_code, 401)
                self.assertNotIn("admin_username", self._session_dict(client))
                body = response.get_data(as_text=True)
                bodies.append(body)
                self.assertIn("Не удалось войти через Google", body)
                self.assertNotIn("private-code", body)
                self.assertNotIn(str(replacement), body)
        self.assertTrue(bodies)
        self.assertEqual(len(bodies), len(cases))

    def test_google_network_http_and_json_failures_create_no_session_or_tokens(self):
        cases = ("post network", "post json", "get network", "get json")
        bodies = []
        for label in cases:
            with self.subTest(label=label):
                http_client = StubGoogleHTTPClient()
                if label == "post network":
                    http_client.post_error = RuntimeError("private provider failure")
                elif label == "post json":
                    http_client.token_json_error = ValueError("private malformed payload")
                elif label == "get network":
                    http_client.get_error = RuntimeError("private provider failure")
                else:
                    http_client.claim_json_error = ValueError("private malformed payload")
                app = self.make_app(google=True, http_client=http_client)
                client = app.test_client()
                self.google_start(client)
                state, nonce = self.google_session_values(client)
                http_client.claims["nonce"] = nonce
                response = client.get(
                    "/admin/google/callback",
                    query_string={"state": state, "code": "private-code"},
                )
                self.assertEqual(response.status_code, 401)
                self.assertNotIn("admin_username", self._session_dict(client))
                body = response.get_data(as_text=True)
                self.assertNotIn("private", body)
                self.assertIn("Не удалось войти через Google", body)
                bodies.append(body)
        self.assertEqual(len(bodies), len(cases))

    def test_google_provider_4xx_and_5xx_are_generic_and_never_create_session(self):
        cases = (
            ("token 4xx", 400, 200),
            ("token 5xx", 503, 200),
            ("tokeninfo 4xx", 200, 401),
            ("tokeninfo 5xx", 200, 500),
        )
        for label, token_status, claim_status in cases:
            with self.subTest(provider_failure=label):
                http_client = StubGoogleHTTPClient()
                http_client.token_status_code = token_status
                http_client.claim_status_code = claim_status
                app = self.make_app(google=True, http_client=http_client)
                client = app.test_client()
                self.google_start(client)
                state, nonce = self.google_session_values(client)
                http_client.claims["nonce"] = nonce
                response = client.get(
                    "/admin/google/callback",
                    query_string={"state": state, "code": "private-code"},
                )
                self.assertEqual(response.status_code, 401)
                body = response.get_data(as_text=True)
                self.assertIn("Не удалось войти через Google", body)
                self.assertNotIn("private-code", body)
                self.assertNotIn("admin_username", self._session_dict(client))
                audit = self.audit_payload()
                self.assertNotIn("private-code", audit)
                self.assertNotIn("private-id-token", audit)


class AdminAuthLauncherContractTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mydictionary-admin-auth-launcher-")
        self.root = Path(self.temporary.name)
        release = self.root / "releases" / ("b" * 40)
        python = release / ".venv" / "bin" / "python3"
        python.parent.mkdir(parents=True)
        python.write_text("", encoding="utf-8")
        (self.root / "current").symlink_to(release, target_is_directory=True)
        secrets = self.root / "admin-secrets.json"
        secrets.write_text(
            json.dumps(
                {
                    "username": "owner",
                    "password_hash": "admin-password-hash",
                    "session_secret": "s" * 40,
                }
            ),
            encoding="utf-8",
        )
        os.chmod(secrets, 0o600)
        self.google_file = self.root / "google.secret"
        self.google_file.write_text(GOOGLE_CLIENT_SECRET, encoding="utf-8")
        os.chmod(self.google_file, 0o600)
        self.smtp_file = self.root / "smtp.secret"
        self.smtp_file.write_text(SMTP_PASSWORD, encoding="utf-8")
        os.chmod(self.smtp_file, 0o600)

    def tearDown(self):
        self.temporary.cleanup()

    def test_launcher_forwards_auth_metadata_and_secret_paths_never_secret_values(self):
        source = {
            "MYDICTIONARY_APP_ROOT": str(self.root),
            "DATABASE_URL": "postgresql+psycopg://user@/mydictionary?host=/tmp",
            "ADMIN_EMAIL": OWNER_EMAIL,
            "ADMIN_PUBLIC_URL": PUBLIC_URL,
            "ADMIN_GOOGLE_CLIENT_ID": GOOGLE_CLIENT_ID,
            "ADMIN_GOOGLE_CLIENT_SECRET_FILE": str(self.google_file),
            "ADMIN_SMTP_HOST": "smtp.example.test",
            "ADMIN_SMTP_PORT": "587",
            "ADMIN_SMTP_USERNAME": "mailer@example.test",
            "ADMIN_SMTP_PASSWORD_FILE": str(self.smtp_file),
            "ADMIN_SMTP_FROM": "MY DICTIONARY <mailer@example.test>",
            "ADMIN_RESET_TOKEN_TTL_SECONDS": "900",
        }
        _, arguments, environment, _ = admin_launcher.build_process(source)
        for name, value in source.items():
            if name.startswith("ADMIN_"):
                self.assertIn(name, environment)
                self.assertEqual(environment[name], value)
        rendered = "\n".join([*arguments, *environment.values()])
        self.assertNotIn(GOOGLE_CLIENT_SECRET, rendered)
        self.assertNotIn(SMTP_PASSWORD, rendered)


if __name__ == "__main__":
    unittest.main()
