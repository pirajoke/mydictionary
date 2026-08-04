"""TTS helper that generates and caches pack-configured pronunciation."""

import hashlib
import os
import secrets
from io import BytesIO
from pathlib import Path

import edge_tts

DATA_DIR = Path(os.environ.get("DATA_DIR", str(Path(__file__).parent)))
CACHE_DIR = DATA_DIR / "audio_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


async def get_audio(
    text: str,
    *,
    voice: str,
    rate: str,
    cache_namespace: str,
) -> BytesIO:
    """Return cached MP3 audio using an explicitly configured voice.

    Speaks the word twice with a pause, at a slower rate for clarity.
    """
    text = text.strip()
    voice = voice.strip()
    rate = rate.strip()
    cache_namespace = cache_namespace.strip()
    if not all((text, voice, rate, cache_namespace)):
        raise ValueError("TTS text, voice, rate, and cache namespace are required")

    key_source = "\0".join((cache_namespace, voice, rate, text))
    key = hashlib.sha256(key_source.encode("utf-8")).hexdigest()
    cached = CACHE_DIR / f"{key}.mp3"

    if not cached.exists():
        spoken = f"{text} ... {text}"
        communicate = edge_tts.Communicate(spoken, voice, rate=rate)
        temporary = cached.with_suffix(
            f".{os.getpid()}.{secrets.token_hex(4)}.tmp"
        )
        try:
            await communicate.save(str(temporary))
            os.replace(temporary, cached)
        finally:
            temporary.unlink(missing_ok=True)

    buf = BytesIO(cached.read_bytes())
    buf.name = "pronunciation.mp3"
    return buf
