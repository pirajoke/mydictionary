#!/usr/bin/env python3
"""Validate Commercial Launch v3 and idempotently seed draft products."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mydictionary.admin_store import AdminStore
from mydictionary.billing import BillingSettings
from mydictionary.storage import DatabaseStore
from ops import mydictionary_economics as economics


EXPECTED_CATALOG = {
    "ai-mini": (20, 69, "one_time"),
    "ai-starter": (50, 129, "one_time"),
    "ai-value": (150, 319, "one_time"),
    "ai-monthly": (100, 229, "subscription"),
}
PRODUCT_FIELDS = (
    "title",
    "description",
    "credits",
    "price_xtr",
    "status",
    "estimated_cost_micro_usd",
    "target_margin_bps",
    "display_order",
    "billing_mode",
    "subscription_period_seconds",
)


def _database_url() -> str:
    value = os.environ.get("DATABASE_URL", "").strip()
    if not value:
        raise RuntimeError("DATABASE_URL is required for product seeding")
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+psycopg://", 1)
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


def _candidate_products(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    validated = economics.validate_snapshot(snapshot)
    packages = snapshot["stars"]["packages"]
    actual_catalog = {
        str(package["product_id"]): (
            int(package["credits"]),
            int(package["price_xtr"]),
            str(package["billing_mode"]),
        )
        for package in packages
    }
    if actual_catalog != EXPECTED_CATALOG:
        raise economics.EconomicsContractError(
            "Commercial Launch v3 catalog differs from approved prices"
        )
    if validated["minimum_margin_bps"] < 5000:
        raise economics.EconomicsContractError(
            "Commercial Launch v3 margin policy is too low"
        )
    return [
        {
            "product_id": str(package["product_id"]),
            "title": str(package["title"]),
            "description": str(package["description"]),
            "credits": int(package["credits"]),
            "price_xtr": int(package["price_xtr"]),
            "status": "draft",
            "estimated_cost_micro_usd": int(
                package["estimated_cost_micro_usd"]
            ),
            "target_margin_bps": int(package["target_margin_bps"]),
            "display_order": int(package["display_order"]),
            "billing_mode": str(package["billing_mode"]),
            "subscription_period_seconds": package.get(
                "subscription_period_seconds"
            ),
        }
        for package in packages
    ]


def seed_products(
    store: DatabaseStore,
    snapshot: Mapping[str, Any],
    *,
    actor: str,
) -> dict[str, int]:
    """Upsert the candidate catalog as draft and skip exact repeats."""
    candidates = _candidate_products(snapshot)
    billing = BillingSettings(
        enabled=False,
        payload_secret=None,
        support_contact="",
        terms_text="Commercial Launch v3 candidate",
        terms_version=str(snapshot["stars"]["terms_version"]),
        net_micro_usd_per_xtr=int(
            snapshot["stars"]["assumed_net_micro_usd_per_xtr"]
        ),
        terms_approved=False,
        economics_reviewed_on=str(snapshot["reviewed_on"]),
        economics_max_age_days=int(snapshot["max_age_days"]),
        private_chat_topics_enabled=False,
    )
    admin = AdminStore(store, billing)
    existing = {
        str(product["product_id"]): product for product in admin.billing_products()
    }
    result = {"created": 0, "updated": 0, "unchanged": 0}
    for candidate in candidates:
        current = existing.get(candidate["product_id"])
        if current is not None and current["status"] != "draft":
            raise RuntimeError(
                f"Refusing to overwrite non-draft product {candidate['product_id']}"
            )
        if current is not None and all(
            current.get(field) == candidate.get(field) for field in PRODUCT_FIELDS
        ):
            result["unchanged"] += 1
            continue
        admin.upsert_billing_product(**candidate, actor=actor)
        result["updated" if current is not None else "created"] += 1
    return result


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--snapshot", type=Path, default=economics.DEFAULT_SNAPSHOT)
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("check")
    seed = commands.add_parser("seed-products")
    seed.add_argument("--execute", action="store_true")
    seed.add_argument("--actor", default="commercial-launch-cli")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        snapshot = economics.load_snapshot(args.snapshot)
        validated = economics.validate_snapshot(snapshot)
        if args.command == "check":
            print(json.dumps({"ok": True, **validated}, sort_keys=True))
            return 0
        if not args.execute:
            raise RuntimeError("Refusing a database write without --execute")
        store = DatabaseStore(_database_url(), migrate=False)
        try:
            result = seed_products(store, snapshot, actor=args.actor)
        finally:
            store.close()
        print(json.dumps({"ok": True, **result}, sort_keys=True))
        return 0
    except (economics.EconomicsContractError, RuntimeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
