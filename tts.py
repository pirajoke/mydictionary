"""TTS helper — generates audio pronunciation via edge-tts with file caching."""

import hashlib
import os
from io import BytesIO
from pathlib import Path

import edge_tts

DATA_DIR = Path(os.environ.get("DATA_DIR", str(Path(__file__).parent)))
CACHE_DIR = DATA_DIR / "audio_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

VOICES = {
    "vi": "vi-VN-HoaiMyNeural",
    "en": "en-US-AriaNeural",
}


async def get_audio(text: str, lang: str) -> BytesIO:
    """Return MP3 audio BytesIO for the given text+lang. Uses file cache.

    Speaks the word twice with a pause, at a slower rate for clarity.
    """
    voice = VOICES.get(lang, VOICES["en"])
    key = hashlib.md5(f"{lang}:v2:{text}".encode()).hexdigest()
    cached = CACHE_DIR / f"{lang}_{key}.mp3"

    if not cached.exists():
        # Say the word twice with a pause for better comprehension
        spoken = f"{text} ... {text}"
        communicate = edge_tts.Communicate(spoken, voice, rate="-25%")
        await communicate.save(str(cached))

    buf = BytesIO(cached.read_bytes())
    buf.name = "pronunciation.mp3"
    return buf
