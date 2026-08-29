#!/usr/bin/env python3
"""Fail-closed readiness checks for the independent free AI pilot."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
from typing import Any, Mapping

from mydictionary.ai_tutor import (
    TutorContext,
    TutorWord,
    parse_tutor_answer,
    validate_tutor_answer,
)
from mydictionary.economics import (
    EconomicsSnapshotError,
    load_ai_economics_contract,
)


EXPECTED_MIGRATION = "0018_interface_locale"
EXPECTED_LANGUAGES = {"en", "fr", "de", "ja", "ar", "zh", "ru", "es"}
EXPECTED_RATES = {
    "AI_INPUT_USD_PER_MILLION": Decimal("0.20"),
    "AI_CACHED_INPUT_USD_PER_MILLION": Decimal("0.02"),
    "AI_CACHE_WRITE_USD_PER_MILLION": Decimal("0.25"),
    "AI_OUTPUT_USD_PER_MILLION": Decimal("1.20"),
}
CONSENT_VERSION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{7,63}")


class AIPilotReadinessError(RuntimeError):
    """Raised when any AI-only activation invariant is not satisfied."""


def _enabled(value: Any) -> bool:
    return str(value).strip().casefold() in {"1", "true", "yes", "on"}


def _load_fixture(path: Path) -> list[Mapping[str, Any]]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AIPilotReadinessError(
            "Eight-language evaluation contract cannot be loaded"
        ) from exc
    if not isinstance(payload, list) or len(payload) != 8:
        raise AIPilotReadinessError(
            "Eight-language evaluation contract must contain eight cases"
        )
    languages = {str(case.get("language", "")) for case in payload}
    if languages != EXPECTED_LANGUAGES:
        raise AIPilotReadinessError(
            "Eight-language evaluation contract has unexpected languages"
        )
    for case in payload:
        try:
            context = TutorContext(
                language=str(case["language"]),
                topic="eval",
                words=(
                    TutorWord(
                        term=str(case["term"]),
                        transcription=str(case["transcription"]),
                        meaning_ru=str(case["meaning_ru"]),
                    ),
                ),
            )
            answer = parse_tutor_answer(
                {
                    "summary_ru": case["summary_ru"],
                    "entries": [
                        {
                            "term": case["term"],
                            "explanation_ru": case["explanation_ru"],
                            "examples": case["examples"],
                        }
                    ],
                }
            )
            validate_tutor_answer(answer, context)
        except (KeyError, TypeError, ValueError) as exc:
            raise AIPilotReadinessError(
                "Eight-language evaluation contract is invalid"
            ) from exc
    return payload


def evaluate_ai_pilot_readiness(
    environment: Mapping[str, str],
    *,
    runtime_state: Mapping[str, Any],
    database_revision: str,
    fixture_path: Path,
    today: date | None = None,
) -> dict[str, Any]:
    """Evaluate, but never mutate, the AI-only pilot activation contract."""
    env = dict(environment)
    checks: dict[str, bool] = {}
    try:
        if not _enabled(env.get("AI_TUTOR_ENABLED")):
            raise AIPilotReadinessError("AI tutor activation flag is not enabled")
        contract = load_ai_economics_contract(
            env.get("AI_ECONOMICS_SNAPSHOT_PATH", ""),
            expected_snapshot_id=env.get("AI_ECONOMICS_SNAPSHOT_ID"),
            expected_snapshot_sha256=env.get("AI_ECONOMICS_SNAPSHOT_SHA256"),
            require_approved=True,
        ).assert_current(today=today)
        expected_contract = {
            "reviewed_on": "2026-08-28",
            "max_age_days": 30,
            "initial_credits": 40,
            "credits_per_request": 1,
            "max_daily_requests_per_user": None,
            "max_preflight_cost_micro_usd_per_request": 5000,
            "retrospective_breaker_micro_usd_per_response": 5000,
            "max_project_cost_micro_usd_per_day": 25000,
            "max_project_cost_micro_usd_per_month": 100000,
            "max_in_flight_cost_micro_usd": 5000,
            "max_provider_input_chars": 12000,
            "max_output_tokens": 1000,
        }
        if any(
            getattr(contract, name) != value
            for name, value in expected_contract.items()
        ):
            raise AIPilotReadinessError(
                "AI economics snapshot differs from the pilot approval"
            )
        expected_environment = {
            "AI_PRICING_REVIEWED_ON": contract.reviewed_on,
            "AI_PRICING_MAX_AGE_DAYS": str(contract.max_age_days),
            "AI_INITIAL_CREDITS": str(contract.initial_credits),
            "AI_CREDITS_PER_REQUEST": str(contract.credits_per_request),
            "AI_MAX_DAILY_REQUESTS_PER_USER": "0",
            "AI_MAX_PREFLIGHT_COST_MICRO_USD_PER_REQUEST": str(
                contract.max_preflight_cost_micro_usd_per_request
            ),
            "AI_RETROSPECTIVE_BREAKER_MICRO_USD_PER_RESPONSE": str(
                contract.retrospective_breaker_micro_usd_per_response
            ),
            "AI_MAX_PROJECT_COST_MICRO_USD_PER_DAY": str(
                contract.max_project_cost_micro_usd_per_day
            ),
            "AI_MAX_PROJECT_COST_MICRO_USD_PER_MONTH": str(
                contract.max_project_cost_micro_usd_per_month
            ),
            "AI_MAX_IN_FLIGHT_COST_MICRO_USD": str(
                contract.max_in_flight_cost_micro_usd
            ),
        }
        if any(env.get(name) != value for name, value in expected_environment.items()):
            raise AIPilotReadinessError(
                "AI runtime economics differ from the approved snapshot"
            )
        checks["economics"] = True

        if (
            env.get("AI_PROVIDER") != contract.provider
            or env.get("AI_MODEL") != contract.model
            or env.get("AI_SERVICE_TIER") != contract.service_tier
            or env.get("AI_SDK_MAX_RETRIES") != "0"
            or not env.get("OPENAI_API_KEY")
            or len(env.get("AI_SAFETY_SALT", "")) < 16
        ):
            raise AIPilotReadinessError("AI model or service tier is not approved")
        checks["model_and_tier"] = True

        contract_rates = {
            "AI_INPUT_USD_PER_MILLION": contract.input_usd_per_million,
            "AI_CACHED_INPUT_USD_PER_MILLION": (
                contract.cached_input_usd_per_million
            ),
            "AI_CACHE_WRITE_USD_PER_MILLION": (
                contract.cache_write_usd_per_million
            ),
            "AI_OUTPUT_USD_PER_MILLION": contract.output_usd_per_million,
        }
        for name, expected in EXPECTED_RATES.items():
            try:
                configured = Decimal(str(env.get(name, "")))
            except InvalidOperation as exc:
                raise AIPilotReadinessError("AI rates are invalid") from exc
            if configured != expected or contract_rates[name] != expected:
                raise AIPilotReadinessError("AI rates differ from approval")
        checks["rates"] = True

        version = str(env.get("AI_CONSENT_VERSION", "")).strip()
        notice = str(env.get("AI_PROCESSING_NOTICE", "")).strip()
        if (
            not CONSENT_VERSION_RE.fullmatch(version)
            or version.casefold() in {"current", "latest"}
            or not 40 <= len(notice) <= 1000
        ):
            raise AIPilotReadinessError("AI consent configuration is invalid")
        checks["consent"] = True

        if database_revision != EXPECTED_MIGRATION:
            raise AIPilotReadinessError("AI consent migration is not current")
        checks["migration"] = True

        cases = _load_fixture(Path(fixture_path))
        checks["eight_language_contract"] = True

        if runtime_state.get("circuit_breaker_open") is not False:
            raise AIPilotReadinessError("AI circuit breaker is open")
        checks["circuit_breaker"] = True
        if int(runtime_state.get("in_flight_micro_usd", -1)) != 0:
            raise AIPilotReadinessError("AI in-flight exposure is not zero")
        checks["in_flight"] = True
        if int(runtime_state.get("fallback_journal_entries", -1)) != 0:
            raise AIPilotReadinessError("AI fallback journal is not empty")
        checks["fallback_journal"] = True
    except (EconomicsSnapshotError, OSError, TypeError, ValueError) as exc:
        if isinstance(exc, AIPilotReadinessError):
            raise
        raise AIPilotReadinessError("AI pilot readiness check failed") from exc

    return {
        "ready": True,
        "checks": checks,
        "migration_revision": database_revision,
        "evaluation_languages": len(cases),
        "voice_status": (
            "enabled" if _enabled(env.get("VOICE_TUTOR_ENABLED")) else "disabled"
        ),
        "stars_status": (
            "enabled"
            if _enabled(env.get("TELEGRAM_STARS_ENABLED"))
            else "disabled"
        ),
    }
