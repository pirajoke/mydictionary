"""Metered voice practice with ephemeral audio and honest STT feedback."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING
from difflib import SequenceMatcher
import hashlib
import json
import os
from pathlib import Path
import re
from time import perf_counter
from typing import Any, Mapping, Protocol, Sequence
import unicodedata
from uuid import uuid4

from sqlalchemy import select

from mydictionary.ai_metering import AIMeteringJournal
from mydictionary.ai_tutor import ProviderUsage
from mydictionary.secret_enrollment import (
    SecretEnrollmentError,
    load_provider_api_key,
)
from mydictionary.storage import (
    AIQuotaExceeded,
    AIUsageStateError,
    DatabaseStore,
    VoiceSession,
    VoiceTurn,
    utcnow,
)


_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class VoiceConfigurationError(RuntimeError):
    """Voice tutor settings are missing or unsafe."""


class VoiceProviderError(RuntimeError):
    """The transcription provider did not return a usable result."""


class VoiceUsageRecoveryError(RuntimeError):
    """A failed voice request could not release its credit reservation."""


class VoiceSessionError(RuntimeError):
    """A voice session is missing, expired, or no longer at the expected turn."""


def _bool(value: str, name: str = "VOICE_TUTOR_ENABLED") -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    raise VoiceConfigurationError(f"{name} must be a boolean")


def _bounded_int(
    values: Mapping[str, str],
    name: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        value = int(values.get(name, str(default)))
    except ValueError as exc:
        raise VoiceConfigurationError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise VoiceConfigurationError(f"{name} is outside the allowed range")
    return value


def _decimal(value: str, name: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except Exception as exc:
        raise VoiceConfigurationError(f"{name} must be a decimal") from exc
    if not parsed.is_finite() or parsed < 0:
        raise VoiceConfigurationError(f"{name} must be finite and non-negative")
    return parsed


@dataclass(frozen=True)
class VoiceTutorSettings:
    enabled: bool
    provider: str
    model: str
    openai_api_key: str | None
    credits_per_request: int
    initial_credits: int
    reservation_timeout_seconds: int
    max_audio_bytes: int
    max_duration_seconds: int
    session_ttl_minutes: int
    transcript_retention_days: int
    cost_micro_usd_per_minute: Decimal
    consent_version: str = "unversioned"
    processing_notice: str = (
        "Голосовое сообщение будет передано OpenAI для распознавания. "
        "Исходное аудио не сохраняется, а текстовая расшифровка хранится "
        "ограниченное время."
    )
    groq_api_key: str | None = None
    minimum_billable_seconds: int = 0
    groq_zdr_verified: bool = False
    retrospective_breaker_micro_usd_per_response: int = 5000

    @classmethod
    def from_env(
        cls, values: Mapping[str, str] | None = None
    ) -> "VoiceTutorSettings":
        env = values if values is not None else os.environ
        enabled = _bool(env.get("VOICE_TUTOR_ENABLED", "false"))
        provider = str(env.get("VOICE_PROVIDER", "openai")).strip().lower()
        if provider not in {"openai", "groq"}:
            raise VoiceConfigurationError("VOICE_PROVIDER must be openai or groq")
        default_model = (
            "whisper-large-v3" if provider == "groq" else "gpt-4o-transcribe"
        )
        model = str(env.get("VOICE_TRANSCRIPTION_MODEL", default_model)).strip()
        if not model or len(model) > 128:
            raise VoiceConfigurationError("VOICE_TRANSCRIPTION_MODEL is invalid")
        groq_api_key = None
        if enabled and provider == "groq":
            try:
                groq_api_key = load_provider_api_key(env, provider="groq")
            except SecretEnrollmentError as exc:
                raise VoiceConfigurationError(str(exc)) from exc
        settings = cls(
            enabled=enabled,
            provider=provider,
            model=model,
            openai_api_key=str(env.get("OPENAI_API_KEY") or "").strip() or None,
            credits_per_request=_bounded_int(
                env,
                "VOICE_CREDITS_PER_REQUEST",
                default=1,
                minimum=1,
                maximum=100,
            ),
            initial_credits=_bounded_int(
                env,
                "AI_INITIAL_CREDITS",
                default=0,
                minimum=0,
                maximum=1000000,
            ),
            reservation_timeout_seconds=_bounded_int(
                env,
                "AI_RESERVATION_TIMEOUT_SECONDS",
                default=300,
                minimum=60,
                maximum=86400,
            ),
            max_audio_bytes=_bounded_int(
                env,
                "VOICE_MAX_AUDIO_BYTES",
                default=8 * 1024 * 1024,
                minimum=1024,
                maximum=20 * 1024 * 1024,
            ),
            max_duration_seconds=_bounded_int(
                env,
                "VOICE_MAX_DURATION_SECONDS",
                default=30,
                minimum=2,
                maximum=120,
            ),
            session_ttl_minutes=_bounded_int(
                env,
                "VOICE_SESSION_TTL_MINUTES",
                default=30,
                minimum=5,
                maximum=240,
            ),
            transcript_retention_days=_bounded_int(
                env,
                "VOICE_TRANSCRIPT_RETENTION_DAYS",
                default=30,
                minimum=1,
                maximum=365,
            ),
            cost_micro_usd_per_minute=_decimal(
                env.get("VOICE_COST_MICRO_USD_PER_MINUTE", "0"),
                "VOICE_COST_MICRO_USD_PER_MINUTE",
            ),
            consent_version=str(env.get("VOICE_CONSENT_VERSION", "")).strip()
            or "unversioned",
            processing_notice=str(
                env.get("VOICE_PROCESSING_NOTICE", "")
            ).strip()
            or cls.processing_notice,
            groq_api_key=groq_api_key,
            minimum_billable_seconds=_bounded_int(
                env,
                "VOICE_MINIMUM_BILLABLE_SECONDS",
                default=10 if provider == "groq" else 0,
                minimum=0,
                maximum=60,
            ),
            groq_zdr_verified=_bool(
                env.get("VOICE_GROQ_ZDR_VERIFIED", "false"),
                "VOICE_GROQ_ZDR_VERIFIED",
            ),
            retrospective_breaker_micro_usd_per_response=_bounded_int(
                env,
                "AI_RETROSPECTIVE_BREAKER_MICRO_USD_PER_RESPONSE",
                default=5000,
                minimum=1,
                maximum=1000000,
            ),
        )
        if not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", settings.consent_version
        ):
            raise VoiceConfigurationError(
                "VOICE_CONSENT_VERSION must be a safe 1 to 64 character identifier"
            )
        if not 40 <= len(settings.processing_notice) <= 1000:
            raise VoiceConfigurationError(
                "VOICE_PROCESSING_NOTICE must contain 40 to 1000 characters"
            )
        if enabled:
            provider_key = (
                settings.groq_api_key
                if settings.provider == "groq"
                else settings.openai_api_key
            )
            if not provider_key:
                raise VoiceConfigurationError(
                    "Enabled voice tutor requires "
                    + (
                        "GROQ_API_KEY or GROQ_API_KEY_FILE"
                        if settings.provider == "groq"
                        else "OPENAI_API_KEY"
                    )
                )
            if settings.provider == "groq" and not settings.groq_zdr_verified:
                raise VoiceConfigurationError(
                    "Enabled Groq voice requires VOICE_GROQ_ZDR_VERIFIED=true"
                )
            if settings.cost_micro_usd_per_minute <= 0:
                raise VoiceConfigurationError(
                    "Enabled voice tutor requires VOICE_COST_MICRO_USD_PER_MINUTE"
                )
            if not str(env.get("VOICE_CONSENT_VERSION", "")).strip():
                raise VoiceConfigurationError(
                    "Enabled voice tutor requires VOICE_CONSENT_VERSION"
                )
            if not str(env.get("VOICE_PROCESSING_NOTICE", "")).strip():
                raise VoiceConfigurationError(
                    "Enabled voice tutor requires VOICE_PROCESSING_NOTICE"
                )
        return settings

    def estimated_cost_micro_usd(self, duration_seconds: int) -> int:
        value = (
            Decimal(
                max(
                    0,
                    int(duration_seconds),
                    int(self.minimum_billable_seconds),
                )
            )
            * self.cost_micro_usd_per_minute
            / Decimal(60)
        )
        return int(value.to_integral_value(rounding=ROUND_CEILING))


@dataclass(frozen=True)
class VoiceTranslationSettings:
    enabled: bool = False
    provider: str = "openai"
    transcription_model: str = "gpt-4o-transcribe"
    translation_model: str = "gpt-5.6-luna"
    requested_service_tier: str = "default"
    openai_api_key: str | None = None
    consent_version: str = "unversioned"
    processing_notice: str = ""
    stt_cost_micro_usd_per_minute: Decimal = Decimal(0)
    input_usd_per_million: Decimal = Decimal(0)
    output_usd_per_million: Decimal = Decimal(0)
    pricing_reviewed_on: str = ""
    max_audio_bytes: int = 8 * 1024 * 1024
    max_duration_seconds: int = 30
    initial_credits: int = 0
    stt_credits_per_request: int = 1
    translation_credits_per_request: int = 1
    reservation_timeout_seconds: int = 300
    max_preflight_cost_micro_usd: int = 5000
    retrospective_breaker_micro_usd_per_response: int = 5000
    max_daily_requests_per_user: int = 5
    max_project_cost_micro_usd_per_day: int = 25000
    max_project_cost_micro_usd_per_month: int = 100000
    max_in_flight_cost_micro_usd: int = 5000
    economics_snapshot_id: str = "voice-translation-disabled"
    economics_snapshot_sha256: str = "0" * 64
    metering_journal_path: str | None = None
    groq_api_key: str | None = None
    stt_minimum_billable_seconds: int = 0
    groq_zdr_verified: bool = False

    @classmethod
    def from_env(
        cls,
        values: Mapping[str, str] | None = None,
        *,
        existing_voice_consent_version: str | None = None,
    ) -> "VoiceTranslationSettings":
        env = values if values is not None else os.environ
        enabled = _bool(
            env.get("VOICE_TRANSLATION_ENABLED", "false"),
            "VOICE_TRANSLATION_ENABLED",
        )
        if not enabled:
            return cls(enabled=False)
        provider = str(env.get("VOICE_TRANSLATION_PROVIDER", "openai")).strip().lower()
        if provider not in {"openai", "groq"}:
            raise ValueError("VOICE_TRANSLATION_PROVIDER must be openai or groq")
        consent_version = str(
            env.get("VOICE_TRANSLATION_CONSENT_VERSION", "")
        ).strip()
        notice = str(env.get("VOICE_TRANSLATION_PROCESSING_NOTICE", "")).strip()
        if (
            not _VERSION_RE.fullmatch(consent_version)
            or consent_version == str(existing_voice_consent_version or "").strip()
        ):
            raise ValueError("Voice translation requires a distinct consent version")
        notice_folded = notice.casefold()
        if (
            not 40 <= len(notice) <= 1000
            or "перевод" not in notice_folded
            or "распозна" not in notice_folded
        ):
            raise ValueError("Voice translation processing notice is incomplete")
        stt_cost = _decimal(
            env.get("VOICE_TRANSLATION_STT_MICRO_USD_PER_MINUTE", "0"),
            "VOICE_TRANSLATION_STT_MICRO_USD_PER_MINUTE",
        )
        input_rate = _decimal(
            env.get("VOICE_TRANSLATION_INPUT_USD_PER_MILLION", "0"),
            "VOICE_TRANSLATION_INPUT_USD_PER_MILLION",
        )
        output_rate = _decimal(
            env.get("VOICE_TRANSLATION_OUTPUT_USD_PER_MILLION", "0"),
            "VOICE_TRANSLATION_OUTPUT_USD_PER_MILLION",
        )
        if min(stt_cost, input_rate, output_rate) <= 0:
            raise ValueError("Voice translation requires positive reviewed prices")
        reviewed_on = str(
            env.get("VOICE_TRANSLATION_PRICING_REVIEWED_ON", "")
        ).strip()
        try:
            reviewed_date = date.fromisoformat(reviewed_on)
        except ValueError as exc:
            raise ValueError("Voice translation pricing review date is invalid") from exc
        if reviewed_date > date.today() or (date.today() - reviewed_date).days > 30:
            raise ValueError("Voice translation pricing review is stale")
        api_key = str(env.get("OPENAI_API_KEY", "")).strip() or None
        if not api_key:
            raise ValueError("Enabled voice translation requires OPENAI_API_KEY")
        groq_api_key = None
        if provider == "groq":
            try:
                groq_api_key = load_provider_api_key(env, provider="groq")
            except SecretEnrollmentError as exc:
                raise VoiceConfigurationError(str(exc)) from exc
        if provider == "groq" and not groq_api_key:
            raise ValueError(
                "Enabled Groq transcription requires GROQ_API_KEY or GROQ_API_KEY_FILE"
            )
        groq_zdr_verified = _bool(
            env.get("VOICE_GROQ_ZDR_VERIFIED", "false"),
            "VOICE_GROQ_ZDR_VERIFIED",
        )
        if provider == "groq" and not groq_zdr_verified:
            raise ValueError(
                "Enabled Groq transcription requires VOICE_GROQ_ZDR_VERIFIED=true"
            )
        max_preflight_cost = _bounded_int(
            env,
            "VOICE_TRANSLATION_MAX_PREFLIGHT_COST_MICRO_USD",
            default=5000,
            minimum=1,
            maximum=1000000,
        )
        retrospective_breaker = _bounded_int(
            env,
            "AI_RETROSPECTIVE_BREAKER_MICRO_USD_PER_RESPONSE",
            default=5000,
            minimum=1,
            maximum=1000000,
        )
        max_daily_requests = _bounded_int(
            env,
            "VOICE_TRANSLATION_MAX_DAILY_REQUESTS_PER_USER",
            default=5,
            minimum=1,
            maximum=100,
        )
        daily_budget = _bounded_int(
            env,
            "AI_MAX_PROJECT_COST_MICRO_USD_PER_DAY",
            default=25000,
            minimum=1,
            maximum=100000000,
        )
        monthly_budget = _bounded_int(
            env,
            "AI_MAX_PROJECT_COST_MICRO_USD_PER_MONTH",
            default=100000,
            minimum=1,
            maximum=1000000000,
        )
        in_flight_budget = _bounded_int(
            env,
            "AI_MAX_IN_FLIGHT_COST_MICRO_USD",
            default=5000,
            minimum=1,
            maximum=100000000,
        )
        if monthly_budget < daily_budget:
            raise ValueError("Voice translation monthly budget cannot be below daily")
        if in_flight_budget < max_preflight_cost:
            raise ValueError(
                "Voice translation in-flight budget cannot be below one request"
            )
        snapshot_payload = {
            "input_usd_per_million": str(input_rate),
            "output_usd_per_million": str(output_rate),
            "provider": provider,
            "requested_service_tier": str(
                env.get("VOICE_TRANSLATION_SERVICE_TIER", "default")
            ).strip(),
            "reviewed_on": reviewed_on,
            "stt_micro_usd_per_minute": str(stt_cost),
            "transcription_model": str(
                env.get(
                    "VOICE_TRANSCRIPTION_MODEL",
                    "whisper-large-v3"
                    if provider == "groq"
                    else "gpt-4o-transcribe",
                )
            ).strip(),
            "translation_model": str(
                env.get("VOICE_TRANSLATION_MODEL", "gpt-5.6-luna")
            ).strip(),
            "groq_zdr_verified": groq_zdr_verified,
        }
        snapshot_sha256 = hashlib.sha256(
            json.dumps(
                snapshot_payload,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        journal_path = str(env.get("AI_METERING_JOURNAL_PATH", "")).strip()
        return cls(
            enabled=True,
            provider=provider,
            transcription_model=str(
                env.get(
                    "VOICE_TRANSCRIPTION_MODEL",
                    "whisper-large-v3"
                    if provider == "groq"
                    else "gpt-4o-transcribe",
                )
            ).strip(),
            translation_model=str(
                env.get("VOICE_TRANSLATION_MODEL", "gpt-5.6-luna")
            ).strip(),
            requested_service_tier=str(
                env.get("VOICE_TRANSLATION_SERVICE_TIER", "default")
            ).strip(),
            openai_api_key=api_key,
            consent_version=consent_version,
            processing_notice=notice,
            stt_cost_micro_usd_per_minute=stt_cost,
            input_usd_per_million=input_rate,
            output_usd_per_million=output_rate,
            pricing_reviewed_on=reviewed_on,
            max_audio_bytes=_bounded_int(
                env,
                "VOICE_TRANSLATION_MAX_AUDIO_BYTES",
                default=8 * 1024 * 1024,
                minimum=1024,
                maximum=20 * 1024 * 1024,
            ),
            max_duration_seconds=_bounded_int(
                env,
                "VOICE_TRANSLATION_MAX_DURATION_SECONDS",
                default=30,
                minimum=2,
                maximum=120,
            ),
            initial_credits=_bounded_int(
                env, "AI_INITIAL_CREDITS", default=0, minimum=0, maximum=1000000
            ),
            stt_credits_per_request=_bounded_int(
                env,
                "VOICE_TRANSLATION_STT_CREDITS_PER_REQUEST",
                default=1,
                minimum=1,
                maximum=100,
            ),
            translation_credits_per_request=_bounded_int(
                env,
                "VOICE_TRANSLATION_CREDITS_PER_REQUEST",
                default=1,
                minimum=1,
                maximum=100,
            ),
            reservation_timeout_seconds=_bounded_int(
                env,
                "AI_RESERVATION_TIMEOUT_SECONDS",
                default=300,
                minimum=60,
                maximum=86400,
            ),
            max_preflight_cost_micro_usd=max_preflight_cost,
            retrospective_breaker_micro_usd_per_response=retrospective_breaker,
            max_daily_requests_per_user=max_daily_requests,
            max_project_cost_micro_usd_per_day=daily_budget,
            max_project_cost_micro_usd_per_month=monthly_budget,
            max_in_flight_cost_micro_usd=in_flight_budget,
            economics_snapshot_id=f"voice-translation-{reviewed_on}",
            economics_snapshot_sha256=snapshot_sha256,
            metering_journal_path=str(
                Path(journal_path).expanduser()
                if journal_path
                else Path("data") / "ai-metering-fallback.jsonl"
            ),
            groq_api_key=groq_api_key,
            stt_minimum_billable_seconds=_bounded_int(
                env,
                "VOICE_TRANSLATION_STT_MINIMUM_BILLABLE_SECONDS",
                default=10 if provider == "groq" else 0,
                minimum=0,
                maximum=60,
            ),
            groq_zdr_verified=groq_zdr_verified,
        )


@dataclass(frozen=True)
class VoiceWord:
    vocabulary_id: str
    target: str
    speech: str
    transcription: str
    meaning_ru: str
    focus_target: str | None = None
    focus_transcription: str | None = None


@dataclass(frozen=True)
class VoiceSessionState:
    session_id: str
    user_id: int
    pack_id: str
    language: str
    topic: str | None
    mode: str
    vocabulary_ids: tuple[str, ...]
    status: str
    next_position: int
    turn_count: int
    expires_at: datetime


@dataclass(frozen=True)
class TranscriptionRequest:
    audio: bytes
    language: str
    prompt: str
    detect_language: bool = False


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    response_id: str | None
    model: str
    usage: ProviderUsage
    detected_language: str = ""
    service_tier: str = "default"
    status: str = "completed"


class TranscriptionProvider(Protocol):
    async def transcribe(
        self, request: TranscriptionRequest
    ) -> TranscriptionResult: ...


class DisabledTranscriptionProvider:
    async def transcribe(
        self, request: TranscriptionRequest
    ) -> TranscriptionResult:
        raise VoiceConfigurationError("Voice tutor is disabled")


@dataclass(frozen=True)
class PronunciationFeedback:
    transcript: str
    expected: VoiceWord
    matched: VoiceWord | None
    code: str
    similarity_bps: int


@dataclass(frozen=True)
class VoiceTurnResult:
    feedback: PronunciationFeedback
    session_status: str
    next_position: int
    available_credits: int


@dataclass(frozen=True)
class VoiceTranscriptResult:
    transcript: str
    detected_language: str
    available_credits: int


def _attr(value: Any, name: str, default: Any = 0) -> Any:
    if value is None:
        return default
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


class OpenAITranscriptionProvider:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        client: Any | None = None,
    ):
        if not api_key:
            raise VoiceConfigurationError("OpenAI API key is required")
        self.model = model
        if client is None:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=api_key, timeout=45.0, max_retries=0)
        self.client = client

    async def transcribe(
        self, request: TranscriptionRequest
    ) -> TranscriptionResult:
        values = {
            "file": ("voice.ogg", request.audio, "audio/ogg"),
            "model": self.model,
            "prompt": request.prompt[:500],
            "response_format": (
                "verbose_json" if request.detect_language else "json"
            ),
        }
        if request.language:
            values["language"] = request.language
        response = await self.client.audio.transcriptions.create(
            **values,
        )
        text = str(_attr(response, "text", "")).strip()
        usage = _attr(response, "usage", None)
        input_details = _attr(
            usage,
            "input_token_details",
            _attr(usage, "input_tokens_details", None),
        )
        provider_usage = ProviderUsage(
            input_tokens=int(_attr(usage, "input_tokens", 0)),
            cached_input_tokens=int(_attr(input_details, "cached_tokens", 0)),
            output_tokens=int(_attr(usage, "output_tokens", 0)),
            total_tokens=int(_attr(usage, "total_tokens", 0)),
        )
        x_groq = _attr(response, "x_groq", None)
        return TranscriptionResult(
            text=text,
            response_id=(
                str(_attr(response, "id", ""))
                or str(_attr(x_groq, "id", ""))
                or None
            ),
            model=str(_attr(response, "model", self.model)),
            usage=provider_usage,
            detected_language=str(_attr(response, "language", request.language)),
        )


class GroqTranscriptionProvider(OpenAITranscriptionProvider):
    """One-attempt Groq STT adapter through its OpenAI-compatible endpoint."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "whisper-large-v3",
        client: Any | None = None,
    ):
        if not api_key:
            raise VoiceConfigurationError("Groq API key is required")
        if client is None:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(
                api_key=api_key,
                base_url="https://api.groq.com/openai/v1",
                timeout=45.0,
                max_retries=0,
            )
        super().__init__(api_key=api_key, model=model, client=client)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _normalized(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value)).casefold()
    return "".join(
        character
        for character in normalized
        if not unicodedata.category(character).startswith(("P", "Z", "C"))
    )


