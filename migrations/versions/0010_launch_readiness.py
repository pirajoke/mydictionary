"""Add versioned learner consent records for paid and voice features."""

from alembic import op
import sqlalchemy as sa


revision = "0010_launch_readiness"
down_revision = "0009_voice_tutor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("payment_orders") as batch:
        batch.add_column(
            sa.Column(
                "terms_version",
                sa.String(length=64),
                nullable=False,
                server_default="unversioned",
            )
        )
    op.create_table(
        "user_consents",
        sa.Column("consent_id", sa.String(length=36), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("consent_type", sa.String(length=32), nullable=False),
        sa.Column("document_version", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "consent_type IN ('billing_terms', 'voice_processing')",
            name="ck_user_consent_type",
        ),
        sa.ForeignKeyConstraint(
            ["telegram_user_id"],
            ["users.telegram_user_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("consent_id"),
        sa.UniqueConstraint(
            "telegram_user_id",
            "consent_type",
            "document_version",
            name="uq_user_consent_version",
        ),
    )
    op.create_index(
        "ix_user_consents_user_type",
        "user_consents",
        ["telegram_user_id", "consent_type", "granted_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_consents_user_type", table_name="user_consents")
    op.drop_table("user_consents")
    with op.batch_alter_table("payment_orders") as batch:
        batch.drop_column("terms_version")
