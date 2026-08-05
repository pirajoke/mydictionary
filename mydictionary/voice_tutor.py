"""Metered voice practice with ephemeral audio and honest STT feedback."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING
from difflib import SequenceMatcher
import hashlib
import json
import os
from time import perf_counter
from typing import Any, Mapping, Protocol, Sequence
import unicodedata
from uuid import uuid4

from sqlalchemy import select

from mydictionary.ai_tutor import ProviderUsage
from mydictionary.storage import (
    AIQuotaExceeded,
    AIUsageStateError,
    DatabaseStore,
    VoiceSession,
    VoiceTurn,
    utcnow,
)


class VoiceConfigurationError(RuntimeError):
    """Voice tutor settings are missing or unsafe."""


class VoiceProviderError(RuntimeError):
    """The transcription provider did not return a usable result."""


class VoiceUsageRecoveryError(RuntimeError):
    """A failed voice request could not release its credit reservation."""


class VoiceSessionError(RuntimeError):
    """A voice session is missing, expired, or no longer at the expected turn."""


def _bool(value: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    raise VoiceConfigurationError("VOICE_TUTOR_ENABLED must be a boolean")


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

    @classmethod
    def from_env(
        cls, values: Mapping[str, str] | None = None
    ) -> "VoiceTutorSettings":
        env = values if values is not None else os.environ
        enabled = _bool(env.get("VOICE_TUTOR_ENABLED", "false"))
        provider = str(env.get("VOICE_PROVIDER", "openai")).strip().lower()
        if provider != "openai":
            raise VoiceConfigurationError("VOICE_PROVIDER must be 'openai'")
        model = str(env.get("VOICE_TRANSCRIPTION_MODEL", "gpt-4o-transcribe")).strip()
        if not model or len(model) > 128:
            raise VoiceConfigurationError("VOICE_TRANSCRIPTION_MODEL is invalid")
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
        )
        if enabled:
            if not settings.openai_api_key:
                raise VoiceConfigurationError(
                    "Enabled voice tutor requires OPENAI_API_KEY"
                )
            if settings.cost_micro_usd_per_minute <= 0:
                raise VoiceConfigurationError(
                    "Enabled voice tutor requires VOICE_COST_MICRO_USD_PER_MINUTE"
                )
        return settings

    def estimated_cost_micro_usd(self, duration_seconds: int) -> int:
        value = (
            Decimal(max(0, int(duration_seconds)))
            * self.cost_micro_usd_per_minute
            / Decimal(60)
        )
        return int(value.to_integral_value(rounding=ROUND_CEILING))


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


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    response_id: str | None
    model: str
    usage: ProviderUsage


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

            client = AsyncOpenAI(api_key=api_key, timeout=45.0, max_retries=1)
        self.client = client

    async def transcribe(
        self, request: TranscriptionRequest
    ) -> TranscriptionResult:
        response = await self.client.audio.transcriptions.create(
            file=("voice.ogg", request.audio, "audio/ogg"),
            model=self.model,
            language=request.language,
            prompt=request.prompt[:500],
            response_format="json",
        )
        text = str(_attr(response, "text", "")).strip()
        if not 1 <= len(text) <= 1000:
            raise VoiceProviderError("Transcription is empty or too large")
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
        return TranscriptionResult(
            text=text,
            response_id=str(_attr(response, "id", "")) or None,
            model=str(_attr(response, "model", self.model)),
            usage=provider_usage,
        )


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
        request_id = self.store.reserve_ai_usage(
            user_id,
            action="voice_transcription",
            provider=self.settings.provider,
            model=self.settings.model,
            credits=self.settings.credits_per_request,
            initial_credits=self.settings.initial_credits,
            context_fingerprint=fingerprint,
        )
        prompt = "; ".join(
            f"{word.target} ({word.speech})" for word in words
        )
        started = perf_counter()
        try:
            provider_result = await self.provider.transcribe(
                TranscriptionRequest(
                    audio=bytes(audio),
                    language=state.language,
                    prompt=prompt,
                )
            )
            feedback = evaluate_transcript(
                provider_result.text, expected=expected, words=words
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
                billed_credits=self.settings.credits_per_request,
                provider_response_id=provider_result.response_id,
                model=provider_result.model,
                usage=provider_result.usage.as_dict(),
                cost_micro_usd=self.settings.estimated_cost_micro_usd(
                    duration_seconds
                ),
                latency_ms=int((perf_counter() - started) * 1000),
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


def build_openai_voice_service(
    store: DatabaseStore, settings: VoiceTutorSettings
) -> VoiceTutorService:
    if not settings.enabled:
        provider: TranscriptionProvider = DisabledTranscriptionProvider()
    else:
        provider = OpenAITranscriptionProvider(
            api_key=settings.openai_api_key or "",
            model=settings.model,
        )
    return VoiceTutorService(store=store, provider=provider, settings=settings)
