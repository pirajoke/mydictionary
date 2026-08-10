#!/usr/bin/env python3
"""Preview or idempotently complete the initial AI-credit grant."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

from sqlalchemy import func, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mydictionary.admin_store import AdminStore
from mydictionary.storage import (
    BillingCreditLedger,
    DatabaseStore,
    User,
)


INITIAL_GRANT_REASON = "Initial AI credit grant"
ROLLOUT_REASON = "Complete initial AI credit grant to configured target"
_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{1,63}$")


def _validated_label(value: str, name: str) -> str:
    clean = str(value).strip()
    if not _LABEL_RE.fullmatch(clean):
        raise ValueError(f"{name} is invalid")
    return clean


def rollout_initial_credits(
    store: DatabaseStore,
    *,
    target_credits: int,
    rollout_id: str,
    actor: str,
    execute: bool,
) -> dict[str, Any]:
    """Return aggregate rollout results and write only when execute is true."""
    target = int(target_credits)
    if not 1 <= target <= 1_000_000:
        raise ValueError("target_credits is outside valid bounds")
    rollout = _validated_label(rollout_id, "rollout_id")
    operator = _validated_label(actor, "actor")

    with store.Session() as session:
        active_users = tuple(
            session.execute(
                select(User.telegram_user_id)
                .where(User.access_status == "active")
                .order_by(User.telegram_user_id)
            ).scalars()
        )
        keys = {
            user_id: f"initial-credit-rollout:{rollout}:{user_id}"
            for user_id in active_users
        }
        grants: dict[int, int] = {}
        applied_keys: set[str] = set()
        if active_users:
            grants = dict(
                session.execute(
                    select(
                        BillingCreditLedger.telegram_user_id,
                        func.coalesce(func.sum(BillingCreditLedger.delta), 0),
                    )
                    .where(
                        BillingCreditLedger.telegram_user_id.in_(active_users),
                        BillingCreditLedger.entry_type == "initial_grant",
                        BillingCreditLedger.reason == INITIAL_GRANT_REASON,
                        BillingCreditLedger.delta > 0,
                    )
                    .group_by(BillingCreditLedger.telegram_user_id)
                ).all()
            )
            applied_keys = set(
                session.execute(
                    select(BillingCreditLedger.idempotency_key).where(
                        BillingCreditLedger.idempotency_key.in_(
                            tuple(keys.values())
                        )
                    )
                ).scalars()
            )

    plan = [
        (user_id, target - max(0, int(grants.get(user_id, 0))), keys[user_id])
        for user_id in active_users
        if keys[user_id] not in applied_keys
        and target - max(0, int(grants.get(user_id, 0))) > 0
    ]
    result: dict[str, Any] = {
        "active_users": len(active_users),
        "pending_users": len(plan),
        "planned_credits": sum(delta for _user_id, delta, _key in plan),
        "applied_users": 0,
        "applied_credits": 0,
        "target_credits": target,
        "executed": bool(execute),
    }
    if not execute:
        return result

    admin = AdminStore(store)
    for user_id, delta, idempotency_key in plan:
        admin.adjust_credits(
            user_id,
            delta=delta,
            reason=ROLLOUT_REASON,
            actor=operator,
            idempotency_key=idempotency_key,
        )
        result["applied_users"] += 1
        result["applied_credits"] += delta
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-credits", type=int, default=40)
    parser.add_argument("--rollout-id", default="pilot-40-v1")
    parser.add_argument("--actor", default="ops-credit-rollout")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply the rollout; without this flag only aggregates are shown.",
    )
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace(
            "postgresql://", "postgresql+psycopg://", 1
        )
    store = DatabaseStore(database_url)
    try:
        result = rollout_initial_credits(
            store,
            target_credits=args.target_credits,
            rollout_id=args.rollout_id,
            actor=args.actor,
            execute=args.execute,
        )
    finally:
        store.close()
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
