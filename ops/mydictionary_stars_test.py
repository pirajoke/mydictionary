#!/usr/bin/env python3
"""Validate an isolated Telegram Stars test-environment configuration."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mydictionary.billing import BillingSettings
from mydictionary.runtime_secrets import (
    RuntimeSecretError,
    load_telegram_test_credentials_file,
)
from mydictionary.telegram_runtime import TelegramRuntimeSettings


def load_test_credentials(values: dict[str, str]) -> dict[str, str]:
    try:
        return load_telegram_test_credentials_file(values)
    except RuntimeSecretError as exc:
        raise RuntimeError(str(exc)) from exc


def check(values: dict[str, str] | None = None) -> dict[str, str | bool]:
    env = load_test_credentials(
        values if values is not None else dict(os.environ)
    )
    runtime = TelegramRuntimeSettings.from_env(env)
    billing = BillingSettings.from_env(env)
    runtime.validate_billing_process(
        env,
        billing_enabled=billing.enabled,
        terms_version=billing.terms_version,
    )
    if not runtime.is_test:
        raise RuntimeError("Stars test preflight requires TELEGRAM_API_ENVIRONMENT=test")
    return {
        "ok": True,
        **runtime.safe_summary(),
        "stars_enabled": billing.enabled,
        "terms_version": billing.terms_version,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--check", action="store_true", required=True)
    return result


def main() -> int:
    parser().parse_args()
    try:
        print(json.dumps(check(), sort_keys=True))
    except Exception as exc:
        print(
            json.dumps(
                {"ok": False, "error": str(exc), "error_type": type(exc).__name__},
                sort_keys=True,
            )
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
