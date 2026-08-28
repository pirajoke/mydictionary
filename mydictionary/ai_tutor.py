"""Block-scoped AI tutor with provider-neutral metering contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_CEILING
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
from time import perf_counter
from typing import Any, Mapping, Protocol
from uuid import uuid4

from .ai_metering import AIMeteringJournal
from .economics import (
    AIEconomicsContract,
    EconomicsSnapshotError,
    load_ai_economics_contract,
    parse_reviewed_on,
    require_current_review,
)
from .localization import response_language_instruction
from .mirror_assistant import (
    MIRROR_COMPACT_REPLY_POLICY,
    MIRROR_SAFETY_ENVELOPE,
    MIRROR_STYLE_GUIDANCE,
    is_mirror_continuation,
    normalize_companion_learner_context,
    normalize_mirror_dialogue,
)
from .prompt_contracts import load_prompt_contract
from .storage import AIQuotaExceeded, DatabaseStore


TUTOR_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary_ru": {"type": "string", "minLength": 1, "maxLength": 700},
        "entries": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "term": {"type": "string", "minLength": 1, "maxLength": 120},
                    "explanation_ru": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 500,
                    },
                    "examples": {
                        "type": "array",
                        "minItems": 2,
                        "maxItems": 2,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "target": {
                                    "type": "string",
                                    "minLength": 1,
                                    "maxLength": 240,
                                },
                                "russian": {
                                    "type": "string",
                                    "minLength": 1,
                                    "maxLength": 240,
                                },
                            },
                            "required": ["target", "russian"],
                        },
                    },
                },
                "required": ["term", "explanation_ru", "examples"],
            },
        },
    },
    "required": ["summary_ru", "entries"],
}

MIRROR_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "answer_ru": {"type": "string", "minLength": 1, "maxLength": 1800},
        "evidence_ru": {
            "type": "array",
            "minItems": 0,
            "maxItems": 5,
            "items": {"type": "string", "minLength": 1, "maxLength": 300},
        },
        "interpretation_ru": {"type": "string", "maxLength": 800},
        "language_items": {
            "type": "array",
            "minItems": 0,
            "maxItems": 3,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "target": {"type": "string", "minLength": 1, "maxLength": 240},
                    "transcription": {"type": "string", "maxLength": 160},
                    "meaning_ru": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 400,
                    },
                    "note_ru": {"type": "string", "maxLength": 400},
                },
                "required": ["target", "transcription", "meaning_ru", "note_ru"],
            },
        },
        "examples": {
            "type": "array",
            "minItems": 0,
            "maxItems": 3,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "target": {"type": "string", "minLength": 1, "maxLength": 240},
                    "transcription": {"type": "string", "maxLength": 160},
                    "russian": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 240,
                    },
                },
                "required": ["target", "transcription", "russian"],
            },
        },
        "next_step_ru": {"type": "string", "maxLength": 500},
    },
    "required": [
        "answer_ru",
        "evidence_ru",
        "interpretation_ru",
        "language_items",
        "examples",
        "next_step_ru",
    ],
}

_PROMPT_ROOT = Path(__file__).resolve().parents[1] / "prompts"
TUTOR_INSTRUCTIONS = load_prompt_contract(_PROMPT_ROOT / "ai-tutor-v1.txt")
MIRROR_INSTRUCTIONS = load_prompt_contract(_PROMPT_ROOT / "mirror-v4.txt")


class AIConfigurationError(RuntimeError):
    """Raised when an enabled provider is missing safe runtime configuration."""


class AIProviderError(RuntimeError):
    """Raised when a provider response cannot be used safely."""


class AIUsageRecoveryError(RuntimeError):
    """Raised when a failed request's credit reservation cannot be released."""


@dataclass(frozen=True)
class TutorWord:
    term: str
    transcription: str
    meaning_ru: str
    example_target: str | None = None


@dataclass(frozen=True)
class TutorContext:
    language: str
    topic: str | None
    words: tuple[TutorWord, ...]


@dataclass(frozen=True)
class TutorExample:
    target: str
    russian: str


@dataclass(frozen=True)
class TutorEntry:
    term: str
    explanation_ru: str
    examples: tuple[TutorExample, TutorExample]


@dataclass(frozen=True)
class TutorAnswer:
    summary_ru: str
    entries: tuple[TutorEntry, ...]


@dataclass(frozen=True)
class MirrorLanguageItem:
    target: str
    transcription: str
    meaning_ru: str
    note_ru: str


@dataclass(frozen=True)
class MirrorExample:
    target: str
    transcription: str
    russian: str


@dataclass(frozen=True)
class MirrorAnswer:
    answer_ru: str
    language_items: tuple[MirrorLanguageItem, ...]
    examples: tuple[MirrorExample, ...]
    next_step_ru: str
    evidence_ru: tuple[str, ...] = ()
    interpretation_ru: str = ""


class MirrorRenderedResponse(str):
    """Rendered text carrying only a metering request identifier."""

    request_id: str

    def __new__(cls, value: str, *, request_id: str):
        instance = super().__new__(cls, value)
        instance.request_id = str(request_id)
        return instance


@dataclass(frozen=True)
class ProviderUsage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            field: max(0, int(getattr(self, field)))
            for field in self.__dataclass_fields__
        }


@dataclass(frozen=True)
class ProviderResult:
    answer: TutorAnswer | None
    response_id: str | None
    model: str
    usage: ProviderUsage
    service_tier: str = "default"
    status: str = "completed"
    output_text: str = ""


@dataclass(frozen=True)
class TutorRequest:
    request_id: str
    user_id: int
    question: str
    context: TutorContext


@dataclass(frozen=True)
class TutorResult:
    answer: TutorAnswer
    context: TutorContext
    usage: ProviderUsage
    allowance: Mapping[str, int]


class AIProvider(Protocol):
    async def generate(self, request: TutorRequest) -> ProviderResult: ...


def _env_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise AIConfigurationError("AI_TUTOR_ENABLED must be true or false")


