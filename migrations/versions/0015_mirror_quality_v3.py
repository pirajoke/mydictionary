"""Add bounded Mirror dialogue memory and learner style."""

from alembic import op
import sqlalchemy as sa


revision = "0015_mirror_quality_v3"
down_revision = "0014_mirror_assistant_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column(
                "mirror_style",
                sa.String(length=16),
                nullable=True,
                server_default="teacher",
            )
        )
        batch.create_check_constraint(
            "ck_user_mirror_style",
            "mirror_style IN ('teacher', 'conversation', 'brief', 'practice')",
        )

    op.create_table(
        "mirror_dialogue_turns",
        sa.Column("turn_id", sa.String(length=36), primary_key=True),
        sa.Column("exchange_id", sa.String(length=36), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('user', 'assistant')", name="ck_mirror_dialogue_turn_role"
        ),
        sa.CheckConstraint(
            "turn_index IN (0, 1)", name="ck_mirror_dialogue_turn_index"
        ),
        sa.ForeignKeyConstraint(
            ["telegram_user_id"],
            ["users.telegram_user_id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "exchange_id", "turn_index", name="uq_mirror_dialogue_exchange_turn"
        ),
    )
    op.create_index(
        "ix_mirror_dialogue_user_created",
        "mirror_dialogue_turns",
        ["telegram_user_id", "created_at"],
    )
    op.create_index(
        "ix_mirror_dialogue_expires",
        "mirror_dialogue_turns",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_mirror_dialogue_expires", table_name="mirror_dialogue_turns")
    op.drop_index(
        "ix_mirror_dialogue_user_created", table_name="mirror_dialogue_turns"
    )
    op.drop_table("mirror_dialogue_turns")
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("ck_user_mirror_style", type_="check")
        batch.drop_column("mirror_style")
