#!/usr/bin/env python3
"""Explicit operator actions for Telegram Stars reconciliation and refunds."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from telegram import Bot

from mydictionary.billing import (
    BillingService,
    BillingSettings,
    TelegramStarsGateway,
)
from mydictionary.storage import DatabaseStore
from mydictionary.telegram_runtime import TelegramRuntimeSettings


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required setting: {name}")
    return value


def _database_url() -> str:
    value = _required("DATABASE_URL")
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+psycopg://", 1)
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


def _reference(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


async def run(args: argparse.Namespace) -> int:
    store = DatabaseStore(_database_url(), migrate=False)
    try:
        settings = BillingSettings.from_env()
        runtime = TelegramRuntimeSettings.from_env()
        runtime.validate_billing_process(
            billing_enabled=settings.enabled,
            terms_version=settings.terms_version,
        )
        service = BillingService(store, settings)
        gateway = TelegramStarsGateway(
            Bot(token=_required("BOT_TOKEN"), **runtime.bot_kwargs())
        )
        if args.command == "reconcile":
            issues = await service.reconcile_gateway(
                gateway, maximum_transactions=args.maximum_transactions
            )
            for issue in issues:
                print(f"{issue.code} reference={_reference(issue.charge_id)}")
            print(f"reconciliation_issues={len(issues)}")
            return 1 if issues else 0
        if not args.execute:
            raise RuntimeError("Refusing a Stars write without --execute")
        if args.command == "process-refund":
            completed = await service.process_refund(
                refund_id=args.refund_id, gateway=gateway
            )
            print("refund_completed=true" if completed else "refund_completed=false")
            return 0 if completed else 1
        completed = await service.set_subscription_autorenew(
            subscription_id=args.subscription_id,
            user_id=args.user_id,
            is_canceled=args.command == "cancel-subscription",
            gateway=gateway,
        )
        print("subscription_updated=true" if completed else "subscription_updated=false")
        return 0 if completed else 1
    finally:
        store.close()


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subcommands = result.add_subparsers(dest="command", required=True)
    reconcile = subcommands.add_parser("reconcile")
    reconcile.add_argument(
        "--maximum-transactions", type=int, default=1000, choices=range(100, 10001)
    )
    refund = subcommands.add_parser("process-refund")
    refund.add_argument("--refund-id", required=True)
    refund.add_argument("--execute", action="store_true")
    for name in ("cancel-subscription", "restore-subscription"):
        subscription = subcommands.add_parser(name)
        subscription.add_argument("--subscription-id", required=True)
        subscription.add_argument("--user-id", required=True, type=int)
        subscription.add_argument("--execute", action="store_true")
    return result


def main() -> int:
    return asyncio.run(run(parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
