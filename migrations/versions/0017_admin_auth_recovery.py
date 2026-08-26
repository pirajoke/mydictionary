"""Add privacy-safe administrator password reset records."""

from alembic import op
import sqlalchemy as sa


revision = "0017_admin_auth_recovery"
down_revision = "0016_mirror_control_plane_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_password_resets",
        sa.Column("reset_id", sa.String(length=36), primary_key=True),
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "token_digest", name="uq_admin_password_resets_token_digest"
        ),
    )
    op.create_index(
        "ix_admin_password_resets_expires_at",
        "admin_password_resets",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_admin_password_resets_expires_at",
        table_name="admin_password_resets",
    )
    op.drop_table("admin_password_resets")
