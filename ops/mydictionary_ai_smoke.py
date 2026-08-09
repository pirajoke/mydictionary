#!/usr/bin/env python3
"""One-attempt, anonymous synthetic smoke for the approved AI pilot."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import json
import os
from pathlib import Path
import re
import tempfile
from time import perf_counter
from typing import Any, Awaitable, Callable, Mapping


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = ROOT / "tests" / "fixtures" / "ai_tutor_eval.json"
EXACT_APPROVAL = "synthetic-ai-pilot-v1"
RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{7,79}")
LANGUAGES = {"en", "fr", "de", "ja", "ar", "zh", "ru", "es"}


class AISmokeError(RuntimeError):
    """Base class for sanitized synthetic-smoke failures."""


class AISmokeConfigurationError(AISmokeError):
    """Raised before a provider attempt when execution is not authorized."""


class AISmokeAlreadyExecutedError(AISmokeError):
    """Raised when an immutable run identifier or receipt already exists."""


class AISmokeExecutionError(AISmokeError):
    """Raised after a failed provider attempt or receipt write."""


Provider = Callable[[Mapping[str, Any]], Awaitable[Mapping[str, Any]]]


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        description="Preview or execute one synthetic AI-pilot provider smoke"
    )
    command.add_argument("--execute", action="store_true")
    command.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    command.add_argument("--receipt", type=Path)
    command.add_argument("--failure-receipt", type=Path)
    command.add_argument("--run-id")
    return command


def _integer(value: Any, *, default: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, parsed)


def _load_fixture(path: Path) -> list[Mapping[str, Any]]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AISmokeConfigurationError(
            "Synthetic evaluation fixture is unavailable"
        ) from exc
    if (
        not isinstance(payload, list)
        or len(payload) != 8
        or {str(case.get("language", "")) for case in payload} != LANGUAGES
    ):
        raise AISmokeConfigurationError(
            "Synthetic evaluation fixture must contain eight launch languages"
        )
    required = {
        "id",
        "language",
        "term",
        "transcription",
        "meaning_ru",
        "summary_ru",
        "explanation_ru",
        "examples",
    }
    if any(not isinstance(case, Mapping) or not required <= set(case) for case in payload):
        raise AISmokeConfigurationError("Synthetic evaluation fixture is invalid")
    return payload


def _validate_configuration(environment: Mapping[str, str]) -> None:
    required_values = {
        "AI_MODEL": "gpt-5.6-luna",
        "AI_SERVICE_TIER": "default",
        "AI_INPUT_USD_PER_MILLION": "0.20",
        "AI_CACHED_INPUT_USD_PER_MILLION": "0.02",
        "AI_CACHE_WRITE_USD_PER_MILLION": "0.25",
        "AI_OUTPUT_USD_PER_MILLION": "1.20",
    }
    if environment.get("AI_SYNTHETIC_SMOKE_APPROVAL") != EXACT_APPROVAL:
        raise AISmokeConfigurationError(
            "Exact synthetic-smoke approval gate is required"
        )
    if any(environment.get(name) != value for name, value in required_values.items()):
        raise AISmokeConfigurationError("Synthetic-smoke model or rates differ")
    if str(environment.get("AI_TUTOR_ENABLED", "")).casefold() != "false":
        raise AISmokeConfigurationError(
            "Synthetic smoke requires production AI to remain disabled"
        )
    if str(environment.get("VOICE_TUTOR_ENABLED", "")).casefold() != "false":
        raise AISmokeConfigurationError("Voice must remain disabled")
    if str(environment.get("TELEGRAM_STARS_ENABLED", "")).casefold() != "false":
        raise AISmokeConfigurationError("Telegram Stars must remain disabled")
    if not environment.get("OPENAI_API_KEY") or len(
        environment.get("AI_SAFETY_SALT", "")
    ) < 16:
        raise AISmokeConfigurationError("Synthetic provider configuration is missing")
    if _integer(
        environment.get("AI_MAX_PREFLIGHT_COST_MICRO_USD_PER_REQUEST"),
        default=-1,
    ) <= 0:
        raise AISmokeConfigurationError("Synthetic-smoke cost limit is invalid")


def _cost_micro_usd(
    usage: Mapping[str, Any], environment: Mapping[str, str]
) -> int:
    try:
        input_tokens = _integer(usage.get("input_tokens"))
        cached_input_tokens = _integer(usage.get("cached_input_tokens"))
        cache_write_tokens = _integer(usage.get("cache_write_tokens"))
        uncached_input_tokens = max(
            0, input_tokens - cached_input_tokens - cache_write_tokens
        )
        cost = (
            Decimal(uncached_input_tokens)
            * Decimal(environment["AI_INPUT_USD_PER_MILLION"])
            + Decimal(cached_input_tokens)
            * Decimal(environment["AI_CACHED_INPUT_USD_PER_MILLION"])
            + Decimal(cache_write_tokens)
            * Decimal(environment["AI_CACHE_WRITE_USD_PER_MILLION"])
            + Decimal(_integer(usage.get("output_tokens")))
            * Decimal(environment["AI_OUTPUT_USD_PER_MILLION"])
        )
    except (InvalidOperation, KeyError) as exc:
        raise AISmokeExecutionError("Synthetic usage cannot be costed") from exc
    return int(cost.to_integral_value(rounding=ROUND_CEILING))


def _receipt(
    *,
    observed_at: datetime,
    model: str,
    service_tier: str,
    usage: Mapping[str, Any],
    cost_micro_usd: int,
    latency_ms: int,
    passed: bool,
    failure_code: str | None,
) -> dict[str, Any]:
    return {
        "date": observed_at.astimezone(timezone.utc).date().isoformat(),
        "model": model,
        "service_tier": service_tier,
        "input_tokens": _integer(usage.get("input_tokens")),
        "cached_input_tokens": _integer(usage.get("cached_input_tokens")),
        "cache_write_tokens": _integer(usage.get("cache_write_tokens")),
        "output_tokens": _integer(usage.get("output_tokens")),
        "total_tokens": _integer(usage.get("total_tokens")),
        "cost_micro_usd": _integer(cost_micro_usd),
        "latency_ms": _integer(latency_ms),
        "passed": bool(passed),
        "failure_code": failure_code,
    }


def _atomic_write_receipt(path: Path, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_temp = tempfile.mkstemp(
        prefix=f".{target.name}.", dir=target.parent
    )
    temporary = Path(raw_temp)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        target.chmod(0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def _reserve_run(environment: Mapping[str, str], run_id: str) -> None:
    runs_dir = Path(environment.get("AI_SYNTHETIC_SMOKE_RUNS_DIR", ""))
    if not str(runs_dir) or str(runs_dir) == ".":
        raise AISmokeConfigurationError("Synthetic-smoke runs directory is required")
    try:
        runs_dir.mkdir(parents=True, exist_ok=True)
        marker = runs_dir / f"{run_id}.attempted"
        descriptor = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
    except FileExistsError as exc:
        raise AISmokeAlreadyExecutedError(
            "Synthetic-smoke run identifier was already used"
        ) from exc
    except OSError as exc:
        raise AISmokeConfigurationError(
            "Synthetic-smoke run reservation failed"
        ) from exc


def _validate_result(
    result: Mapping[str, Any],
    *,
    fixture: list[Mapping[str, Any]],
    environment: Mapping[str, str],
) -> tuple[Mapping[str, Any], int, int]:
    if result.get("model") != environment["AI_MODEL"]:
        raise AISmokeExecutionError("wrong_model")
    if result.get("service_tier") != environment["AI_SERVICE_TIER"]:
        raise AISmokeExecutionError("wrong_tier")
    if result.get("status") != "completed":
        raise AISmokeExecutionError("provider_incomplete")
    output = result.get("structured_output")
    returned_cases = output.get("cases") if isinstance(output, Mapping) else None
    if not isinstance(returned_cases, list) or len(returned_cases) != len(fixture):
        raise AISmokeExecutionError("invalid_output")
    expected_by_id = {str(case["id"]): case for case in fixture}
    for returned in returned_cases:
        if not isinstance(returned, Mapping):
            raise AISmokeExecutionError("invalid_output")
        expected = expected_by_id.get(str(returned.get("id", "")))
        if expected is None or any(
            returned.get(field) != expected[field]
            for field in ("term", "summary_ru", "explanation_ru", "examples")
        ):
            raise AISmokeExecutionError("ungrounded_output")
    usage = result.get("usage")
    if not isinstance(usage, Mapping):
        raise AISmokeExecutionError("invalid_usage")
    cost = _cost_micro_usd(usage, environment)
    reported_cost = _integer(result.get("cost_micro_usd"), default=-1)
    limit = int(environment["AI_MAX_PREFLIGHT_COST_MICRO_USD_PER_REQUEST"])
    if reported_cost != cost:
        raise AISmokeExecutionError("invalid_cost")
    if cost > limit:
        raise AISmokeExecutionError("cost_limit_exceeded")
    return usage, cost, _integer(result.get("latency_ms"))


async def run_smoke(
    *,
    environment: Mapping[str, str],
    provider: Provider,
    fixture_path: Path,
    receipt_path: Path,
    run_id: str,
    execute: bool = False,
    failure_receipt_path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Preview by default; execute at most one anonymous provider attempt."""
    fixture = _load_fixture(Path(fixture_path))
    preview = {
        "status": "preview",
        "model": environment.get("AI_MODEL", ""),
        "service_tier": environment.get("AI_SERVICE_TIER", ""),
        "evaluation_languages": len(fixture),
        "provider_attempts": 0,
    }
    if not execute:
        return preview
    _validate_configuration(environment)
    if not RUN_ID_RE.fullmatch(str(run_id)):
        raise AISmokeConfigurationError("Synthetic-smoke run identifier is invalid")
    receipt_target = Path(receipt_path)
    if receipt_target.is_file() or receipt_target.is_symlink():
        raise AISmokeAlreadyExecutedError("Synthetic-smoke receipt already exists")
    _reserve_run(environment, str(run_id))

    observed_at = now or datetime.now(timezone.utc)
    usage: Mapping[str, Any] = {}
    cost = 0
    latency = 0
    request = {
        "model": environment["AI_MODEL"],
        "service_tier": environment["AI_SERVICE_TIER"],
        "evaluation_cases": fixture,
    }
    try:
        result = await provider(request)
        if not isinstance(result, Mapping):
            raise AISmokeExecutionError("invalid_provider_result")
        raw_usage = result.get("usage")
        if isinstance(raw_usage, Mapping):
            usage = raw_usage
        cost = _integer(result.get("cost_micro_usd"))
        latency = _integer(result.get("latency_ms"))
        usage, cost, latency = _validate_result(
            result, fixture=fixture, environment=environment
        )
        receipt = _receipt(
            observed_at=observed_at,
            model=environment["AI_MODEL"],
            service_tier=environment["AI_SERVICE_TIER"],
            usage=usage,
            cost_micro_usd=cost,
            latency_ms=latency,
            passed=True,
            failure_code=None,
        )
    except Exception as exc:
        failure_code = (
            str(exc)
            if isinstance(exc, AISmokeExecutionError)
            and re.fullmatch(r"[a-z][a-z0-9_]{2,63}", str(exc))
            else "provider_failure"
        )
        receipt = _receipt(
            observed_at=observed_at,
            model=environment["AI_MODEL"],
            service_tier=environment["AI_SERVICE_TIER"],
            usage=usage,
            cost_micro_usd=cost,
            latency_ms=latency,
            passed=False,
            failure_code=failure_code,
        )
        try:
            _atomic_write_receipt(receipt_target, receipt)
        except OSError:
            emergency = failure_receipt_path or receipt_target.with_name(
                f"{receipt_target.name}.failed.json"
            )
            storage_receipt = dict(receipt)
            storage_receipt["failure_code"] = "receipt_storage_failure"
            _atomic_write_receipt(Path(emergency), storage_receipt)
        raise AISmokeExecutionError(failure_code) from None

    try:
        _atomic_write_receipt(receipt_target, receipt)
    except OSError:
        emergency = failure_receipt_path or receipt_target.with_name(
            f"{receipt_target.name}.failed.json"
        )
        storage_receipt = dict(receipt)
        storage_receipt["passed"] = False
        storage_receipt["failure_code"] = "receipt_storage_failure"
        _atomic_write_receipt(Path(emergency), storage_receipt)
        raise AISmokeExecutionError("receipt_storage_failure") from None
    return receipt


