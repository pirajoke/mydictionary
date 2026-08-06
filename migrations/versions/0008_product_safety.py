"""Add privacy state, persistent rate limits, and abuse events."""

from alembic import op
import sqlalchemy as sa


revision = "0008_product_safety"
down_revision = "0007_stars_subscriptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column(
                "privacy_status",
                sa.String(length=16),
                nullable=False,
                server_default="active",
            )
        )
        batch.add_column(
            sa.Column("privacy_deleted_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.create_check_constraint(
            "ck_user_privacy_status",
            "privacy_status IN ('active', 'erased')",
        )

    op.create_table(
        "rate_limit_buckets",
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("attempts >= 0", name="ck_rate_limit_attempts"),
        sa.ForeignKeyConstraint(
            ["telegram_user_id"],
            ["users.telegram_user_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("telegram_user_id", "scope"),
    )
    op.create_index(
        "ix_rate_limit_buckets_updated",
        "rate_limit_buckets",
        ["updated_at"],
    )

    op.create_table(
        "abuse_events",
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("rule", sa.String(length=64), nullable=False),
        sa.Column("limit_value", sa.Integer(), nullable=False),
        sa.Column("observed_count", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["telegram_user_id"],
            ["users.telegram_user_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_abuse_events_user_occurred",
        "abuse_events",
        ["telegram_user_id", "occurred_at"],
    )
    op.create_index(
        "ix_abuse_events_scope_occurred",
        "abuse_events",
        ["scope", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_abuse_events_scope_occurred", table_name="abuse_events")
    op.drop_index("ix_abuse_events_user_occurred", table_name="abuse_events")
    op.drop_table("abuse_events")
    op.drop_index("ix_rate_limit_buckets_updated", table_name="rate_limit_buckets")
    op.drop_table("rate_limit_buckets")
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("ck_user_privacy_status", type_="check")
        batch.drop_column("privacy_deleted_at")
        batch.drop_column("privacy_status")
