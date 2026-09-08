"""Persist the completed guided-onboarding version."""

from alembic import op
import sqlalchemy as sa


revision = "0020_onboarding_version_v2"
down_revision = "0019_referral_program_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("onboarding_version", sa.Integer(), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE users
            SET onboarding_version = 2
            WHERE onboarding_completed_at IS NOT NULL
              AND EXISTS (
                  SELECT 1
                  FROM analytics_events
                  WHERE analytics_events.telegram_user_id = users.telegram_user_id
                    AND analytics_events.event_name = 'onboarding_preference_selected'
              )
            """
        )
    )


def downgrade() -> None:
    op.drop_column("users", "onboarding_version")