class OpenAISyntheticProvider:
    """Single-attempt Responses API adapter used only by this operator command."""

    def __init__(self, api_key: str, environment: Mapping[str, str]):
        from openai import AsyncOpenAI

        self.client = AsyncOpenAI(api_key=api_key, timeout=25.0, max_retries=0)
        self.environment = dict(environment)

    async def __call__(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        started = perf_counter()
        response = await self.client.responses.create(
            model=request["model"],
            service_tier=request["service_tier"],
            instructions=(
                "Return the supplied eight evaluation cases unchanged as JSON. "
                "Do not add facts or identifiers."
            ),
            input=json.dumps(
                {"evaluation_cases": request["evaluation_cases"]},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            max_output_tokens=4000,
            reasoning={"effort": "low"},
            text={
                "format": {
                    "type": "json_schema",
                    "name": "mydictionary_synthetic_evaluation",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "cases": {
                                "type": "array",
                                "minItems": 8,
                                "maxItems": 8,
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "id": {"type": "string"},
                                        "term": {"type": "string"},
                                        "summary_ru": {"type": "string"},
                                        "explanation_ru": {"type": "string"},
                                        "examples": {
                                            "type": "array",
                                            "minItems": 2,
                                            "maxItems": 2,
                                            "items": {
                                                "type": "object",
                                                "additionalProperties": False,
                                                "properties": {
                                                    "target": {"type": "string"},
                                                    "russian": {"type": "string"},
                                                },
                                                "required": ["target", "russian"],
                                            },
                                        },
                                    },
                                    "required": [
                                        "id",
                                        "term",
                                        "summary_ru",
                                        "explanation_ru",
                                        "examples",
                                    ],
                                },
                            }
                        },
                        "required": ["cases"],
                    },
                }
            },
            store=False,
        )
        usage = getattr(response, "usage", None)
        details = getattr(usage, "input_tokens_details", None)
        output = json.loads(str(getattr(response, "output_text", "")))
        usage_values = {
            "input_tokens": _integer(getattr(usage, "input_tokens", 0)),
            "cached_input_tokens": _integer(
                getattr(details, "cached_tokens", 0)
            ),
            "cache_write_tokens": _integer(
                getattr(details, "cache_write_tokens", 0)
            ),
            "output_tokens": _integer(getattr(usage, "output_tokens", 0)),
            "total_tokens": _integer(getattr(usage, "total_tokens", 0)),
        }
        return {
            "model": str(getattr(response, "model", "")),
            "service_tier": str(getattr(response, "service_tier", "")),
            "status": str(getattr(response, "status", "")),
            "structured_output": output,
            "usage": usage_values,
            "cost_micro_usd": _cost_micro_usd(
                usage_values, self.environment
            ),
            "latency_ms": int((perf_counter() - started) * 1000),
        }


async def _main() -> int:
    args = parser().parse_args()
    environment = dict(os.environ)
    run_id = args.run_id or datetime.now(timezone.utc).strftime(
        "synthetic-%Y%m%dT%H%M%SZ"
    )
    receipt = args.receipt or Path(
        environment.get("AI_SYNTHETIC_SMOKE_RECEIPT", "ai-smoke-receipt.json")
    )
    if args.execute:
        provider = OpenAISyntheticProvider(
            environment.get("OPENAI_API_KEY", ""), environment
        )
    else:
        async def provider(_request: Mapping[str, Any]) -> Mapping[str, Any]:
            raise AssertionError("Preview must not call the provider")
    try:
        result = await run_smoke(
            environment=environment,
            provider=provider,
            fixture_path=args.fixture,
            receipt_path=receipt,
            failure_receipt_path=args.failure_receipt,
            run_id=run_id,
            execute=args.execute,
        )
    except AISmokeError as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__}))
        return 1
    print(json.dumps({"ok": True, **result}, sort_keys=True))
    return 0


def main() -> int:
    return asyncio.run(_main())


if __name__ == "__main__":
    raise SystemExit(main())
