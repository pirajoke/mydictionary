#!/usr/bin/env python3
"""Validate and render the disabled AI/Stars commercial contract."""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mydictionary.commercial_launch import (
    CommercialLaunchError,
    load_measurement_report,
    validate_measurement_report,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT = ROOT / "config" / "launch-economics.json"
ALLOWED_SOURCE_HOSTS = {
    "core.telegram.org",
    "developers.openai.com",
    "europa.eu",
    "telegram.org",
    "www.economie.gouv.fr",
}
EXPECTED_AI_PRICING = {
    "input": Decimal("0.20"),
    "cached_input": Decimal("0.02"),
    "cache_write": Decimal("0.25"),
    "output": Decimal("1.20"),
}
CONSERVATIVE_STAR_NET_MICRO_USD = 10_000
PRODUCT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{2,59}$")
TERMS_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class EconomicsContractError(RuntimeError):
    """Raised when the versioned economics snapshot is unsafe or inconsistent."""


def _snapshot_sha256(snapshot: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _object(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EconomicsContractError(f"{name} must be an object")
    return value


def _integer(value: Any, name: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EconomicsContractError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise EconomicsContractError(
            f"{name} must be between {minimum} and {maximum}"
        )
    return value


def _decimal(value: Any, name: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise EconomicsContractError(f"{name} must be decimal") from exc
    if not parsed.is_finite() or parsed < 0:
        raise EconomicsContractError(f"{name} must be finite and non-negative")
    return parsed


def load_snapshot(path: Path = DEFAULT_SNAPSHOT) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EconomicsContractError(f"Cannot read economics snapshot: {exc}") from exc
    return _object(payload, "snapshot")


def validate_snapshot(
    snapshot: Mapping[str, Any], *, root: Path = ROOT
) -> dict[str, int | str]:
    if snapshot.get("schema_version") != 3:
        raise EconomicsContractError("Unsupported economics schema_version")
    if snapshot.get("status") != "candidate":
        raise EconomicsContractError("Economics snapshot must remain candidate")
    reviewed_on = str(snapshot.get("reviewed_on", ""))
    try:
        from datetime import date

        parsed_review_date = date.fromisoformat(reviewed_on)
    except ValueError as exc:
        raise EconomicsContractError("reviewed_on must use YYYY-MM-DD") from exc
    if parsed_review_date > date.today():
        raise EconomicsContractError("reviewed_on cannot be in the future")
    max_age_days = _integer(
        snapshot.get("max_age_days"),
        "max_age_days",
        minimum=1,
        maximum=90,
    )

    sources = snapshot.get("sources")
    if not isinstance(sources, list) or len(sources) < 4:
        raise EconomicsContractError("At least four official sources are required")
    for source in sources:
        parsed = urlparse(str(source))
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_SOURCE_HOSTS:
            raise EconomicsContractError(f"Unapproved economics source: {source}")

    ai = _object(snapshot.get("ai"), "ai")
    if ai.get("status") not in {"draft", "approved"}:
        raise EconomicsContractError("AI economics status must be draft or approved")
    if ai.get("provider") != "openai" or ai.get("model") != "gpt-5.6-luna":
        raise EconomicsContractError("AI provider/model does not match the review")
    if ai.get("service_tier") != "default":
        raise EconomicsContractError("AI pricing is reviewed only for default tier")
    rates = _object(
        ai.get("short_context_usd_per_million"), "AI short-context pricing"
    )
    for key, expected in EXPECTED_AI_PRICING.items():
        if _decimal(rates.get(key), f"AI price {key}") != expected:
            raise EconomicsContractError(f"AI price {key} differs from snapshot")
    long_context = _object(ai.get("long_context"), "AI long_context")
    if long_context.get("threshold_input_tokens") != 272000:
        raise EconomicsContractError("AI long-context threshold is inconsistent")
    if _decimal(long_context.get("input_multiplier"), "input multiplier") != 2:
        raise EconomicsContractError("AI long-context input multiplier is inconsistent")
    if _decimal(long_context.get("output_multiplier"), "output multiplier") != Decimal(
        "1.5"
    ):
        raise EconomicsContractError("AI long-context output multiplier is inconsistent")

    credit_policy = _object(ai.get("credit_policy"), "AI credit_policy")
    credits_per_request = _integer(
        credit_policy.get("credits_per_request"),
        "credits_per_request",
        minimum=1,
        maximum=100,
    )
    _integer(
        credit_policy.get("initial_credits"),
        "initial_credits",
        minimum=0,
        maximum=1_000_000,
    )
    limits = _object(ai.get("limits"), "AI limits")
    daily_limit = _integer(
        limits.get("max_daily_requests_per_user"),
        "AI daily limit",
        minimum=1,
        maximum=100,
    )
    preflight_budget = _integer(
        limits.get("max_preflight_cost_micro_usd_per_request"),
        "AI preflight request budget",
        minimum=1,
        maximum=1_000_000,
    )
    retrospective_breaker = _integer(
        limits.get("retrospective_breaker_micro_usd_per_response"),
        "AI retrospective response breaker",
        minimum=1,
        maximum=1_000_000,
    )
    project_daily_budget = _integer(
        limits.get("max_project_cost_micro_usd_per_day"),
        "AI project daily budget",
        minimum=1,
        maximum=100_000_000,
    )
    project_monthly_budget = _integer(
        limits.get("max_project_cost_micro_usd_per_month"),
        "AI project monthly budget",
        minimum=1,
        maximum=1_000_000_000,
    )
    in_flight_budget = _integer(
        limits.get("max_in_flight_cost_micro_usd"),
        "AI in-flight budget",
        minimum=1,
        maximum=100_000_000,
    )
    if project_monthly_budget < project_daily_budget:
        raise EconomicsContractError("AI monthly budget cannot be below daily budget")
    if in_flight_budget < preflight_budget:
        raise EconomicsContractError(
            "AI in-flight budget cannot be below one preflight request budget"
        )
    input_chars = _integer(
        limits.get("max_provider_input_chars"),
        "AI input character limit",
        minimum=1000,
        maximum=50000,
    )
    output_tokens = _integer(
        limits.get("max_output_tokens"),
        "AI output token limit",
        minimum=256,
        maximum=4000,
    )
    try:
        measurement = validate_measurement_report(
            load_measurement_report(
                _object(ai.get("measurement"), "AI measurement"), root=root
            )
        )
    except CommercialLaunchError as exc:
        raise EconomicsContractError(f"Invalid AI measurement: {exc}") from exc
    if measurement["model"] != ai["model"]:
        raise EconomicsContractError("AI measurement model differs from snapshot")
    if measurement["service_tier"] != ai["service_tier"]:
        raise EconomicsContractError("AI measurement tier differs from snapshot")

    stars = _object(snapshot.get("stars"), "stars")
    if stars.get("status") != "candidate" or stars.get("currency") != "XTR":
        raise EconomicsContractError(
            "Stars economics must remain candidate and XTR-only"
        )
    reward = _integer(
        stars.get("reward_micro_usd_per_xtr"),
        "Star reward",
        minimum=1,
        maximum=13000,
    )
    topics_enabled = stars.get("private_chat_topics_enabled")
    if not isinstance(topics_enabled, bool):
        raise EconomicsContractError("private_chat_topics_enabled must be boolean")
    expected_topics_fee = 1500 if topics_enabled else 0
    if stars.get("private_chat_topics_fee_bps") != expected_topics_fee:
        raise EconomicsContractError("Private-chat topics fee assumption is inconsistent")
    maximum_reward_after_topics = (
        reward * (10000 - expected_topics_fee) // 10000
    )
    conservative_net_after_topics = (
        CONSERVATIVE_STAR_NET_MICRO_USD
        * (10000 - expected_topics_fee)
        // 10000
    )
    net_per_xtr = _integer(
        stars.get("assumed_net_micro_usd_per_xtr"),
        "assumed net Star value",
        minimum=1,
        maximum=min(maximum_reward_after_topics, conservative_net_after_topics),
    )
    refund_reserve_bps = _integer(
        stars.get("refund_reserve_bps"),
        "refund reserve",
        minimum=0,
        maximum=5000,
    )
    support_overhead = _integer(
        stars.get("support_overhead_micro_usd_per_purchase"),
        "support overhead",
        minimum=0,
        maximum=10_000_000,
    )
    minimum_margin_bps = _integer(
        stars.get("minimum_margin_bps"),
        "minimum commercial margin",
        minimum=5000,
        maximum=9000,
    )
    stress_net_per_xtr = _integer(
        stars.get("stress_net_micro_usd_per_xtr"),
        "stress net Star value",
        minimum=1,
        maximum=net_per_xtr,
    )
    if stress_net_per_xtr >= net_per_xtr:
        raise EconomicsContractError(
            "Stress net Star value must be below the nominal assumption"
        )
    _integer(
        stars.get("funds_availability_delay_days"),
        "Stars availability delay",
        minimum=1,
        maximum=365,
    )
    _integer(
        stars.get("earned_stars_expiry_years"),
        "Stars expiry years",
        minimum=1,
        maximum=10,
    )

    terms_version = str(stars.get("terms_version", ""))
    if not TERMS_VERSION_RE.fullmatch(terms_version):
        raise EconomicsContractError("Draft terms version is invalid")
    terms_relative = Path(str(stars.get("terms_document", "")))
    terms_path = (root / terms_relative).resolve()
    try:
        terms_path.relative_to(root.resolve())
    except ValueError as exc:
        raise EconomicsContractError("Terms document escapes the repository") from exc
    try:
        terms_payload = terms_path.read_bytes()
        terms_text = terms_payload.decode("utf-8").strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise EconomicsContractError("Draft terms document is missing") from exc
    terms_digest = str(stars.get("terms_sha256", "")).strip().lower()
    if (
        not re.fullmatch(r"[a-f0-9]{64}", terms_digest)
        or hashlib.sha256(terms_text.encode("utf-8")).hexdigest() != terms_digest
    ):
        raise EconomicsContractError("Candidate terms SHA-256 does not match")
    if not 1 <= len(terms_text) <= 3500:
        raise EconomicsContractError("Draft terms must contain 1-3500 characters")
    for required_text in (
        "кандидат",
        "/paysupport",
        "полный возврат",
        "XTR",
        "начать оказание",
        "право на отказ",
        "юридическое имя продавца",
    ):
        if required_text.casefold() not in terms_text.casefold():
            raise EconomicsContractError(
                f"Draft terms are missing required language: {required_text}"
            )

    packages = stars.get("packages")
    if not isinstance(packages, list) or not packages:
        raise EconomicsContractError("At least one candidate Stars package is required")
    product_ids: set[str] = set()
    for package_value in packages:
        package = _object(package_value, "Stars package")
        product_id = str(package.get("product_id", ""))
        if not PRODUCT_ID_RE.fullmatch(product_id) or product_id in product_ids:
            raise EconomicsContractError("Stars package product_id is invalid or duplicate")
        product_ids.add(product_id)
        if package.get("status") != "candidate":
            raise EconomicsContractError(f"Package {product_id} must remain candidate")
        title = str(package.get("title", "")).strip()
        description = str(package.get("description", "")).strip()
        if not 1 <= len(title) <= 32 or not 1 <= len(description) <= 255:
            raise EconomicsContractError(
                f"Package {product_id} title/description is invalid"
            )
        billing_mode = package.get("billing_mode")
        if billing_mode not in {"one_time", "subscription"}:
            raise EconomicsContractError(f"Package {product_id} billing_mode is invalid")
        if billing_mode == "subscription" and package.get(
            "subscription_period_seconds"
        ) != 2592000:
            raise EconomicsContractError(
                f"Package {product_id} subscription period must be 30 days"
            )
        credits = _integer(
            package.get("credits"),
            f"{product_id} credits",
            minimum=1,
            maximum=1_000_000,
        )
        price_xtr = _integer(
            package.get("price_xtr"),
            f"{product_id} price",
            minimum=1,
            maximum=1_000_000,
        )
        net_revenue = price_xtr * net_per_xtr
        provider_cost = credits * preflight_budget
        reserve = (net_revenue * refund_reserve_bps + 9999) // 10000
        estimated_cost = provider_cost + reserve + support_overhead
        margin_bps = (net_revenue - estimated_cost) * 10000 // net_revenue
        expected_values = {
            "modelled_provider_cost_micro_usd": provider_cost,
            "refund_reserve_micro_usd": reserve,
            "estimated_cost_micro_usd": estimated_cost,
            "net_revenue_micro_usd": net_revenue,
            "estimated_margin_bps": margin_bps,
        }
        stress_revenue = price_xtr * stress_net_per_xtr
        stress_margin_bps = (
            (stress_revenue - estimated_cost) * 10000 // stress_revenue
        )
        expected_values["stress_margin_bps"] = stress_margin_bps
        for key, expected in expected_values.items():
            if package.get(key) != expected:
                raise EconomicsContractError(
                    f"Package {product_id} has inconsistent {key}"
                )
        target_margin = _integer(
            package.get("target_margin_bps"),
            f"{product_id} target margin",
            minimum=0,
            maximum=9999,
        )
        if target_margin < minimum_margin_bps:
            raise EconomicsContractError(
                f"Package {product_id} margin floor is below commercial policy"
            )
        if margin_bps < target_margin:
            raise EconomicsContractError(
                f"Package {product_id} is below its target margin"
            )

    stress_launchable = all(
        int(_object(value, "Stars package")["stress_margin_bps"])
        >= int(_object(value, "Stars package")["target_margin_bps"])
        for value in packages
    )
    return {
        "snapshot_id": str(snapshot.get("snapshot_id", "")),
        "snapshot_sha256": _snapshot_sha256(snapshot),
        "packages": len(packages),
        "credits_per_request": credits_per_request,
        "initial_credits": credit_policy["initial_credits"],
        "daily_limit": daily_limit,
        "input_chars": input_chars,
        "output_tokens": output_tokens,
        "preflight_budget": preflight_budget,
        "retrospective_breaker": retrospective_breaker,
        "project_daily_budget": project_daily_budget,
        "project_monthly_budget": project_monthly_budget,
        "in_flight_budget": in_flight_budget,
        "net_micro_usd_per_xtr": net_per_xtr,
        "max_age_days": max_age_days,
        "pricing_max_age_days": max_age_days,
        "minimum_margin_bps": minimum_margin_bps,
        "stress_net_micro_usd_per_xtr": stress_net_per_xtr,
        "stress_launchable": stress_launchable,
        "measurement_provider_attempts": measurement["provider_attempts"],
        "measurement_cost_micro_usd": measurement["cost_micro_usd"],
        "measurement_dashboard_charge_verified": measurement[
            "dashboard_charge_verified"
        ],
    }


def render_environment(snapshot: Mapping[str, Any]) -> str:
    validated = validate_snapshot(snapshot)
    ai = _object(snapshot["ai"], "ai")
    rates = _object(ai["short_context_usd_per_million"], "rates")
    credit_policy = _object(ai["credit_policy"], "credit policy")
    limits = _object(ai["limits"], "limits")
    stars = _object(snapshot["stars"], "stars")
    values = {
        "AI_TUTOR_ENABLED": "false",
        "AI_PROVIDER": ai["provider"],
        "AI_MODEL": ai["model"],
        "AI_SERVICE_TIER": ai["service_tier"],
        "AI_ECONOMICS_SNAPSHOT_PATH": "config/launch-economics.json",
        "AI_ECONOMICS_SNAPSHOT_ID": snapshot["snapshot_id"],
        "AI_ECONOMICS_SNAPSHOT_SHA256": validated["snapshot_sha256"],
        "AI_INITIAL_CREDITS": credit_policy["initial_credits"],
        "AI_CREDITS_PER_REQUEST": credit_policy["credits_per_request"],
        "AI_INPUT_USD_PER_MILLION": rates["input"],
        "AI_CACHED_INPUT_USD_PER_MILLION": rates["cached_input"],
        "AI_CACHE_WRITE_USD_PER_MILLION": rates["cache_write"],
        "AI_OUTPUT_USD_PER_MILLION": rates["output"],
        "AI_PRICING_REVIEWED_ON": snapshot["reviewed_on"],
        "AI_PRICING_MAX_AGE_DAYS": snapshot["max_age_days"],
        "AI_MAX_DAILY_REQUESTS_PER_USER": limits["max_daily_requests_per_user"],
        "AI_MAX_PREFLIGHT_COST_MICRO_USD_PER_REQUEST": limits[
            "max_preflight_cost_micro_usd_per_request"
        ],
        "AI_RETROSPECTIVE_BREAKER_MICRO_USD_PER_RESPONSE": limits[
            "retrospective_breaker_micro_usd_per_response"
        ],
        "AI_MAX_PROJECT_COST_MICRO_USD_PER_DAY": limits[
            "max_project_cost_micro_usd_per_day"
        ],
        "AI_MAX_PROJECT_COST_MICRO_USD_PER_MONTH": limits[
            "max_project_cost_micro_usd_per_month"
        ],
        "AI_MAX_IN_FLIGHT_COST_MICRO_USD": limits[
            "max_in_flight_cost_micro_usd"
        ],
        "AI_MAX_PROVIDER_INPUT_CHARS": limits["max_provider_input_chars"],
        "AI_MAX_OUTPUT_TOKENS": limits["max_output_tokens"],
        "AI_SDK_MAX_RETRIES": "0",
        "VOICE_TUTOR_ENABLED": "false",
        "TELEGRAM_STARS_ENABLED": "false",
        "BILLING_NET_MICRO_USD_PER_XTR": validated["net_micro_usd_per_xtr"],
        "BILLING_ECONOMICS_REVIEWED_ON": snapshot["reviewed_on"],
        "BILLING_ECONOMICS_MAX_AGE_DAYS": snapshot["max_age_days"],
        "BILLING_PRIVATE_CHAT_TOPICS_ENABLED": str(
            stars["private_chat_topics_enabled"]
        ).lower(),
        "BILLING_TERMS_VERSION": stars["terms_version"],
        "BILLING_TERMS_SHA256": stars["terms_sha256"],
        "BILLING_TERMS_APPROVED": "false",
    }
    return "\n".join(f"{key}={value}" for key, value in values.items())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true")
    action.add_argument("--render-env", action="store_true")
    args = parser.parse_args()
    try:
        snapshot = load_snapshot(args.snapshot)
        if args.render_env:
            print(render_environment(snapshot))
        else:
            result = validate_snapshot(snapshot)
            print(json.dumps({"ok": True, **result}, sort_keys=True))
    except EconomicsContractError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
