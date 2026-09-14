"""Add short-lived Mini App curated swipe sessions."""

from alembic import op
import sqlalchemy as sa

revision = "0023_miniapp_swipe_sessions"
down_revision = "0022_custom_vocab_translation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "miniapp_swipe_sessions",
        sa.Column("session_id", sa.String(36), primary_key=True),
        sa.Column("telegram_user_id", sa.BigInteger(),
                  sa.ForeignKey("users.telegram_user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("pack_id", sa.String(64), nullable=False),
        sa.Column("language", sa.String(16), nullable=False),
        sa.Column("initial_indices_json", sa.Text(), nullable=False),
        sa.Column("state_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_miniapp_swipe_sessions_telegram_user_id", "miniapp_swipe_sessions", ["telegram_user_id"])
    op.create_index("ix_miniapp_swipe_sessions_created_at", "miniapp_swipe_sessions", ["created_at"])


def downgrade() -> None:
    op.drop_table("miniapp_swipe_sessions")
