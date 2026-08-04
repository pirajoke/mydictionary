"""Add administration settings, credentials, audit, and pilot credit ledger."""

from alembic import op
import sqlalchemy as sa


revision = "0003_admin_console"
down_revision = "0002_ai_tutor_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "admin_credentials",
        sa.Column("singleton_id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("session_version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("singleton_id"),
    )
    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("actor", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=128), nullable=True),
        sa.Column("details_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_admin_audit_created", "admin_audit_log", ["created_at"]
    )
    op.create_table(
        "ai_credit_ledger",
        sa.Column("entry_id", sa.String(length=36), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("actor", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("delta != 0", name="ck_ai_credit_ledger_delta"),
        sa.CheckConstraint(
            "balance_after >= 0", name="ck_ai_credit_ledger_balance"
        ),
        sa.ForeignKeyConstraint(
            ["telegram_user_id"],
            ["users.telegram_user_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("entry_id"),
    )
    op.create_index(
        "ix_ai_credit_ledger_user_created",
        "ai_credit_ledger",
        ["telegram_user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_credit_ledger_user_created", table_name="ai_credit_ledger"
    )
    op.drop_table("ai_credit_ledger")
    op.drop_index("ix_admin_audit_created", table_name="admin_audit_log")
    op.drop_table("admin_audit_log")
    op.drop_table("admin_credentials")
    op.drop_table("app_settings")
