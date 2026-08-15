#!/usr/bin/env python3
"""Check and activate a fully proven Stars one-time-product launch."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from mydictionary.admin_store import AdminStore
from mydictionary.billing import BillingService, BillingSettings
from mydictionary.stars_launch import stars_launch_readiness
from mydictionary.storage import (
    AdminAuditLog,
    BillingProduct,
    DatabaseStore,
    utcnow,
)


ONE_TIME_PRODUCT_IDS = ("ai-mini", "ai-starter", "ai-value")


def _database_url(values: Mapping[str, str]) -> str:
    value = str(values.get("DATABASE_URL") or "").strip()
    if not value:
        raise RuntimeError("DATABASE_URL is required")
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+psycopg://", 1)
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


def _products(store: DatabaseStore) -> list[dict[str, Any]]:
    query_settings = BillingSettings(
        enabled=False,
        payload_secret=None,
        support_contact="",
        terms_text="Stars launch readiness",
    )
    return AdminStore(store, query_settings).billing_products()


def check_readiness(
    store: DatabaseStore,
    values: Mapping[str, str],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return privacy-safe local gates without network access or writes."""
    return stars_launch_readiness(values, _products(store), now=now)


def activate_products(
    store: DatabaseStore,
    values: Mapping[str, str],
    *,
    actor: str,
    execute: bool,
    now: datetime | None = None,
) -> dict[str, int]:
    """Activate only the approved one-time catalog after every gate passes."""
    if not execute:
        raise RuntimeError("Refusing a database write without --execute")
    settings = BillingSettings.from_env(values)
    billing = BillingService(store, settings)
    result = {"activated": 0, "unchanged": 0}
    with store.Session.begin() as session:
        locked_rows = session.execute(
            select(BillingProduct).order_by(BillingProduct.product_id).with_for_update()
        ).scalars().all()
        products = [
            {
                column.name: getattr(row, column.name)
                for column in BillingProduct.__table__.columns
            }
            for row in locked_rows
        ]
        readiness = stars_launch_readiness(values, products, now=now)
        if not readiness["ready"]:
            raise RuntimeError("Stars launch is not ready")
        rows = {row.product_id: row for row in locked_rows}
        for product_id in ONE_TIME_PRODUCT_IDS:
            row = rows[product_id]
            if row.status == "active":
                result["unchanged"] += 1
                continue
            estimated_margin = billing.product_margin_bps(row)
            if (
                row.status != "draft"
                or estimated_margin is None
                or estimated_margin < row.target_margin_bps
            ):
                raise RuntimeError("Stars launch catalog changed during activation")
            row.status = "active"
            row.updated_at = utcnow()
            session.add(
                AdminAuditLog(
                    actor=str(actor)[:64],
                    action="billing_product_updated",
                    target_type="billing_product",
                    target_id=product_id,
                    details_json=json.dumps(
                        {
                            "billing_mode": row.billing_mode,
                            "credits": row.credits,
                            "estimated_margin_bps": estimated_margin,
                            "price_xtr": row.price_xtr,
                            "status": "active",
                            "transition": "stars_launch_v1",
                        },
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                )
            )
            result["activated"] += 1
    return result


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("check")
    activate = commands.add_parser("activate-products")
    activate.add_argument("--execute", action="store_true")
    activate.add_argument("--actor", default="stars-launch-cli")
    return result


def main() -> int:
    args = parser().parse_args()
    values = dict(os.environ)
    try:
        store = DatabaseStore(_database_url(values), migrate=False)
        try:
            if args.command == "check":
                report = check_readiness(store, values)
                print(json.dumps(report, sort_keys=True))
                return 0 if report["ready"] else 1
            result = activate_products(
                store,
                values,
                actor=args.actor,
                execute=args.execute,
            )
            print(json.dumps({"ok": True, **result}, sort_keys=True))
            return 0
        finally:
            store.close()
    except Exception as exc:
        error_code = (
            "execution_required"
            if "--execute" in str(exc)
            else "readiness_blocked"
            if "not ready" in str(exc)
            else "configuration_error"
        )
        print(json.dumps({"ok": False, "error_code": error_code}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
