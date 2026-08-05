"""Add metered voice practice sessions and expiring transcripts."""

from alembic import op
import sqlalchemy as sa


revision = "0009_voice_tutor"
down_revision = "0008_product_safety"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voice_sessions",
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("pack_id", sa.String(length=64), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("topic", sa.String(length=64), nullable=True),
        sa.Column("block_session_id", sa.String(length=64), nullable=True),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("vocabulary_ids_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("turn_count", sa.Integer(), nullable=False),
        sa.Column("next_position", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('active', 'completed', 'cancelled', 'expired')",
            name="ck_voice_session_status",
        ),
        sa.CheckConstraint(
            "mode IN ('pronunciation', 'conversation')",
            name="ck_voice_session_mode",
        ),
        sa.CheckConstraint("turn_count >= 0", name="ck_voice_session_turn_count"),
        sa.CheckConstraint("next_position >= 0", name="ck_voice_session_position"),
        sa.ForeignKeyConstraint(
            ["telegram_user_id"],
            ["users.telegram_user_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_index(
        "ix_voice_sessions_user_status_updated",
        "voice_sessions",
        ["telegram_user_id", "status", "updated_at"],
    )
    op.create_index(
        "uq_voice_sessions_one_active_user",
        "voice_sessions",
        ["telegram_user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        sqlite_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "voice_turns",
        sa.Column("turn_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=True),
        sa.Column("expected_vocabulary_id", sa.String(length=64), nullable=False),
        sa.Column("matched_vocabulary_id", sa.String(length=64), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=False),
        sa.Column("feedback_code", sa.String(length=16), nullable=False),
        sa.Column("similarity_bps", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "feedback_code IN ('exact', 'close', 'retry')",
            name="ck_voice_turn_feedback",
        ),
        sa.CheckConstraint(
            "similarity_bps >= 0 AND similarity_bps <= 10000",
            name="ck_voice_turn_similarity",
        ),
        sa.ForeignKeyConstraint(
            ["request_id"], ["ai_usage.request_id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["voice_sessions.session_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["telegram_user_id"],
            ["users.telegram_user_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("turn_id"),
        sa.UniqueConstraint("request_id", name="uq_voice_turn_request"),
    )
    op.create_index(
        "ix_voice_turns_session_created",
        "voice_turns",
        ["session_id", "created_at"],
    )
    op.create_index(
        "ix_voice_turns_expires", "voice_turns", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_voice_turns_expires", table_name="voice_turns")
    op.drop_index("ix_voice_turns_session_created", table_name="voice_turns")
    op.drop_table("voice_turns")
    op.drop_index(
        "uq_voice_sessions_one_active_user", table_name="voice_sessions"
    )
    op.drop_index(
        "ix_voice_sessions_user_status_updated", table_name="voice_sessions"
    )
    op.drop_table("voice_sessions")
