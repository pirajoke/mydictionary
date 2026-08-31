"""Add privacy-safe referral codes and one-time referral attribution."""

from alembic import op
import sqlalchemy as sa


revision = "0019_referral_program_v1"
down_revision = "0018_interface_locale"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "referral_codes",
        sa.Column("code", sa.String(length=48), primary_key=True),
        sa.Column("inviter_user_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["inviter_user_id"],
            ["users.telegram_user_id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "inviter_user_id", name="uq_referral_codes_inviter_user_id"
        ),
    )
    op.create_table(
        "referral_attributions",
        sa.Column("attribution_id", sa.String(length=36), primary_key=True),
        sa.Column("inviter_user_id", sa.BigInteger(), nullable=False),
        sa.Column("invitee_user_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reward_credits", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rewarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "inviter_user_id != invitee_user_id",
            name="ck_referral_attribution_distinct_users",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'activated')",
            name="ck_referral_attribution_status",
        ),
        sa.CheckConstraint(
            "reward_credits >= 0 AND reward_credits <= 5",
            name="ck_referral_attribution_reward",
        ),
        sa.ForeignKeyConstraint(
            ["inviter_user_id"],
            ["users.telegram_user_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["invitee_user_id"],
            ["users.telegram_user_id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "invitee_user_id", name="uq_referral_attributions_invitee_user_id"
        ),
    )
    op.create_index(
        "ix_referral_attributions_inviter_status",
        "referral_attributions",
        ["inviter_user_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_referral_attributions_inviter_status",
        table_name="referral_attributions",
    )
    op.drop_table("referral_attributions")
    op.drop_table("referral_codes")
