"""Telegram Stars billing with signed orders and idempotent credit fulfillment."""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os
import re
from typing import Any, Mapping, Protocol, Sequence
from uuid import UUID, uuid4

from sqlalchemy import select

from mydictionary.storage import (
    AIUsageStateError,
    AdminAuditLog,
    BillingCreditLedger,
    BillingProduct,
    DatabaseStore,
    PaymentOrder,
    RefundRequest,
    StarsPayment,
    StarsSubscription,
    UserConsent,
    utcnow,
)


PRODUCT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{2,59}$")
PAYLOAD_PREFIX = "md1"
PAYLOAD_SIGNATURE_BYTES = 16
PRODUCT_STATUSES = {"draft", "active", "archived"}
BILLING_MODES = {"one_time", "subscription"}
SUBSCRIPTION_PERIOD_SECONDS = 30 * 24 * 60 * 60


def _aware_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class BillingConfigurationError(RuntimeError):
    """Raised when Stars billing is enabled without safe runtime settings."""


class BillingStateError(RuntimeError):
    """Raised when an order, payment, or refund transition is invalid."""


class BillingValidationError(ValueError):
    """Raised when Telegram payment data does not match the signed order."""


def _env_bool(value: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    raise BillingConfigurationError("TELEGRAM_STARS_ENABLED must be a boolean")


@dataclass(frozen=True)
class BillingSettings:
    enabled: bool
    payload_secret: str | None
    support_contact: str
    terms_text: str
    terms_version: str = "unversioned"
    order_ttl_seconds: int = 1800
    net_micro_usd_per_xtr: int = 0

    @classmethod
    def from_env(cls, values: Mapping[str, str] | None = None) -> "BillingSettings":
        env = values if values is not None else os.environ
        enabled = _env_bool(env.get("TELEGRAM_STARS_ENABLED", "false"))
        payload_secret = env.get("BILLING_PAYLOAD_SECRET") or None
        support_contact = env.get("BILLING_SUPPORT_CONTACT", "").strip()
        configured_terms = env.get("BILLING_TERMS_TEXT", "").strip()
        configured_terms_version = env.get("BILLING_TERMS_VERSION", "").strip()
        terms_text = configured_terms or (
            "AI-кредиты используются только для функций AI-репетитора. "
            "Базовые словари и обычные режимы обучения остаются бесплатными."
        )
        try:
            order_ttl_seconds = int(env.get("BILLING_ORDER_TTL_SECONDS", "1800"))
            net_micro_usd_per_xtr = int(
                env.get("BILLING_NET_MICRO_USD_PER_XTR", "0")
            )
        except ValueError as exc:
            raise BillingConfigurationError(
                "Billing TTL and unit economics settings must be integers"
            ) from exc
        if not 300 <= order_ttl_seconds <= 86400:
            raise BillingConfigurationError(
                "BILLING_ORDER_TTL_SECONDS must be between 300 and 86400"
            )
        if net_micro_usd_per_xtr < 0:
            raise BillingConfigurationError(
                "BILLING_NET_MICRO_USD_PER_XTR cannot be negative"
            )
        if not terms_text or len(terms_text) > 3500:
            raise BillingConfigurationError(
                "BILLING_TERMS_TEXT must contain 1 to 3500 characters"
            )
        terms_version = configured_terms_version or "unversioned"
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", terms_version):
            raise BillingConfigurationError(
                "BILLING_TERMS_VERSION must be a safe 1 to 64 character identifier"
            )
        if enabled:
            if not payload_secret or len(payload_secret) < 32:
                raise BillingConfigurationError(
                    "Enabled Stars billing requires BILLING_PAYLOAD_SECRET "
                    "of at least 32 characters"
                )
            if not support_contact or len(support_contact) > 256:
                raise BillingConfigurationError(
                    "Enabled Stars billing requires BILLING_SUPPORT_CONTACT"
                )
            if not configured_terms:
                raise BillingConfigurationError(
                    "Enabled Stars billing requires explicit BILLING_TERMS_TEXT"
                )
            if not configured_terms_version:
                raise BillingConfigurationError(
                    "Enabled Stars billing requires BILLING_TERMS_VERSION"
                )
            if net_micro_usd_per_xtr <= 0:
                raise BillingConfigurationError(
                    "Enabled Stars billing requires BILLING_NET_MICRO_USD_PER_XTR"
                )
        return cls(
            enabled=enabled,
            payload_secret=payload_secret,
            support_contact=support_contact,
            terms_text=terms_text,
            terms_version=terms_version,
            order_ttl_seconds=order_ttl_seconds,
            net_micro_usd_per_xtr=net_micro_usd_per_xtr,
        )


@dataclass(frozen=True)
class InvoiceOrder:
    order_id: str
    product_id: str
    title: str
    description: str
    credits: int
    amount_xtr: int
    payload: str
    subscription_period_seconds: int | None = None


@dataclass(frozen=True)
class FulfillmentResult:
    payment_id: str
    order_id: str
    credits: int
    available_credits: int
    created: bool
    subscription_id: str | None = None


@dataclass(frozen=True)
class ReconciliationIssue:
    code: str
    charge_id: str
    details: str


@dataclass(frozen=True)
class StarTransactionPage:
    rows: tuple[Mapping[str, Any], ...]
    fetched_count: int


class TelegramStarsGatewayProtocol(Protocol):
    async def refund_star_payment(
        self, *, user_id: int, telegram_payment_charge_id: str
    ) -> bool: ...

    async def edit_user_star_subscription(
        self,
        *,
        user_id: int,
        telegram_payment_charge_id: str,
        is_canceled: bool,
    ) -> bool: ...

    async def get_star_transactions(
        self, *, offset: int, limit: int
    ) -> StarTransactionPage: ...


class TelegramStarsGateway:
    """Normalize python-telegram-bot Stars methods behind a testable protocol."""

    def __init__(self, bot: Any):
        self.bot = bot

    async def refund_star_payment(
        self, *, user_id: int, telegram_payment_charge_id: str
    ) -> bool:
        return bool(
            await self.bot.refund_star_payment(
                user_id=int(user_id),
                telegram_payment_charge_id=str(telegram_payment_charge_id),
            )
        )

    async def edit_user_star_subscription(
        self,
        *,
        user_id: int,
        telegram_payment_charge_id: str,
        is_canceled: bool,
    ) -> bool:
        return bool(
            await self.bot.edit_user_star_subscription(
                user_id=int(user_id),
                telegram_payment_charge_id=str(telegram_payment_charge_id),
                is_canceled=bool(is_canceled),
            )
        )

    async def get_star_transactions(
        self, *, offset: int, limit: int
    ) -> StarTransactionPage:
        page = await self.bot.get_star_transactions(
            offset=max(0, int(offset)), limit=max(1, min(int(limit), 100))
        )
        source_rows = tuple(getattr(page, "transactions", ()))
        normalized = []
        for transaction in source_rows:
            source = getattr(transaction, "source", None)
            receiver = getattr(transaction, "receiver", None)
            partner = source or receiver
            if (
                partner is None
                or getattr(partner, "transaction_type", "")
                != "invoice_payment"
            ):
                continue
            user = getattr(partner, "user", None)
            normalized.append(
                {
                    "telegram_payment_charge_id": str(
                        getattr(transaction, "id", "")
                    ),
                    "user_id": int(getattr(user, "id", 0) or 0),
                    "currency": "XTR",
                    "total_amount": abs(
                        int(getattr(transaction, "amount", 0) or 0)
                    ),
                    "is_refund": receiver is not None,
                    "subscription_period": getattr(
                        partner, "subscription_period", None
                    ),
                }
            )
        return StarTransactionPage(tuple(normalized), len(source_rows))


class BillingService:
    def __init__(self, store: DatabaseStore, settings: BillingSettings):
        self.store = store
        self.settings = settings

    def active_products(self) -> list[dict[str, Any]]:
        with self.store.Session() as session:
            rows = session.execute(
                select(BillingProduct)
                .where(BillingProduct.status == "active")
                .order_by(BillingProduct.display_order, BillingProduct.price_xtr)
            ).scalars().all()
        return [self._product_dict(row) for row in rows]

    def product_margin_bps(self, product: BillingProduct | Mapping[str, Any]) -> int | None:
        price_xtr = int(
            product.price_xtr
            if isinstance(product, BillingProduct)
            else product["price_xtr"]
        )
        cost = int(
            product.estimated_cost_micro_usd
            if isinstance(product, BillingProduct)
            else product["estimated_cost_micro_usd"]
        )
        revenue = price_xtr * self.settings.net_micro_usd_per_xtr
        if revenue <= 0:
            return None
        return ((revenue - cost) * 10000) // revenue

    @staticmethod
    def _product_dict(row: BillingProduct) -> dict[str, Any]:
        return {
            column.name: getattr(row, column.name)
            for column in BillingProduct.__table__.columns
        }

    def _secret(self) -> bytes:
        secret = self.settings.payload_secret
        if not secret or len(secret) < 32:
            raise BillingConfigurationError("Billing payload secret is not configured")
        return secret.encode("utf-8")

    def _lock_current_terms_consent(self, session: Any, user_id: int) -> None:
        consent = session.execute(
            select(UserConsent)
            .where(
                UserConsent.telegram_user_id == int(user_id),
                UserConsent.consent_type == "billing_terms",
                UserConsent.document_version == self.settings.terms_version,
                UserConsent.revoked_at.is_(None),
            )
            .with_for_update()
        ).scalar_one_or_none()
        if consent is None:
            raise BillingValidationError("Current billing terms are not accepted")

    def _signature(
        self, *, order_id: str, user_id: int, amount_xtr: int, credits: int
    ) -> str:
        message = f"{order_id}:{int(user_id)}:{int(amount_xtr)}:{int(credits)}"
        digest = hmac.new(
            self._secret(), message.encode("ascii"), hashlib.sha256
        ).digest()[:PAYLOAD_SIGNATURE_BYTES]
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    def _payload(
        self, *, order_id: str, user_id: int, amount_xtr: int, credits: int
    ) -> str:
        order_hex = UUID(order_id).hex
        signature = self._signature(
            order_id=order_id,
            user_id=user_id,
            amount_xtr=amount_xtr,
            credits=credits,
        )
        payload = f"{PAYLOAD_PREFIX}.{order_hex}.{signature}"
        if len(payload.encode("utf-8")) > 128:
            raise BillingConfigurationError("Invoice payload exceeds Telegram limit")
        return payload

    @staticmethod
    def _order_id_from_payload(payload: str) -> str:
        try:
            prefix, order_hex, signature = str(payload).split(".")
            order_id = str(UUID(hex=order_hex))
        except (TypeError, ValueError) as exc:
            raise BillingValidationError("Malformed invoice payload") from exc
        if prefix != PAYLOAD_PREFIX or len(signature) < 16:
            raise BillingValidationError("Malformed invoice payload")
        return order_id

    def _validate_payload(self, order: PaymentOrder, payload: str) -> None:
        expected = self._payload(
            order_id=order.order_id,
            user_id=order.telegram_user_id,
            amount_xtr=order.amount_xtr,
            credits=order.credits_snapshot,
        )
        if not hmac.compare_digest(expected, str(payload)):
            raise BillingValidationError("Invoice payload signature mismatch")

    def create_order(self, *, user_id: int, product_id: str) -> InvoiceOrder:
        if not self.settings.enabled:
            raise BillingConfigurationError("Telegram Stars billing is disabled")
        self.store.ensure_user_id(user_id)
        with self.store.Session.begin() as session:
            self._lock_current_terms_consent(session, user_id)
            product = session.get(BillingProduct, str(product_id))
            if product is None or product.status != "active":
                raise BillingValidationError("Billing product is not available")
            margin_bps = self.product_margin_bps(product)
            if margin_bps is None or margin_bps < product.target_margin_bps:
                raise BillingConfigurationError(
                    "Billing product does not satisfy its configured margin floor"
                )
            order_id = str(uuid4())
            payload = self._payload(
                order_id=order_id,
                user_id=user_id,
                amount_xtr=product.price_xtr,
                credits=product.credits,
            )
            session.add(
                PaymentOrder(
                    order_id=order_id,
                    telegram_user_id=int(user_id),
                    product_id=product.product_id,
                    product_title=product.title,
                    product_description=product.description,
                    credits_snapshot=product.credits,
                    amount_xtr=product.price_xtr,
                    currency="XTR",
                    terms_version=self.settings.terms_version,
                    invoice_payload=payload,
                    billing_mode=product.billing_mode,
                    subscription_period_seconds=(
                        product.subscription_period_seconds
                        if product.billing_mode == "subscription"
                        else None
                    ),
                    status="created",
                    expires_at=utcnow()
                    + timedelta(seconds=self.settings.order_ttl_seconds),
                )
            )
        return InvoiceOrder(
            order_id=order_id,
            product_id=product.product_id,
            title=product.title,
            description=product.description,
            credits=product.credits,
            amount_xtr=product.price_xtr,
            payload=payload,
            subscription_period_seconds=(
                product.subscription_period_seconds
                if product.billing_mode == "subscription"
                else None
            ),
        )

    def validate_pre_checkout(
        self,
        *,
        user_id: int,
        payload: str,
        currency: str,
        total_amount: int,
    ) -> str:
        if not self.settings.enabled:
            raise BillingConfigurationError("Telegram Stars billing is disabled")
        order_id = self._order_id_from_payload(payload)
        with self.store.Session.begin() as session:
            self._lock_current_terms_consent(session, user_id)
            order = session.execute(
                select(PaymentOrder)
                .where(PaymentOrder.order_id == order_id)
                .with_for_update()
            ).scalar_one_or_none()
            if order is None:
                raise BillingValidationError("Payment order does not exist")
            self._validate_payload(order, payload)
            if order.telegram_user_id != int(user_id):
                raise BillingValidationError("Payment order belongs to another user")
            if str(currency) != "XTR" or order.currency != "XTR":
                raise BillingValidationError("Payment currency mismatch")
            if int(total_amount) != order.amount_xtr:
                raise BillingValidationError("Payment amount mismatch")
            if order.terms_version != self.settings.terms_version:
                raise BillingValidationError("Payment order uses outdated terms")
            if order.status not in {"created", "prechecked"}:
                raise BillingStateError("Payment order is not payable")
            if _aware_utc(order.expires_at) < utcnow():
                order.status = "expired"
                order.updated_at = utcnow()
                raise BillingStateError("Payment order expired")
            order.status = "prechecked"
            order.prechecked_at = utcnow()
            order.updated_at = utcnow()
            return order.order_id

    def fulfill_successful_payment(
        self,
        *,
        user_id: int,
        payload: str,
        currency: str,
        total_amount: int,
        telegram_payment_charge_id: str,
        provider_payment_charge_id: str | None = None,
        is_recurring: bool = False,
        is_first_recurring: bool = False,
        subscription_expiration_date: datetime | None = None,
    ) -> FulfillmentResult:
        """Grant credits exactly once, including after the feature flag is disabled."""
        order_id = self._order_id_from_payload(payload)
        charge_id = str(telegram_payment_charge_id).strip()
        if not charge_id or len(charge_id) > 255:
            raise BillingValidationError("Telegram payment charge ID is invalid")
        with self.store.Session.begin() as session:
            order = session.execute(
                select(PaymentOrder)
                .where(PaymentOrder.order_id == order_id)
                .with_for_update()
            ).scalar_one_or_none()
            if order is None:
                raise BillingValidationError("Payment order does not exist")
            self._validate_payload(order, payload)
            if order.telegram_user_id != int(user_id):
                raise BillingValidationError("Payment order belongs to another user")
            if str(currency) != "XTR" or int(total_amount) != order.amount_xtr:
                raise BillingValidationError("Successful payment does not match order")
            recurring = bool(is_recurring or is_first_recurring)
            if order.billing_mode == "subscription":
                if not recurring or subscription_expiration_date is None:
                    raise BillingValidationError(
                        "Subscription payment metadata is missing"
                    )
                expiration = _aware_utc(subscription_expiration_date)
                if expiration <= utcnow():
                    raise BillingValidationError(
                        "Subscription expiration date is invalid"
                    )
            elif recurring or subscription_expiration_date is not None:
                raise BillingValidationError(
                    "One-time order cannot accept a recurring payment"
                )
            else:
                expiration = None
            existing_charge = session.execute(
                select(StarsPayment)
                .where(StarsPayment.telegram_payment_charge_id == charge_id)
                .with_for_update()
            ).scalar_one_or_none()
            if existing_charge is not None:
                if existing_charge.order_id != order.order_id:
                    raise BillingStateError("Telegram charge is already used")
                wallet = self.store._ensure_ai_wallet(session, user_id)
                return FulfillmentResult(
                    payment_id=existing_charge.payment_id,
                    order_id=order.order_id,
                    credits=order.credits_snapshot,
                    available_credits=(
                        wallet.balance_credits - wallet.reserved_credits
                    ),
                    created=False,
                    subscription_id=existing_charge.subscription_id,
                )
            subscription = session.execute(
                select(StarsSubscription)
                .where(StarsSubscription.order_id == order.order_id)
                .with_for_update()
            ).scalar_one_or_none()
            if order.billing_mode == "one_time":
                if order.status == "paid":
                    raise BillingStateError("Paid order has no matching charge record")
                if order.status not in {"created", "prechecked"}:
                    raise BillingStateError("Payment order cannot be fulfilled")
                subscription_id = None
            elif is_first_recurring:
                if subscription is not None:
                    raise BillingStateError(
                        "Subscription already has its first payment"
                    )
                if order.status not in {"created", "prechecked"}:
                    raise BillingStateError("Subscription order cannot be fulfilled")
                subscription_id = str(uuid4())
                subscription = StarsSubscription(
                    subscription_id=subscription_id,
                    order_id=order.order_id,
                    telegram_user_id=int(user_id),
                    product_id=order.product_id,
                    telegram_payment_charge_id=charge_id,
                    status="active",
                    period_seconds=order.subscription_period_seconds,
                    current_period_end=expiration,
                )
                session.add(subscription)
            else:
                if subscription is None:
                    raise BillingStateError(
                        "Subscription renewal has no first payment"
                    )
                if subscription.telegram_user_id != int(user_id):
                    raise BillingValidationError(
                        "Subscription belongs to another user"
                    )
                subscription_id = subscription.subscription_id
                subscription.status = "active"
                subscription.cancelled_at = None
                subscription.current_period_end = expiration
                subscription.updated_at = utcnow()
            wallet = self.store._ensure_ai_wallet(session, user_id)
            wallet.balance_credits += order.credits_snapshot
            wallet.updated_at = utcnow()
            payment_id = str(uuid4())
            session.add(
                StarsPayment(
                    payment_id=payment_id,
                    order_id=order.order_id,
                    telegram_user_id=int(user_id),
                    currency="XTR",
                    total_amount=order.amount_xtr,
                    telegram_payment_charge_id=charge_id,
                    provider_payment_charge_id=(
                        str(provider_payment_charge_id)[:255]
                        if provider_payment_charge_id
                        else None
                    ),
                    subscription_id=subscription_id,
                    is_recurring=recurring,
                    is_first_recurring=bool(is_first_recurring),
                    subscription_expiration_date=expiration,
                    status="paid",
                )
            )
            session.add(
                BillingCreditLedger(
                    entry_id=str(uuid4()),
                    telegram_user_id=int(user_id),
                    delta=order.credits_snapshot,
                    balance_after=wallet.balance_credits,
                    entry_type=(
                        "stars_subscription_renewal"
                        if recurring
                        else "stars_purchase"
                    ),
                    idempotency_key=f"stars-payment:{charge_id}",
                    reference_type="stars_payment",
                    reference_id=payment_id,
                    reason=(
                        f"Telegram Stars subscription: {order.product_id}"
                        if recurring
                        else f"Telegram Stars purchase: {order.product_id}"
                    )[:255],
                    actor="telegram",
                )
            )
            order.status = (
                "subscription_active"
                if order.billing_mode == "subscription"
                else "paid"
            )
            if order.paid_at is None:
                order.paid_at = utcnow()
            order.updated_at = utcnow()
            available = wallet.balance_credits - wallet.reserved_credits
        return FulfillmentResult(
            payment_id=payment_id,
            order_id=order_id,
            credits=order.credits_snapshot,
            available_credits=available,
            created=True,
            subscription_id=subscription_id,
        )

    def request_refund(
        self, *, payment_id: str, reason: str, actor: str
    ) -> str:
        reason = str(reason).strip()
        if not 3 <= len(reason) <= 255:
            raise ValueError("Refund reason must contain 3 to 255 characters")
        with self.store.Session.begin() as session:
            payment = session.execute(
                select(StarsPayment)
                .where(StarsPayment.payment_id == str(payment_id))
                .with_for_update()
            ).scalar_one_or_none()
            if payment is None:
                raise BillingValidationError("Stars payment does not exist")
            existing = session.execute(
                select(RefundRequest).where(
                    RefundRequest.payment_id == payment.payment_id
                )
            ).scalar_one_or_none()
            if existing is not None:
                return existing.refund_id
            if payment.status != "paid":
                raise BillingStateError("Stars payment is not refundable")
            order = session.execute(
                select(PaymentOrder)
                .where(PaymentOrder.order_id == payment.order_id)
                .with_for_update()
            ).scalar_one()
            wallet = self.store._ensure_ai_wallet(session, payment.telegram_user_id)
            available = wallet.balance_credits - wallet.reserved_credits
            if available < order.credits_snapshot:
                raise BillingStateError(
                    "Purchased credits are already reserved or spent; manual review required"
                )
            wallet.reserved_credits += order.credits_snapshot
            wallet.updated_at = utcnow()
            refund_id = str(uuid4())
            session.add(
                RefundRequest(
                    refund_id=refund_id,
                    payment_id=payment.payment_id,
                    telegram_user_id=payment.telegram_user_id,
                    credits=order.credits_snapshot,
                    status="requested",
                    reason=reason,
                    requested_by=actor[:64],
                )
            )
            payment.status = "refund_pending"
            if payment.subscription_id is None:
                order.status = "refund_pending"
            session.add(
                AdminAuditLog(
                    actor=actor[:64],
                    action="stars_refund_requested",
                    target_type="stars_payment",
                    target_id=payment.payment_id,
                    details_json=(
                        '{"credits":%d,"refund_id":"%s"}'
                        % (order.credits_snapshot, refund_id)
                    ),
                )
            )
            return refund_id

    async def process_refund(
        self, *, refund_id: str, gateway: TelegramStarsGatewayProtocol
    ) -> bool:
        """Process a queued refund through an injected gateway, never implicitly."""
        with self.store.Session.begin() as session:
            refund = session.execute(
                select(RefundRequest)
                .where(RefundRequest.refund_id == str(refund_id))
                .with_for_update()
            ).scalar_one_or_none()
            if refund is None:
                raise BillingValidationError("Refund request does not exist")
            if refund.status == "completed":
                return True
            if refund.status not in {"requested", "failed"}:
                raise BillingStateError("Refund request is not processable")
            payment = session.get(StarsPayment, refund.payment_id)
            refund.status = "processing"
            refund.error_code = None
            refund.updated_at = utcnow()
            user_id = refund.telegram_user_id
            charge_id = payment.telegram_payment_charge_id
        try:
            refunded = await asyncio.wait_for(
                gateway.refund_star_payment(
                    user_id=user_id,
                    telegram_payment_charge_id=charge_id,
                ),
                timeout=8,
            )
            if not refunded:
                raise BillingStateError("Telegram rejected the Stars refund")
        except Exception as exc:
            with self.store.Session.begin() as session:
                refund = session.get(RefundRequest, str(refund_id))
                if refund and refund.status == "processing":
                    refund.status = "failed"
                    refund.error_code = type(exc).__name__[:128]
                    refund.updated_at = utcnow()
            return False
        with self.store.Session.begin() as session:
            refund = session.execute(
                select(RefundRequest)
                .where(RefundRequest.refund_id == str(refund_id))
                .with_for_update()
            ).scalar_one()
            payment = session.execute(
                select(StarsPayment)
                .where(StarsPayment.payment_id == refund.payment_id)
                .with_for_update()
            ).scalar_one()
            order = session.execute(
                select(PaymentOrder)
                .where(PaymentOrder.order_id == payment.order_id)
                .with_for_update()
            ).scalar_one()
            wallet = self.store._ensure_ai_wallet(session, refund.telegram_user_id)
            if wallet.reserved_credits < refund.credits:
                raise AIUsageStateError("Refund credit hold is missing")
            wallet.reserved_credits -= refund.credits
            wallet.balance_credits -= refund.credits
            wallet.updated_at = utcnow()
            session.add(
                BillingCreditLedger(
                    entry_id=str(uuid4()),
                    telegram_user_id=refund.telegram_user_id,
                    delta=-refund.credits,
                    balance_after=wallet.balance_credits,
                    entry_type="stars_refund",
                    idempotency_key=f"stars-refund:{payment.telegram_payment_charge_id}",
                    reference_type="refund",
                    reference_id=refund.refund_id,
                    reason=refund.reason,
                    actor=refund.requested_by,
                )
            )
            now = utcnow()
            refund.status = "completed"
            refund.completed_at = now
            refund.updated_at = now
            payment.status = "refunded"
            payment.refunded_at = now
            if payment.subscription_id is None:
                order.status = "refunded"
                order.refunded_at = now
                order.updated_at = now
            session.add(
                AdminAuditLog(
                    actor=refund.requested_by,
                    action="stars_refund_completed",
                    target_type="stars_payment",
                    target_id=payment.payment_id,
                    details_json='{"refund_id":"%s"}' % refund.refund_id,
                )
            )
        return True

    def subscriptions_for_user(self, user_id: int) -> list[dict[str, Any]]:
        with self.store.Session() as session:
            rows = session.execute(
                select(StarsSubscription)
                .where(StarsSubscription.telegram_user_id == int(user_id))
                .order_by(StarsSubscription.created_at.desc())
            ).scalars().all()
        return [
            {
                column.name: getattr(row, column.name)
                for column in StarsSubscription.__table__.columns
                if column.name != "telegram_payment_charge_id"
            }
            for row in rows
        ]

    async def set_subscription_autorenew(
        self,
        *,
        subscription_id: str,
        user_id: int,
        is_canceled: bool,
        gateway: TelegramStarsGatewayProtocol,
    ) -> bool:
        with self.store.Session() as session:
            subscription = session.get(StarsSubscription, str(subscription_id))
            if subscription is None:
                raise BillingValidationError("Stars subscription does not exist")
            if subscription.telegram_user_id != int(user_id):
                raise BillingValidationError(
                    "Stars subscription belongs to another user"
                )
            desired_status = "cancelled" if is_canceled else "active"
            if subscription.status == desired_status:
                return True
            charge_id = subscription.telegram_payment_charge_id
        changed = await asyncio.wait_for(
            gateway.edit_user_star_subscription(
                user_id=int(user_id),
                telegram_payment_charge_id=charge_id,
                is_canceled=bool(is_canceled),
            ),
            timeout=8,
        )
        if not changed:
            raise BillingStateError("Telegram rejected subscription update")
        with self.store.Session.begin() as session:
            subscription = session.execute(
                select(StarsSubscription)
                .where(StarsSubscription.subscription_id == str(subscription_id))
                .with_for_update()
            ).scalar_one()
            subscription.status = desired_status
            subscription.cancelled_at = utcnow() if is_canceled else None
            subscription.updated_at = utcnow()
            order = session.get(PaymentOrder, subscription.order_id)
            order.status = (
                "subscription_cancelled" if is_canceled else "subscription_active"
            )
            order.updated_at = utcnow()
        return True

    async def reconcile_gateway(
        self,
        gateway: TelegramStarsGatewayProtocol,
        *,
        page_size: int = 100,
        maximum_transactions: int = 1000,
    ) -> list[ReconciliationIssue]:
        page_size = max(1, min(int(page_size), 100))
        maximum_transactions = max(page_size, min(int(maximum_transactions), 10000))
        transactions: list[Mapping[str, Any]] = []
        offset = 0
        history_complete = False
        while offset < maximum_transactions:
            request_limit = min(page_size, maximum_transactions - offset)
            page = await gateway.get_star_transactions(
                offset=offset,
                limit=request_limit,
            )
            transactions.extend(page.rows)
            if page.fetched_count < request_limit:
                history_complete = True
                break
            offset += page.fetched_count
        issues = self.reconcile_transactions(transactions)
        if not history_complete:
            issues.append(
                ReconciliationIssue(
                    "remote_history_truncated",
                    "history",
                    "Telegram history reached the configured reconciliation limit",
                )
            )
            return issues
        remote_ids = {
            str(row.get("telegram_payment_charge_id") or "")
            for row in transactions
        }
        with self.store.Session() as session:
            local_ids = set(
                session.execute(
                    select(StarsPayment.telegram_payment_charge_id).where(
                        StarsPayment.status.in_(
                            {"paid", "refund_pending", "refunded"}
                        )
                    )
                ).scalars()
            )
        for charge_id in sorted(local_ids - remote_ids):
            issues.append(
                ReconciliationIssue(
                    "local_payment_missing_remotely",
                    charge_id,
                    "Local payment is absent from the fetched Telegram history",
                )
            )
        return issues

    def reconcile_transactions(
        self, transactions: Sequence[Mapping[str, Any]]
    ) -> list[ReconciliationIssue]:
        """Compare an explicitly supplied Telegram transaction page to local rows."""
        issues: list[ReconciliationIssue] = []
        grouped: dict[str, list[Mapping[str, Any]]] = {}
        for transaction in transactions:
            charge_id = str(
                transaction.get("telegram_payment_charge_id") or ""
            ).strip()
            if not charge_id:
                issues.append(
                    ReconciliationIssue(
                        "remote_charge_missing", "", "Remote row has no charge ID"
                    )
                )
                continue
            grouped.setdefault(charge_id, []).append(transaction)
        with self.store.Session() as session:
            for charge_id, charge_rows in grouped.items():
                payment = session.execute(
                    select(StarsPayment).where(
                        StarsPayment.telegram_payment_charge_id == charge_id
                    )
                ).scalar_one_or_none()
                if payment is None:
                    issues.append(
                        ReconciliationIssue(
                            "remote_payment_missing_locally",
                            charge_id,
                            "Telegram transaction has no local payment",
                        )
                    )
                    continue
                if any(
                    int(row.get("user_id") or 0) != payment.telegram_user_id
                    or str(row.get("currency") or "") != payment.currency
                    or int(row.get("total_amount") or 0) != payment.total_amount
                    for row in charge_rows
                ):
                    issues.append(
                        ReconciliationIssue(
                            "remote_payment_mismatch",
                            charge_id,
                            "User, currency, or amount differs from the local payment",
                        )
                    )
                remote_refunded = any(
                    bool(row.get("is_refund")) for row in charge_rows
                )
                if remote_refunded and payment.status == "paid":
                    issues.append(
                        ReconciliationIssue(
                            "remote_refund_missing_locally",
                            charge_id,
                            "Telegram reports a refund while the local payment is paid",
                        )
                    )
                elif remote_refunded and payment.status == "refund_pending":
                    issues.append(
                        ReconciliationIssue(
                            "remote_refund_pending_locally",
                            charge_id,
                            "Telegram reports a refund while local finalization is pending",
                        )
                    )
                elif not remote_refunded and payment.status == "refunded":
                    issues.append(
                        ReconciliationIssue(
                            "local_refund_missing_remotely",
                            charge_id,
                            "Local payment is refunded without a Telegram refund row",
                        )
                    )
                elif not remote_refunded and payment.status == "refund_pending":
                    issues.append(
                        ReconciliationIssue(
                            "local_refund_pending_remotely",
                            charge_id,
                            "Local refund remains pending without a Telegram refund row",
                        )
                    )
        return issues
