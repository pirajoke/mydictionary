"""Allow independently versioned AI-processing consent."""

from alembic import op


revision = "0013_ai_processing_consent"
down_revision = "0012_ai_runtime_gates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_consents") as batch:
        batch.drop_constraint("ck_user_consent_type", type_="check")
        batch.create_check_constraint(
            "ck_user_consent_type",
            "consent_type IN ('billing_terms', 'voice_processing', 'ai_processing')",
        )


def downgrade() -> None:
    with op.batch_alter_table("user_consents") as batch:
        batch.drop_constraint("ck_user_consent_type", type_="check")
        batch.create_check_constraint(
            "ck_user_consent_type",
            "consent_type IN ('billing_terms', 'voice_processing')",
        )
