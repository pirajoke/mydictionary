#!/usr/bin/env python3
"""Privacy-safe operator actions for the production Stars owner canary."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from telegram import Bot

from mydictionary.billing import (
    BillingSettings,
    ProductionStarsCanaryService,
    ProductionStarsCanarySettings,
    TelegramStarsGateway,
    TelegramStarsGatewayProtocol,
    read_production_stars_canary_status,
)
from mydictionary.stars_launch import build_production_stars_canary_receipt
from mydictionary.runtime_secrets import load_bot_token_file
from mydictionary.storage import DatabaseStore
from mydictionary.telegram_runtime import TelegramRuntimeSettings


def _required(values: Mapping[str, str], name: str) -> str:
    value = str(values.get(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required setting: {name}")
    return value


def _database_url(values: Mapping[str, str]) -> str:
    value = _required(values, "DATABASE_URL")
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+psycopg://", 1)
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


def status_report(
    store: DatabaseStore,
    values: Mapping[str, str],
) -> dict[str, Any]:
    """Return only the fixed aggregate canary status schema."""
    settings = ProductionStarsCanarySettings.from_env(values)
    return read_production_stars_canary_status(
        store=store,
        canary_settings=settings,
    )


async def recover(
    service: ProductionStarsCanaryService,
    *,
    gateway: TelegramStarsGatewayProtocol,
    execute: bool,
) -> dict[str, Any]:
    """Run only the service's reconciliation-first explicit recovery path."""
    if not execute:
        raise RuntimeError("Refusing refund recovery without --execute")
    completed = await service.recover_current_refund(gateway=gateway)
    state = str(service.status().get("state") or "blocked")
    if not completed or state != "refunded":
        raise RuntimeError("Refund recovery did not reach refunded state")
    return {"ok": True, "operation": "recover", "state": "refunded"}


def write_receipt(
    status: Mapping[str, Any],
    output: Path,
    *,
    execute: bool,
    completed_at: datetime | None = None,
) -> dict[str, Any]:
    """Exclusively create a mode-0600 aggregate final receipt."""
    if not execute:
        raise RuntimeError("Refusing receipt creation without --execute")
    receipt = build_production_stars_canary_receipt(
        status,
        completed_at=completed_at,
    )
    target = Path(output)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(target, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            json.dump(
                receipt,
                handle,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return {"ok": True, "operation": "receipt", "state": "refunded"}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    recovery = commands.add_parser("recover")
    recovery.add_argument("--execute", action="store_true")
    receipt = commands.add_parser("receipt")
    receipt.add_argument("--output", type=Path, required=True)
    receipt.add_argument("--execute", action="store_true")
    return result


async def run(
    args: argparse.Namespace,
    values: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    env = dict(values if values is not None else os.environ)
    if args.command == "recover":
        if not args.execute:
            raise RuntimeError("Refusing refund recovery without --execute")
        env = load_bot_token_file(env)
    store = DatabaseStore(_database_url(env), migrate=False)
    try:
        if args.command == "status":
            return status_report(store, env)
        if args.command == "receipt":
            return write_receipt(
                status_report(store, env),
                args.output,
                execute=bool(args.execute),
            )
        canary_settings = ProductionStarsCanarySettings.from_env(env)
        service = ProductionStarsCanaryService(
            store,
            BillingSettings.from_env(env),
            canary_settings,
        )
        runtime = TelegramRuntimeSettings.from_env(env)
        gateway = TelegramStarsGateway(
            Bot(
                token=_required(env, "BOT_TOKEN"),
                **runtime.bot_kwargs(),
            )
        )
        return await recover(
            service,
            gateway=gateway,
            execute=True,
        )
    finally:
        store.close()


def main() -> int:
    args = parser().parse_args()
    try:
        result = asyncio.run(run(args))
    except Exception:
        print(
            json.dumps(
                {
                    "ok": False,
                    "operation": args.command,
                    "error_code": "blocked",
                },
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
