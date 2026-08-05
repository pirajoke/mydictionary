"""Add recurring Telegram Stars subscriptions and renewal payments."""

from alembic import op
import sqlalchemy as sa


revision = "0007_stars_subscriptions"
down_revision = "0006_telegram_stars_billing"
branch_labels = None
depends_on = None


SUBSCRIPTION_PERIOD_SECONDS = 30 * 24 * 60 * 60


def upgrade() -> None:
    with op.batch_alter_table("billing_products") as batch:
        batch.add_column(
            sa.Column(
                "billing_mode",
                sa.String(length=16),
                nullable=False,
                server_default="one_time",
            )
        )
        batch.add_column(
            sa.Column("subscription_period_seconds", sa.Integer(), nullable=True)
        )
        batch.create_check_constraint(
            "ck_billing_product_mode",
            "billing_mode IN ('one_time', 'subscription')",
        )
        batch.create_check_constraint(
            "ck_billing_product_subscription_period",
            "(billing_mode = 'one_time' AND subscription_period_seconds IS NULL) "
            "OR (billing_mode = 'subscription' AND "
            f"subscription_period_seconds = {SUBSCRIPTION_PERIOD_SECONDS})",
        )

    with op.batch_alter_table("payment_orders") as batch:
        batch.drop_constraint("ck_payment_order_status", type_="check")
        batch.add_column(
            sa.Column(
                "billing_mode",
                sa.String(length=16),
                nullable=False,
                server_default="one_time",
            )
        )
        batch.add_column(
            sa.Column("subscription_period_seconds", sa.Integer(), nullable=True)
        )
        batch.create_check_constraint(
            "ck_payment_order_status",
            "status IN ('created', 'prechecked', 'paid', 'expired', "
            "'cancelled', 'refund_pending', 'refunded', "
            "'subscription_active', 'subscription_cancelled')",
        )
        batch.create_check_constraint(
            "ck_payment_order_mode",
            "billing_mode IN ('one_time', 'subscription')",
        )
        batch.create_check_constraint(
            "ck_payment_order_subscription_period",
            "(billing_mode = 'one_time' AND subscription_period_seconds IS NULL) "
            "OR (billing_mode = 'subscription' AND "
            f"subscription_period_seconds = {SUBSCRIPTION_PERIOD_SECONDS})",
        )

    op.create_table(
        "stars_subscriptions",
        sa.Column("subscription_id", sa.String(length=36), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column(
            "telegram_payment_charge_id", sa.String(length=255), nullable=False
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("period_seconds", sa.Integer(), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'cancelled', 'expired')",
            name="ck_stars_subscription_status",
        ),
        sa.CheckConstraint(
            f"period_seconds = {SUBSCRIPTION_PERIOD_SECONDS}",
            name="ck_stars_subscription_period",
        ),
        sa.ForeignKeyConstraint(["order_id"], ["payment_orders.order_id"]),
        sa.ForeignKeyConstraint(["product_id"], ["billing_products.product_id"]),
        sa.ForeignKeyConstraint(
            ["telegram_user_id"],
            ["users.telegram_user_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("subscription_id"),
        sa.UniqueConstraint("order_id", name="uq_stars_subscription_order"),
        sa.UniqueConstraint(
            "telegram_payment_charge_id", name="uq_stars_subscription_charge"
        ),
    )
    op.create_index(
        "ix_stars_subscriptions_user_status",
        "stars_subscriptions",
        ["telegram_user_id", "status"],
    )

    with op.batch_alter_table("stars_payments") as batch:
        batch.drop_constraint("uq_stars_payment_order", type_="unique")
        batch.add_column(
            sa.Column("subscription_id", sa.String(length=36), nullable=True)
        )
        batch.add_column(
            sa.Column(
                "is_recurring",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.add_column(
            sa.Column(
                "is_first_recurring",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.add_column(
            sa.Column(
                "subscription_expiration_date",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch.create_foreign_key(
            "fk_stars_payments_subscription",
            "stars_subscriptions",
            ["subscription_id"],
            ["subscription_id"],
        )
    op.create_index(
        "ix_stars_payments_subscription_received",
        "stars_payments",
        ["subscription_id", "received_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_stars_payments_subscription_received", table_name="stars_payments"
    )
    with op.batch_alter_table("stars_payments") as batch:
        batch.drop_constraint("fk_stars_payments_subscription", type_="foreignkey")
        batch.drop_column("subscription_expiration_date")
        batch.drop_column("is_first_recurring")
        batch.drop_column("is_recurring")
        batch.drop_column("subscription_id")
        batch.create_unique_constraint("uq_stars_payment_order", ["order_id"])

    op.drop_index(
        "ix_stars_subscriptions_user_status", table_name="stars_subscriptions"
    )
    op.drop_table("stars_subscriptions")

    with op.batch_alter_table("payment_orders") as batch:
        batch.drop_constraint(
            "ck_payment_order_subscription_period", type_="check"
        )
        batch.drop_constraint("ck_payment_order_mode", type_="check")
        batch.drop_constraint("ck_payment_order_status", type_="check")
        batch.drop_column("subscription_period_seconds")
        batch.drop_column("billing_mode")
        batch.create_check_constraint(
            "ck_payment_order_status",
            "status IN ('created', 'prechecked', 'paid', 'expired', "
            "'cancelled', 'refund_pending', 'refunded')",
        )

    with op.batch_alter_table("billing_products") as batch:
        batch.drop_constraint(
            "ck_billing_product_subscription_period", type_="check"
        )
        batch.drop_constraint("ck_billing_product_mode", type_="check")
        batch.drop_column("subscription_period_seconds")
        batch.drop_column("billing_mode")
