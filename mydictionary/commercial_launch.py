"""Privacy-safe Commercial Launch v2 contract helpers."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
SENSITIVE_MEASUREMENT_KEYS = {
    "api_key",
    "charge_id",
    "credential",
    "invoice_payload",
    "prompt",
    "provider_charge_id",
    "request_id",
    "response",
    "telegram_user_id",
    "user_id",
}
EXPECTED_V2_CATALOG = {
    "ai-mini": (20, 60, "one_time"),
    "ai-starter": (50, 100, "one_time"),
    "ai-value": (150, 250, "one_time"),
    "ai-monthly": (100, 180, "subscription"),
}


class CommercialLaunchError(ValueError):
    """Raised when launch evidence is incomplete, inconsistent, or unsafe."""


def canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CommercialLaunchError(f"{name} must be an object")
    return value


def _integer(value: Any, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise CommercialLaunchError(f"{name} must be an integer >= {minimum}")
    return value


def _decimal(value: Any, name: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise CommercialLaunchError(f"{name} must be a decimal") from exc
    if not parsed.is_finite() or parsed < 0:
        raise CommercialLaunchError(f"{name} must be finite and non-negative")
    return parsed


def _reject_sensitive_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).casefold() in SENSITIVE_MEASUREMENT_KEYS:
                raise CommercialLaunchError(
                    f"AI measurement contains sensitive field: {key}"
                )
            _reject_sensitive_keys(child)
    elif isinstance(value, list):
        for child in value:
            _reject_sensitive_keys(child)


def load_measurement_report(
    reference: Mapping[str, Any], *, root: Path = PROJECT_ROOT
) -> Mapping[str, Any]:
    relative = Path(str(reference.get("report", "")))
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise CommercialLaunchError("AI measurement path escapes the repository") from exc
    expected_digest = str(reference.get("sha256", "")).strip().lower()
    if not SHA256_RE.fullmatch(expected_digest):
        raise CommercialLaunchError("AI measurement SHA-256 is invalid")
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise CommercialLaunchError("AI measurement report is missing") from exc
    if hashlib.sha256(payload).hexdigest() != expected_digest:
        raise CommercialLaunchError("AI measurement SHA-256 does not match")
    try:
        report = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CommercialLaunchError("AI measurement report is malformed") from exc
    return _mapping(report, "AI measurement report")


def validate_measurement_report(report: Mapping[str, Any]) -> dict[str, Any]:
    _reject_sensitive_keys(report)
    if report.get("schema_version") != 1:
        raise CommercialLaunchError("AI measurement schema must be version 1")
    if report.get("environment") != "production_gate2_single_call":
        raise CommercialLaunchError("AI measurement environment is invalid")
    if report.get("source") != "durable_ai_usage_metering":
        raise CommercialLaunchError("AI measurement source is invalid")
    if report.get("provider") != "openai" or report.get("model") != "gpt-5.6-luna":
        raise CommercialLaunchError("AI measurement provider/model is invalid")
    if (
        report.get("requested_service_tier") != "default"
        or report.get("returned_service_tier") != "default"
    ):
        raise CommercialLaunchError("AI measurement service tier is invalid")
    provider_attempts = _integer(
        report.get("provider_attempts"), "provider attempts", minimum=1
    )
    if provider_attempts != 1:
        raise CommercialLaunchError("AI measurement must contain one provider attempt")

    tokens = _mapping(report.get("tokens"), "AI measurement tokens")
    input_tokens = _integer(tokens.get("input"), "input tokens")
    cached_input_tokens = _integer(tokens.get("cached_input"), "cached input tokens")
    cache_write_tokens = _integer(tokens.get("cache_write"), "cache-write tokens")
    output_tokens = _integer(tokens.get("output"), "output tokens")
    total_tokens = _integer(tokens.get("total"), "total tokens", minimum=1)
    if input_tokens + output_tokens != total_tokens:
        raise CommercialLaunchError("AI measurement total token count is inconsistent")

    rates = _mapping(
        report.get("metering_rates_usd_per_million"), "AI measurement rates"
    )
    calculated_cost = (
        Decimal(input_tokens) * _decimal(rates.get("input"), "input rate")
        + Decimal(cached_input_tokens)
        * _decimal(rates.get("cached_input"), "cached-input rate")
        + Decimal(cache_write_tokens)
        * _decimal(rates.get("cache_write"), "cache-write rate")
        + Decimal(output_tokens) * _decimal(rates.get("output"), "output rate")
    )
    local_cost = _integer(
        report.get("local_cost_micro_usd"), "local cost", minimum=1
    )
    if calculated_cost != Decimal(local_cost):
        raise CommercialLaunchError("AI measurement local cost is inconsistent")
    if report.get("cost_is_estimate") is not False:
        raise CommercialLaunchError("AI measurement cost must be settled")
    latency_ms = _integer(report.get("latency_ms"), "latency", minimum=1)
    if report.get("validation_status") != "passed":
        raise CommercialLaunchError("AI measurement validation did not pass")
    if report.get("provider_status") != "completed":
        raise CommercialLaunchError("AI measurement provider response is incomplete")

    dashboard = _mapping(report.get("dashboard_charge"), "dashboard charge")
    dashboard_verified = dashboard.get("verified")
    if not isinstance(dashboard_verified, bool):
        raise CommercialLaunchError("dashboard charge verified must be boolean")
    if dashboard_verified:
        _integer(dashboard.get("micro_usd"), "dashboard charge", minimum=0)
    elif dashboard.get("micro_usd") is not None or dashboard.get("status") != "not_recorded":
        raise CommercialLaunchError("unknown dashboard charge must remain not_recorded")

    privacy = _mapping(report.get("privacy"), "AI measurement privacy")
    if not privacy or any(value is not False for value in privacy.values()):
        raise CommercialLaunchError("AI measurement privacy flags must all be false")
    return {
        "model": str(report["model"]),
        "service_tier": str(report["returned_service_tier"]),
        "provider_attempts": provider_attempts,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cost_micro_usd": local_cost,
        "latency_ms": latency_ms,
        "validation_status": str(report["validation_status"]),
        "dashboard_charge_verified": dashboard_verified,
    }


def commercial_launch_overview(
    snapshot: Mapping[str, Any],
    *,
    products: Sequence[Mapping[str, Any]],
    seller_complete: bool,
    terms_approved: bool,
    checkout_enabled: bool,
    root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    if snapshot.get("schema_version") != 3 or snapshot.get("status") != "candidate":
        raise CommercialLaunchError("Commercial launch contract is not a v3 candidate")
    stars = _mapping(snapshot.get("stars"), "Stars contract")
    ai = _mapping(snapshot.get("ai"), "AI contract")
    references = _mapping(
        ai.get("measurement"),
        "AI measurement reference",
    )
    measurement = validate_measurement_report(
        load_measurement_report(references, root=root)
    )
    expected_packages = stars.get("packages")
    if not isinstance(expected_packages, list):
        raise CommercialLaunchError("Commercial packages must be a list")
    catalog = {
        str(package.get("product_id")): (
            package.get("credits"),
            package.get("price_xtr"),
            package.get("billing_mode"),
        )
        for package in expected_packages
        if isinstance(package, Mapping)
    }
    if catalog != EXPECTED_V2_CATALOG:
        raise CommercialLaunchError("Commercial Launch v2 catalog is inconsistent")
    nominal_net = _integer(
        stars.get("assumed_net_micro_usd_per_xtr"), "nominal net XTR", minimum=1
    )
    stress_net = _integer(
        stars.get("stress_net_micro_usd_per_xtr"), "stress net XTR", minimum=1
    )
    margin_floor = _integer(
        stars.get("minimum_margin_bps"), "commercial margin floor", minimum=5000
    )
    refund_reserve_bps = _integer(
        stars.get("refund_reserve_bps"), "refund reserve"
    )
    support_overhead = _integer(
        stars.get("support_overhead_micro_usd_per_purchase"), "support overhead"
    )
    modelled_cost_per_credit = _integer(
        _mapping(ai.get("credit_policy"), "AI credit policy").get(
            "modelled_cost_micro_usd_per_credit"
        ),
        "modelled AI cost per credit",
        minimum=1,
    )
    terms_path = (root / Path(str(stars.get("terms_document", "")))).resolve()
    try:
        terms_path.relative_to(root.resolve())
        terms_text = terms_path.read_text(encoding="utf-8").strip()
    except (ValueError, OSError, UnicodeDecodeError) as exc:
        raise CommercialLaunchError("Commercial terms cannot be loaded") from exc
    terms_digest = str(stars.get("terms_sha256", "")).strip().lower()
    if (
        not SHA256_RE.fullmatch(terms_digest)
        or hashlib.sha256(terms_text.encode("utf-8")).hexdigest() != terms_digest
    ):
        raise CommercialLaunchError("Commercial terms SHA-256 does not match")
    actual = {str(row.get("product_id")): row for row in products}
    package_rows: list[dict[str, Any]] = []
    matches = 0
    for value in expected_packages:
        package = _mapping(value, "Commercial package")
        product_id = str(package.get("product_id", ""))
        credits = _integer(package.get("credits"), f"{product_id} credits", minimum=1)
        price_xtr = _integer(package.get("price_xtr"), f"{product_id} price", minimum=1)
        provider_cost = credits * modelled_cost_per_credit
        nominal_revenue = price_xtr * nominal_net
        reserve = (nominal_revenue * refund_reserve_bps + 9999) // 10000
        estimated_cost = provider_cost + reserve + support_overhead
        nominal_margin = (
            (nominal_revenue - estimated_cost) * 10000 // nominal_revenue
        )
        stress_revenue = price_xtr * stress_net
        stress_margin = (
            (stress_revenue - estimated_cost) * 10000 // stress_revenue
        )
        formula = {
            "modelled_provider_cost_micro_usd": provider_cost,
            "refund_reserve_micro_usd": reserve,
            "estimated_cost_micro_usd": estimated_cost,
            "net_revenue_micro_usd": nominal_revenue,
            "estimated_margin_bps": nominal_margin,
            "stress_margin_bps": stress_margin,
        }
        if package.get("status") != "candidate" or any(
            package.get(key) != expected for key, expected in formula.items()
        ):
            raise CommercialLaunchError(
                f"Commercial package {product_id} formula is inconsistent"
            )
        expected = {
            "credits": credits,
            "price_xtr": price_xtr,
            "billing_mode": package.get("billing_mode"),
            "subscription_period_seconds": package.get("subscription_period_seconds"),
            "estimated_cost_micro_usd": package.get("estimated_cost_micro_usd"),
            "target_margin_bps": package.get("target_margin_bps"),
            "status": "draft",
        }
        current = actual.get(product_id)
        database_ready = current is not None and all(
            current.get(key) == expected_value for key, expected_value in expected.items()
        )
        matches += int(database_ready)
        floor = _integer(package.get("target_margin_bps"), "margin floor")
        if floor < margin_floor:
            raise CommercialLaunchError(
                f"Commercial package {product_id} margin floor is too low"
            )
        package_rows.append(
            {
                "product_id": product_id,
                "credits": credits,
                "price_xtr": price_xtr,
                "nominal_margin_bps": nominal_margin,
                "stress_margin_bps": stress_margin,
                "nominal_ready": nominal_margin >= floor,
                "stress_ready": stress_margin >= floor,
                "database_ready": database_ready,
            }
        )
    catalog_status = (
        "missing" if not actual else "ready" if matches == len(package_rows) and len(actual) == matches else "drift"
    )
    contract_ready = all(row["nominal_ready"] for row in package_rows)
    ready = all(
        (
            contract_ready,
            catalog_status == "ready",
            seller_complete,
            terms_approved,
            checkout_enabled,
            measurement["dashboard_charge_verified"],
        )
    )
    return {
        "status": "ready" if ready else "blocked",
        "snapshot_id": str(snapshot.get("snapshot_id", "")),
        "snapshot_sha256": canonical_sha256(snapshot),
        "contract_ready": contract_ready,
        "catalog_status": catalog_status,
        "seller_complete": bool(seller_complete),
        "terms_approved": bool(terms_approved),
        "checkout_enabled": bool(checkout_enabled),
        "measurement": measurement,
        "packages": package_rows,
    }
