"""Add bounded native Telegram learning sessions."""

from alembic import op
import sqlalchemy as sa

revision = "0024_bot_learning_sessions"
down_revision = "0023_miniapp_swipe_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bot_learning_sessions",
        sa.Column("telegram_user_id", sa.BigInteger(),
                  sa.ForeignKey("users.telegram_user_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("pack_id", sa.String(64), primary_key=True),
        sa.Column("session_id", sa.String(16), nullable=False),
        sa.Column("state_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_bot_learning_sessions_created_at", "bot_learning_sessions", ["created_at"])


def downgrade() -> None:
    op.drop_table("bot_learning_sessions")
