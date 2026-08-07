#!/usr/bin/env python3
"""Inspect or reconcile the private AI provider metering fallback journal."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mydictionary.ai_metering import AIMeteringJournal
from mydictionary.storage import DatabaseStore


def _database_url() -> str:
    value = os.environ.get("DATABASE_URL", "").strip()
    if not value:
        raise RuntimeError("DATABASE_URL is required")
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+psycopg://", 1)
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


def _journal() -> AIMeteringJournal:
    configured = os.environ.get("AI_METERING_JOURNAL_PATH", "").strip()
    data_dir = Path(os.environ.get("DATA_DIR", ".")).expanduser()
    return AIMeteringJournal(
        Path(configured).expanduser()
        if configured
        else data_dir / "ai-metering-fallback.jsonl"
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subcommands = result.add_subparsers(dest="command", required=True)
    subcommands.add_parser("status")
    reconcile = subcommands.add_parser("reconcile")
    reconcile.add_argument("--actor", required=True)
    reconcile.add_argument("--execute", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    journal = _journal()
    pending = journal.pending_count()
    if args.command == "status":
        print(json.dumps({"pending_records": pending}, sort_keys=True))
        return 0 if pending == 0 else 2
    if not args.execute:
        raise RuntimeError("Refusing AI metering reconciliation without --execute")
    store = DatabaseStore(_database_url(), migrate=False)
    reconciled = 0

    def apply(record):
        nonlocal reconciled
        if store.reconcile_ai_provider_response(record, actor=args.actor):
            reconciled += 1

    try:
        processed = journal.reconcile(apply)
        print(
            json.dumps(
                {
                    "processed_records": processed,
                    "reconciled_records": reconciled,
                    "breaker_reset": False,
                },
                sort_keys=True,
            )
        )
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
