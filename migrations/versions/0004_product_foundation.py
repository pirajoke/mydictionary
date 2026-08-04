"""Add product roles, onboarding, pack enrollments, and event analytics."""

from alembic import op
import sqlalchemy as sa


revision = "0004_product_foundation"
down_revision = "0003_admin_console"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "role", sa.String(length=16), nullable=False, server_default="learner"
        ),
    )
    op.add_column(
        "users", sa.Column("native_language", sa.String(length=16), nullable=True)
    )
    op.add_column(
        "users", sa.Column("learning_goal", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column(
            "daily_word_goal", sa.Integer(), nullable=False, server_default="10"
        ),
    )
    op.add_column(
        "users",
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users", sa.Column("acquisition_source", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "user_progress",
        sa.Column("active_pack_id", sa.String(length=64), nullable=True),
    )

    op.create_table(
        "user_pack_enrollments",
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("pack_id", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["telegram_user_id"],
            ["users.telegram_user_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("telegram_user_id", "pack_id"),
    )
    op.create_index(
        "ix_pack_enrollments_pack", "user_pack_enrollments", ["pack_id"]
    )
    op.create_table(
        "analytics_events",
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("event_name", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("properties_json", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["telegram_user_id"],
            ["users.telegram_user_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_analytics_event_occurred",
        "analytics_events",
        ["event_name", "occurred_at"],
    )
    op.create_index(
        "ix_analytics_user_occurred",
        "analytics_events",
        ["telegram_user_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_analytics_user_occurred", table_name="analytics_events")
    op.drop_index("ix_analytics_event_occurred", table_name="analytics_events")
    op.drop_table("analytics_events")
    op.drop_index("ix_pack_enrollments_pack", table_name="user_pack_enrollments")
    op.drop_table("user_pack_enrollments")
    op.drop_column("user_progress", "active_pack_id")
    op.drop_column("users", "acquisition_source")
    op.drop_column("users", "onboarding_completed_at")
    op.drop_column("users", "daily_word_goal")
    op.drop_column("users", "learning_goal")
    op.drop_column("users", "native_language")
    op.drop_column("users", "role")
