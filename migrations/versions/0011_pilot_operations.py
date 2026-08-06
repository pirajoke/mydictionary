"""Add a transactional Telegram notification outbox for pilot operations."""

from alembic import op
import sqlalchemy as sa


revision = "0011_pilot_operations"
down_revision = "0010_launch_readiness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telegram_notifications",
        sa.Column("notification_id", sa.String(length=36), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "kind IN ('pilot_access_approved')",
            name="ck_telegram_notification_kind",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'sent', 'failed', 'cancelled')",
            name="ck_telegram_notification_status",
        ),
        sa.CheckConstraint(
            "attempts >= 0", name="ck_telegram_notification_attempts"
        ),
        sa.ForeignKeyConstraint(
            ["telegram_user_id"],
            ["users.telegram_user_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("notification_id"),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_telegram_notification_idempotency"
        ),
    )
    op.create_index(
        "ix_telegram_notifications_delivery",
        "telegram_notifications",
        ["status", "available_at", "lease_until"],
    )
    op.create_index(
        "ix_telegram_notifications_user",
        "telegram_notifications",
        ["telegram_user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_telegram_notifications_user", table_name="telegram_notifications"
    )
    op.drop_index(
        "ix_telegram_notifications_delivery",
        table_name="telegram_notifications",
    )
    op.drop_table("telegram_notifications")
