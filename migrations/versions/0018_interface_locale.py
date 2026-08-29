"""Add a durable learner-selected bot interface locale."""

from alembic import op
import sqlalchemy as sa


revision = "0018_interface_locale"
down_revision = "0017_admin_auth_recovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("interface_locale", sa.String(length=16), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("interface_locale")
