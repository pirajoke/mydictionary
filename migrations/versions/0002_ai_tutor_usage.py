"""Add pilot AI allowance and privacy-minimized usage metering."""

from alembic import op
import sqlalchemy as sa


revision = "0002_ai_tutor_usage"
down_revision = "0001_multiuser_learning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_allowances",
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("available_credits", sa.Integer(), nullable=False),
        sa.Column("reserved_credits", sa.Integer(), nullable=False),
        sa.Column("spent_credits", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "available_credits >= 0", name="ck_ai_allowance_available"
        ),
        sa.CheckConstraint(
            "reserved_credits >= 0", name="ck_ai_allowance_reserved"
        ),
        sa.CheckConstraint("spent_credits >= 0", name="ck_ai_allowance_spent"),
        sa.ForeignKeyConstraint(
            ["telegram_user_id"], ["users.telegram_user_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("telegram_user_id"),
    )
    op.create_table(
        "ai_usage",
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("context_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("reserved_credits", sa.Integer(), nullable=False),
        sa.Column("billed_credits", sa.Integer(), nullable=False),
        sa.Column("provider_response_id", sa.String(length=128), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_write_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_micro_usd", sa.BigInteger(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('reserved', 'completed', 'failed')",
            name="ck_ai_usage_status",
        ),
        sa.CheckConstraint("reserved_credits >= 0", name="ck_ai_usage_reserved"),
        sa.CheckConstraint("billed_credits >= 0", name="ck_ai_usage_billed"),
        sa.ForeignKeyConstraint(
            ["telegram_user_id"], ["users.telegram_user_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("request_id"),
    )
    op.create_index(
        "ix_ai_usage_user_created",
        "ai_usage",
        ["telegram_user_id", "created_at"],
    )
    op.create_index(
        "ix_ai_usage_status_created", "ai_usage", ["status", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_ai_usage_status_created", table_name="ai_usage")
    op.drop_index("ix_ai_usage_user_created", table_name="ai_usage")
    op.drop_table("ai_usage")
    op.drop_table("ai_allowances")
