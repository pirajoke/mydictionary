"""Add managed learner access states for a controlled public pilot."""

from alembic import op
import sqlalchemy as sa


revision = "0005_pilot_access"
down_revision = "0004_product_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "access_status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "access_status_updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    # Every pre-pilot account already had production access through the
    # allowlist and must remain usable after switching to pilot mode.
    op.execute(
        sa.text(
            "UPDATE users SET access_status = 'active', "
            "access_status_updated_at = updated_at"
        )
    )
    op.create_index("ix_users_access_status", "users", ["access_status"])


def downgrade() -> None:
    op.drop_index("ix_users_access_status", table_name="users")
    op.drop_column("users", "access_status_updated_at")
    op.drop_column("users", "access_status")
