"""Ephemeral speech rendering for Mirror Assistant responses."""

from __future__ import annotations

from io import BytesIO
import os
from typing import Any, Protocol


class AssistantSpeechError(RuntimeError):
    """Raised when safe in-memory speech rendering is unavailable."""


class SpeechTransport(Protocol):
    async def synthesize(self, text: str) -> bytes: ...


class OpenAISpeechTransport:
    """Minimal adapter around the already-supported OpenAI audio boundary."""

    def __init__(self, *, client: Any | None = None):
        if client is None:
            api_key = str(os.environ.get("OPENAI_API_KEY") or "").strip()
            if not api_key:
                raise AssistantSpeechError("Speech provider is not configured")
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=api_key, timeout=25.0, max_retries=0)
        self.client = client

    async def synthesize(self, text: str) -> bytes:
        response = await self.client.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice="alloy",
            input=text,
            response_format="mp3",
        )
        content = getattr(response, "content", response)
        if callable(getattr(content, "read", None)):
            content = content.read()
            if hasattr(content, "__await__"):
                content = await content
        try:
            return bytes(content)
        except (TypeError, ValueError) as exc:
            raise AssistantSpeechError("Speech provider returned invalid audio") from exc


def build_mirror_speech_renderer(*, transport: SpeechTransport | None = None):
    """Build an async renderer that retains audio only in memory."""
    selected = transport or OpenAISpeechTransport()

    async def render(text: str) -> BytesIO:
        safe_text = str(text).strip()
        if not 1 <= len(safe_text) <= 4096:
            raise AssistantSpeechError("Speech text is outside the safe size limit")
        payload = await selected.synthesize(safe_text)
        if not payload or len(payload) > 20 * 1024 * 1024:
            raise AssistantSpeechError("Speech audio is outside the safe size limit")
        audio = BytesIO(payload)
        audio.name = "mirror-response.mp3"
        return audio

    return render
