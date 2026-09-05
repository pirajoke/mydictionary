#!/usr/bin/env python3
"""Preview or execute Lexi retention and user erasure."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mydictionary.privacy import (
    RetentionPolicy,
    apply_retention,
    erase_user_learning_data,
    retention_report,
)
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


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subcommands = result.add_subparsers(dest="command", required=True)
    retention = subcommands.add_parser("retention")
    retention.add_argument("--execute", action="store_true")
    erase = subcommands.add_parser("erase-user")
    erase.add_argument("--user-id", required=True, type=int)
    erase.add_argument("--actor", required=True)
    erase.add_argument("--execute", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    store = DatabaseStore(_database_url(), migrate=False)
    try:
        if args.command == "retention":
            policy = RetentionPolicy.from_env()
            report = (
                apply_retention(store, policy)
                if args.execute
                else retention_report(store, policy)
            )
            print(json.dumps(asdict(report), sort_keys=True))
            print("mode=execute" if args.execute else "mode=preview")
            return 0
        if not args.execute:
            raise RuntimeError("Refusing user erasure without --execute")
        result = erase_user_learning_data(
            store, user_id=args.user_id, actor=args.actor
        )
        print(
            json.dumps(
                {
                    "already_erased": result.already_erased,
                    "deleted_rows": result.deleted_rows,
                    "user_reference": result.user_reference,
                },
                sort_keys=True,
            )
        )
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