def _word_score(transcript: str, word: VoiceWord) -> int:
    observed = _normalized(transcript)
    if not observed:
        return 0
    variants = {
        _normalized(word.target),
        _normalized(word.speech),
        _normalized(word.transcription.strip("/[]")),
    }
    variants.discard("")
    return max(
        int(SequenceMatcher(None, observed, variant).ratio() * 10000)
        for variant in variants
    )


def evaluate_transcript(
    transcript: str,
    *,
    expected: VoiceWord,
    words: Sequence[VoiceWord],
) -> PronunciationFeedback:
    transcript = str(transcript).strip()
    if not transcript:
        raise VoiceProviderError("Transcription is empty")
    expected_score = _word_score(transcript, expected)
    matched = max(words, key=lambda word: _word_score(transcript, word), default=None)
    matched_score = _word_score(transcript, matched) if matched else 0
    if expected_score >= 9000:
        code = "exact"
    elif expected_score >= 6500:
        code = "close"
    else:
        code = "retry"
    return PronunciationFeedback(
        transcript=transcript,
        expected=expected,
        matched=matched if matched_score >= 6500 else None,
        code=code,
        similarity_bps=expected_score,
    )


class VoiceTutorService:
    def __init__(
        self,
        *,
        store: DatabaseStore,
        provider: TranscriptionProvider,
        settings: VoiceTutorSettings,
    ):
        self.store = store
        self.provider = provider
        self.settings = settings

    @staticmethod
    def _state(row: VoiceSession) -> VoiceSessionState:
        identifiers = json.loads(row.vocabulary_ids_json)
        if not isinstance(identifiers, list) or not all(
            isinstance(value, str) for value in identifiers
        ):
            raise VoiceSessionError("Voice session word list is invalid")
        return VoiceSessionState(
            session_id=row.session_id,
            user_id=row.telegram_user_id,
            pack_id=row.pack_id,
            language=row.language,
            topic=row.topic,
            mode=row.mode,
            vocabulary_ids=tuple(identifiers),
            status=row.status,
            next_position=row.next_position,
            turn_count=row.turn_count,
            expires_at=row.expires_at,
        )

    def start_session(
        self,
        *,
        user_id: int,
        pack_id: str,
        language: str,
        topic: str | None,
        block_session_id: str | None,
        mode: str = "pronunciation",
        words: Sequence[VoiceWord],
    ) -> VoiceSessionState:
        if not self.settings.enabled:
            raise VoiceConfigurationError("Voice tutor is disabled")
        identifiers = [word.vocabulary_id for word in words]
        if mode not in {"pronunciation", "conversation"}:
            raise ValueError("Unknown voice session mode")
        if not 1 <= len(identifiers) <= 10 or len(set(identifiers)) != len(identifiers):
            raise ValueError("Voice session requires 1-10 unique block words")
        if any(len(value) != 64 for value in identifiers):
            raise ValueError("Voice vocabulary identities are invalid")
        self.store.ensure_user_id(user_id)
        now = utcnow()
        session_id = str(uuid4())
        with self.store.Session.begin() as session:
            active = session.execute(
                select(VoiceSession)
                .where(
                    VoiceSession.telegram_user_id == int(user_id),
                    VoiceSession.status == "active",
                )
                .with_for_update()
            ).scalars().all()
            for row in active:
                row.status = "cancelled"
                row.ended_at = now
                row.updated_at = now
            row = VoiceSession(
                session_id=session_id,
                telegram_user_id=int(user_id),
                pack_id=str(pack_id)[:64],
                language=str(language)[:16],
                topic=str(topic)[:64] if topic else None,
                block_session_id=(
                    str(block_session_id)[:64] if block_session_id else None
                ),
                mode=mode,
                vocabulary_ids_json=json.dumps(identifiers, separators=(",", ":")),
                status="active",
                turn_count=0,
                next_position=0,
                expires_at=now + timedelta(minutes=self.settings.session_ttl_minutes),
                created_at=now,
                updated_at=now,
            )
            session.add(row)
        return self._state(row)

    def active_session(self, user_id: int) -> VoiceSessionState | None:
        now = utcnow()
        with self.store.Session.begin() as session:
            row = session.execute(
                select(VoiceSession)
                .where(
                    VoiceSession.telegram_user_id == int(user_id),
                    VoiceSession.status == "active",
                )
                .order_by(VoiceSession.updated_at.desc())
                .with_for_update()
            ).scalars().first()
            if row is None:
                return None
            if _aware(row.expires_at) <= now:
                row.status = "expired"
                row.ended_at = now
                row.updated_at = now
                return None
            return self._state(row)

    def latest_session(self, user_id: int) -> VoiceSessionState | None:
        with self.store.Session() as session:
            row = session.execute(
                select(VoiceSession)
                .where(VoiceSession.telegram_user_id == int(user_id))
                .order_by(VoiceSession.updated_at.desc())
            ).scalars().first()
            return self._state(row) if row else None

    def stop_session(self, user_id: int) -> bool:
        with self.store.Session.begin() as session:
            row = session.execute(
                select(VoiceSession)
                .where(
                    VoiceSession.telegram_user_id == int(user_id),
                    VoiceSession.status == "active",
                )
                .order_by(VoiceSession.updated_at.desc())
                .with_for_update()
            ).scalars().first()
            if row is None:
                return False
            row.status = "cancelled"
            row.ended_at = utcnow()
            row.updated_at = utcnow()
            return True

    def _record_provider_response(
        self,
        *,
        request_id: str,
        result: TranscriptionResult,
        duration_seconds: int,
        started: float,
    ) -> tuple[dict[str, int], int, int]:
        usage = result.usage.as_dict()
        cost_micro_usd = self.settings.estimated_cost_micro_usd(duration_seconds)
        latency_ms = int((perf_counter() - started) * 1000)
        telemetry = self.store.record_ai_provider_response(
            request_id,
            provider_response_id=result.response_id,
            model=result.model,
            service_tier=result.service_tier,
            provider_status=result.status,
            usage=usage,
            cost_micro_usd=cost_micro_usd,
            latency_ms=latency_ms,
            expected_model=self.settings.model,
            expected_service_tier="default",
            retrospective_breaker_micro_usd=(
                self.settings.retrospective_breaker_micro_usd_per_response
            ),
        )
        if telemetry["breaker_open"]:
            raise VoiceProviderError("Voice cost or provider contract breaker opened")
        if result.model != self.settings.model:
            raise VoiceProviderError("Voice provider returned an unapproved model")
        if result.service_tier != "default":
            raise VoiceProviderError(
                "Voice provider returned an unapproved service tier"
            )
        if result.status != "completed":
            raise VoiceProviderError("Voice provider response did not complete")
        return usage, cost_micro_usd, latency_ms

    def turns(self, *, user_id: int, session_id: str) -> list[dict[str, Any]]:
        with self.store.Session() as session:
            owner = session.get(VoiceSession, str(session_id))
            if owner is None or owner.telegram_user_id != int(user_id):
                raise VoiceSessionError("Voice session does not belong to the user")
            rows = session.execute(
                select(VoiceTurn)
                .where(VoiceTurn.session_id == str(session_id))
                .order_by(VoiceTurn.created_at)
            ).scalars().all()
        return [
            {
                column.name: getattr(row, column.name)
                for column in VoiceTurn.__table__.columns
            }
            for row in rows
        ]

    async def transcribe_message(
        self,
        *,
        user_id: int,
        audio: bytes,
        duration_seconds: int,
    ) -> VoiceTranscriptResult:
        """Transcribe one ephemeral voice note for the contextual assistant."""
        if not self.settings.enabled:
            raise VoiceConfigurationError("Voice tutor is disabled")
        if not 1 <= int(duration_seconds) <= self.settings.max_duration_seconds:
            raise ValueError("Voice duration is outside the allowed range")
        if not audio or len(audio) > self.settings.max_audio_bytes:
            raise ValueError("Voice audio size is outside the allowed range")
        try:
            self.store.recover_stale_ai_usage(
                timeout_seconds=self.settings.reservation_timeout_seconds,
                user_id=user_id,
            )
        except Exception as exc:
            raise VoiceUsageRecoveryError(
                "Stale voice reservation recovery failed"
            ) from exc

        charge_credits = self.store.ai_charge_credits(
            user_id, self.settings.credits_per_request
        )
        request_id = self.store.reserve_ai_usage(
            user_id,
            action="voice_transcription",
            provider=self.settings.provider,
            model=self.settings.model,
            credits=charge_credits,
            initial_credits=self.settings.initial_credits,
            context_fingerprint=hashlib.sha256(
                f"voice-assistant:{int(user_id)}:{uuid4()}".encode("ascii")
            ).hexdigest(),
        )
        started = perf_counter()
        try:
            self.store.mark_ai_provider_attempt_started(request_id)
            provider_result = await self.provider.transcribe(
                TranscriptionRequest(
                    audio=bytes(audio),
                    language="",
                    prompt="",
                    detect_language=True,
                )
            )
            usage, cost_micro_usd, latency_ms = self._record_provider_response(
                request_id=request_id,
                result=provider_result,
                duration_seconds=duration_seconds,
                started=started,
            )
            transcript = str(provider_result.text).strip()
            if not 1 <= len(transcript) <= 1000:
                raise VoiceProviderError("Transcription is empty or too large")
            completed = self.store.complete_ai_usage(
                request_id,
                billed_credits=charge_credits,
                provider_response_id=provider_result.response_id,
                model=provider_result.model,
                usage=usage,
                cost_micro_usd=cost_micro_usd,
                latency_ms=latency_ms,
                returned_service_tier=provider_result.service_tier,
                provider_status=provider_result.status,
            )
        except BaseException as exc:
            try:
                released = self.store.fail_ai_usage(
                    request_id, error_code=type(exc).__name__
                )
            except Exception as recovery_error:
                raise VoiceUsageRecoveryError(
                    "Voice request failed and its reservation could not be released"
                ) from recovery_error
            if not released:
                raise VoiceUsageRecoveryError(
                    "Voice request reservation state is unknown"
                ) from exc
            raise
        return VoiceTranscriptResult(
            transcript=transcript,
            detected_language=str(provider_result.detected_language).strip().lower()[:16],
            available_credits=int(completed["available_credits"]),
        )

    async def process_turn(
        self,
        *,
        user_id: int,
        audio: bytes,
        duration_seconds: int,
        words: Sequence[VoiceWord],
    ) -> VoiceTurnResult:
        if not self.settings.enabled:
            raise VoiceConfigurationError("Voice tutor is disabled")
        if not 1 <= int(duration_seconds) <= self.settings.max_duration_seconds:
            raise ValueError("Voice duration is outside the allowed range")
        if not audio or len(audio) > self.settings.max_audio_bytes:
            raise ValueError("Voice audio size is outside the allowed range")
        state = self.active_session(user_id)
        if state is None or state.next_position >= len(state.vocabulary_ids):
            raise VoiceSessionError("No active voice session")
        by_id = {word.vocabulary_id: word for word in words}
        if set(by_id) != set(state.vocabulary_ids):
            raise VoiceSessionError("Voice session content changed")
        expected = by_id[state.vocabulary_ids[state.next_position]]
        try:
            self.store.recover_stale_ai_usage(
                timeout_seconds=self.settings.reservation_timeout_seconds,
                user_id=user_id,
            )
        except Exception as exc:
            raise VoiceUsageRecoveryError(
                "Stale voice reservation recovery failed"
            ) from exc
        fingerprint = hashlib.sha256(
            f"voice:{state.session_id}:{expected.vocabulary_id}".encode("ascii")
        ).hexdigest()
        charge_credits = self.store.ai_charge_credits(
            user_id, self.settings.credits_per_request
        )
        request_id = self.store.reserve_ai_usage(
            user_id,
            action="voice_transcription",
            provider=self.settings.provider,
            model=self.settings.model,
            credits=charge_credits,
            initial_credits=self.settings.initial_credits,
            context_fingerprint=fingerprint,
        )
        prompt = "; ".join(
            f"{word.target} ({word.speech})" for word in words
        )
        started = perf_counter()
        try:
            self.store.mark_ai_provider_attempt_started(request_id)
            provider_result = await self.provider.transcribe(
                TranscriptionRequest(
                    audio=bytes(audio),
                    language=state.language,
                    prompt=prompt,
                )
            )
            usage, cost_micro_usd, latency_ms = self._record_provider_response(
                request_id=request_id,
                result=provider_result,
                duration_seconds=duration_seconds,
                started=started,
            )
            transcript = str(provider_result.text).strip()
            if not 1 <= len(transcript) <= 1000:
                raise VoiceProviderError("Transcription is empty or too large")
            feedback = evaluate_transcript(
                transcript, expected=expected, words=words
            )
            completed = self.store.complete_voice_usage(
                request_id=request_id,
                session_id=state.session_id,
                user_id=user_id,
                turn_id=str(uuid4()),
                expected_vocabulary_id=expected.vocabulary_id,
                matched_vocabulary_id=(
                    feedback.matched.vocabulary_id if feedback.matched else None
                ),
                transcript=feedback.transcript,
                feedback_code=feedback.code,
                similarity_bps=feedback.similarity_bps,
                transcript_expires_at=utcnow()
                + timedelta(days=self.settings.transcript_retention_days),
                billed_credits=charge_credits,
                provider_response_id=provider_result.response_id,
                model=provider_result.model,
                usage=usage,
                cost_micro_usd=cost_micro_usd,
                latency_ms=latency_ms,
            )
        except BaseException as exc:
            try:
                released = self.store.fail_ai_usage(
                    request_id, error_code=type(exc).__name__
                )
            except Exception as recovery_error:
                raise VoiceUsageRecoveryError(
                    "Voice request failed and its reservation could not be released"
                ) from recovery_error
            if not released:
                raise VoiceUsageRecoveryError(
                    "Voice request reservation state is unknown"
                ) from exc
            raise
        return VoiceTurnResult(
            feedback=feedback,
            session_status=str(completed["session_status"]),
            next_position=int(completed["next_position"]),
            available_credits=int(completed["available_credits"]),
        )


