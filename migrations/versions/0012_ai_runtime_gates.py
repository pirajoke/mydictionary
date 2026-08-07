"""Add durable AI provider metering, budgets, and breaker state."""

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "0012_ai_runtime_gates"
down_revision = "0011_pilot_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ai_usage") as batch:
        batch.add_column(
            sa.Column(
                "requested_service_tier",
                sa.String(length=32),
                nullable=False,
                server_default="default",
            )
        )
        batch.add_column(
            sa.Column("returned_service_tier", sa.String(length=32), nullable=True)
        )
        batch.add_column(
            sa.Column(
                "economics_snapshot_id",
                sa.String(length=128),
                nullable=False,
                server_default="legacy",
            )
        )
        batch.add_column(
            sa.Column(
                "economics_snapshot_sha256",
                sa.String(length=64),
                nullable=False,
                server_default="0" * 64,
            )
        )
        batch.add_column(
            sa.Column("provider_status", sa.String(length=32), nullable=True)
        )
        batch.add_column(
            sa.Column(
                "provider_attempts",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch.add_column(
            sa.Column(
                "provider_response_received",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.add_column(
            sa.Column(
                "cost_is_estimate",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )
        batch.add_column(
            sa.Column(
                "projected_cost_micro_usd",
                sa.BigInteger(),
                nullable=False,
                server_default="0",
            )
        )
        batch.add_column(
            sa.Column("provider_completed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.create_check_constraint(
            "ck_ai_usage_provider_attempts",
            "provider_attempts BETWEEN 0 AND 1",
        )
        batch.create_check_constraint(
            "ck_ai_usage_projected_cost",
            "projected_cost_micro_usd >= 0",
        )
    op.create_index(
        "ix_ai_usage_provider_completed",
        "ai_usage",
        ["provider_response_received", "provider_completed_at"],
    )
    ai_usage = sa.table(
        "ai_usage",
        sa.column("action", sa.String()),
        sa.column("status", sa.String()),
        sa.column("provider_attempts", sa.Integer()),
        sa.column("provider_response_received", sa.Boolean()),
        sa.column("cost_is_estimate", sa.Boolean()),
        sa.column("provider_status", sa.String()),
        sa.column("completed_at", sa.DateTime(timezone=True)),
        sa.column("provider_completed_at", sa.DateTime(timezone=True)),
    )
    op.execute(
        ai_usage.update()
        .where(
            ai_usage.c.action == "block_tutor",
            ai_usage.c.status == "completed",
        )
        .values(
            provider_attempts=1,
            provider_response_received=True,
            cost_is_estimate=False,
            provider_status="completed",
            provider_completed_at=ai_usage.c.completed_at,
        )
    )
    op.create_table(
        "ai_budget_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "in_flight_micro_usd", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column(
            "breaker_open", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("breaker_reason", sa.String(length=128), nullable=True),
        sa.Column("breaker_opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "breaker_acknowledged_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "breaker_acknowledged_by", sa.String(length=64), nullable=True
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_ai_budget_singleton"),
        sa.CheckConstraint(
            "in_flight_micro_usd >= 0", name="ck_ai_budget_in_flight"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.bulk_insert(
        sa.table(
            "ai_budget_state",
            sa.column("id", sa.Integer()),
            sa.column("in_flight_micro_usd", sa.BigInteger()),
            sa.column("breaker_open", sa.Boolean()),
            sa.column("updated_at", sa.DateTime(timezone=True)),
        ),
        [
            {
                "id": 1,
                "in_flight_micro_usd": 0,
                "breaker_open": False,
                "updated_at": datetime.now(timezone.utc),
            }
        ],
    )


def downgrade() -> None:
    op.drop_table("ai_budget_state")
    op.drop_index("ix_ai_usage_provider_completed", table_name="ai_usage")
    with op.batch_alter_table("ai_usage") as batch:
        batch.drop_constraint("ck_ai_usage_projected_cost", type_="check")
        batch.drop_constraint("ck_ai_usage_provider_attempts", type_="check")
        batch.drop_column("provider_completed_at")
        batch.drop_column("projected_cost_micro_usd")
        batch.drop_column("cost_is_estimate")
        batch.drop_column("provider_response_received")
        batch.drop_column("provider_attempts")
        batch.drop_column("provider_status")
        batch.drop_column("economics_snapshot_sha256")
        batch.drop_column("economics_snapshot_id")
        batch.drop_column("returned_service_tier")
        batch.drop_column("requested_service_tier")
