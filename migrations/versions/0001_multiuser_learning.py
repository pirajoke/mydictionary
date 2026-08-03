"""Create multi-user learning tables."""

from alembic import op
import sqlalchemy as sa


revision = "0001_multiuser_learning"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column("last_name", sa.String(length=255), nullable=True),
        sa.Column("language_code", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("telegram_user_id"),
    )
    op.create_table(
        "user_progress",
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("total_correct", sa.Integer(), nullable=False),
        sa.Column("total_wrong", sa.Integer(), nullable=False),
        sa.Column("sessions", sa.Integer(), nullable=False),
        sa.Column("xp", sa.Integer(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("streak", sa.Integer(), nullable=False),
        sa.Column("streak_best", sa.Integer(), nullable=False),
        sa.Column("last_activity_date", sa.String(length=10), nullable=True),
        sa.Column("today_xp", sa.Integer(), nullable=False),
        sa.Column("today_date", sa.String(length=10), nullable=True),
        sa.Column("active_lang", sa.String(length=16), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["telegram_user_id"], ["users.telegram_user_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("telegram_user_id"),
    )
    op.create_table(
        "word_progress",
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("vocabulary_id", sa.String(length=64), nullable=False),
        sa.Column("term", sa.String(length=512), nullable=False),
        sa.Column("word_index", sa.Integer(), nullable=False),
        sa.Column("correct_count", sa.Integer(), nullable=False),
        sa.Column("wrong_count", sa.Integer(), nullable=False),
        sa.Column("last_seen", sa.String(length=64), nullable=True),
        sa.Column("interval", sa.Integer(), nullable=False),
        sa.Column("next_review", sa.String(length=64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["telegram_user_id"], ["users.telegram_user_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("telegram_user_id", "language", "vocabulary_id"),
    )
    op.create_index(
        "ix_word_progress_due",
        "word_progress",
        ["telegram_user_id", "language", "next_review"],
    )
    op.create_table(
        "data_imports",
        sa.Column("import_key", sa.String(length=255), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("import_key"),
    )


def downgrade() -> None:
    op.drop_table("data_imports")
    op.drop_index("ix_word_progress_due", table_name="word_progress")
    op.drop_table("word_progress")
    op.drop_table("user_progress")
    op.drop_table("users")
