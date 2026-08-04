import asyncio
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import tts


class TTSContractTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="mydictionary-tts-")
        self.cache_dir = Path(self.temp_dir.name)
        self.cache_patch = patch.object(tts, "CACHE_DIR", self.cache_dir)
        self.cache_patch.start()

    def tearDown(self):
        self.cache_patch.stop()
        self.temp_dir.cleanup()

    async def test_configured_voice_rate_and_text_are_used_and_cached(self):
        communicate = Mock()

        async def save(path):
            Path(path).write_bytes(b"mp3-data")

        communicate.return_value = SimpleNamespace(save=AsyncMock(side_effect=save))
        with patch.object(tts.edge_tts, "Communicate", communicate):
            first = await tts.get_audio(
                "مرحبا",
                voice="ar-SA-ZariyahNeural",
                rate="-20%",
                cache_namespace="ar-basics-100:v1",
            )
            second = await tts.get_audio(
                "مرحبا",
                voice="ar-SA-ZariyahNeural",
                rate="-20%",
                cache_namespace="ar-basics-100:v1",
            )

        communicate.assert_called_once_with(
            "مرحبا ... مرحبا",
            "ar-SA-ZariyahNeural",
            rate="-20%",
        )
        self.assertEqual(first.read(), b"mp3-data")
        self.assertEqual(second.read(), b"mp3-data")

    async def test_cache_is_partitioned_by_pack_voice_and_rate(self):
        communicate = Mock()

        async def save(path):
            Path(path).write_bytes(b"mp3-data")

        communicate.return_value = SimpleNamespace(save=AsyncMock(side_effect=save))
        with patch.object(tts.edge_tts, "Communicate", communicate):
            for voice, rate, namespace in (
                ("voice-a", "-20%", "pack-a:v1"),
                ("voice-b", "-20%", "pack-a:v1"),
                ("voice-a", "-10%", "pack-a:v1"),
                ("voice-a", "-20%", "pack-a:v2"),
            ):
                await tts.get_audio(
                    "term",
                    voice=voice,
                    rate=rate,
                    cache_namespace=namespace,
                )

        self.assertEqual(communicate.call_count, 4)
        self.assertEqual(len(list(self.cache_dir.glob("*.mp3"))), 4)

    async def test_concurrent_cache_misses_use_distinct_temporary_files(self):
        communicate = Mock()
        both_started = asyncio.Event()
        paths = []

        async def save(path):
            paths.append(Path(path))
            if len(paths) == 2:
                both_started.set()
            await both_started.wait()
            Path(path).write_bytes(b"mp3-data")

        communicate.return_value = SimpleNamespace(save=AsyncMock(side_effect=save))
        kwargs = {
            "voice": "voice-a",
            "rate": "-20%",
            "cache_namespace": "pack-a:v1",
        }
        with patch.object(tts.edge_tts, "Communicate", communicate):
            audio = await asyncio.gather(
                tts.get_audio("term", **kwargs),
                tts.get_audio("term", **kwargs),
            )

        self.assertEqual(len(set(paths)), 2)
        self.assertEqual([item.read() for item in audio], [b"mp3-data", b"mp3-data"])
        self.assertEqual(len(list(self.cache_dir.glob("*.mp3"))), 1)
        self.assertFalse(list(self.cache_dir.glob("*.tmp")))

    async def test_missing_configuration_fails_closed(self):
        for field in ("text", "voice", "rate", "cache_namespace"):
            values = {
                "text": "term",
                "voice": "voice-a",
                "rate": "-20%",
                "cache_namespace": "pack-a:v1",
            }
            values[field] = ""
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    await tts.get_audio(
                        values.pop("text"),
                        **values,
                    )


if __name__ == "__main__":
    unittest.main()
