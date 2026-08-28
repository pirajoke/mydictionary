"""Shared fail-closed helpers for dated commercial assumptions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


class EconomicsSnapshotError(ValueError):
    """Raised when runtime economics do not match an approved snapshot."""


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def parse_reviewed_on(
    value: str,
    *,
    setting_name: str,
    today: date | None = None,
) -> date:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{setting_name} is required")
    try:
        reviewed_on = date.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{setting_name} must use YYYY-MM-DD") from exc
    current_day = today or utc_today()
    if reviewed_on > current_day:
        raise ValueError(f"{setting_name} cannot be in the future")
    return reviewed_on


def require_current_review(
    value: str,
    *,
    max_age_days: int,
    setting_name: str,
    today: date | None = None,
) -> date:
    if not 1 <= int(max_age_days) <= 90:
        raise ValueError("Economics review age must be between 1 and 90 days")
    current_day = today or utc_today()
    reviewed_on = parse_reviewed_on(
        value,
        setting_name=setting_name,
        today=current_day,
    )
    if (current_day - reviewed_on).days > int(max_age_days):
        raise ValueError(
            f"{setting_name} is stale; refresh the reviewed economics"
        )
    return reviewed_on


def review_is_current(value: str, *, max_age_days: int) -> bool:
    try:
        require_current_review(
            value,
            max_age_days=max_age_days,
            setting_name="economics review date",
        )
    except (TypeError, ValueError):
        return False
    return True


def snapshot_sha256(snapshot: Mapping[str, Any]) -> str:
    """Return a formatting-independent digest for an economics snapshot."""
    encoded = json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _snapshot_object(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EconomicsSnapshotError(f"{name} must be an object")
    return value


def _snapshot_int(
    value: Any,
    name: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EconomicsSnapshotError(f"{name} must be an integer")
    parsed = value
    if not minimum <= parsed <= maximum:
        raise EconomicsSnapshotError(f"{name} is outside the allowed range")
    return parsed


def _snapshot_decimal(value: Any, name: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise EconomicsSnapshotError(f"{name} must be a decimal") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise EconomicsSnapshotError(f"{name} must be positive and finite")
    return parsed


def _snapshot_unlimited_request_cap(value: Any) -> None:
    if value is not None:
        raise EconomicsSnapshotError("AI daily request limit must be null")
    return None


@dataclass(frozen=True)
class AIEconomicsContract:
    path: Path
    snapshot_id: str
    snapshot_sha256: str
    reviewed_on: str
    max_age_days: int
    status: str
    provider: str
    model: str
    service_tier: str
    input_usd_per_million: Decimal
    cached_input_usd_per_million: Decimal
    cache_write_usd_per_million: Decimal
    output_usd_per_million: Decimal
    credits_per_request: int
    initial_credits: int
    max_daily_requests_per_user: int | None
    max_preflight_cost_micro_usd_per_request: int
    retrospective_breaker_micro_usd_per_response: int
    max_project_cost_micro_usd_per_day: int
    max_project_cost_micro_usd_per_month: int
    max_in_flight_cost_micro_usd: int
    max_provider_input_chars: int
    max_output_tokens: int

    def assert_current(self, *, today: date | None = None) -> "AIEconomicsContract":
        current = load_ai_economics_contract(
            self.path,
            expected_snapshot_id=self.snapshot_id,
            expected_snapshot_sha256=self.snapshot_sha256,
            require_approved=True,
        )
        require_current_review(
            current.reviewed_on,
            max_age_days=current.max_age_days,
            setting_name="AI economics snapshot",
            today=today,
        )
        return current


def resolve_snapshot_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def load_ai_economics_contract(
    path_value: str | Path,
    *,
    expected_snapshot_id: str | None = None,
    expected_snapshot_sha256: str | None = None,
    require_approved: bool = False,
) -> AIEconomicsContract:
    path = resolve_snapshot_path(path_value)
    try:
        raw_snapshot = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EconomicsSnapshotError("AI economics snapshot cannot be loaded") from exc
    snapshot = _snapshot_object(raw_snapshot, "economics snapshot")
    if snapshot.get("schema_version") not in {2, 3}:
        raise EconomicsSnapshotError("AI economics snapshot schema must be version 2 or 3")
    snapshot_id = str(snapshot.get("snapshot_id", "")).strip()
    if not 1 <= len(snapshot_id) <= 128:
        raise EconomicsSnapshotError("AI economics snapshot_id is invalid")
    digest = snapshot_sha256(snapshot)
    if expected_snapshot_id and snapshot_id != expected_snapshot_id:
        raise EconomicsSnapshotError("AI economics snapshot_id does not match runtime")
    if expected_snapshot_sha256:
        expected_digest = str(expected_snapshot_sha256).strip().lower()
        if not SHA256_RE.fullmatch(expected_digest) or digest != expected_digest:
            raise EconomicsSnapshotError("AI economics snapshot hash does not match runtime")

    reviewed_on = str(snapshot.get("reviewed_on", "")).strip()
    max_age_days = _snapshot_int(
        snapshot.get("max_age_days"),
        "economics max_age_days",
        minimum=1,
        maximum=90,
    )
    parse_reviewed_on(reviewed_on, setting_name="economics reviewed_on")
    ai = _snapshot_object(snapshot.get("ai"), "AI economics")
    status = str(ai.get("status", "")).strip().lower()
    if status not in {"draft", "approved"}:
        raise EconomicsSnapshotError("AI economics status must be draft or approved")
    if require_approved and status != "approved":
        raise EconomicsSnapshotError("AI economics snapshot is not approved")
    provider = str(ai.get("provider", "")).strip().lower()
    model = str(ai.get("model", "")).strip()
    service_tier = str(ai.get("service_tier", "")).strip().lower()
    if provider != "openai" or not model:
        raise EconomicsSnapshotError("AI provider and model are invalid")
    if service_tier != "default":
        raise EconomicsSnapshotError("AI service_tier must be default")

    rates = _snapshot_object(
        ai.get("short_context_usd_per_million"),
        "AI short-context rates",
    )
    credit_policy = _snapshot_object(ai.get("credit_policy"), "AI credit policy")
    limits = _snapshot_object(ai.get("limits"), "AI limits")
    if "max_daily_requests_per_user" not in limits:
        raise EconomicsSnapshotError("AI daily request limit is required")
    contract = AIEconomicsContract(
        path=path,
        snapshot_id=snapshot_id,
        snapshot_sha256=digest,
        reviewed_on=reviewed_on,
        max_age_days=max_age_days,
        status=status,
        provider=provider,
        model=model,
        service_tier=service_tier,
        input_usd_per_million=_snapshot_decimal(rates.get("input"), "AI input rate"),
        cached_input_usd_per_million=_snapshot_decimal(
            rates.get("cached_input"), "AI cached-input rate"
        ),
        cache_write_usd_per_million=_snapshot_decimal(
            rates.get("cache_write"), "AI cache-write rate"
        ),
        output_usd_per_million=_snapshot_decimal(
            rates.get("output"), "AI output rate"
        ),
        credits_per_request=_snapshot_int(
            credit_policy.get("credits_per_request"),
            "AI credits per request",
            minimum=1,
            maximum=100,
        ),
        initial_credits=_snapshot_int(
            credit_policy.get("initial_credits"),
            "AI initial credits",
            minimum=0,
            maximum=1_000_000,
        ),
        max_daily_requests_per_user=_snapshot_unlimited_request_cap(
            limits.get("max_daily_requests_per_user")
        ),
        max_preflight_cost_micro_usd_per_request=_snapshot_int(
            limits.get("max_preflight_cost_micro_usd_per_request"),
            "AI preflight request budget",
            minimum=1,
            maximum=1_000_000,
        ),
        retrospective_breaker_micro_usd_per_response=_snapshot_int(
            limits.get("retrospective_breaker_micro_usd_per_response"),
            "AI retrospective breaker",
            minimum=1,
            maximum=1_000_000,
        ),
        max_project_cost_micro_usd_per_day=_snapshot_int(
            limits.get("max_project_cost_micro_usd_per_day"),
            "AI project daily budget",
            minimum=1,
            maximum=100_000_000,
        ),
        max_project_cost_micro_usd_per_month=_snapshot_int(
            limits.get("max_project_cost_micro_usd_per_month"),
            "AI project monthly budget",
            minimum=1,
            maximum=1_000_000_000,
        ),
        max_in_flight_cost_micro_usd=_snapshot_int(
            limits.get("max_in_flight_cost_micro_usd"),
            "AI in-flight budget",
            minimum=1,
            maximum=100_000_000,
        ),
        max_provider_input_chars=_snapshot_int(
            limits.get("max_provider_input_chars"),
            "AI provider input character limit",
            minimum=1000,
            maximum=50000,
        ),
        max_output_tokens=_snapshot_int(
            limits.get("max_output_tokens"),
            "AI output token limit",
            minimum=256,
            maximum=4000,
        ),
    )
    if contract.max_project_cost_micro_usd_per_month < contract.max_project_cost_micro_usd_per_day:
        raise EconomicsSnapshotError("AI monthly budget cannot be below the daily budget")
    if contract.max_in_flight_cost_micro_usd < contract.max_preflight_cost_micro_usd_per_request:
        raise EconomicsSnapshotError("AI in-flight budget cannot be below one request budget")
    return contract
