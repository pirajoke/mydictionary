"""Add learner-owned custom vocabulary and SRS state."""

from alembic import op
import sqlalchemy as sa


revision = "0021_custom_vocabulary_v1"
down_revision = "0020_onboarding_version_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "custom_vocabulary_entries",
        sa.Column("entry_id", sa.String(length=36), primary_key=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("target_language", sa.String(length=16), nullable=False),
        sa.Column("meaning_language", sa.String(length=16), nullable=False),
        sa.Column("normalized_target", sa.String(length=120), nullable=False),
        sa.Column("target", sa.String(length=120), nullable=False),
        sa.Column("meaning", sa.String(length=240), nullable=False),
        sa.Column("transcription", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("source_kind", sa.String(length=16), nullable=False),
        sa.Column("correct_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("wrong_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_seen", sa.String(length=64), nullable=True),
        sa.Column("interval", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("next_review", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_kind IN ('text', 'photo', 'pdf', 'voice')",
            name="ck_custom_vocabulary_source_kind",
        ),
        sa.ForeignKeyConstraint(
            ["telegram_user_id"], ["users.telegram_user_id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "telegram_user_id",
            "target_language",
            "meaning_language",
            "normalized_target",
            name="uq_custom_vocabulary_owner_language_target",
        ),
    )
    op.create_index(
        "ix_custom_vocabulary_owner_language_review",
        "custom_vocabulary_entries",
        ["telegram_user_id", "target_language", "meaning_language", "next_review"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_custom_vocabulary_owner_language_review",
        table_name="custom_vocabulary_entries",
    )
    op.drop_table("custom_vocabulary_entries")