def build_voice_service(
    store: DatabaseStore, settings: VoiceTutorSettings
) -> VoiceTutorService:
    if not settings.enabled:
        provider: TranscriptionProvider = DisabledTranscriptionProvider()
    elif settings.provider == "groq":
        provider = GroqTranscriptionProvider(
            api_key=settings.groq_api_key or "",
            model=settings.model,
        )
    else:
        provider = OpenAITranscriptionProvider(
            api_key=settings.openai_api_key or "",
            model=settings.model,
        )
    return VoiceTutorService(store=store, provider=provider, settings=settings)


def build_openai_voice_service(
    store: DatabaseStore, settings: VoiceTutorSettings
) -> VoiceTutorService:
    """Backward-compatible factory; provider selection is settings-driven."""
    return build_voice_service(store, settings)


@dataclass(frozen=True)
class VoiceTranslationRequest:
    text: str
    source_language: str
    target_language: str


@dataclass(frozen=True)
class VoiceTranslationProviderResult:
    translation: str
    latin_transcription: str
    response_id: str | None
    model: str
    service_tier: str
    status: str
    usage: ProviderUsage
    cost_micro_usd: int = 0
    output_text: str | None = None


@dataclass(frozen=True)
class VoiceTranslationResult:
    detected_language: str
    source_transcript: str
    target_language: str
    translation: str
    latin_transcription: str
    partial: bool
    notice_ru: str


