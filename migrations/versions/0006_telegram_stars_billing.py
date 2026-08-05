"""Add Telegram Stars orders, payments, wallets, and financial credit ledger."""

from alembic import op
import sqlalchemy as sa


revision = "0006_telegram_stars_billing"
down_revision = "0005_pilot_access"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_wallets",
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("balance_credits", sa.Integer(), nullable=False),
        sa.Column("reserved_credits", sa.Integer(), nullable=False),
        sa.Column("spent_credits", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("balance_credits >= 0", name="ck_ai_wallet_balance"),
        sa.CheckConstraint("reserved_credits >= 0", name="ck_ai_wallet_reserved"),
        sa.CheckConstraint("spent_credits >= 0", name="ck_ai_wallet_spent"),
        sa.CheckConstraint(
            "reserved_credits <= balance_credits",
            name="ck_ai_wallet_reserved_balance",
        ),
        sa.ForeignKeyConstraint(
            ["telegram_user_id"], ["users.telegram_user_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("telegram_user_id"),
    )
    op.execute(
        sa.text(
            "INSERT INTO ai_wallets "
            "(telegram_user_id, balance_credits, reserved_credits, spent_credits, updated_at) "
            "SELECT telegram_user_id, available_credits + reserved_credits, "
            "reserved_credits, spent_credits, updated_at FROM ai_allowances"
        )
    )

    op.create_table(
        "billing_products",
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=32), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("price_xtr", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("estimated_cost_micro_usd", sa.BigInteger(), nullable=False),
        sa.Column("target_margin_bps", sa.Integer(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("credits > 0", name="ck_billing_product_credits"),
        sa.CheckConstraint("price_xtr > 0", name="ck_billing_product_price"),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'archived')",
            name="ck_billing_product_status",
        ),
        sa.CheckConstraint(
            "estimated_cost_micro_usd >= 0", name="ck_billing_product_cost"
        ),
        sa.CheckConstraint(
            "target_margin_bps >= 0 AND target_margin_bps <= 10000",
            name="ck_billing_product_margin",
        ),
        sa.PrimaryKeyConstraint("product_id"),
    )

    op.create_table(
        "payment_orders",
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("product_title", sa.String(length=32), nullable=False),
        sa.Column("product_description", sa.String(length=255), nullable=False),
        sa.Column("credits_snapshot", sa.Integer(), nullable=False),
        sa.Column("amount_xtr", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("invoice_payload", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("prechecked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("credits_snapshot > 0", name="ck_payment_order_credits"),
        sa.CheckConstraint("amount_xtr > 0", name="ck_payment_order_amount"),
        sa.CheckConstraint("currency = 'XTR'", name="ck_payment_order_currency"),
        sa.CheckConstraint(
            "status IN ('created', 'prechecked', 'paid', 'expired', "
            "'cancelled', 'refund_pending', 'refunded')",
            name="ck_payment_order_status",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["billing_products.product_id"]
        ),
        sa.ForeignKeyConstraint(
            ["telegram_user_id"], ["users.telegram_user_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("order_id"),
        sa.UniqueConstraint("invoice_payload", name="uq_payment_order_payload"),
    )
    op.create_index(
        "ix_payment_orders_user_created",
        "payment_orders",
        ["telegram_user_id", "created_at"],
    )
    op.create_index(
        "ix_payment_orders_status_created",
        "payment_orders",
        ["status", "created_at"],
    )

    op.create_table(
        "stars_payments",
        sa.Column("payment_id", sa.String(length=36), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("total_amount", sa.Integer(), nullable=False),
        sa.Column("telegram_payment_charge_id", sa.String(length=255), nullable=False),
        sa.Column("provider_payment_charge_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("total_amount > 0", name="ck_stars_payment_amount"),
        sa.CheckConstraint("currency = 'XTR'", name="ck_stars_payment_currency"),
        sa.CheckConstraint(
            "status IN ('paid', 'refund_pending', 'refunded')",
            name="ck_stars_payment_status",
        ),
        sa.ForeignKeyConstraint(["order_id"], ["payment_orders.order_id"]),
        sa.ForeignKeyConstraint(
            ["telegram_user_id"], ["users.telegram_user_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("payment_id"),
        sa.UniqueConstraint("order_id", name="uq_stars_payment_order"),
        sa.UniqueConstraint(
            "telegram_payment_charge_id", name="uq_stars_payment_charge"
        ),
    )
    op.create_index(
        "ix_stars_payments_user_received",
        "stars_payments",
        ["telegram_user_id", "received_at"],
    )

    op.create_table(
        "billing_credit_ledger",
        sa.Column("entry_id", sa.String(length=36), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("entry_type", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("reference_type", sa.String(length=32), nullable=True),
        sa.Column("reference_id", sa.String(length=255), nullable=True),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("actor", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("delta != 0", name="ck_billing_credit_ledger_delta"),
        sa.CheckConstraint(
            "balance_after >= 0", name="ck_billing_credit_ledger_balance"
        ),
        sa.ForeignKeyConstraint(
            ["telegram_user_id"], ["users.telegram_user_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("entry_id"),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_billing_credit_ledger_idempotency"
        ),
    )
    op.create_index(
        "ix_billing_credit_ledger_user_created",
        "billing_credit_ledger",
        ["telegram_user_id", "created_at"],
    )
    op.execute(
        sa.text(
            "INSERT INTO billing_credit_ledger "
            "(entry_id, telegram_user_id, delta, balance_after, entry_type, "
            "idempotency_key, reference_type, reference_id, reason, actor, created_at) "
            "SELECT entry_id, telegram_user_id, delta, balance_after, "
            "'legacy_admin_adjustment', 'legacy:' || entry_id, 'legacy_ledger', "
            "entry_id, reason, actor, created_at FROM ai_credit_ledger"
        )
    )

    op.create_table(
        "refund_requests",
        sa.Column("refund_id", sa.String(length=36), nullable=False),
        sa.Column("payment_id", sa.String(length=36), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("requested_by", sa.String(length=64), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("credits > 0", name="ck_refund_request_credits"),
        sa.CheckConstraint(
            "status IN ('requested', 'processing', 'completed', 'failed', 'cancelled')",
            name="ck_refund_request_status",
        ),
        sa.ForeignKeyConstraint(["payment_id"], ["stars_payments.payment_id"]),
        sa.ForeignKeyConstraint(
            ["telegram_user_id"], ["users.telegram_user_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("refund_id"),
        sa.UniqueConstraint("payment_id", name="uq_refund_request_payment"),
    )
    op.create_index(
        "ix_refund_requests_status_created",
        "refund_requests",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_refund_requests_status_created", table_name="refund_requests")
    op.drop_table("refund_requests")
    op.drop_index(
        "ix_billing_credit_ledger_user_created", table_name="billing_credit_ledger"
    )
    op.drop_table("billing_credit_ledger")
    op.drop_index("ix_stars_payments_user_received", table_name="stars_payments")
    op.drop_table("stars_payments")
    op.drop_index("ix_payment_orders_status_created", table_name="payment_orders")
    op.drop_index("ix_payment_orders_user_created", table_name="payment_orders")
    op.drop_table("payment_orders")
    op.drop_table("billing_products")
    op.drop_table("ai_wallets")
