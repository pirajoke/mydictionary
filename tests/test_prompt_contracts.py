import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest


os.environ.setdefault("BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("ALLOWED_USER_ID", "1")
os.environ.setdefault("ALLOW_SQLITE_DEV", "true")

import bot
from mydictionary.ai_tutor import (
    OpenAIResponsesProvider,
    TutorContext,
    TutorRequest,
    TutorWord,
)


ROOT = Path(__file__).resolve().parents[1]


def normalized_reviewed_prompt(path: Path) -> str:
    reviewed = path.read_text(encoding="utf-8")
    return reviewed[:-1] if reviewed.endswith("\n") else reviewed


def require_prompt_contracts(testcase: unittest.TestCase):
    try:
        module = importlib.import_module("mydictionary.prompt_contracts")
    except ModuleNotFoundError:
        testcase.fail(
            "missing prompt-contract loader: mydictionary.prompt_contracts"
        )
    testcase.assertTrue(
        hasattr(module, "PromptContractError"),
        "missing non-secret prompt configuration error type",
    )
    testcase.assertTrue(
        hasattr(module, "load_prompt_contract"),
        "missing public prompt-contract loader",
    )
    return module


class CaptureResponses:
    def __init__(self):
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        schema_name = kwargs["text"]["format"]["name"]
        if "mirror" in schema_name:
            payload = {
                "answer_ru": "Короткий ответ.",
                "language_items": [],
                "examples": [],
                "next_step_ru": "Продолжить практику.",
            }
        else:
            payload = {
                "summary_ru": "Короткое объяснение.",
                "entries": [
                    {
                        "term": "bonjour",
                        "explanation_ru": "Приветствие.",
                        "examples": [
                            {"target": "Bonjour !", "russian": "Здравствуйте!"},
                            {"target": "Bonjour, Marie.", "russian": "Привет, Мари."},
                        ],
                    }
                ],
            }
        return SimpleNamespace(
            id="prompt-contract-test",
            model="gpt-test",
            service_tier="default",
            status="completed",
            output_text=json.dumps(payload, ensure_ascii=False),
            usage=SimpleNamespace(
                input_tokens=1,
                input_tokens_details=SimpleNamespace(
                    cached_tokens=0,
                    cache_write_tokens=0,
                ),
                output_tokens=1,
                output_tokens_details=SimpleNamespace(reasoning_tokens=0),
                total_tokens=2,
            ),
        )


def provider_with(responses: CaptureResponses) -> OpenAIResponsesProvider:
    return OpenAIResponsesProvider(
        api_key="test-key",
        model="gpt-test",
        service_tier="default",
        safety_salt="prompt-contract-test-safety-salt",
        client=SimpleNamespace(responses=responses),
    )


class RuntimePromptContractTest(unittest.IsolatedAsyncioTestCase):
    async def test_ac_1_ai_tutor_runtime_uses_exact_reviewed_contract(self):
        responses = CaptureResponses()

        await provider_with(responses).generate(
            TutorRequest(
                request_id="ai-prompt-contract",
                user_id=1,
                question="Explique bonjour",
                context=TutorContext(
                    language="fr",
                    topic="greetings",
                    words=(
                        TutorWord(
                            term="bonjour",
                            transcription="/bɔ̃.ʒuʁ/",
                            meaning_ru="здравствуйте",
                        ),
                    ),
                ),
            )
        )

        self.assertEqual(
            responses.kwargs["instructions"],
            normalized_reviewed_prompt(ROOT / "prompts/ai-tutor-v1.txt"),
        )

    async def test_ac_2_mirror_runtime_uses_exact_reviewed_v7_contract_and_token_cap(self):
        responses = CaptureResponses()
        payload = bot.build_mirror_provider_payload(
            question="Comment employer bonjour ?",
            admin_guidance="Réponds comme un professeur bienveillant.",
            grounded_snapshot={"language": "fr", "has_progress": True},
            learning_context={
                "language": "fr",
                "words": [
                    {
                        "target": "bonjour",
                        "transcription": "/bɔ̃.ʒuʁ/",
                        "meaning_ru": "здравствуйте",
                    }
                ],
            },
        )

        await provider_with(responses).generate_mirror(
            request_id="mirror-prompt-contract",
            user_id=1,
            payload=payload,
        )

        self.assertEqual(
            responses.kwargs["instructions"],
            normalized_reviewed_prompt(ROOT / "prompts/mirror-v7.txt"),
        )
        self.assertEqual(responses.kwargs["max_output_tokens"], 480)


class PromptLoaderContractTest(unittest.TestCase):
    def test_ec_1_unicode_and_multiline_are_preserved_semantically(self):
        contracts = require_prompt_contracts(self)
        reviewed = "First line\nПривет, 世界 👋\nDernière ligne\n"
        with tempfile.TemporaryDirectory(prefix="prompt-contract-unicode-") as temp:
            path = Path(temp) / "reviewed.txt"
            path.write_text(reviewed, encoding="utf-8")

            loaded = contracts.load_prompt_contract(path)

        self.assertEqual(loaded, reviewed[:-1])
        self.assertIn("Привет, 世界 👋", loaded)
        self.assertEqual(loaded.splitlines(), reviewed.splitlines())

    def test_err_1_unsafe_invalid_or_blank_contracts_fail_closed(self):
        contracts = require_prompt_contracts(self)
        error_type = contracts.PromptContractError
        secret_marker = "PROMPT_CONTENT_MUST_NOT_LEAK"
        with tempfile.TemporaryDirectory(prefix="prompt-contract-invalid-") as temp:
            root = Path(temp)
            missing = root / "missing.txt"
            directory = root / "directory.txt"
            directory.mkdir()
            target = root / "target.txt"
            target.write_text(secret_marker, encoding="utf-8")
            symlink = root / "symlink.txt"
            symlink.symlink_to(target)
            invalid_utf8 = root / "invalid-utf8.txt"
            invalid_utf8.write_bytes(b"\xff\xfe" + secret_marker.encode("ascii"))
            blank = root / "blank.txt"
            blank.write_text(" \n\t\n", encoding="utf-8")

            cases = {
                "missing": missing,
                "non-regular": directory,
                "symlinked": symlink,
                "invalid UTF-8": invalid_utf8,
                "blank": blank,
            }
            for label, path in cases.items():
                with self.subTest(case=label):
                    with self.assertRaises(error_type) as raised:
                        contracts.load_prompt_contract(path)
                    message = str(raised.exception)
                    self.assertTrue(message.strip())
                    self.assertNotIn(secret_marker, message)

    def test_err_1_runtime_import_uses_fail_closed_contract_loader(self):
        contracts = require_prompt_contracts(self)
        script = """
import importlib
from mydictionary import prompt_contracts

def reject(_path):
    raise prompt_contracts.PromptContractError(
        "prompt contract configuration error"
    )

prompt_contracts.load_prompt_contract = reject
try:
    importlib.import_module("mydictionary.ai_tutor")
except prompt_contracts.PromptContractError as exc:
    print(type(exc).__name__)
    print(str(exc))
else:
    raise SystemExit("runtime import did not fail closed")
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            env={**os.environ, "PYTHONPATH": str(ROOT)},
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(contracts.PromptContractError.__name__, result.stdout)
        self.assertNotIn("api_key", (result.stdout + result.stderr).casefold())


class PromptLibraryDocumentationTest(unittest.TestCase):
    def test_ac_3_readme_traces_contracts_consumers_evaluations_and_changes(self):
        readme = (ROOT / "prompts/README.md").read_text(encoding="utf-8")
        normalized = " ".join(readme.casefold().split())

        expected_contracts = (
            (
                "ai-tutor-v1.txt",
                "openairesponsesprovider.generate",
                "tests/fixtures/ai_tutor_eval.json",
            ),
            (
                "mirror-v7.txt",
                "openairesponsesprovider.generate_mirror",
                "tests/fixtures/mirror_quality_v2.json",
            ),
        )
        for filename, consumer, evaluation in expected_contracts:
            with self.subTest(contract=filename):
                self.assertIn(filename, normalized)
                self.assertIn(consumer, normalized)
                self.assertIn(evaluation, normalized)

        self.assertTrue((ROOT / "prompts/mirror-v6.txt").is_file())
        self.assertIn("mirror-v6.txt", normalized)
        self.assertIn("historical", normalized)
        self.assertIn("mirror-v7.txt", normalized)
        self.assertIn("active", normalized)

        self.assertIn("change procedure", normalized)
        for required_step in ("new version", "review", "evaluation", "test"):
            with self.subTest(change_step=required_step):
                self.assertIn(required_step, normalized)


if __name__ == "__main__":
    unittest.main()
