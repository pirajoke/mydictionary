"""Persist the per-user Mirror response preference."""

from alembic import op
import sqlalchemy as sa


revision = "0014_mirror_assistant_v1"
down_revision = "0013_ai_processing_consent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column(
                "mirror_response_mode",
                sa.String(length=8),
                nullable=True,
                server_default="text",
            )
        )
        batch.create_check_constraint(
            "ck_user_mirror_response_mode",
            "mirror_response_mode IN ('text', 'voice', 'both')",
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("ck_user_mirror_response_mode", type_="check")
        batch.drop_column("mirror_response_mode")