class TranslationProvider(Protocol):
    async def translate(
        self, request: VoiceTranslationRequest
    ) -> VoiceTranslationProviderResult: ...


class DisabledTranslationProvider:
    async def translate(
        self, request: VoiceTranslationRequest
    ) -> VoiceTranslationProviderResult:
        raise VoiceConfigurationError("Voice translation is disabled")


VOICE_TRANSLATION_REQUIREMENTS = (
    "Return an accurate translation plus a readable Latin transcription. "
    "Preserve ambiguity with semicolon-separated variants."
)
VOICE_TRANSLATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "translation": {
            "type": "string",
            "minLength": 1,
            "maxLength": 3000,
        },
        "latin_transcription": {
            "type": "string",
            "minLength": 1,
            "maxLength": 3000,
        },
    },
    "required": ["translation", "latin_transcription"],
}


def serialize_voice_translation_input(request: VoiceTranslationRequest) -> str:
    return json.dumps(
        {
            "source_language": request.source_language,
            "target_language": request.target_language,
            "text": request.text,
            "requirements": VOICE_TRANSLATION_REQUIREMENTS,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


class OpenAITranslationProvider:
    """One-attempt structured translation adapter for completed voice notes."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        service_tier: str = "default",
        client: Any | None = None,
    ):
        if not api_key:
            raise VoiceConfigurationError("OpenAI API key is required")
        self.model = model
        self.service_tier = service_tier
        if client is None:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=api_key, timeout=45.0, max_retries=0)
        self.client = client

    async def translate(
        self, request: VoiceTranslationRequest
    ) -> VoiceTranslationProviderResult:
        response = await self.client.responses.create(
            model=self.model,
            service_tier=self.service_tier,
            input=serialize_voice_translation_input(request),
            max_output_tokens=400,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "voice_translation",
                    "strict": True,
                    "schema": VOICE_TRANSLATION_SCHEMA,
                }
            },
        )
        usage = _attr(response, "usage", None)
        provider_usage = ProviderUsage(
            input_tokens=int(_attr(usage, "input_tokens", 0) or 0),
            output_tokens=int(_attr(usage, "output_tokens", 0) or 0),
            total_tokens=int(_attr(usage, "total_tokens", 0) or 0),
        )
        return VoiceTranslationProviderResult(
            translation="",
            latin_transcription="",
            response_id=str(_attr(response, "id", "")) or None,
            model=str(_attr(response, "model", self.model)),
            service_tier=str(_attr(response, "service_tier", self.service_tier)),
            status=str(_attr(response, "status", "completed")),
            usage=provider_usage,
            output_text=str(_attr(response, "output_text", "")),
        )


class VoiceTranslationService:
    def __init__(
        self,
        *,
        store: DatabaseStore,
        transcription_provider: TranscriptionProvider,
        translation_provider: TranslationProvider,
        settings: VoiceTranslationSettings,
        metering_journal: AIMeteringJournal | None = None,
    ):
        self.store = store
        self.transcription_provider = transcription_provider
        self.translation_provider = translation_provider
        self.settings = settings
        self.metering_journal = metering_journal or AIMeteringJournal(
            getattr(settings, "metering_journal_path", None)
            or "ai-metering-fallback.jsonl"
        )

    @staticmethod
    def _usage(value: Any) -> dict[str, int]:
        if isinstance(value, ProviderUsage):
            return value.as_dict()
        return ProviderUsage(
            input_tokens=max(0, int(_attr(value, "input_tokens", 0) or 0)),
            output_tokens=max(0, int(_attr(value, "output_tokens", 0) or 0)),
            total_tokens=max(0, int(_attr(value, "total_tokens", 0) or 0)),
        ).as_dict()

    def _stt_cost(self, duration_seconds: int) -> int:
        cost = (
            Decimal(
                max(
                    0,
                    int(duration_seconds),
                    int(
                        getattr(
                            self.settings,
                            "stt_minimum_billable_seconds",
                            0,
                        )
                    ),
                )
            )
            * Decimal(str(self.settings.stt_cost_micro_usd_per_minute))
            / Decimal(60)
        )
        return int(cost.to_integral_value(rounding=ROUND_CEILING))

    def _translation_cost(self, result: Any) -> int:
        explicit = int(_attr(result, "cost_micro_usd", 0) or 0)
        if explicit > 0:
            return explicit
        usage = _attr(result, "usage", None)
        input_tokens = max(0, int(_attr(usage, "input_tokens", 0) or 0))
        output_tokens = max(0, int(_attr(usage, "output_tokens", 0) or 0))
        input_rate = Decimal(str(getattr(self.settings, "input_usd_per_million", 0)))
        output_rate = Decimal(str(getattr(self.settings, "output_usd_per_million", 0)))
        return int(
            (input_rate * input_tokens + output_rate * output_tokens).to_integral_value(
                rounding=ROUND_CEILING
            )
        )

    @staticmethod
    def _language_code(value: Any) -> str:
        normalized = str(value or "").strip().casefold()
        aliases = {
            "arabic": "ar",
            "chinese": "zh",
            "english": "en",
            "french": "fr",
            "german": "de",
            "japanese": "ja",
            "russian": "ru",
            "spanish": "es",
            "vietnamese": "vi",
        }
        code = aliases.get(normalized, normalized)
        if not re.fullmatch(r"[a-z]{2,3}", code):
            raise VoiceProviderError("Detected language is invalid")
        return code

    def _translation_preflight_cost(
        self,
        *,
        transcript: str,
        source_language: str,
        target_language: str,
    ) -> int:
        serialized_input = serialize_voice_translation_input(
            VoiceTranslationRequest(
                text=transcript,
                source_language=source_language,
                target_language=target_language,
            )
        )
        serialized_schema = json.dumps(
            VOICE_TRANSLATION_SCHEMA,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        input_tokens = max(
            1,
            (len(serialized_input) + len(serialized_schema) + 1) // 2,
        )
        output_tokens = 400
        input_rate = Decimal(str(getattr(self.settings, "input_usd_per_million", 0)))
        output_rate = Decimal(str(getattr(self.settings, "output_usd_per_million", 0)))
        return int(
            (input_rate * input_tokens + output_rate * output_tokens).to_integral_value(
                rounding=ROUND_CEILING
            )
        )

    def _reservation_budget(self, projected_cost: int) -> dict[str, Any]:
        return {
            "max_daily_requests": int(
                getattr(self.settings, "max_daily_requests_per_user", 5)
            ),
            "economics_snapshot_id": str(
                getattr(
                    self.settings,
                    "economics_snapshot_id",
                    "voice-translation-test",
                )
            ),
            "economics_snapshot_sha256": str(
                getattr(self.settings, "economics_snapshot_sha256", "0" * 64)
            ),
            "projected_cost_micro_usd": int(projected_cost),
            "max_project_cost_micro_usd_per_day": int(
                getattr(
                    self.settings,
                    "max_project_cost_micro_usd_per_day",
                    25000,
                )
            ),
            "max_project_cost_micro_usd_per_month": int(
                getattr(
                    self.settings,
                    "max_project_cost_micro_usd_per_month",
                    100000,
                )
            ),
            "max_in_flight_cost_micro_usd": int(
                getattr(self.settings, "max_in_flight_cost_micro_usd", 5000)
            ),
        }

    def _record_provider_response(
        self,
        *,
        request_id: str,
        result: Any,
        expected_model: str,
        cost_micro_usd: int,
        latency_ms: int,
    ) -> None:
        usage = self._usage(_attr(result, "usage", None))
        model = str(_attr(result, "model", expected_model))
        service_tier = str(
            _attr(result, "service_tier", self.settings.requested_service_tier)
        )
        provider_status = str(_attr(result, "status", "completed"))
        telemetry = {
            "request_id": request_id,
            "provider_response_id": _attr(result, "response_id", None),
            "model": model,
            "service_tier": service_tier,
            "provider_status": provider_status,
            **usage,
            "cost_micro_usd": int(cost_micro_usd),
            "latency_ms": int(latency_ms),
        }
        try:
            self.store.record_ai_provider_response(
                request_id,
                provider_response_id=telemetry["provider_response_id"],
                model=model,
                service_tier=service_tier,
                provider_status=provider_status,
                usage=usage,
                cost_micro_usd=int(cost_micro_usd),
                latency_ms=int(latency_ms),
                expected_model=expected_model,
                expected_service_tier=self.settings.requested_service_tier,
                retrospective_breaker_micro_usd=int(
                    getattr(
                        self.settings,
                        "retrospective_breaker_micro_usd_per_response",
                        self.settings.max_preflight_cost_micro_usd,
                    )
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
            raise VoiceUsageRecoveryError(
                "Voice provider telemetry was journaled after database failure"
            ) from storage_error
        if model != expected_model:
            raise VoiceProviderError("Voice provider returned an unapproved model")
        if service_tier != self.settings.requested_service_tier:
            raise VoiceProviderError(
                "Voice provider returned an unapproved service tier"
            )
        if provider_status != "completed":
            raise VoiceProviderError("Voice provider response did not complete")

    async def translate_note(
        self,
        *,
        user_id: int,
        audio: bytes,
        duration_seconds: int,
        active_language: str,
    ) -> VoiceTranslationResult:
        if not self.settings.enabled:
            raise VoiceConfigurationError("Voice translation is disabled")
        if not 1 <= int(duration_seconds) <= self.settings.max_duration_seconds:
            raise ValueError("Voice duration is outside the allowed range")
        if not audio or len(audio) > self.settings.max_audio_bytes:
            raise ValueError("Voice audio size is outside the allowed range")
        try:
            self.store.recover_stale_ai_usage(
                timeout_seconds=self.settings.reservation_timeout_seconds,
                user_id=user_id,
            )
        except Exception as exc:
            raise VoiceUsageRecoveryError(
                "Stale voice translation reservation recovery failed"
            ) from exc

        stt_cost = self._stt_cost(duration_seconds)
        if stt_cost > self.settings.max_preflight_cost_micro_usd:
            raise AIQuotaExceeded("Voice translation preflight budget exceeded")
        stt_charge_credits = self.store.ai_charge_credits(
            user_id, self.settings.stt_credits_per_request
        )
        stt_request_id = self.store.reserve_ai_usage(
            user_id,
            action="voice_transcription",
            provider=self.settings.provider,
            model=self.settings.transcription_model,
            credits=stt_charge_credits,
            initial_credits=self.settings.initial_credits,
            requested_service_tier=self.settings.requested_service_tier,
            context_fingerprint=hashlib.sha256(
                f"voice-translation-stt:{int(user_id)}:{int(duration_seconds)}".encode(
                    "ascii"
                )
            ).hexdigest(),
            **self._reservation_budget(stt_cost),
        )
        started = perf_counter()
        stt_settlement_started = False
        try:
            self.store.mark_ai_provider_attempt_started(stt_request_id)
            stt = await self.transcription_provider.transcribe(
                TranscriptionRequest(
                    audio=bytes(audio),
                    language="",
                    prompt="",
                    detect_language=True,
                )
            )
            stt_latency_ms = int((perf_counter() - started) * 1000)
            self._record_provider_response(
                request_id=stt_request_id,
                result=stt,
                expected_model=self.settings.transcription_model,
                cost_micro_usd=stt_cost,
                latency_ms=stt_latency_ms,
            )
            transcript = str(_attr(stt, "text", "")).strip()
            if not 1 <= len(transcript) <= 5000:
                raise VoiceProviderError("Voice translation transcript is invalid")
            detected = self._language_code(_attr(stt, "detected_language", ""))
            stt_settlement_started = True
            self.store.complete_ai_usage(
                stt_request_id,
                billed_credits=stt_charge_credits,
                provider_response_id=_attr(stt, "response_id", None),
                model=str(_attr(stt, "model", self.settings.transcription_model)),
                usage=self._usage(_attr(stt, "usage", None)),
                cost_micro_usd=stt_cost,
                latency_ms=stt_latency_ms,
                returned_service_tier=str(
                    _attr(stt, "service_tier", self.settings.requested_service_tier)
                ),
                provider_status=str(_attr(stt, "status", "completed")),
            )
        except BaseException as exc:
            try:
                self.store.fail_ai_usage(
                    stt_request_id,
                    error_code=type(exc).__name__,
                    open_breaker_reason=(
                        "voice_settlement_storage_failure"
                        if stt_settlement_started
                        else None
                    ),
                )
            except Exception as recovery_error:
                raise VoiceUsageRecoveryError(
                    "Voice transcription reservation could not be released"
                ) from recovery_error
            raise

        target_language = (
            str(active_language).strip().lower() if detected == "ru" else "ru"
        )
        if not re.fullmatch(r"[a-z]{2,3}", target_language):
            raise ValueError("Active translation language is invalid")
        translation_preflight_cost = self._translation_preflight_cost(
            transcript=transcript,
            source_language=detected,
            target_language=target_language,
        )
        if translation_preflight_cost > self.settings.max_preflight_cost_micro_usd:
            return VoiceTranslationResult(
                detected_language=detected,
                source_transcript=transcript,
                target_language=target_language,
                translation="",
                latin_transcription="",
                partial=True,
                notice_ru="Распознавание готово, но перевод не начат из-за лимита стоимости.",
            )
        try:
            translation_charge_credits = self.store.ai_charge_credits(
                user_id, self.settings.translation_credits_per_request
            )
            translation_request_id = self.store.reserve_ai_usage(
                user_id,
                action="voice_translation",
                provider="openai",
                model=self.settings.translation_model,
                credits=translation_charge_credits,
                initial_credits=self.settings.initial_credits,
                requested_service_tier=self.settings.requested_service_tier,
                context_fingerprint=hashlib.sha256(
                    f"voice-translation:{detected}:{target_language}".encode("ascii")
                ).hexdigest(),
                **self._reservation_budget(translation_preflight_cost),
            )
        except AIQuotaExceeded:
            return VoiceTranslationResult(
                detected_language=detected,
                source_transcript=transcript,
                target_language=target_language,
                translation="",
                latin_transcription="",
                partial=True,
                notice_ru="Распознавание готово, но перевод не начат из-за лимита.",
            )
        started = perf_counter()
        translation_settlement_started = False
        try:
            self.store.mark_ai_provider_attempt_started(translation_request_id)
            translated = await self.translation_provider.translate(
                VoiceTranslationRequest(
                    text=transcript,
                    source_language=detected,
                    target_language=target_language,
                )
            )
            translation_latency_ms = int((perf_counter() - started) * 1000)
            cost = self._translation_cost(translated)
            self._record_provider_response(
                request_id=translation_request_id,
                result=translated,
                expected_model=self.settings.translation_model,
                cost_micro_usd=cost,
                latency_ms=translation_latency_ms,
            )
            translation = str(_attr(translated, "translation", "")).strip()
            latin = str(_attr(translated, "latin_transcription", "")).strip()
            if not translation or not latin:
                try:
                    content = json.loads(str(_attr(translated, "output_text", "")))
                    translation = str(content["translation"]).strip()
                    latin = str(content["latin_transcription"]).strip()
                except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise VoiceProviderError(
                        "Voice translation output is invalid"
                    ) from exc
            if not 1 <= len(translation) <= 3000 or not 1 <= len(latin) <= 3000:
                raise VoiceProviderError("Voice translation result is invalid")
            translation_settlement_started = True
            self.store.complete_ai_usage(
                translation_request_id,
                billed_credits=translation_charge_credits,
                provider_response_id=_attr(translated, "response_id", None),
                model=str(
                    _attr(translated, "model", self.settings.translation_model)
                ),
                usage=self._usage(_attr(translated, "usage", None)),
                cost_micro_usd=cost,
                latency_ms=translation_latency_ms,
                returned_service_tier=str(
                    _attr(
                        translated,
                        "service_tier",
                        self.settings.requested_service_tier,
                    )
                ),
                provider_status=str(_attr(translated, "status", "completed")),
            )
            return VoiceTranslationResult(
                detected_language=detected,
                source_transcript=transcript,
                target_language=target_language,
                translation=translation,
                latin_transcription=latin,
                partial=False,
                notice_ru="",
            )
        except BaseException as exc:
            try:
                self.store.fail_ai_usage(
                    translation_request_id,
                    error_code=type(exc).__name__,
                    open_breaker_reason=(
                        "voice_settlement_storage_failure"
                        if translation_settlement_started
                        else None
                    ),
                )
            except Exception as recovery_error:
                raise VoiceUsageRecoveryError(
                    "Voice translation reservation could not be released"
                ) from recovery_error
            return VoiceTranslationResult(
                detected_language=detected,
                source_transcript=transcript,
                target_language=target_language,
                translation="",
                latin_transcription="",
                partial=True,
                notice_ru="Распознавание готово, но перевод не завершён.",
            )


def build_voice_translation_service(
    store: DatabaseStore, settings: VoiceTranslationSettings
) -> VoiceTranslationService:
    if not settings.enabled:
        transcription: TranscriptionProvider = DisabledTranscriptionProvider()
        translation: TranslationProvider = DisabledTranslationProvider()
    else:
        if settings.provider == "groq":
            transcription = GroqTranscriptionProvider(
                api_key=settings.groq_api_key or "",
                model=settings.transcription_model,
            )
        else:
            transcription = OpenAITranscriptionProvider(
                api_key=settings.openai_api_key or "",
                model=settings.transcription_model,
            )
        translation = OpenAITranslationProvider(
            api_key=settings.openai_api_key or "",
            model=settings.translation_model,
            service_tier=settings.requested_service_tier,
        )
    return VoiceTranslationService(
        store=store,
        transcription_provider=transcription,
        translation_provider=translation,
        settings=settings,
    )


def build_openai_voice_translation_service(
    store: DatabaseStore, settings: VoiceTranslationSettings
) -> VoiceTranslationService:
    """Backward-compatible factory; STT provider selection is settings-driven."""
    return build_voice_translation_service(store, settings)
