"""Fail-closed setup and readiness contracts for a future Stars launch."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
from typing import Any, Mapping, Sequence

from mydictionary.economics import require_current_review
from mydictionary.runtime_secrets import (
    RuntimeSecretError,
    read_private_json,
    validate_telegram_bot_token,
)


TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off", ""}
MAX_PRIVATE_JSON_BYTES = 16 * 1024
PROFILE_ENV_KEYS = {
    "BILLING_PAYLOAD_SECRET",
    "BILLING_SUPPORT_CONTACT",
    "BILLING_SELLER_LEGAL_NAME",
    "BILLING_SELLER_ADDRESS",
    "BILLING_SELLER_EMAIL",
    "BILLING_SELLER_PHONE",
    "BILLING_TERMS_TEXT",
    "BILLING_TERMS_VERSION",
    "BILLING_TERMS_SHA256",
    "BILLING_TERMS_APPROVED",
}
RECEIPT_SCENARIOS = {
    "purchase",
    "duplicate_delivery",
    "restart_recovery",
    "reconciliation",
    "refund",
}
EXPECTED_PRODUCTS = {
    "ai-mini": {
        "credits": 20,
        "price_xtr": 69,
        "billing_mode": "one_time",
        "subscription_period_seconds": None,
        "estimated_cost_micro_usd": 289_000,
        "target_margin_bps": 5_000,
    },
    "ai-starter": {
        "credits": 50,
        "price_xtr": 129,
        "billing_mode": "one_time",
        "subscription_period_seconds": None,
        "estimated_cost_micro_usd": 529_000,
        "target_margin_bps": 5_000,
    },
    "ai-value": {
        "credits": 150,
        "price_xtr": 319,
        "billing_mode": "one_time",
        "subscription_period_seconds": None,
        "estimated_cost_micro_usd": 1_319_000,
        "target_margin_bps": 5_000,
    },
    "ai-monthly": {
        "credits": 100,
        "price_xtr": 229,
        "billing_mode": "subscription",
        "subscription_period_seconds": 2_592_000,
        "estimated_cost_micro_usd": 929_000,
        "target_margin_bps": 5_000,
    },
}


class StarsLaunchError(RuntimeError):
    """Raised when Stars launch setup or evidence is unsafe."""


def _utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise StarsLaunchError("Stars launch timestamps must include timezone")
    return current.astimezone(timezone.utc)


def _parse_bool(value: object, *, label: str) -> bool:
    normalized = str(value or "").strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise StarsLaunchError(f"{label} must be a boolean")


def _parse_expiry(value: object) -> datetime:
    raw = str(value or "").strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise StarsLaunchError(
            "Stars launch enrollment expiry must use ISO 8601"
        ) from exc
    return _utc(parsed)


def _destination(
    value: object, *, label: str, allowed_directory: Path | None
) -> Path:
    raw = str(value or "").strip()
    destination = Path(raw).expanduser()
    if not raw or not destination.is_absolute():
        raise StarsLaunchError(f"{label} path must be absolute")
    if allowed_directory is not None:
        allowed = Path(allowed_directory).expanduser().resolve()
        if destination.parent.resolve() != allowed:
            raise StarsLaunchError(f"{label} path must stay in local-config")
    return destination


def _status(
    *, enabled: bool, path: Path | None, expires_at: datetime | None, now: datetime
) -> str:
    if not enabled or path is None or expires_at is None:
        return "disabled"
    if path.exists() or path.is_symlink():
        return "consumed"
    if now >= expires_at:
        return "expired"
    return "ready"


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _fingerprint(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()[:12]


def _write_private_json(path: Path, value: Mapping[str, Any], *, label: str) -> str:
    payload = _canonical_bytes(value)
    if not payload or len(payload) > MAX_PRIVATE_JSON_BYTES:
        raise StarsLaunchError(f"{label} payload size is invalid")
    parent = path.parent
    try:
        metadata = parent.lstat()
    except OSError as exc:
        raise StarsLaunchError(f"{label} directory is unavailable") from exc
    if not stat.S_ISDIR(metadata.st_mode) or parent.is_symlink():
        raise StarsLaunchError(f"{label} directory is unavailable")
    if metadata.st_uid != os.geteuid():
        raise StarsLaunchError(f"{label} directory must be owned by this user")
    if stat.S_IMODE(metadata.st_mode) & 0o022:
        raise StarsLaunchError(f"{label} directory permissions are unsafe")

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise StarsLaunchError(f"{label} enrollment is consumed") from exc
    except OSError as exc:
        raise StarsLaunchError(f"{label} file cannot be created safely") from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        # A partial file intentionally consumes the one-time destination.
        raise
    metadata = path.stat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise StarsLaunchError(f"{label} file permissions are unsafe")
    return hashlib.sha256(payload).hexdigest()[:12]


def _required_text(
    values: Mapping[str, object], key: str, *, maximum: int
) -> str:
    value = str(values.get(key) or "").strip()
    if not value or len(value) > maximum:
        raise StarsLaunchError(f"{key} is required and must be at most {maximum} characters")
    return value


def _profile_payload(values: Mapping[str, object]) -> dict[str, Any]:
    if not _parse_bool(values.get("terms_approved"), label="Terms approval"):
        raise StarsLaunchError("Terms approval is required")
    terms_text = _required_text(values, "terms_text", maximum=3500)
    terms_sha256 = hashlib.sha256(terms_text.encode("utf-8")).hexdigest()
    payload = {
        "schema_version": 1,
        "seller": {
            "legal_name": _required_text(
                values, "seller_legal_name", maximum=160
            ),
            "address": _required_text(values, "seller_address", maximum=500),
            "email": _required_text(values, "seller_email", maximum=254),
            "phone": _required_text(values, "seller_phone", maximum=64),
        },
        "support_contact": _required_text(
            values, "support_contact", maximum=256
        ),
        "terms": {
            "text": terms_text,
            "version": _required_text(values, "terms_version", maximum=64),
            "sha256": terms_sha256,
            "approved": True,
        },
        "payload_secret": secrets.token_urlsafe(48),
    }
    # Reuse the runtime validator before anything reaches disk.
    from mydictionary.billing import BillingConfigurationError, BillingSettings

    try:
        BillingSettings.from_env(
            {
                "TELEGRAM_STARS_ENABLED": "false",
                **_profile_env(payload),
            }
        )
    except BillingConfigurationError as exc:
        raise StarsLaunchError("Billing launch profile is invalid") from exc
    return payload


def _test_credentials_payload(values: Mapping[str, object]) -> dict[str, Any]:
    try:
        token = validate_telegram_bot_token(values.get("bot_token"))
    except RuntimeSecretError as exc:
        raise StarsLaunchError("Telegram test credential format is invalid") from exc
    raw_user_id = values.get("test_user_id")
    try:
        if isinstance(raw_user_id, bool):
            raise ValueError
        user_id = int(str(raw_user_id))
        if user_id <= 0 or str(user_id) != str(raw_user_id):
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise StarsLaunchError(
            "Telegram test credentials require a positive numeric user ID"
        ) from exc
    return {"bot_token": token, "test_user_id": user_id}


@dataclass(frozen=True)
class StarsLaunchEnrollmentSettings:
    enabled: bool
    profile_path: Path | None = None
    test_credentials_path: Path | None = None
    expires_at: datetime | None = None

    @classmethod
    def from_mapping(
        cls,
        values: Mapping[str, object],
        *,
        now: datetime | None = None,
        allowed_directory: Path | None = None,
    ) -> "StarsLaunchEnrollmentSettings":
        enabled = _parse_bool(
            values.get("STARS_LAUNCH_ENROLLMENT_ENABLED", "false"),
            label="Stars launch enrollment flag",
        )
        if not enabled:
            return cls(enabled=False)
        current = _utc(now)
        expires_at = _parse_expiry(
            values.get("STARS_LAUNCH_ENROLLMENT_EXPIRES_AT")
        )
        if expires_at > current + timedelta(hours=1):
            raise StarsLaunchError(
                "Stars launch enrollment window cannot exceed one hour"
            )
        profile_path = _destination(
            values.get("STARS_LAUNCH_PROFILE_PATH"),
            label="Stars launch profile",
            allowed_directory=allowed_directory,
        )
        credentials_path = _destination(
            values.get("STARS_TEST_CREDENTIALS_PATH"),
            label="Telegram test credentials",
            allowed_directory=allowed_directory,
        )
        if profile_path == credentials_path:
            raise StarsLaunchError(
                "Billing profile and test credentials require separate files"
            )
        return cls(
            enabled=True,
            profile_path=profile_path,
            test_credentials_path=credentials_path,
            expires_at=expires_at,
        )

    def statuses(self, *, now: datetime | None = None) -> dict[str, str]:
        current = _utc(now)
        return {
            "profile": _status(
                enabled=self.enabled,
                path=self.profile_path,
                expires_at=self.expires_at,
                now=current,
            ),
            "test_credentials": _status(
                enabled=self.enabled,
                path=self.test_credentials_path,
                expires_at=self.expires_at,
                now=current,
            ),
        }

    def _require_ready(self, kind: str, *, now: datetime | None) -> Path:
        state = self.statuses(now=now)[kind]
        if state != "ready":
            raise StarsLaunchError(f"Stars {kind} enrollment is {state}")
        path = (
            self.profile_path
            if kind == "profile"
            else self.test_credentials_path
        )
        if path is None:
            raise StarsLaunchError(f"Stars {kind} enrollment is disabled")
        return path

    def enroll_profile(
        self, values: Mapping[str, object], *, now: datetime | None = None
    ) -> str:
        path = self._require_ready("profile", now=now)
        payload = _profile_payload(values)
        return _write_private_json(path, payload, label="Stars launch profile")

    def enroll_test_credentials(
        self, values: Mapping[str, object], *, now: datetime | None = None
    ) -> str:
        path = self._require_ready("test_credentials", now=now)
        payload = _test_credentials_payload(values)
        return _write_private_json(
            path, payload, label="Telegram test credentials"
        )


def _exact_keys(value: Mapping[str, Any], expected: set[str], *, label: str) -> None:
    if set(value) != expected:
        raise StarsLaunchError(f"{label} schema is invalid")


def _require_mode_0600(path: Path, *, label: str) -> None:
    if not path.is_absolute():
        raise StarsLaunchError(f"{label} path must be absolute")
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise StarsLaunchError(f"{label} file cannot be opened safely") from exc
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise StarsLaunchError(f"{label} path must be a regular file")
    if metadata.st_uid != os.geteuid():
        raise StarsLaunchError(f"{label} file must be owned by the service user")
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise StarsLaunchError(f"{label} file permissions must be 0600")


def _profile_env(profile: Mapping[str, Any]) -> dict[str, str]:
    _exact_keys(
        profile,
        {"schema_version", "seller", "support_contact", "terms", "payload_secret"},
        label="Billing launch profile",
    )
    if profile.get("schema_version") != 1:
        raise StarsLaunchError("Billing launch profile schema is invalid")
    seller = profile.get("seller")
    terms = profile.get("terms")
    if not isinstance(seller, Mapping) or not isinstance(terms, Mapping):
        raise StarsLaunchError("Billing launch profile schema is invalid")
    _exact_keys(
        seller,
        {"legal_name", "address", "email", "phone"},
        label="Billing launch profile",
    )
    _exact_keys(
        terms,
        {"text", "version", "sha256", "approved"},
        label="Billing launch profile",
    )
    terms_text = str(terms.get("text") or "")
    digest = str(terms.get("sha256") or "").lower()
    if (
        not re.fullmatch(r"[a-f0-9]{64}", digest)
        or hashlib.sha256(terms_text.encode("utf-8")).hexdigest() != digest
        or terms.get("approved") is not True
    ):
        raise StarsLaunchError("Billing launch profile terms are invalid")
    secret = str(profile.get("payload_secret") or "")
    if len(secret) < 43 or len(secret) > 512 or secret != secret.strip():
        raise StarsLaunchError("Billing launch profile payload secret is invalid")
    string_values = {
        "BILLING_PAYLOAD_SECRET": secret,
        "BILLING_SUPPORT_CONTACT": profile.get("support_contact"),
        "BILLING_SELLER_LEGAL_NAME": seller.get("legal_name"),
        "BILLING_SELLER_ADDRESS": seller.get("address"),
        "BILLING_SELLER_EMAIL": seller.get("email"),
        "BILLING_SELLER_PHONE": seller.get("phone"),
        "BILLING_TERMS_TEXT": terms_text,
        "BILLING_TERMS_VERSION": terms.get("version"),
        "BILLING_TERMS_SHA256": digest,
        "BILLING_TERMS_APPROVED": "true",
    }
    if any(not isinstance(value, str) for value in string_values.values()):
        raise StarsLaunchError("Billing launch profile schema is invalid")
    return {key: str(value) for key, value in string_values.items()}


def load_billing_launch_profile(values: Mapping[str, str]) -> dict[str, str]:
    raw_path = str(values.get("BILLING_LAUNCH_PROFILE_FILE") or "").strip()
    if not raw_path:
        return {}
    conflicts = [
        key for key in PROFILE_ENV_KEYS if str(values.get(key) or "").strip()
    ]
    if conflicts:
        raise StarsLaunchError(
            "BILLING_LAUNCH_PROFILE_FILE cannot be mixed with inline billing profile settings"
        )
    _require_mode_0600(Path(raw_path).expanduser(), label="Billing launch profile")
    try:
        profile = read_private_json(raw_path, label="Billing launch profile")
    except RuntimeSecretError as exc:
        raise StarsLaunchError(str(exc)) from exc
    return _profile_env(profile)


def _test_credentials_fingerprint(path: Path) -> str:
    _require_mode_0600(path, label="Telegram test credentials")
    try:
        payload = read_private_json(path, label="Telegram test credentials")
    except RuntimeSecretError as exc:
        raise StarsLaunchError(str(exc)) from exc
    _exact_keys(
        payload,
        {"bot_token", "test_user_id"},
        label="Telegram test credentials",
    )
    normalized = _test_credentials_payload(payload)
    return _fingerprint(normalized)


def build_production_stars_canary_receipt(
    status: Mapping[str, Any], *, completed_at: datetime | None = None
) -> dict[str, Any]:
    """Build aggregate evidence that is deliberately not a test-launch receipt."""
    expected_fields = {
        "public_checkout_enabled",
        "canary_enabled",
        "state",
        "product_id",
        "amount_xtr",
        "payment_completed",
        "refund_pending",
        "refund_completed",
    }
    if not isinstance(status, Mapping) or set(status) != expected_fields:
        raise StarsLaunchError("Production Stars canary status schema is invalid")
    boolean_fields = {
        "public_checkout_enabled",
        "canary_enabled",
        "payment_completed",
        "refund_pending",
        "refund_completed",
    }
    if any(not isinstance(status[field], bool) for field in boolean_fields):
        raise StarsLaunchError("Production Stars canary status schema is invalid")
    if (
        not isinstance(status["state"], str)
        or not isinstance(status["product_id"], str)
        or type(status["amount_xtr"]) is not int
    ):
        raise StarsLaunchError("Production Stars canary status schema is invalid")
    final_status = {
        "public_checkout_enabled": False,
        "canary_enabled": False,
        "state": "refunded",
        "product_id": "ai-mini",
        "amount_xtr": 69,
        "payment_completed": True,
        "refund_pending": False,
        "refund_completed": True,
    }
    if any(status[field] != value for field, value in final_status.items()):
        raise StarsLaunchError(
            "Production Stars canary receipt requires disabled refunded status"
        )
    timestamp = _utc(completed_at).isoformat().replace("+00:00", "Z")
    return {
        "schema_version": 1,
        "environment": "telegram_production_canary",
        "completed_at": timestamp,
        "status": {field: status[field] for field in sorted(expected_fields)},
    }


def validate_stars_test_receipt(
    path: Path, *, now: datetime | None = None, max_age_days: int = 30
) -> dict[str, Any]:
    if not 1 <= int(max_age_days) <= 90:
        raise StarsLaunchError("Stars test receipt age must be between 1 and 90 days")
    _require_mode_0600(path, label="Stars test receipt")
    try:
        receipt = read_private_json(path, label="Stars test receipt")
    except RuntimeSecretError as exc:
        raise StarsLaunchError(str(exc)) from exc
    _exact_keys(
        receipt,
        {"schema_version", "environment", "completed_at", "scenarios"},
        label="Stars test receipt",
    )
    if receipt.get("schema_version") != 1 or receipt.get("environment") != "telegram_test":
        raise StarsLaunchError("Stars test receipt schema is invalid")
    scenarios = receipt.get("scenarios")
    if not isinstance(scenarios, Mapping):
        raise StarsLaunchError("Stars test receipt schema is invalid")
    _exact_keys(scenarios, RECEIPT_SCENARIOS, label="Stars test receipt")
    if any(value != "passed" for value in scenarios.values()):
        raise StarsLaunchError("Stars test receipt scenarios are incomplete")
    completed_at = _parse_expiry(receipt.get("completed_at"))
    current = _utc(now)
    if completed_at > current:
        raise StarsLaunchError("Stars test receipt cannot be from the future")
    if current - completed_at > timedelta(days=int(max_age_days)):
        raise StarsLaunchError("Stars test receipt is stale")
    return {
        "status": "passed",
        "scenario_count": len(RECEIPT_SCENARIOS),
        "fingerprint": _fingerprint(receipt),
    }


def _catalog_ready(products: Sequence[Mapping[str, Any]]) -> bool:
    rows = {str(row.get("product_id")): row for row in products}
    if set(rows) != set(EXPECTED_PRODUCTS):
        return False
    one_time_statuses: set[str] = set()
    for product_id, expected in EXPECTED_PRODUCTS.items():
        row = rows[product_id]
        if any(row.get(key) != value for key, value in expected.items()):
            return False
        status = str(row.get("status") or "")
        if product_id == "ai-monthly":
            if status != "draft":
                return False
        else:
            if status not in {"draft", "active"}:
                return False
            one_time_statuses.add(status)
    return len(one_time_statuses) == 1


def stars_launch_readiness(
    values: Mapping[str, str],
    products: Sequence[Mapping[str, Any]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _utc(now)
    gates = {
        "billing_profile": False,
        "test_credentials": False,
        "test_receipt": False,
        "economics": False,
        "catalog": False,
        "checkout_disabled": False,
    }
    try:
        from mydictionary.billing import BillingSettings

        settings = BillingSettings.from_env(values)
        gates["billing_profile"] = bool(
            settings.seller_identity_complete
            and settings.terms_approved
            and settings.payload_secret
        )
    except Exception:
        pass
    try:
        credentials_path = Path(
            str(values.get("TELEGRAM_TEST_CREDENTIALS_FILE") or "")
        )
        _test_credentials_fingerprint(credentials_path)
        gates["test_credentials"] = True
    except Exception:
        pass
    try:
        receipt_path = Path(str(values.get("STARS_TEST_RECEIPT_FILE") or ""))
        max_age = int(values.get("STARS_TEST_RECEIPT_MAX_AGE_DAYS", "30"))
        validate_stars_test_receipt(
            receipt_path, now=current, max_age_days=max_age
        )
        gates["test_receipt"] = True
    except Exception:
        pass
    try:
        net_xtr = int(values.get("BILLING_NET_MICRO_USD_PER_XTR", "0"))
        max_age = int(values.get("BILLING_ECONOMICS_MAX_AGE_DAYS", "30"))
        require_current_review(
            str(values.get("BILLING_ECONOMICS_REVIEWED_ON") or ""),
            max_age_days=max_age,
            setting_name="BILLING_ECONOMICS_REVIEWED_ON",
            today=current.date(),
        )
        gates["economics"] = 0 < net_xtr <= 10_000
    except (TypeError, ValueError):
        pass
    gates["catalog"] = _catalog_ready(products)
    try:
        gates["checkout_disabled"] = not _parse_bool(
            values.get("TELEGRAM_STARS_ENABLED", "false"),
            label="TELEGRAM_STARS_ENABLED",
        )
    except StarsLaunchError:
        pass
    blockers = [name for name, passed in gates.items() if not passed]
    return {
        "ready": not blockers,
        "status": "ready" if not blockers else "blocked",
        "gates": gates,
        "blockers": blockers,
        "one_time_products": 3,
        "subscription_status": "draft",
    }


def _private_fingerprint(path: Path | None, *, kind: str) -> str:
    if path is None:
        return "missing"
    try:
        if kind == "profile":
            profile = read_private_json(path, label="Billing launch profile")
            _profile_env(profile)
            return _fingerprint(profile)
        return _test_credentials_fingerprint(path)
    except (RuntimeSecretError, StarsLaunchError):
        return "invalid"


def stars_launch_enrollment_overview(
    settings: StarsLaunchEnrollmentSettings,
    *,
    receipt_path: Path | None = None,
    runtime_profile_path: Path | None = None,
    runtime_test_credentials_path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _utc(now)
    statuses = settings.statuses(now=current)
    profile_path = settings.profile_path or runtime_profile_path
    test_credentials_path = (
        settings.test_credentials_path or runtime_test_credentials_path
    )
    if statuses["profile"] == "disabled" and profile_path is not None:
        statuses["profile"] = (
            "consumed"
            if profile_path.exists() or profile_path.is_symlink()
            else "missing"
        )
    if (
        statuses["test_credentials"] == "disabled"
        and test_credentials_path is not None
    ):
        statuses["test_credentials"] = (
            "consumed"
            if test_credentials_path.exists() or test_credentials_path.is_symlink()
            else "missing"
        )
    receipt_status = "missing"
    receipt_fingerprint = "missing"
    if receipt_path and (receipt_path.exists() or receipt_path.is_symlink()):
        try:
            receipt = validate_stars_test_receipt(receipt_path, now=current)
            receipt_status = "passed"
            receipt_fingerprint = str(receipt["fingerprint"])
        except StarsLaunchError:
            receipt_status = "invalid"
            receipt_fingerprint = "invalid"
    return {
        "enabled": settings.enabled,
        "profile_status": statuses["profile"],
        "test_credentials_status": statuses["test_credentials"],
        "profile_fingerprint": (
            _private_fingerprint(profile_path, kind="profile")
            if statuses["profile"] == "consumed"
            else "missing"
        ),
        "test_credentials_fingerprint": (
            _private_fingerprint(
                test_credentials_path, kind="test_credentials"
            )
            if statuses["test_credentials"] == "consumed"
            else "missing"
        ),
        "test_receipt_status": receipt_status,
        "test_receipt_fingerprint": receipt_fingerprint,
        "enrollment_available": "ready" in statuses.values(),
        "expires_at": (
            settings.expires_at.isoformat() if settings.expires_at else None
        ),
    }