def _non_negative_decimal(value: str, name: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except Exception as exc:
        raise AIConfigurationError(f"{name} must be a decimal number") from exc
    if not parsed.is_finite() or parsed < 0:
        raise AIConfigurationError(f"{name} must be finite and non-negative")
    return parsed


@dataclass(frozen=True)
class ModelPricing:
    input_usd_per_million: Decimal = Decimal("0")
    cached_input_usd_per_million: Decimal = Decimal("0")
    cache_write_usd_per_million: Decimal = Decimal("0")
    output_usd_per_million: Decimal = Decimal("0")

    def cost_micro_usd(self, usage: ProviderUsage) -> int:
        values = usage.as_dict()
        uncached = max(
            0,
            values["input_tokens"]
            - values["cached_input_tokens"]
            - values["cache_write_tokens"],
        )
        cost = (
            Decimal(uncached) * self.input_usd_per_million
            + Decimal(values["cached_input_tokens"])
            * self.cached_input_usd_per_million
            + Decimal(values["cache_write_tokens"])
            * self.cache_write_usd_per_million
            + Decimal(values["output_tokens"]) * self.output_usd_per_million
        )
        return int(cost.to_integral_value(rounding=ROUND_CEILING))

    def worst_case_cost_micro_usd(
        self,
        *,
        input_tokens: int,
        output_tokens: int,
    ) -> int:
        input_rate = max(
            self.input_usd_per_million,
            self.cache_write_usd_per_million,
        )
        cost = (
            Decimal(max(0, int(input_tokens))) * input_rate
            + Decimal(max(0, int(output_tokens)))
            * self.output_usd_per_million
        )
        return int(cost.to_integral_value(rounding=ROUND_CEILING))


@dataclass(frozen=True)
class AITutorSettings:
    enabled: bool
    provider: str
    model: str
    service_tier: str
    initial_credits: int
    credits_per_request: int
    openai_api_key: str | None
    safety_salt: str | None
    pricing: ModelPricing
    reservation_timeout_seconds: int = 300
    pricing_reviewed_on: str | None = None
    pricing_max_age_days: int = 30
    max_daily_requests_per_user: int | None = None
    max_preflight_cost_micro_usd_per_request: int = 5000
    retrospective_breaker_micro_usd_per_response: int = 5000
    max_project_cost_micro_usd_per_day: int = 25000
    max_project_cost_micro_usd_per_month: int = 100000
    max_in_flight_cost_micro_usd: int = 5000
    max_provider_input_chars: int = 12000
    max_output_tokens: int = 1000
    economics_contract: AIEconomicsContract | None = None
    metering_journal_path: str | None = None
    consent_version: str | None = None
    processing_notice: str | None = None

    def assert_runtime_ready(
        self, *, today: date | None = None
    ) -> AIEconomicsContract:
        if not self.enabled:
            raise AIConfigurationError("AI tutor feature is disabled")
        if (
            self.provider != "openai"
            or not self.openai_api_key
            or not self.safety_salt
            or len(self.safety_salt) < 16
        ):
            raise AIConfigurationError(
                "Enabled AI tutor requires the OpenAI provider, API key, and salt"
            )
        if self.economics_contract is None:
            raise AIConfigurationError(
                "Enabled AI tutor requires an approved economics snapshot"
            )
        try:
            contract = self.economics_contract.assert_current(today=today)
        except (EconomicsSnapshotError, ValueError) as exc:
            raise AIConfigurationError(str(exc)) from exc
        expected = {
            "provider": self.provider,
            "model": self.model,
            "service_tier": self.service_tier,
            "initial_credits": self.initial_credits,
            "credits_per_request": self.credits_per_request,
            "pricing_reviewed_on": self.pricing_reviewed_on,
            "pricing_max_age_days": self.pricing_max_age_days,
            "max_daily_requests_per_user": self.max_daily_requests_per_user,
            "max_preflight_cost_micro_usd_per_request": (
                self.max_preflight_cost_micro_usd_per_request
            ),
            "retrospective_breaker_micro_usd_per_response": (
                self.retrospective_breaker_micro_usd_per_response
            ),
            "max_project_cost_micro_usd_per_day": (
                self.max_project_cost_micro_usd_per_day
            ),
            "max_project_cost_micro_usd_per_month": (
                self.max_project_cost_micro_usd_per_month
            ),
            "max_in_flight_cost_micro_usd": self.max_in_flight_cost_micro_usd,
            "max_provider_input_chars": self.max_provider_input_chars,
            "max_output_tokens": self.max_output_tokens,
        }
        actual = {
            "provider": contract.provider,
            "model": contract.model,
            "service_tier": contract.service_tier,
            "initial_credits": contract.initial_credits,
            "credits_per_request": contract.credits_per_request,
            "pricing_reviewed_on": contract.reviewed_on,
            "pricing_max_age_days": contract.max_age_days,
            "max_daily_requests_per_user": contract.max_daily_requests_per_user,
            "max_preflight_cost_micro_usd_per_request": (
                contract.max_preflight_cost_micro_usd_per_request
            ),
            "retrospective_breaker_micro_usd_per_response": (
                contract.retrospective_breaker_micro_usd_per_response
            ),
            "max_project_cost_micro_usd_per_day": (
                contract.max_project_cost_micro_usd_per_day
            ),
            "max_project_cost_micro_usd_per_month": (
                contract.max_project_cost_micro_usd_per_month
            ),
            "max_in_flight_cost_micro_usd": contract.max_in_flight_cost_micro_usd,
            "max_provider_input_chars": contract.max_provider_input_chars,
            "max_output_tokens": contract.max_output_tokens,
        }
        if expected != actual:
            raise AIConfigurationError(
                "AI runtime settings drift from the approved economics snapshot"
            )
        contract_pricing = (
            contract.input_usd_per_million,
            contract.cached_input_usd_per_million,
            contract.cache_write_usd_per_million,
            contract.output_usd_per_million,
        )
        runtime_pricing = (
            self.pricing.input_usd_per_million,
            self.pricing.cached_input_usd_per_million,
            self.pricing.cache_write_usd_per_million,
            self.pricing.output_usd_per_million,
        )
        if runtime_pricing != contract_pricing:
            raise AIConfigurationError(
                "AI runtime pricing drifts from the approved economics snapshot"
            )
        return contract

    @classmethod
    def from_env(cls, values: Mapping[str, str] | None = None) -> "AITutorSettings":
        env = values if values is not None else os.environ
        enabled = _env_bool(env.get("AI_TUTOR_ENABLED", "false"))
        provider = env.get("AI_PROVIDER", "openai").strip().lower()
        if provider != "openai":
            raise AIConfigurationError("AI_PROVIDER must be 'openai'")
        service_tier = env.get("AI_SERVICE_TIER", "default").strip().lower()
        if service_tier != "default":
            raise AIConfigurationError("AI_SERVICE_TIER must be 'default'")
        try:
            initial_credits = int(env.get("AI_INITIAL_CREDITS", "0"))
            credits_per_request = int(env.get("AI_CREDITS_PER_REQUEST", "1"))
            pricing_max_age_days = int(
                env.get("AI_PRICING_MAX_AGE_DAYS", "30")
            )
            max_preflight_cost_micro_usd_per_request = int(
                env.get("AI_MAX_PREFLIGHT_COST_MICRO_USD_PER_REQUEST", "5000")
            )
            retrospective_breaker_micro_usd_per_response = int(
                env.get(
                    "AI_RETROSPECTIVE_BREAKER_MICRO_USD_PER_RESPONSE",
                    "5000",
                )
            )
            max_project_cost_micro_usd_per_day = int(
                env.get("AI_MAX_PROJECT_COST_MICRO_USD_PER_DAY", "25000")
            )
            max_project_cost_micro_usd_per_month = int(
                env.get("AI_MAX_PROJECT_COST_MICRO_USD_PER_MONTH", "100000")
            )
            max_in_flight_cost_micro_usd = int(
                env.get("AI_MAX_IN_FLIGHT_COST_MICRO_USD", "5000")
            )
            max_provider_input_chars = int(
                env.get("AI_MAX_PROVIDER_INPUT_CHARS", "12000")
            )
            max_output_tokens = int(env.get("AI_MAX_OUTPUT_TOKENS", "1000"))
        except ValueError as exc:
            raise AIConfigurationError(
                "AI credit, pricing review, and request limits must be integers"
            ) from exc
        if initial_credits < 0 or credits_per_request <= 0:
            raise AIConfigurationError("AI credit settings are outside valid bounds")
        if not 1 <= pricing_max_age_days <= 90:
            raise AIConfigurationError(
                "AI_PRICING_MAX_AGE_DAYS must be between 1 and 90"
            )
        daily_request_wire = env.get("AI_MAX_DAILY_REQUESTS_PER_USER")
        if enabled and (
            daily_request_wire is None
            or str(daily_request_wire).strip() != "0"
        ):
            raise AIConfigurationError(
                "Enabled AI requires AI_MAX_DAILY_REQUESTS_PER_USER=0"
            )
        max_daily_requests_per_user = None
        if not 1 <= max_preflight_cost_micro_usd_per_request <= 1_000_000:
            raise AIConfigurationError(
                "AI_MAX_PREFLIGHT_COST_MICRO_USD_PER_REQUEST must be between 1 and 1000000"
            )
        if not 1 <= retrospective_breaker_micro_usd_per_response <= 1_000_000:
            raise AIConfigurationError(
                "AI_RETROSPECTIVE_BREAKER_MICRO_USD_PER_RESPONSE is invalid"
            )
        if not 1 <= max_project_cost_micro_usd_per_day <= 100_000_000:
            raise AIConfigurationError("AI daily project budget is invalid")
        if not 1 <= max_project_cost_micro_usd_per_month <= 1_000_000_000:
            raise AIConfigurationError("AI monthly project budget is invalid")
        if max_project_cost_micro_usd_per_month < max_project_cost_micro_usd_per_day:
            raise AIConfigurationError("AI monthly budget cannot be below daily budget")
        if not 1 <= max_in_flight_cost_micro_usd <= 100_000_000:
            raise AIConfigurationError("AI in-flight budget is invalid")
        if max_in_flight_cost_micro_usd < max_preflight_cost_micro_usd_per_request:
            raise AIConfigurationError(
                "AI in-flight budget cannot be below one request budget"
            )
        if not 1000 <= max_provider_input_chars <= 50000:
            raise AIConfigurationError(
                "AI_MAX_PROVIDER_INPUT_CHARS must be between 1000 and 50000"
            )
        if not 256 <= max_output_tokens <= 4000:
            raise AIConfigurationError(
                "AI_MAX_OUTPUT_TOKENS must be between 256 and 4000"
            )
        try:
            reservation_timeout_seconds = int(
                env.get("AI_RESERVATION_TIMEOUT_SECONDS", "300")
            )
        except ValueError as exc:
            raise AIConfigurationError(
                "AI_RESERVATION_TIMEOUT_SECONDS must be an integer"
            ) from exc
        if not 60 <= reservation_timeout_seconds <= 86400:
            raise AIConfigurationError(
                "AI_RESERVATION_TIMEOUT_SECONDS must be between 60 and 86400"
            )
        model = env.get("AI_MODEL", "gpt-5.6-luna").strip()
        api_key = env.get("OPENAI_API_KEY")
        safety_salt = env.get("AI_SAFETY_SALT")
        consent_version = env.get("AI_CONSENT_VERSION", "").strip()
        processing_notice = env.get("AI_PROCESSING_NOTICE", "").strip()
        if not model:
            raise AIConfigurationError("AI_MODEL cannot be empty")
        if enabled and (not api_key or not safety_salt or len(safety_salt) < 16):
            raise AIConfigurationError(
                "Enabled AI tutor requires OPENAI_API_KEY and AI_SAFETY_SALT "
                "of at least 16 characters"
            )
        if enabled:
            if (
                not re.fullmatch(
                    r"[A-Za-z0-9][A-Za-z0-9_-]{7,63}", consent_version
                )
                or consent_version.casefold() in {"current", "latest"}
            ):
                raise AIConfigurationError(
                    "AI consent version must be a safe immutable identifier"
                )
            if not 40 <= len(processing_notice) <= 1000:
                raise AIConfigurationError(
                    "AI processing notice must contain 40-1000 characters"
                )
        pricing = ModelPricing(
            input_usd_per_million=_non_negative_decimal(
                env.get("AI_INPUT_USD_PER_MILLION", "0"),
                "AI_INPUT_USD_PER_MILLION",
            ),
            cached_input_usd_per_million=_non_negative_decimal(
                env.get("AI_CACHED_INPUT_USD_PER_MILLION", "0"),
                "AI_CACHED_INPUT_USD_PER_MILLION",
            ),
            cache_write_usd_per_million=_non_negative_decimal(
                env.get("AI_CACHE_WRITE_USD_PER_MILLION", "0"),
                "AI_CACHE_WRITE_USD_PER_MILLION",
            ),
            output_usd_per_million=_non_negative_decimal(
                env.get("AI_OUTPUT_USD_PER_MILLION", "0"),
                "AI_OUTPUT_USD_PER_MILLION",
            ),
        )
        if enabled and any(
            price <= 0
            for price in (
                pricing.input_usd_per_million,
                pricing.cached_input_usd_per_million,
                pricing.cache_write_usd_per_million,
                pricing.output_usd_per_million,
            )
        ):
            raise AIConfigurationError(
                "Enabled AI tutor requires positive input, cached input, "
                "cache write, and output pricing"
            )
        pricing_reviewed_on = env.get("AI_PRICING_REVIEWED_ON", "").strip()
        if pricing_reviewed_on:
            try:
                parse_reviewed_on(
                    pricing_reviewed_on,
                    setting_name="AI_PRICING_REVIEWED_ON",
                )
            except ValueError as exc:
                raise AIConfigurationError(str(exc)) from exc
        if enabled:
            try:
                require_current_review(
                    pricing_reviewed_on,
                    max_age_days=pricing_max_age_days,
                    setting_name="AI_PRICING_REVIEWED_ON",
                )
            except ValueError as exc:
                raise AIConfigurationError(str(exc)) from exc
        snapshot_path = env.get("AI_ECONOMICS_SNAPSHOT_PATH", "").strip()
        snapshot_id = env.get("AI_ECONOMICS_SNAPSHOT_ID", "").strip()
        snapshot_digest = env.get("AI_ECONOMICS_SNAPSHOT_SHA256", "").strip()
        snapshot_values = (snapshot_path, snapshot_id, snapshot_digest)
        if any(snapshot_values) and not all(snapshot_values):
            raise AIConfigurationError(
                "AI economics snapshot path, id, and hash must be configured together"
            )
        economics_contract = None
        if all(snapshot_values):
            try:
                economics_contract = load_ai_economics_contract(
                    snapshot_path,
                    expected_snapshot_id=snapshot_id,
                    expected_snapshot_sha256=snapshot_digest,
                    require_approved=enabled,
                )
            except (EconomicsSnapshotError, ValueError) as exc:
                raise AIConfigurationError(str(exc)) from exc
        if enabled and economics_contract is None:
            raise AIConfigurationError(
                "Enabled AI tutor requires an approved economics snapshot"
            )
        data_dir = Path(env.get("DATA_DIR", ".")).expanduser()
        journal_path = env.get("AI_METERING_JOURNAL_PATH", "").strip()
        configured = cls(
            enabled=enabled,
            provider=provider,
            model=model,
            service_tier=service_tier,
            initial_credits=initial_credits,
            credits_per_request=credits_per_request,
            openai_api_key=api_key,
            safety_salt=safety_salt,
            pricing=pricing,
            reservation_timeout_seconds=reservation_timeout_seconds,
            pricing_reviewed_on=pricing_reviewed_on or None,
            pricing_max_age_days=pricing_max_age_days,
            max_daily_requests_per_user=max_daily_requests_per_user,
            max_preflight_cost_micro_usd_per_request=(
                max_preflight_cost_micro_usd_per_request
            ),
            retrospective_breaker_micro_usd_per_response=(
                retrospective_breaker_micro_usd_per_response
            ),
            max_project_cost_micro_usd_per_day=max_project_cost_micro_usd_per_day,
            max_project_cost_micro_usd_per_month=(
                max_project_cost_micro_usd_per_month
            ),
            max_in_flight_cost_micro_usd=max_in_flight_cost_micro_usd,
            max_provider_input_chars=max_provider_input_chars,
            max_output_tokens=max_output_tokens,
            economics_contract=economics_contract,
            metering_journal_path=str(
                Path(journal_path).expanduser()
                if journal_path
                else data_dir / "ai-metering-fallback.jsonl"
            ),
            consent_version=consent_version or None,
            processing_notice=processing_notice or None,
        )
        if enabled:
            configured.assert_runtime_ready()
        return configured


def parse_tutor_answer(payload: Mapping[str, Any]) -> TutorAnswer:
    try:
        summary = payload["summary_ru"]
        raw_entries = payload["entries"]
    except (KeyError, TypeError) as exc:
        raise AIProviderError("Tutor response has no required fields") from exc
    if not isinstance(summary, str):
        raise AIProviderError("Tutor summary must be text")
    summary = summary.strip()
    if (
        not 1 <= len(summary) <= 700
        or not isinstance(raw_entries, list)
        or not 1 <= len(raw_entries) <= 3
    ):
        raise AIProviderError("Tutor response has invalid summary or entry count")
    entries = []
    for raw_entry in raw_entries:
        try:
            term = raw_entry["term"]
            explanation = raw_entry["explanation_ru"]
            raw_examples = raw_entry["examples"]
        except (KeyError, TypeError) as exc:
            raise AIProviderError("Tutor entry has no required fields") from exc
        if not isinstance(term, str) or not isinstance(explanation, str):
            raise AIProviderError("Tutor entry text fields are invalid")
        term = term.strip()
        explanation = explanation.strip()
        if (
            not 1 <= len(term) <= 120
            or not 1 <= len(explanation) <= 500
            or not isinstance(raw_examples, list)
        ):
            raise AIProviderError("Tutor entry is invalid")
        if len(raw_examples) != 2:
            raise AIProviderError("Tutor entry must contain two examples")
        examples = []
        for raw_example in raw_examples:
            try:
                target = raw_example["target"]
                russian = raw_example["russian"]
            except (KeyError, TypeError) as exc:
                raise AIProviderError("Tutor example has no required fields") from exc
            if not isinstance(target, str) or not isinstance(russian, str):
                raise AIProviderError("Tutor example text fields are invalid")
            target = target.strip()
            russian = russian.strip()
            if not 1 <= len(target) <= 240 or not 1 <= len(russian) <= 240:
                raise AIProviderError("Tutor example cannot be empty")
            examples.append(TutorExample(target=target, russian=russian))
        entries.append(
            TutorEntry(
                term=term,
                explanation_ru=explanation,
                examples=(examples[0], examples[1]),
            )
        )
    return TutorAnswer(summary_ru=summary, entries=tuple(entries))


def _mirror_text(
    value: Any, name: str, *, minimum: int = 0, maximum: int
) -> str:
    if not isinstance(value, str):
        raise AIProviderError(f"Mirror {name} must be text")
    cleaned = value.strip()
    if not minimum <= len(cleaned) <= maximum:
        raise AIProviderError(f"Mirror {name} is outside valid bounds")
    return cleaned


def parse_mirror_answer(payload: Mapping[str, Any]) -> MirrorAnswer:
    legacy = {"answer_ru", "language_items", "examples", "next_step_ru"}
    current = legacy | {"evidence_ru", "interpretation_ru"}
    if not isinstance(payload, Mapping) or (
        set(payload) != legacy and set(payload) != current
    ):
        raise AIProviderError("Mirror response has no exact required fields")
    answer_ru = _mirror_text(
        payload["answer_ru"], "answer_ru", minimum=1, maximum=1800
    )
    raw_items = payload["language_items"]
    raw_examples = payload["examples"]
    if not isinstance(raw_items, list) or len(raw_items) > 3:
        raise AIProviderError("Mirror language items are invalid")
    if not isinstance(raw_examples, list) or len(raw_examples) > 3:
        raise AIProviderError("Mirror examples are invalid")
    raw_evidence = payload.get("evidence_ru", [])
    if not isinstance(raw_evidence, list) or len(raw_evidence) > 5:
        raise AIProviderError("Mirror evidence is invalid")
    evidence = tuple(
        _mirror_text(value, "evidence_ru", minimum=1, maximum=300)
        for value in raw_evidence
    )

    items = []
    item_fields = {"target", "transcription", "meaning_ru", "note_ru"}
    for raw in raw_items:
        if not isinstance(raw, Mapping) or set(raw) != item_fields:
            raise AIProviderError("Mirror language item has invalid fields")
        items.append(
            MirrorLanguageItem(
                target=_mirror_text(raw["target"], "target", minimum=1, maximum=240),
                transcription=_mirror_text(
                    raw["transcription"], "transcription", maximum=160
                ),
                meaning_ru=_mirror_text(
                    raw["meaning_ru"], "meaning_ru", minimum=1, maximum=400
                ),
                note_ru=_mirror_text(raw["note_ru"], "note_ru", maximum=400),
            )
        )

    examples = []
    example_fields = {"target", "transcription", "russian"}
    for raw in raw_examples:
        if not isinstance(raw, Mapping) or set(raw) != example_fields:
            raise AIProviderError("Mirror example has invalid fields")
        examples.append(
            MirrorExample(
                target=_mirror_text(raw["target"], "target", minimum=1, maximum=240),
                transcription=_mirror_text(
                    raw["transcription"], "transcription", maximum=160
                ),
                russian=_mirror_text(
                    raw["russian"], "russian", minimum=1, maximum=240
                ),
            )
        )
    return MirrorAnswer(
        answer_ru=answer_ru,
        language_items=tuple(items),
        examples=tuple(examples),
        next_step_ru=_mirror_text(
            payload["next_step_ru"], "next_step_ru", maximum=500
        ),
        evidence_ru=evidence,
        interpretation_ru=_mirror_text(
            payload.get("interpretation_ru", ""),
            "interpretation_ru",
            maximum=800,
        ),
    )


def validate_tutor_answer(answer: TutorAnswer, context: TutorContext) -> None:
    allowed_terms = {word.term for word in context.words}
    terms = [entry.term for entry in answer.entries]
    if any(term not in allowed_terms for term in terms):
        raise AIProviderError("Tutor response contains a term outside the active block")
    if len(terms) != len(set(terms)):
        raise AIProviderError("Tutor response repeats a term")


def context_fingerprint(context: TutorContext) -> str:
    content = {
        "language": context.language,
        "topic": context.topic,
        "terms": [word.term for word in context.words],
    }
    serialized = json.dumps(content, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def serialize_tutor_provider_input(question: str, context: TutorContext) -> str:
    provider_input = {
        "question_ru": question,
        "language": context.language,
        "topic": context.topic,
        "active_block": [
            {
                "term": word.term,
                "transcription": word.transcription,
                "meaning_ru": word.meaning_ru,
                "dictionary_example": word.example_target,
            }
            for word in context.words
        ],
    }
    return json.dumps(provider_input, ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True)
class ProviderBudget:
    input_tokens_upper_bound: int
    output_tokens_upper_bound: int
    projected_cost_micro_usd: int


def _estimate_provider_budget(
    *,
    serialized_input: str,
    pricing: ModelPricing,
    max_output_tokens: int,
    instructions: str,
    response_schema: Mapping[str, Any],
) -> ProviderBudget:
    schema_text = json.dumps(
        response_schema,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    # A valid UTF-8 token consumes at least one byte. Counting every byte as one
    # token plus protocol overhead intentionally overestimates local preflight.
    input_upper_bound = sum(
        len(value.encode("utf-8"))
        for value in (instructions, serialized_input, schema_text)
    ) + 256
    output_upper_bound = max(0, int(max_output_tokens))
    return ProviderBudget(
        input_tokens_upper_bound=input_upper_bound,
        output_tokens_upper_bound=output_upper_bound,
        projected_cost_micro_usd=pricing.worst_case_cost_micro_usd(
            input_tokens=input_upper_bound,
            output_tokens=output_upper_bound,
        ),
    )


def estimate_tutor_provider_budget(
    *,
    serialized_input: str,
    pricing: ModelPricing,
    max_output_tokens: int,
) -> ProviderBudget:
    return _estimate_provider_budget(
        serialized_input=serialized_input,
        pricing=pricing,
        max_output_tokens=max_output_tokens,
        instructions=TUTOR_INSTRUCTIONS,
        response_schema=TUTOR_RESPONSE_SCHEMA,
    )


def estimate_mirror_provider_budget(
    *,
    serialized_input: str,
    pricing: ModelPricing,
    max_output_tokens: int,
) -> ProviderBudget:
    return _estimate_provider_budget(
        serialized_input=serialized_input,
        pricing=pricing,
        max_output_tokens=max_output_tokens,
        instructions=MIRROR_INSTRUCTIONS,
        response_schema=MIRROR_RESPONSE_SCHEMA,
    )


def render_tutor_answer(result: TutorResult) -> str:
    words = {word.term: word for word in result.context.words}
    lines = [f"🇷🇺 {result.answer.summary_ru}"]
    for entry in result.answer.entries:
        word = words[entry.term]
        lines.extend(
            [
                "",
                f"{entry.term}",
                f"Транскрипция: {word.transcription}",
                f"Значение: {word.meaning_ru}",
                f"Объяснение: {entry.explanation_ru}",
                "Примеры:",
            ]
        )
        for number, example in enumerate(entry.examples, 1):
            lines.append(f"{number}. {example.target}")
            lines.append(f"   {example.russian}")
    lines.extend(
        [
            "",
            f"AI-кредиты: {result.allowance['available_credits']}",
        ]
    )
    return "\n".join(lines)


def render_mirror_answer(answer: MirrorAnswer, *, available_credits: int) -> str:
    del available_credits
    seen: set[str] = set()
    protected_period = "\ue000"

    def clean(value: str) -> str:
        plain = re.sub(r"```[A-Za-z0-9_-]*", "", str(value))
        return re.sub(r"\s+", " ", plain.strip())

    def sentences(value: str) -> list[str]:
        protected = re.sub(r"(?<=\d)\.(?=\d)", protected_period, value)
        protected = re.sub(
            r"\b(?:[A-Za-z]\.){2,}",
            lambda match: match.group(0).replace(".", protected_period),
            protected,
        )
        return [
            unit.replace(protected_period, ".")
            for unit in re.findall(r"[^.!?。！？]+(?:[.!?。！？]+|$)", protected)
        ]

    def take(value: str, *, sentence_level: bool = True) -> str:
        normalized = clean(value)
        if not normalized:
            return ""
        units = (
            sentences(normalized)
            if sentence_level
            else [normalized]
        )
        kept: list[str] = []
        for unit in units:
            clean_unit = unit.strip()
            key = clean_unit.casefold()
            duplicate = any(
                key == existing
                or (
                    min(len(key), len(existing)) >= 8
                    and key in existing
                )
                for existing in seen
            )
            if not clean_unit or duplicate:
                continue
            seen.add(key)
            kept.append(clean_unit)
        return " ".join(kept)

    answer_text = take(answer.answer_ru)
    support: list[str] = []
    for value in answer.evidence_ru:
        unique = take(value)
        if unique:
            support.append(f"• {unique}")
    interpretation = take(answer.interpretation_ru)
    if interpretation:
        support.append(interpretation)
    for item in answer.language_items:
        pronunciation = f" {item.transcription}" if item.transcription else ""
        item_text = take(
            f"{item.target}{pronunciation} — {item.meaning_ru}",
            sentence_level=False,
        )
        if item_text:
            support.append(item_text)
        note = take(item.note_ru)
        if note:
            support.append(note)
    if answer.examples:
        example = answer.examples[0]
        pronunciation = f" {example.transcription}" if example.transcription else ""
        example_text = take(
            f"{example.target}{pronunciation} — {example.russian}",
            sentence_level=False,
        )
        if example_text:
            support.append(example_text)
    next_step = take(answer.next_step_ru)

    paragraphs = [answer_text]
    if support:
        paragraphs.append("\n".join(support))
    if next_step:
        paragraphs.append(next_step)
    rendered = "\n\n".join(value for value in paragraphs if value)
    if len(rendered) <= 900:
        return rendered or "."

    candidate = rendered[:900].rstrip()
    boundaries = list(re.finditer(r"[.!?。！？]", candidate))
    if boundaries:
        candidate = candidate[: boundaries[-1].end()].rstrip()
    if candidate:
        if not re.search(r"[.!?。！？]$", candidate):
            candidate = candidate[:899].rstrip(" ,;:-") + "."
        return candidate
    return "."


def _attr(value: Any, name: str, default: Any = 0) -> Any:
    if value is None:
        return default
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _non_negative_int_attr(value: Any, name: str) -> int:
    try:
        return max(0, int(_attr(value, name, 0) or 0))
    except (TypeError, ValueError):
        return 0


class OpenAIResponsesProvider:
    """OpenAI Responses API adapter behind the provider-neutral protocol."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        service_tier: str,
        safety_salt: str,
        max_provider_input_chars: int = 12000,
        max_output_tokens: int = 1000,
        client: Any | None = None,
    ):
        if not api_key or not safety_salt or len(safety_salt) < 16:
            raise AIConfigurationError(
                "OpenAI key and AI_SAFETY_SALT of at least 16 characters are required"
            )
        self.model = model
        if service_tier != "default":
            raise AIConfigurationError("OpenAI service tier must be default")
        self.service_tier = service_tier
        self.safety_salt = safety_salt.encode("utf-8")
        if not 1000 <= int(max_provider_input_chars) <= 50000:
            raise AIConfigurationError("OpenAI input character limit is invalid")
        if not 256 <= int(max_output_tokens) <= 4000:
            raise AIConfigurationError("OpenAI output token limit is invalid")
        self.max_provider_input_chars = int(max_provider_input_chars)
        self.max_output_tokens = int(max_output_tokens)
        if client is None:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=api_key, timeout=25.0, max_retries=0)
        self.client = client

    def _safety_identifier(self, user_id: int) -> str:
        return hmac.new(
            self.safety_salt,
            str(int(user_id)).encode("ascii"),
            hashlib.sha256,
        ).hexdigest()

    async def generate(self, request: TutorRequest) -> ProviderResult:
        serialized_input = serialize_tutor_provider_input(
            request.question, request.context
        )
        if len(serialized_input) > self.max_provider_input_chars:
            raise AIProviderError(
                "Tutor provider input exceeds the configured character ceiling"
            )
        response = await self.client.responses.create(
            model=self.model,
            instructions=TUTOR_INSTRUCTIONS,
            input=serialized_input,
            max_output_tokens=self.max_output_tokens,
            service_tier=self.service_tier,
            reasoning={"effort": "low"},
            text={
                "format": {
                    "type": "json_schema",
                    "name": "my_dictionary_tutor_answer",
                    "strict": True,
                    "schema": TUTOR_RESPONSE_SCHEMA,
                },
                "verbosity": "low",
            },
            metadata={"request_id": request.request_id},
            safety_identifier=self._safety_identifier(request.user_id),
            store=False,
        )
        output_text = str(_attr(response, "output_text", "")).strip()
        usage = _attr(response, "usage", None)
        input_details = _attr(usage, "input_tokens_details", None)
        output_details = _attr(usage, "output_tokens_details", None)
        provider_usage = ProviderUsage(
            input_tokens=_non_negative_int_attr(usage, "input_tokens"),
            cached_input_tokens=_non_negative_int_attr(
                input_details, "cached_tokens"
            ),
            cache_write_tokens=_non_negative_int_attr(
                input_details, "cache_write_tokens"
            ),
            output_tokens=_non_negative_int_attr(usage, "output_tokens"),
            reasoning_tokens=_non_negative_int_attr(
                output_details, "reasoning_tokens"
            ),
            total_tokens=_non_negative_int_attr(usage, "total_tokens"),
        )
        return ProviderResult(
            answer=None,
            response_id=str(_attr(response, "id", "")) or None,
            model=str(_attr(response, "model", "")),
            usage=provider_usage,
            service_tier=str(_attr(response, "service_tier", "")),
            status=str(_attr(response, "status", "")),
            output_text=output_text,
        )

    async def generate_mirror(
        self,
        *,
        request_id: str,
        user_id: int,
        payload: Mapping[str, Any],
    ) -> ProviderResult:
        serialized_input = json.dumps(
            dict(payload), ensure_ascii=False, separators=(",", ":")
        )
        if len(serialized_input) > self.max_provider_input_chars:
            raise AIProviderError(
                "Mirror provider input exceeds the configured character ceiling"
            )
        response = await self.client.responses.create(
            model=self.model,
            instructions=MIRROR_INSTRUCTIONS,
            input=serialized_input,
            max_output_tokens=min(self.max_output_tokens, 480),
            service_tier=self.service_tier,
            reasoning={"effort": "medium"},
            text={
                "format": {
                    "type": "json_schema",
                    "name": "my_dictionary_mirror_v2_answer",
                    "strict": True,
                    "schema": MIRROR_RESPONSE_SCHEMA,
                },
                "verbosity": "medium",
            },
            metadata={"request_id": request_id},
            safety_identifier=self._safety_identifier(user_id),
            store=False,
        )
        usage = _attr(response, "usage", None)
        input_details = _attr(usage, "input_tokens_details", None)
        output_details = _attr(usage, "output_tokens_details", None)
        return ProviderResult(
            answer=None,
            response_id=str(_attr(response, "id", "")) or None,
            model=str(_attr(response, "model", "")),
            usage=ProviderUsage(
                input_tokens=_non_negative_int_attr(usage, "input_tokens"),
                cached_input_tokens=_non_negative_int_attr(
                    input_details, "cached_tokens"
                ),
                cache_write_tokens=_non_negative_int_attr(
                    input_details, "cache_write_tokens"
                ),
                output_tokens=_non_negative_int_attr(usage, "output_tokens"),
                reasoning_tokens=_non_negative_int_attr(
                    output_details, "reasoning_tokens"
                ),
                total_tokens=_non_negative_int_attr(usage, "total_tokens"),
            ),
            service_tier=str(_attr(response, "service_tier", "")),
            status=str(_attr(response, "status", "")),
            output_text=str(_attr(response, "output_text", "")).strip(),
        )


class AITutorService:
    def __init__(
        self,
        *,
        store: DatabaseStore,
        provider: AIProvider,
        settings: AITutorSettings,
        metering_journal: AIMeteringJournal | None = None,
    ):
        self.store = store
        self.provider = provider
        self.settings = settings
        self.metering_journal = metering_journal or AIMeteringJournal(
            settings.metering_journal_path or "ai-metering-fallback.jsonl"
        )

    async def ask(
        self,
        *,
        user_id: int,
        question: str,
        context: TutorContext | None = None,
        mirror_payload: Mapping[str, Any] | None = None,
    ) -> TutorResult | str:
        if mirror_payload is not None:
            return await self.ask_mirror(user_id=user_id, payload=mirror_payload)
        if context is None:
            raise ValueError("AI tutor context is required")
        question = question.strip()
        if not question or len(question) > 500:
            raise ValueError("AI question must contain 1-500 characters")
        if not 1 <= len(context.words) <= 10:
            raise ValueError("AI tutor context must contain 1-10 block words")
        contract = self.settings.assert_runtime_ready()
        if self.metering_journal.pending_count():
            raise AIUsageRecoveryError(
                "Unreconciled AI metering journal blocks provider calls"
            )
        serialized_input = serialize_tutor_provider_input(question, context)
        if len(serialized_input) > self.settings.max_provider_input_chars:
            raise AIProviderError(
                "Tutor provider input exceeds the configured character ceiling"
            )
        budget = estimate_tutor_provider_budget(
            serialized_input=serialized_input,
            pricing=self.settings.pricing,
            max_output_tokens=self.settings.max_output_tokens,
        )
        if (
            budget.projected_cost_micro_usd
            > self.settings.max_preflight_cost_micro_usd_per_request
        ):
            raise AIQuotaExceeded("AI preflight request cost budget exceeded")
        try:
            self.store.recover_stale_ai_usage(
                timeout_seconds=self.settings.reservation_timeout_seconds,
                user_id=user_id,
            )
        except Exception as exc:
            raise AIUsageRecoveryError(
                "Stale AI reservation recovery failed before a new request"
            ) from exc
        charge_credits = self.store.ai_charge_credits(
            user_id, self.settings.credits_per_request
        )
        request_id = str(uuid4())
        request_id = self.store.reserve_ai_usage(
            user_id,
            action="block_tutor",
            provider=self.settings.provider,
            model=self.settings.model,
            credits=charge_credits,
            initial_credits=self.settings.initial_credits,
            context_fingerprint=context_fingerprint(context),
            max_daily_requests=None,
            requested_service_tier=self.settings.service_tier,
            economics_snapshot_id=contract.snapshot_id,
            economics_snapshot_sha256=contract.snapshot_sha256,
            projected_cost_micro_usd=budget.projected_cost_micro_usd,
            max_project_cost_micro_usd_per_day=(
                self.settings.max_project_cost_micro_usd_per_day
            ),
            max_project_cost_micro_usd_per_month=(
                self.settings.max_project_cost_micro_usd_per_month
            ),
            max_in_flight_cost_micro_usd=(
                self.settings.max_in_flight_cost_micro_usd
            ),
            request_id=request_id,
        )
        started = perf_counter()
        provider_attempt_started = False
        provider_result: ProviderResult | None = None
        settlement_started = False
        try:
            self.store.mark_ai_provider_attempt_started(request_id)
            provider_attempt_started = True
            provider_result = await self.provider.generate(
                TutorRequest(
                    request_id=request_id,
                    user_id=int(user_id),
                    question=question,
                    context=context,
                )
            )
            latency_ms = int((perf_counter() - started) * 1000)
            response_cost = self.settings.pricing.cost_micro_usd(
                provider_result.usage
            )
            telemetry = {
                "request_id": request_id,
                "provider_response_id": provider_result.response_id,
                "model": provider_result.model,
                "service_tier": provider_result.service_tier,
                "provider_status": provider_result.status,
                **provider_result.usage.as_dict(),
                "cost_micro_usd": response_cost,
                "latency_ms": latency_ms,
            }
            try:
                self.store.record_ai_provider_response(
                    request_id,
                    provider_response_id=provider_result.response_id,
                    model=provider_result.model,
                    service_tier=provider_result.service_tier,
                    provider_status=provider_result.status,
                    usage=provider_result.usage.as_dict(),
                    cost_micro_usd=response_cost,
                    latency_ms=latency_ms,
                    expected_model=self.settings.model,
                    expected_service_tier=self.settings.service_tier,
                    retrospective_breaker_micro_usd=(
                        self.settings.retrospective_breaker_micro_usd_per_response
                    ),
                )
            except Exception as storage_error:
                self.metering_journal.append(
                    {
                        **telemetry,
                        "error_code": "provider_telemetry_storage_failure",
                    }
                )
                try:
                    self.store.open_ai_breaker(
                        reason="provider_telemetry_storage_failure"
                    )
                except Exception:
                    pass
                raise AIUsageRecoveryError(
                    "Provider telemetry was journaled after database failure"
                ) from storage_error
            if provider_result.model != self.settings.model:
                raise AIProviderError("OpenAI returned an unapproved model")
            if provider_result.service_tier != self.settings.service_tier:
                raise AIProviderError("OpenAI returned an unapproved service tier")
            if provider_result.status != "completed":
                raise AIProviderError("OpenAI response did not complete")
            answer = provider_result.answer
            if answer is None:
                if not provider_result.output_text:
                    raise AIProviderError("OpenAI returned no tutor output")
                try:
                    payload = json.loads(provider_result.output_text)
                except json.JSONDecodeError as exc:
                    raise AIProviderError("OpenAI returned invalid JSON") from exc
                answer = parse_tutor_answer(payload)
            validate_tutor_answer(answer, context)
            settlement_started = True
            allowance = self.store.complete_ai_usage(
                request_id,
                billed_credits=charge_credits,
                provider_response_id=provider_result.response_id,
                model=provider_result.model,
                usage=provider_result.usage.as_dict(),
                cost_micro_usd=response_cost,
                latency_ms=latency_ms,
                returned_service_tier=provider_result.service_tier,
                provider_status=provider_result.status,
            )
            return TutorResult(
                answer=answer,
                context=context,
                usage=provider_result.usage,
                allowance=allowance,
            )
        except BaseException as exc:
            if settlement_started:
                try:
                    self.store.open_ai_breaker(
                        reason="ai_settlement_storage_failure"
                    )
                except Exception:
                    pass
            try:
                released = self.store.fail_ai_usage(
                    request_id,
                    error_code=type(exc).__name__,
                    open_breaker_reason=(
                        "provider_attempt_outcome_unknown"
                        if provider_attempt_started and provider_result is None
                        else None
                    ),
                )
            except Exception as recovery_error:
                raise AIUsageRecoveryError(
                    "AI request failed and its reservation could not be released"
                ) from recovery_error
            if not released:
                raise AIUsageRecoveryError(
                    "AI request failed and its reservation state is unknown"
                ) from exc
            raise

    async def ask_mirror(
        self,
        *,
        user_id: int,
        payload: Mapping[str, Any],
    ) -> str:
        """Run one block-independent Mirror request through existing AI gates."""
        legacy_fields = {
            "safety_envelope",
            "admin_guidance",
            "question",
            "grounded_snapshot",
            "learning_context",
            "recent_dialogue",
            "response_style",
        }
        control_fields = legacy_fields | {
            "task_kind",
            "communication_mode",
            "answer_depth",
            "learner_level",
        }
        locale_fields = {
            "interface_locale",
            "response_language_instruction",
        }
        companion_fields = {
            "learner_context",
            "compact_reply_policy",
            "style_guidance",
        }
        valid_field_sets = (
            legacy_fields,
            control_fields,
            legacy_fields | locale_fields,
            control_fields | locale_fields,
            legacy_fields | companion_fields,
            control_fields | companion_fields,
            legacy_fields | locale_fields | companion_fields,
            control_fields | locale_fields | companion_fields,
        )
        supplied_fields = set(payload)
        has_continuation_flag = "is_continuation" in supplied_fields
        contract_fields = supplied_fields - {"is_continuation"}
        if contract_fields not in valid_field_sets:
            raise ValueError("Mirror provider payload is invalid")
        if payload["safety_envelope"] != MIRROR_SAFETY_ENVELOPE:
            raise ValueError("Mirror safety envelope is invalid")
        response_style = str(payload["response_style"])
        if response_style not in MIRROR_STYLE_GUIDANCE:
            raise ValueError("Mirror response style is invalid")
        provider_payload = dict(payload)
        if companion_fields.issubset(payload):
            if payload["style_guidance"] != MIRROR_STYLE_GUIDANCE[response_style]:
                raise ValueError("Mirror style guidance is invalid")
        else:
            provider_payload["style_guidance"] = MIRROR_STYLE_GUIDANCE[response_style]
        if control_fields.issubset(payload):
            if payload["communication_mode"] != response_style:
                raise ValueError("Mirror communication mode is inconsistent")
        if locale_fields.issubset(payload):
            locale = str(payload["interface_locale"]).strip()
            instruction = str(payload["response_language_instruction"]).strip()
            if locale not in {"en", "fr", "de", "ja", "ar", "zh", "ru", "es"}:
                raise ValueError("Mirror interface locale is invalid")
            if instruction != response_language_instruction(locale):
                raise ValueError("Mirror response language instruction is invalid")
        if companion_fields.issubset(payload):
            if payload["compact_reply_policy"] != dict(
                MIRROR_COMPACT_REPLY_POLICY
            ):
                raise ValueError("Mirror compact reply policy is invalid")
            learner_context = payload["learner_context"]
            try:
                normalized_context = normalize_companion_learner_context(
                    learner_context
                )
            except ValueError as exc:
                raise ValueError("Mirror learner context is invalid") from exc
            if normalized_context != learner_context:
                raise ValueError("Mirror learner context is invalid")
        question = str(payload["question"]).strip()
        if not 1 <= len(question) <= 500:
            raise ValueError("Mirror question must contain 1-500 characters")
        normalized_dialogue = normalize_mirror_dialogue(payload["recent_dialogue"])[-8:]
        computed_continuation = is_mirror_continuation(
            question,
            recent_dialogue=normalized_dialogue,
        )
        if has_continuation_flag and (
            type(payload["is_continuation"]) is not bool
            or payload["is_continuation"] is not computed_continuation
        ):
            raise ValueError("Mirror continuation flag is invalid")
        provider_payload["recent_dialogue"] = normalized_dialogue
        provider_payload["is_continuation"] = computed_continuation
        serialized_input = json.dumps(
            provider_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        if len(serialized_input) > self.settings.max_provider_input_chars:
            raise AIProviderError(
                "Mirror provider input exceeds the configured character ceiling"
            )
        contract = self.settings.assert_runtime_ready()
        if self.metering_journal.pending_count():
            raise AIUsageRecoveryError(
                "Unreconciled AI metering journal blocks provider calls"
            )
        budget = estimate_mirror_provider_budget(
            serialized_input=serialized_input,
            pricing=self.settings.pricing,
            max_output_tokens=min(self.settings.max_output_tokens, 480),
        )
        if (
            budget.projected_cost_micro_usd
            > self.settings.max_preflight_cost_micro_usd_per_request
        ):
            raise AIQuotaExceeded("AI preflight request cost budget exceeded")
        try:
            self.store.recover_stale_ai_usage(
                timeout_seconds=self.settings.reservation_timeout_seconds,
                user_id=user_id,
            )
        except Exception as exc:
            raise AIUsageRecoveryError(
                "Stale AI reservation recovery failed before a new request"
            ) from exc
        charge_credits = self.store.ai_charge_credits(
            user_id, self.settings.credits_per_request
        )
        request_id = self.store.reserve_ai_usage(
            user_id,
            action="block_tutor",
            provider=self.settings.provider,
            model=self.settings.model,
            credits=charge_credits,
            initial_credits=self.settings.initial_credits,
            context_fingerprint=hashlib.sha256(
                serialized_input.encode("utf-8")
            ).hexdigest(),
            max_daily_requests=None,
            requested_service_tier=self.settings.service_tier,
            economics_snapshot_id=contract.snapshot_id,
            economics_snapshot_sha256=contract.snapshot_sha256,
            projected_cost_micro_usd=budget.projected_cost_micro_usd,
            max_project_cost_micro_usd_per_day=(
                self.settings.max_project_cost_micro_usd_per_day
            ),
            max_project_cost_micro_usd_per_month=(
                self.settings.max_project_cost_micro_usd_per_month
            ),
            max_in_flight_cost_micro_usd=self.settings.max_in_flight_cost_micro_usd,
            request_id=str(uuid4()),
        )
        started = perf_counter()
        provider_attempt_started = False
        provider_result: ProviderResult | None = None
        settlement_started = False
        try:
            self.store.mark_ai_provider_attempt_started(request_id)
            provider_attempt_started = True
            generator = getattr(self.provider, "generate_mirror", None)
            if not callable(generator):
                raise AIConfigurationError(
                    "Configured AI provider does not support Mirror requests"
                )
            provider_result = await generator(
                request_id=request_id,
                user_id=int(user_id),
                payload=provider_payload,
            )
            latency_ms = int((perf_counter() - started) * 1000)
            response_cost = self.settings.pricing.cost_micro_usd(
                provider_result.usage
            )
            telemetry = {
                "request_id": request_id,
                "provider_response_id": provider_result.response_id,
                "model": provider_result.model,
                "service_tier": provider_result.service_tier,
                "provider_status": provider_result.status,
                **provider_result.usage.as_dict(),
                "cost_micro_usd": response_cost,
                "latency_ms": latency_ms,
            }
            try:
                self.store.record_ai_provider_response(
                    request_id,
                    provider_response_id=provider_result.response_id,
                    model=provider_result.model,
                    service_tier=provider_result.service_tier,
                    provider_status=provider_result.status,
                    usage=provider_result.usage.as_dict(),
                    cost_micro_usd=response_cost,
                    latency_ms=latency_ms,
                    expected_model=self.settings.model,
                    expected_service_tier=self.settings.service_tier,
                    retrospective_breaker_micro_usd=(
                        self.settings.retrospective_breaker_micro_usd_per_response
                    ),
                )
            except Exception as storage_error:
                self.metering_journal.append(
                    {**telemetry, "error_code": "provider_telemetry_storage_failure"}
                )
                try:
                    self.store.open_ai_breaker(
                        reason="provider_telemetry_storage_failure"
                    )
                except Exception:
                    pass
                raise AIUsageRecoveryError(
                    "Provider telemetry was journaled after database failure"
                ) from storage_error
            if provider_result.model != self.settings.model:
                raise AIProviderError("OpenAI returned an unapproved model")
            if provider_result.service_tier != self.settings.service_tier:
                raise AIProviderError("OpenAI returned an unapproved service tier")
            if provider_result.status != "completed":
                raise AIProviderError("OpenAI response did not complete")
            if not provider_result.output_text:
                raise AIProviderError("OpenAI returned no Mirror output")
            try:
                answer = parse_mirror_answer(json.loads(provider_result.output_text))
            except json.JSONDecodeError as exc:
                raise AIProviderError("OpenAI returned invalid JSON") from exc
            settlement_started = True
            allowance = self.store.complete_ai_usage(
                request_id,
                billed_credits=charge_credits,
                provider_response_id=provider_result.response_id,
                model=provider_result.model,
                usage=provider_result.usage.as_dict(),
                cost_micro_usd=response_cost,
                latency_ms=latency_ms,
                returned_service_tier=provider_result.service_tier,
                provider_status=provider_result.status,
            )
            rendered = render_mirror_answer(
                answer,
                available_credits=allowance["available_credits"],
            )
            try:
                self.store.record_mirror_quality(
                    request_id=request_id,
                    user_id=user_id,
                    task=str(payload.get("task_kind") or "general_conversation"),
                    mode=str(payload.get("communication_mode") or response_style),
                    depth=str(payload.get("answer_depth") or "balanced"),
                    level=str(payload.get("learner_level") or "adaptive"),
                    contract_version="mirror-control-v1",
                    response_length=len(rendered),
                    evidence_count=len(answer.evidence_ru),
                    example_count=len(answer.examples),
                    has_next_step=bool(answer.next_step_ru),
                    deterministic_score_bps=min(
                        10000,
                        5000
                        + len(answer.evidence_ru) * 1000
                        + (1500 if answer.interpretation_ru else 0)
                        + (1500 if answer.next_step_ru else 0),
                    ),
                )
            except Exception:
                # Quality telemetry is non-billing metadata and must not hide a
                # successfully settled learner response.
                pass
            return MirrorRenderedResponse(rendered, request_id=request_id)
        except BaseException as exc:
            if settlement_started:
                try:
                    self.store.open_ai_breaker(
                        reason="ai_settlement_storage_failure"
                    )
                except Exception:
                    pass
            try:
                released = self.store.fail_ai_usage(
                    request_id,
                    error_code=type(exc).__name__,
                    open_breaker_reason=(
                        "provider_attempt_outcome_unknown"
                        if provider_attempt_started and provider_result is None
                        else None
                    ),
                )
            except Exception as recovery_error:
                raise AIUsageRecoveryError(
                    "AI request failed and its reservation could not be released"
                ) from recovery_error
            if not released:
                raise AIUsageRecoveryError(
                    "AI request failed and its reservation state is unknown"
                ) from exc
            raise


def build_openai_tutor_service(
    store: DatabaseStore, settings: AITutorSettings
) -> AITutorService:
    if not settings.enabled:
        raise AIConfigurationError("AI tutor feature is disabled")
    provider = OpenAIResponsesProvider(
        api_key=settings.openai_api_key or "",
        model=settings.model,
        service_tier=settings.service_tier,
        safety_salt=settings.safety_salt or "",
        max_provider_input_chars=settings.max_provider_input_chars,
        max_output_tokens=settings.max_output_tokens,
    )
    return AITutorService(store=store, provider=provider, settings=settings)
