"""Shared fail-closed helpers for dated commercial assumptions."""

from __future__ import annotations

from datetime import date, datetime, timezone


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
