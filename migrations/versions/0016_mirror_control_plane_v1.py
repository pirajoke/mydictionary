"""Add Mirror control plane, quality audit, and voice translation consent."""

from alembic import op
import sqlalchemy as sa


revision = "0016_mirror_control_plane_v1"
down_revision = "0015_mirror_quality_v3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("ck_user_mirror_style", type_="check")
        batch.add_column(
            sa.Column(
                "mirror_depth",
                sa.String(length=16),
                nullable=True,
                server_default="balanced",
            )
        )
        batch.add_column(
            sa.Column(
                "mirror_level",
                sa.String(length=16),
                nullable=True,
                server_default="adaptive",
            )
        )
        batch.create_check_constraint(
            "ck_user_mirror_style",
            "mirror_style IN ('teacher', 'conversation', 'coach', 'practice', 'brief', 'exam')",
        )
        batch.create_check_constraint(
            "ck_user_mirror_depth",
            "mirror_depth IN ('compact', 'balanced', 'deep')",
        )
        batch.create_check_constraint(
            "ck_user_mirror_level",
            "mirror_level IN ('adaptive', 'a1', 'a2', 'b1', 'b2', 'c1')",
        )

    with op.batch_alter_table("user_consents") as batch:
        batch.drop_constraint("ck_user_consent_type", type_="check")
        batch.create_check_constraint(
            "ck_user_consent_type",
            "consent_type IN ('billing_terms', 'voice_processing', 'voice_translation_processing', 'ai_processing')",
        )

    op.create_table(
        "mirror_policy_snapshots",
        sa.Column("snapshot_id", sa.String(length=36), primary_key=True),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("enabled_modes_json", sa.Text(), nullable=False),
        sa.Column("default_mode", sa.String(length=16), nullable=False),
        sa.Column("answer_depth", sa.String(length=16), nullable=False),
        sa.Column("learner_level", sa.String(length=16), nullable=False),
        sa.Column("mode_guidance_json", sa.Text(), nullable=False),
        sa.Column("config_sha256", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_mirror_policy_created",
        "mirror_policy_snapshots",
        ["created_at"],
    )

    op.create_table(
        "mirror_response_quality",
        sa.Column("request_id", sa.String(length=36), primary_key=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("task", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("depth", sa.String(length=16), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("contract_version", sa.String(length=64), nullable=False),
        sa.Column("response_length", sa.Integer(), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("example_count", sa.Integer(), nullable=False),
        sa.Column("has_next_step", sa.Boolean(), nullable=False),
        sa.Column("deterministic_score_bps", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["request_id"], ["ai_usage.request_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["telegram_user_id"], ["users.telegram_user_id"], ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "deterministic_score_bps BETWEEN 0 AND 10000",
            name="ck_mirror_quality_score",
        ),
    )
    op.create_index(
        "ix_mirror_quality_created",
        "mirror_response_quality",
        ["created_at"],
    )
    op.create_index(
        "ix_mirror_quality_dimensions",
        "mirror_response_quality",
        ["mode", "task", "level"],
    )

    op.create_table(
        "mirror_response_feedback",
        sa.Column("request_id", sa.String(length=36), primary_key=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("helpful", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["request_id"], ["ai_usage.request_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["telegram_user_id"], ["users.telegram_user_id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_mirror_feedback_created",
        "mirror_response_feedback",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_mirror_feedback_created", table_name="mirror_response_feedback")
    op.drop_table("mirror_response_feedback")
    op.drop_index("ix_mirror_quality_dimensions", table_name="mirror_response_quality")
    op.drop_index("ix_mirror_quality_created", table_name="mirror_response_quality")
    op.drop_table("mirror_response_quality")
    op.drop_index("ix_mirror_policy_created", table_name="mirror_policy_snapshots")
    op.drop_table("mirror_policy_snapshots")

    with op.batch_alter_table("user_consents") as batch:
        batch.drop_constraint("ck_user_consent_type", type_="check")
        batch.create_check_constraint(
            "ck_user_consent_type",
            "consent_type IN ('billing_terms', 'voice_processing', 'ai_processing')",
        )

    op.execute(
        "UPDATE users SET mirror_style = 'teacher' "
        "WHERE mirror_style IN ('coach', 'exam')"
    )
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("ck_user_mirror_level", type_="check")
        batch.drop_constraint("ck_user_mirror_depth", type_="check")
        batch.drop_constraint("ck_user_mirror_style", type_="check")
        batch.drop_column("mirror_level")
        batch.drop_column("mirror_depth")
        batch.create_check_constraint(
            "ck_user_mirror_style",
            "mirror_style IN ('teacher', 'conversation', 'brief', 'practice')",
        )
