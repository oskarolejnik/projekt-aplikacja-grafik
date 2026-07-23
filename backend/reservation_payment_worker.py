"""Durable R5c provider-command worker for reservation payments.

The reservation transaction only appends ``RezerwacjaPlatnoscPolecenie`` rows.
This module claims one row in a short transaction, commits the lease, performs
Stripe I/O with no database session open, then projects the result in another
short transaction.  Every retry reuses the command's immutable provider key.

The same worker consumes the signed, metadata-only webhook inbox. It retrieves
canonical Stripe objects outside database transactions and applies the same
monotonic aggregate projection as command reconciliation.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
import logging
import secrets
import threading
from typing import Any, Literal, Mapping

from sqlalchemy import text

import integracje
import models
import reservation_audit
import reservation_payments
import reservation_service
from database import SessionLocal
from deps import utcnow_naive
from stripe_payments import (
    StripePaymentDriver,
    StripePaymentsError,
    StripeSDKUnavailable,
)


logger = logging.getLogger(__name__)

PENDING_STATES = ("queued", "retry")
LEASE_SECONDS = 120
SUPPORTED_COMMANDS = frozenset(
    {
        "create_checkout",
        "capture",
        "cancel_authorization",
        "refund",
        "reconcile",
    }
)
WEBHOOK_EVENT_OBJECTS = {
    "checkout.session.completed": "checkout.session",
    "checkout.session.async_payment_succeeded": "checkout.session",
    "checkout.session.async_payment_failed": "checkout.session",
    "checkout.session.expired": "checkout.session",
    "payment_intent.amount_capturable_updated": "payment_intent",
    "payment_intent.succeeded": "payment_intent",
    "payment_intent.payment_failed": "payment_intent",
    "payment_intent.canceled": "payment_intent",
    "refund.created": "refund",
    "refund.updated": "refund",
    "refund.failed": "refund",
}
WEBHOOK_LEASE_SECONDS = 120

_stop_event = threading.Event()
_state_lock = threading.Lock()
_thread: threading.Thread | None = None

ProviderOutcome = Literal["succeeded", "retry", "failed", "uncertain"]


class ProviderCommandContractError(RuntimeError):
    """A provider replied, but its object cannot be projected safely."""


class PaymentIntegrationDisabled(RuntimeError):
    """The signed webhook/worker surface is unavailable without full settings."""

    code = "PAYMENT_INTEGRATION_DISABLED"


@dataclass(frozen=True)
class ClaimedPaymentCommand:
    id: int
    payment_id: int
    attempt_number: int
    lease_token: str
    command_type: str
    command_ref: str
    command_amount_minor: int | None
    payment_ref: str
    reservation_ref: str | None
    reservation_revision: int
    policy_version: str
    payment_amount_minor: int
    captured_minor: int
    refunded_minor: int
    capture_mode: str
    payment_expires_at: datetime | None
    checkout_session_id: str | None
    payment_intent_id: str | None
    refund_id: str | None
    reconcile_source_id: int | None = None
    reconcile_source_type: str | None = None
    reconcile_source_ref: str | None = None
    reconcile_source_amount_minor: int | None = None
    reconcile_source_provider_object_id: str | None = None


@dataclass(frozen=True)
class ProviderCommandResult:
    outcome: ProviderOutcome
    code: str | None = None
    provider_object_id: str | None = None
    checkout_session_id: str | None = None
    payment_intent_id: str | None = None
    charge_id: str | None = None
    checkout_url: str | None = None
    checkout_expires_at: datetime | None = None
    payment_target: str | None = None
    captured_minor: int | None = None
    authorization_expires_at: datetime | None = None
    refund_status: str | None = None
    provider_object_type: str | None = None
    provider_payment_ref: str | None = None
    provider_client_reference: str | None = None
    provider_currency: str | None = None
    provider_amount_minor: int | None = None


@dataclass(frozen=True)
class ClaimedPaymentWebhook:
    id: int
    payment_id: int | None
    attempt_number: int
    lease_token: str
    event_id: str
    event_type: str
    object_id: str
    object_type: str


@dataclass(frozen=True)
class WebhookProcessingResult:
    outcome: Literal["processed", "ignored", "retry", "failed"]
    code: str | None = None
    projection: ProviderCommandResult | None = None


@dataclass(frozen=True)
class IngestedPaymentWebhook:
    id: int
    duplicate: bool
    state: str


def _now(value: datetime | None = None) -> datetime:
    result = value or utcnow_naive()
    if result.tzinfo is not None:
        result = result.astimezone(timezone.utc).replace(tzinfo=None)
    return result


def _begin_worker_write(db) -> None:
    if db.get_bind().dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))


def _locked(query, db, *, skip_locked: bool = False):
    if db.get_bind().dialect.name == "postgresql":
        return query.with_for_update(skip_locked=skip_locked)
    return query


def _value(source: Any, key: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def _nested(source: Any, *keys: str) -> Any:
    value = source
    for key in keys:
        value = _value(value, key)
        if value is None:
            break
    return value


def _provider_id(value: Any, prefix: str, *, required: bool = False) -> str | None:
    candidate = value if isinstance(value, str) else _value(value, "id")
    if candidate is None and not required:
        return None
    if (
        not isinstance(candidate, str)
        or not candidate.startswith(prefix)
        or len(candidate) > 255
    ):
        raise ProviderCommandContractError("Unexpected provider object identifier.")
    return candidate


def _provider_status(value: Any, allowed: set[str], object_name: str) -> str:
    status = _value(value, "status")
    if status not in allowed:
        raise ProviderCommandContractError(
            f"Unexpected {object_name} status contract."
        )
    return status


def _from_epoch(value: Any) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    try:
        return datetime.fromtimestamp(value, timezone.utc).replace(tzinfo=None)
    except (OverflowError, OSError, ValueError):
        return None


def _to_epoch(value: datetime | None) -> int | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return int(value.timestamp())


def _policy_version(snapshot: Any) -> str:
    raw = snapshot.get("version", 1) if isinstance(snapshot, Mapping) else 1
    if isinstance(raw, bool) or not isinstance(raw, (int, str)):
        raw = 1
    value = str(raw)
    if not value or len(value) > 40 or not value.replace("-", "").isalnum():
        value = "1"
    return f"r5c-{value}"


def backoff_seconds(command_id: int, attempt_number: int) -> int:
    base = min(6 * 60 * 60, 30 * (4 ** max(0, attempt_number - 1)))
    jitter = int(
        hashlib.sha256(f"{command_id}:{attempt_number}".encode("ascii")).hexdigest()[:4],
        16,
    ) % max(1, base // 5)
    return base + jitter


def _finish_without_io(row, *, state: str, code: str, now: datetime) -> None:
    row.stan = state
    row.lease_token = None
    row.lease_expires_at = None
    row.last_error_code = code
    row.updated_at = now
    row.finished_at = now
    if state == "uncertain":
        row.uncertain_at = now


def _recover_expired_leases(db, now: datetime) -> int:
    query = db.query(models.RezerwacjaPlatnoscPolecenie).filter(
        models.RezerwacjaPlatnoscPolecenie.stan == "processing",
        models.RezerwacjaPlatnoscPolecenie.lease_expires_at <= now,
    ).order_by(models.RezerwacjaPlatnoscPolecenie.id)
    rows = _locked(query, db, skip_locked=True).all()
    for row in rows:
        if row.expires_at > now and row.liczba_prob < row.maks_prob:
            row.stan = "retry"
            row.available_at = now
            row.last_error_code = "LEASE_EXPIRED_SAFE_RETRY"
            row.updated_at = now
            row.lease_token = None
            row.lease_expires_at = None
        else:
            # A lease is committed immediately before provider I/O.  If its retry
            # window is gone, local state cannot prove whether Stripe accepted it.
            _finish_without_io(
                row,
                state="uncertain",
                code="LEASE_EXPIRED_RECONCILIATION_REQUIRED",
                now=now,
            )
    return len(rows)


def _settle_stale_command(row, payment, *, now: datetime) -> bool:
    if payment is None:
        _finish_without_io(
            row, state="cancelled", code="PAYMENT_OWNER_MISSING", now=now
        )
        return True

    satisfied = (
        (row.typ == "create_checkout" and payment.provider_checkout_session_id)
        or (row.typ == "capture" and payment.status in {"oplacona", "zwrocona"})
        or (
            row.typ == "cancel_authorization"
            and payment.status in {"anulowana", "wygasla"}
        )
        or (row.typ == "refund" and payment.status == "zwrocona")
    )
    if satisfied:
        _finish_without_io(
            row, state="succeeded", code="ALREADY_RECONCILED", now=now
        )
        return True

    relevant = {
        "create_checkout": payment.status == "oczekuje",
        "capture": payment.status == "autoryzowana",
        "cancel_authorization": payment.status in {"oczekuje", "autoryzowana"},
        "refund": payment.status == "oplacona",
        "reconcile": True,
    }.get(row.typ, False)
    if not relevant:
        _finish_without_io(
            row, state="cancelled", code="PAYMENT_COMMAND_STALE", now=now
        )
        return True
    return False


def _refund_reference(db, payment_id: int) -> str | None:
    row = db.query(models.RezerwacjaPlatnoscPolecenie).filter(
        models.RezerwacjaPlatnoscPolecenie.platnosc_id == payment_id,
        models.RezerwacjaPlatnoscPolecenie.typ == "refund",
        models.RezerwacjaPlatnoscPolecenie.provider_object_id.isnot(None),
    ).order_by(models.RezerwacjaPlatnoscPolecenie.id.desc()).first()
    if row is None or not str(row.provider_object_id).startswith("re_"):
        return None
    return row.provider_object_id


def _expire_due_commands_before_claim(db, now: datetime) -> int:
    """Settle queued commands whose durable execution window has elapsed.

    Candidate discovery deliberately does not lock command rows yet.  For a
    Checkout expiry we first acquire the reservation-day guard, matching normal
    reservation writers, and only then lock command/payment rows and revalidate.
    """

    candidates = db.query(
        models.RezerwacjaPlatnoscPolecenie.id,
        models.RezerwacjaPlatnoscPolecenie.platnosc_id,
        models.RezerwacjaPlatnoscPolecenie.typ,
    ).filter(
        models.RezerwacjaPlatnoscPolecenie.stan.in_(PENDING_STATES),
        models.RezerwacjaPlatnoscPolecenie.expires_at <= now,
    ).order_by(models.RezerwacjaPlatnoscPolecenie.id).all()
    settled = 0
    for command_id, payment_id, command_type in candidates:
        day_guards = (
            _lock_projection_reservation_day(db, payment_id, "wygasla")
            if command_type == "create_checkout"
            else ()
        )
        row_query = db.query(models.RezerwacjaPlatnoscPolecenie).filter_by(
            id=command_id,
        )
        row = _locked(row_query, db).first()
        if (
            row is None
            or row.stan not in PENDING_STATES
            or row.expires_at > now
        ):
            continue
        payment_query = db.query(models.Platnosc).filter_by(id=row.platnosc_id)
        payment = _locked(payment_query, db).first()
        if _settle_stale_command(row, payment, now=now):
            settled += 1
            continue
        if row.liczba_prob > 0 or row.provider_object_id is not None:
            # Provider I/O may already have happened. A deadline cannot turn an
            # ambiguous financial result into a local failure or release a table.
            _finish_without_io(
                row,
                state="uncertain",
                code="PROVIDER_RECONCILIATION_REQUIRED",
                now=now,
            )
            settled += 1
            continue
        if row.typ == "create_checkout" and payment.status == "oczekuje":
            reservation_payments.apply_payment_status(
                payment,
                "wygasla",
                now=now,
                error_code="COMMAND_EXPIRED_BEFORE_CLAIM",
                strict=True,
            )
            payment.link = None
            reconcile_payment_reservation(
                db,
                payment,
                now=now,
                day_guards=day_guards,
            )
        _finish_without_io(
            row,
            state="failed",
            code="COMMAND_EXPIRED_BEFORE_CLAIM",
            now=now,
        )
        if row.typ == "refund" and payment.refund_status == "oczekuje":
            # Zero attempts and no provider object prove that Stripe never saw
            # this refund.  Do not leave the aggregate in a fake pending state:
            # it would hide the safe retry even though no money can be moving.
            another_active_refund = db.query(
                models.RezerwacjaPlatnoscPolecenie.id
            ).filter(
                models.RezerwacjaPlatnoscPolecenie.platnosc_id == payment.id,
                models.RezerwacjaPlatnoscPolecenie.id != row.id,
                models.RezerwacjaPlatnoscPolecenie.typ == "refund",
                models.RezerwacjaPlatnoscPolecenie.stan.in_({
                    "queued", "processing", "retry", "uncertain",
                }),
            ).first()
            if another_active_refund is None:
                payment.refund_status = "nieudana"
                payment.zaktualizowano_at = now
                payment.version = int(payment.version or 0) + 1
        settled += 1
    return settled


def claim_next(*, now: datetime | None = None) -> ClaimedPaymentCommand | None:
    """Claim and commit one due command; no provider is contacted here."""

    effective_now = _now(now)
    db = SessionLocal()
    try:
        _begin_worker_write(db)
        _recover_expired_leases(db, effective_now)
        db.flush()
        _expire_due_commands_before_claim(db, effective_now)
        db.flush()

        query = db.query(models.RezerwacjaPlatnoscPolecenie).filter(
            models.RezerwacjaPlatnoscPolecenie.stan.in_(PENDING_STATES),
            models.RezerwacjaPlatnoscPolecenie.available_at <= effective_now,
            models.RezerwacjaPlatnoscPolecenie.expires_at > effective_now,
        ).order_by(
            models.RezerwacjaPlatnoscPolecenie.available_at,
            models.RezerwacjaPlatnoscPolecenie.id,
        )

        while True:
            row = _locked(query, db, skip_locked=True).first()
            if row is None:
                db.commit()
                return None
            payment_query = db.query(models.Platnosc).filter_by(id=row.platnosc_id)
            payment = _locked(payment_query, db).first()
            if _settle_stale_command(row, payment, now=effective_now):
                db.flush()
                continue
            if row.typ not in SUPPORTED_COMMANDS:
                _finish_without_io(
                    row,
                    state="failed",
                    code="PAYMENT_COMMAND_UNSUPPORTED",
                    now=effective_now,
                )
                db.flush()
                continue
            if row.liczba_prob >= row.maks_prob:
                terminal = "uncertain" if row.liczba_prob else "failed"
                _finish_without_io(
                    row,
                    state=terminal,
                    code="ATTEMPTS_EXHAUSTED",
                    now=effective_now,
                )
                db.flush()
                continue
            break

        token = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
        row.liczba_prob += 1
        row.stan = "processing"
        row.lease_token = token
        row.lease_expires_at = effective_now + timedelta(seconds=LEASE_SECONDS)
        row.updated_at = effective_now

        refund_id = (
            _refund_reference(db, payment.id)
            if row.typ == "reconcile" and payment.refund_status == "oczekuje"
            else None
        )
        checkout_session_id = payment.provider_checkout_session_id
        payment_intent_id = payment.provider_payment_intent_id
        reconcile_source = None
        if row.typ == "reconcile":
            reconcile_sources = db.query(
                models.RezerwacjaPlatnoscPolecenie
            ).filter(
                models.RezerwacjaPlatnoscPolecenie.platnosc_id == payment.id,
                models.RezerwacjaPlatnoscPolecenie.id != row.id,
                models.RezerwacjaPlatnoscPolecenie.typ.in_({
                    "create_checkout", "capture", "cancel_authorization", "refund",
                }),
                models.RezerwacjaPlatnoscPolecenie.stan == "uncertain",
            ).order_by(models.RezerwacjaPlatnoscPolecenie.id).all()
            # Resolve dependencies before their reverse operations.  The ID is
            # the durable causal order within each dependency level, making the
            # choice stable across workers and database engines.
            dependency_order = {
                "create_checkout": 0,
                "capture": 1,
                "cancel_authorization": 2,
                "refund": 2,
            }
            reconcile_source = min(
                reconcile_sources,
                key=lambda candidate: (
                    dependency_order.get(candidate.typ, 99), candidate.id,
                ),
                default=None,
            )
            provider_ref = (
                reconcile_source.provider_object_id
                if reconcile_source is not None
                else None
            )
            if provider_ref and str(provider_ref).startswith("cs_"):
                checkout_session_id = checkout_session_id or provider_ref
            elif provider_ref and str(provider_ref).startswith("pi_"):
                payment_intent_id = payment_intent_id or provider_ref
            elif provider_ref and str(provider_ref).startswith("re_"):
                refund_id = refund_id or provider_ref
        claimed = ClaimedPaymentCommand(
            id=row.id,
            payment_id=payment.id,
            attempt_number=row.liczba_prob,
            lease_token=token,
            command_type=row.typ,
            command_ref=row.provider_idempotency_key,
            command_amount_minor=(
                int(row.kwota_minor) if row.kwota_minor is not None else None
            ),
            payment_ref=payment.external_id or f"payment_{payment.id}",
            reservation_ref=payment.reservation_ref,
            reservation_revision=max(0, int(payment.version or 0)),
            policy_version=_policy_version(payment.policy_snapshot),
            payment_amount_minor=int(payment.kwota_minor or 0),
            captured_minor=int(payment.przechwycono_minor or 0),
            refunded_minor=int(payment.zwrocono_minor or 0),
            capture_mode=payment.tryb_przechwycenia,
            payment_expires_at=payment.expires_at,
            checkout_session_id=checkout_session_id,
            payment_intent_id=payment_intent_id,
            refund_id=refund_id,
            reconcile_source_id=(
                reconcile_source.id if reconcile_source is not None else None
            ),
            reconcile_source_type=(
                reconcile_source.typ if reconcile_source is not None else None
            ),
            reconcile_source_ref=(
                reconcile_source.provider_idempotency_key
                if reconcile_source is not None else None
            ),
            reconcile_source_amount_minor=(
                int(reconcile_source.kwota_minor)
                if reconcile_source is not None
                and reconcile_source.kwota_minor is not None
                else None
            ),
            reconcile_source_provider_object_id=(
                reconcile_source.provider_object_id
                if reconcile_source is not None
                else None
            ),
        )
        db.commit()
        return claimed
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _payment_intent_result(payment_intent: Any) -> ProviderCommandResult:
    payment_intent_id = _provider_id(payment_intent, "pi_", required=True)
    status = _provider_status(
        payment_intent,
        {
            "requires_payment_method",
            "requires_confirmation",
            "requires_action",
            "processing",
            "requires_capture",
            "canceled",
            "succeeded",
        },
        "PaymentIntent",
    )
    latest_charge = _value(payment_intent, "latest_charge")
    charge_id = _provider_id(latest_charge, "ch_")
    metadata = _value(payment_intent, "metadata")
    payment_ref = (
        _value(metadata, "lokalo_payment_ref")
        if isinstance(metadata, Mapping) or metadata is not None
        else None
    )
    currency = _value(payment_intent, "currency")
    amount_total = _value(payment_intent, "amount")
    authorization_expires_at = _from_epoch(
        _nested(latest_charge, "payment_method_details", "card", "capture_before")
    )
    target = None
    captured_minor = None
    refund_status = None
    if status == "requires_capture":
        target = "autoryzowana"
    elif status == "succeeded":
        target = "oplacona"
        amount_received = _value(payment_intent, "amount_received")
        amount = amount_received if amount_received is not None else _value(payment_intent, "amount")
        if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
            raise ProviderCommandContractError("Captured amount is missing.")
        captured_minor = amount
        amount_refunded = _value(latest_charge, "amount_refunded")
        if (
            _value(latest_charge, "refunded") is True
            and isinstance(amount_refunded, int)
            and not isinstance(amount_refunded, bool)
            and amount_refunded >= captured_minor
        ):
            target = "zwrocona"
            refund_status = "zwrocona"
    elif status == "canceled":
        target = "anulowana"
    return ProviderCommandResult(
        outcome="succeeded",
        code=f"PAYMENT_INTENT_{status.upper()}",
        provider_object_id=payment_intent_id,
        payment_intent_id=payment_intent_id,
        charge_id=charge_id,
        payment_target=target,
        captured_minor=captured_minor,
        authorization_expires_at=authorization_expires_at,
        refund_status=refund_status,
        provider_object_type="payment_intent",
        provider_payment_ref=payment_ref if isinstance(payment_ref, str) else None,
        provider_currency=currency if isinstance(currency, str) else None,
        provider_amount_minor=(
            amount_total
            if isinstance(amount_total, int) and not isinstance(amount_total, bool)
            else None
        ),
    )


def _checkout_result(
    session: Any,
    *,
    payment_amount_minor: int,
    explicit_cancel: bool = False,
) -> ProviderCommandResult:
    session_id = _provider_id(session, "cs_", required=True)
    status = _provider_status(session, {"open", "complete", "expired"}, "Checkout Session")
    payment_status = _value(session, "payment_status")
    if payment_status not in {None, "paid", "unpaid", "no_payment_required"}:
        raise ProviderCommandContractError("Unexpected Checkout payment status.")
    url = _value(session, "url")
    if url is not None and not isinstance(url, str):
        raise ProviderCommandContractError("Unexpected Checkout URL.")

    payment_intent = _value(session, "payment_intent")
    payment_intent_id = _provider_id(payment_intent, "pi_")
    projection = None
    if payment_intent is not None and not isinstance(payment_intent, str):
        projection = _payment_intent_result(payment_intent)

    target = projection.payment_target if projection is not None else None
    captured_minor = projection.captured_minor if projection is not None else None
    authorization_expires_at = (
        projection.authorization_expires_at if projection is not None else None
    )
    charge_id = projection.charge_id if projection is not None else None
    financially_terminal = target in {"autoryzowana", "oplacona", "zwrocona"}
    if explicit_cancel and status == "expired" and not financially_terminal:
        target = "anulowana"
    elif status == "expired" and not financially_terminal:
        target = "wygasla"
    elif target is None and payment_status == "paid":
        target = "oplacona"
        session_amount = _value(session, "amount_total")
        captured_minor = (
            session_amount
            if isinstance(session_amount, int) and not isinstance(session_amount, bool)
            else payment_amount_minor
        )

    metadata = _value(session, "metadata")
    payment_ref = (
        _value(metadata, "lokalo_payment_ref")
        if isinstance(metadata, Mapping) or metadata is not None
        else None
    )
    currency = _value(session, "currency")
    amount_total = _value(session, "amount_total")
    client_reference = _value(session, "client_reference_id")
    return ProviderCommandResult(
        outcome="succeeded",
        code=f"CHECKOUT_{status.upper()}",
        provider_object_id=session_id,
        checkout_session_id=session_id,
        payment_intent_id=payment_intent_id,
        charge_id=charge_id,
        checkout_url=url,
        checkout_expires_at=_from_epoch(_value(session, "expires_at")),
        payment_target=target,
        captured_minor=captured_minor,
        authorization_expires_at=authorization_expires_at,
        provider_object_type="checkout.session",
        provider_payment_ref=payment_ref if isinstance(payment_ref, str) else None,
        provider_client_reference=(
            client_reference if isinstance(client_reference, str) else None
        ),
        provider_currency=currency if isinstance(currency, str) else None,
        provider_amount_minor=(
            amount_total
            if isinstance(amount_total, int) and not isinstance(amount_total, bool)
            else None
        ),
    )


def _refund_result(refund: Any) -> ProviderCommandResult:
    refund_id = _provider_id(refund, "re_", required=True)
    status = _provider_status(
        refund,
        {"pending", "requires_action", "succeeded", "failed", "canceled"},
        "Refund",
    )
    payment_intent_id = _provider_id(_value(refund, "payment_intent"), "pi_")
    metadata = _value(refund, "metadata")
    payment_ref = (
        _value(metadata, "lokalo_payment_ref")
        if isinstance(metadata, Mapping) or metadata is not None
        else None
    )
    currency = _value(refund, "currency")
    amount = _value(refund, "amount")
    canonical_amount = (
        amount
        if isinstance(amount, int) and not isinstance(amount, bool) and amount > 0
        else None
    )
    if status == "succeeded":
        return ProviderCommandResult(
            outcome="succeeded",
            code="REFUND_SUCCEEDED",
            provider_object_id=refund_id,
            payment_target="zwrocona",
            captured_minor=canonical_amount,
            refund_status="zwrocona",
            payment_intent_id=payment_intent_id,
            provider_object_type="refund",
            provider_payment_ref=payment_ref if isinstance(payment_ref, str) else None,
            provider_currency=currency if isinstance(currency, str) else None,
            provider_amount_minor=canonical_amount,
        )
    if status in {"failed", "canceled"}:
        return ProviderCommandResult(
            outcome="failed",
            code=f"REFUND_{status.upper()}",
            provider_object_id=refund_id,
            refund_status="nieudana",
            payment_intent_id=payment_intent_id,
            provider_object_type="refund",
            provider_payment_ref=payment_ref if isinstance(payment_ref, str) else None,
            provider_currency=currency if isinstance(currency, str) else None,
            provider_amount_minor=canonical_amount,
        )
    return ProviderCommandResult(
        outcome="retry",
        code=f"REFUND_{status.upper()}",
        provider_object_id=refund_id,
        refund_status="oczekuje",
        payment_intent_id=payment_intent_id,
        provider_object_type="refund",
        provider_payment_ref=payment_ref if isinstance(payment_ref, str) else None,
        provider_currency=currency if isinstance(currency, str) else None,
        provider_amount_minor=canonical_amount,
    )


def _command_semantic_result(
    command_type: str,
    result: ProviderCommandResult,
) -> ProviderCommandResult:
    """Require the provider state that proves this exact mutation completed."""

    if result.outcome != "succeeded":
        return result
    target = result.payment_target
    if command_type == "create_checkout":
        if result.provider_object_id is not None:
            return result
        return replace(
            result,
            outcome="uncertain",
            code="CHECKOUT_CANONICAL_REFERENCE_MISSING",
        )
    if command_type == "capture":
        if target in {"oplacona", "zwrocona"}:
            return result
        if target in {"anulowana", "wygasla", "nieudana"}:
            return replace(result, outcome="failed", code="CAPTURE_NOT_COMPLETED")
        return replace(result, outcome="retry", code="CAPTURE_CANONICAL_PENDING")
    if command_type == "cancel_authorization":
        if target in {"anulowana", "wygasla", "zwrocona"}:
            return result
        if target == "oplacona":
            return replace(
                result,
                outcome="failed",
                code="AUTHORIZATION_ALREADY_CAPTURED",
            )
        return replace(
            result,
            outcome="retry",
            code="CANCELLATION_CANONICAL_PENDING",
        )
    if command_type == "refund":
        if target == "zwrocona" and result.refund_status == "zwrocona":
            return result
        return replace(result, outcome="retry", code="REFUND_CANONICAL_PENDING")
    return result


def _retrieve_reconcile_source(
    claim: ClaimedPaymentCommand,
    driver: StripePaymentDriver,
) -> ProviderCommandResult | None:
    """Retrieve a source-owned object, avoiding a cached POST idempotency snapshot."""

    provider_object_id = claim.reconcile_source_provider_object_id
    if not provider_object_id:
        return None
    allowed_prefixes = {
        "create_checkout": ("cs_", "pi_"),
        "capture": ("pi_",),
        "cancel_authorization": ("pi_", "cs_"),
        "refund": ("re_",),
    }.get(claim.reconcile_source_type, ())
    if not provider_object_id.startswith(allowed_prefixes):
        raise ProviderCommandContractError(
            "Reconciliation source object does not match its operation."
        )
    if provider_object_id.startswith("re_"):
        return _refund_result(driver.retrieve_refund(provider_object_id))
    if provider_object_id.startswith("pi_"):
        return _payment_intent_result(
            driver.retrieve_payment_intent(provider_object_id)
        )
    if provider_object_id.startswith("cs_"):
        return _checkout_result(
            driver.retrieve_checkout_session(provider_object_id),
            payment_amount_minor=claim.payment_amount_minor,
            explicit_cancel=(
                claim.reconcile_source_type == "cancel_authorization"
            ),
        )
    raise ProviderCommandContractError("Unexpected reconciliation source object.")


def _failure_result(claim: ClaimedPaymentCommand, code: str) -> ProviderCommandResult:
    return ProviderCommandResult(
        outcome="failed",
        code=code,
        payment_target=("nieudana" if claim.command_type == "create_checkout" else None),
        refund_status=("nieudana" if claim.command_type == "refund" else None),
    )


def _exception_result(claim: ClaimedPaymentCommand, exc: Exception) -> ProviderCommandResult:
    status = getattr(exc, "http_status", None)
    if isinstance(status, int) and 400 <= status < 500 and status not in {
        408,
        409,
        425,
        429,
    }:
        return _failure_result(claim, f"STRIPE_HTTP_{status}")
    if isinstance(status, int):
        code = f"STRIPE_HTTP_{status}_RETRY"
    else:
        name = type(exc).__name__.upper()
        safe_name = "".join(char for char in name if char.isalnum() or char == "_")[:32]
        code = f"STRIPE_IO_{safe_name or 'ERROR'}"
    return ProviderCommandResult(outcome="retry", code=code[:64])


def execute_claim(
    claim: ClaimedPaymentCommand,
    driver: StripePaymentDriver,
    *,
    now: datetime | None = None,
) -> ProviderCommandResult:
    """Perform provider I/O only; this function never opens a database session."""

    try:
        if claim.command_type == "create_checkout":
            if claim.reservation_ref is None:
                return _failure_result(claim, "PAYMENT_RESERVATION_REF_MISSING")
            # Stripe accepts ``expires_at`` only 30 minutes to 24 hours after
            # Session creation.  The policy deadline was persisted before this
            # durable worker ran, so even a normal queue delay can make a
            # 30-minute deadline invalid.  Keep the requested deadline whenever
            # possible, but leave a one-minute transport margin at the lower
            # bound and project Stripe's canonical expiry back afterwards.
            checkout_expires_at = claim.payment_expires_at
            if checkout_expires_at is not None:
                checkout_expires_at = max(
                    checkout_expires_at,
                    _now(now) + timedelta(minutes=31),
                )
            session = driver.create_checkout_session(
                payment_ref=claim.payment_ref,
                reservation_ref=claim.reservation_ref,
                reservation_revision=claim.reservation_revision,
                policy_version=claim.policy_version,
                amount_minor=claim.payment_amount_minor,
                kind=(
                    "preauthorization"
                    if claim.capture_mode == "manual"
                    else "deposit"
                ),
                attempt_ref=claim.command_ref,
                expires_at=_to_epoch(checkout_expires_at),
            )
            return _checkout_result(
                session, payment_amount_minor=claim.payment_amount_minor
            )

        if claim.command_type == "capture":
            if claim.payment_intent_id is None:
                return _failure_result(claim, "PAYMENT_INTENT_REFERENCE_MISSING")
            intent = driver.capture_payment_intent(
                claim.payment_intent_id,
                operation_ref=claim.command_ref,
                amount_minor=claim.command_amount_minor,
            )
            return _command_semantic_result(
                "capture", _payment_intent_result(intent)
            )

        if claim.command_type == "cancel_authorization":
            if claim.payment_intent_id is not None:
                intent = driver.cancel_payment_intent(
                    claim.payment_intent_id,
                    operation_ref=claim.command_ref,
                    reason="abandoned",
                )
                return _command_semantic_result(
                    "cancel_authorization", _payment_intent_result(intent)
                )
            if claim.checkout_session_id is not None:
                session = driver.expire_checkout_session(
                    claim.checkout_session_id,
                    operation_ref=claim.command_ref,
                )
                return _command_semantic_result(
                    "cancel_authorization",
                    _checkout_result(
                        session,
                        payment_amount_minor=claim.payment_amount_minor,
                        explicit_cancel=True,
                    ),
                )
            # Tworzenie Checkout i anulowanie mogą ścigać się w osobnych workerach.
            # Kolejna próba odczyta świeżo zapisaną referencję providera.
            return ProviderCommandResult(
                outcome="retry", code="PROVIDER_REFERENCE_NOT_READY"
            )

        if claim.command_type == "refund":
            if claim.payment_intent_id is None:
                return _failure_result(claim, "PAYMENT_INTENT_REFERENCE_MISSING")
            remaining = claim.captured_minor - claim.refunded_minor
            if claim.command_amount_minor not in {None, remaining}:
                return _failure_result(claim, "PARTIAL_REFUND_UNSUPPORTED")
            refund = driver.create_full_refund(
                claim.payment_intent_id,
                payment_ref=claim.payment_ref,
                operation_ref=claim.command_ref,
            )
            return _command_semantic_result("refund", _refund_result(refund))

        if claim.command_type == "reconcile":
            if (
                claim.reconcile_source_id is not None
                and claim.reconcile_source_type is not None
                and claim.reconcile_source_ref is not None
            ):
                # Re-run the exact ambiguous operation first.  Its immutable
                # provider idempotency key turns this into a canonical lookup at
                # Stripe and, unlike a generic object retrieve, proves whether a
                # dependent cancel/capture/refund actually took effect.
                canonical = _retrieve_reconcile_source(claim, driver)
                if canonical is None:
                    canonical = execute_claim(
                        replace(
                            claim,
                            command_type=claim.reconcile_source_type,
                            command_ref=claim.reconcile_source_ref,
                            command_amount_minor=claim.reconcile_source_amount_minor,
                            reconcile_source_id=None,
                            reconcile_source_type=None,
                            reconcile_source_ref=None,
                            reconcile_source_amount_minor=None,
                            reconcile_source_provider_object_id=None,
                        ),
                        driver,
                        now=now,
                    )
                return _command_semantic_result(
                    claim.reconcile_source_type, canonical
                )
            if claim.refund_id is not None:
                return _refund_result(driver.retrieve_refund(claim.refund_id))
            if claim.payment_intent_id is not None:
                return _payment_intent_result(
                    driver.retrieve_payment_intent(claim.payment_intent_id)
                )
            if claim.checkout_session_id is not None:
                return _checkout_result(
                    driver.retrieve_checkout_session(claim.checkout_session_id),
                    payment_amount_minor=claim.payment_amount_minor,
                )
            return _failure_result(claim, "RECONCILE_REFERENCE_MISSING")

        return _failure_result(claim, "PAYMENT_COMMAND_UNSUPPORTED")
    except ProviderCommandContractError:
        return ProviderCommandResult(
            outcome="uncertain", code="PROVIDER_RESPONSE_CONTRACT_MISMATCH"
        )
    except StripeSDKUnavailable:
        return ProviderCommandResult(outcome="retry", code="STRIPE_SDK_UNAVAILABLE")
    except ValueError:
        return _failure_result(claim, "LOCAL_PROVIDER_REQUEST_INVALID")
    except StripePaymentsError:
        return ProviderCommandResult(outcome="retry", code="STRIPE_DRIVER_ERROR")
    except Exception as exc:  # provider exceptions are classified without logging secrets
        logger.warning(
            "Stripe R5c command failed with %s; provider message omitted.",
            type(exc).__name__,
        )
        return _exception_result(claim, exc)


def _immutable_conflict(payment, result: ProviderCommandResult) -> bool:
    for attribute, new_value in (
        ("provider_checkout_session_id", result.checkout_session_id),
        ("provider_payment_intent_id", result.payment_intent_id),
        ("provider_charge_id", result.charge_id),
    ):
        current = getattr(payment, attribute)
        if new_value is not None and current is not None and current != new_value:
            return True
    return False


def _validate_provider_contract(db, payment, result: ProviderCommandResult) -> None:
    """Bind a canonical Stripe object to exactly one local money aggregate.

    A valid webhook signature proves the Stripe account, not that the object
    belongs to this reservation.  Metadata/reference, currency and original
    amount therefore remain mandatory before any financial projection.
    """

    object_type = result.provider_object_type
    if object_type is None:
        return
    if payment.provider != "stripe":
        raise ProviderCommandContractError("Provider object targets a non-Stripe payment.")
    expected_ref = payment.external_id
    if not expected_ref or result.provider_currency != str(payment.waluta or "").lower():
        raise ProviderCommandContractError("Provider currency/reference contract is incomplete.")
    amount = result.provider_amount_minor
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        raise ProviderCommandContractError("Provider amount contract is incomplete.")

    if object_type in {"checkout.session", "payment_intent"}:
        if result.provider_payment_ref != expected_ref:
            raise ProviderCommandContractError("Provider payment reference does not match.")
        if amount != int(payment.kwota_minor or 0):
            raise ProviderCommandContractError("Provider payment amount does not match.")
        if (
            object_type == "checkout.session"
            and result.provider_client_reference != expected_ref
        ):
            raise ProviderCommandContractError("Checkout client reference does not match.")
        captured = result.captured_minor
        if (
            result.payment_target == "oplacona"
            and captured is not None
            and captured < int(payment.kwota_minor or 0)
        ):
            explicit_partial_capture = db.query(
                models.RezerwacjaPlatnoscPolecenie.id
            ).filter(
                models.RezerwacjaPlatnoscPolecenie.platnosc_id == payment.id,
                models.RezerwacjaPlatnoscPolecenie.typ == "capture",
                models.RezerwacjaPlatnoscPolecenie.kwota_minor == captured,
                models.RezerwacjaPlatnoscPolecenie.stan.in_({
                    "queued", "processing", "retry", "succeeded", "uncertain",
                }),
            ).first()
            if explicit_partial_capture is None:
                raise ProviderCommandContractError(
                    "Partial capture has no matching local command."
                )
        return

    if object_type == "refund":
        if (
            payment.provider_payment_intent_id is None
            or result.payment_intent_id != payment.provider_payment_intent_id
        ):
            raise ProviderCommandContractError("Refund PaymentIntent does not match.")
        if (
            result.provider_payment_ref is not None
            and result.provider_payment_ref != expected_ref
        ):
            raise ProviderCommandContractError("Refund payment reference does not match.")
        remaining = int(payment.przechwycono_minor or 0) - int(
            payment.zwrocono_minor or 0
        )
        unordered_full_refund = (
            int(payment.przechwycono_minor or 0) == 0
            and amount == int(payment.kwota_minor or 0)
        )
        if amount != remaining and not unordered_full_refund:
            raise ProviderCommandContractError("Refund amount does not match the local balance.")
        return

    raise ProviderCommandContractError("Unsupported canonical provider object.")


def _lock_projection_reservation_day(
    db,
    payment_id: int | None,
    target: str | None,
):
    """Acquire the reservation writer's day guard before projection row locks."""

    if payment_id is None or target not in reservation_payments.PAYMENT_STATUSES:
        return ()
    payment = db.get(models.Platnosc, payment_id)
    if payment is None or payment.termin_id is None:
        return ()
    reservation = db.get(models.Termin, payment.termin_id)
    if reservation is None:
        return ()
    return reservation_service.lock_days_in_current_transaction(
        db, (reservation.data,)
    )


def reconcile_payment_reservation(
    db,
    payment,
    *,
    now: datetime,
    day_guards=(),
) -> bool:
    """Synchronize reservation money and apply the snapshot failure policy.

    The caller owns the transaction.  For ``zwolnij`` it should pass day guards
    acquired before locking the payment rows; the function acquires them itself as
    a defensive fallback for direct callers.
    """

    changed = False
    reservation = None
    if payment.termin_id is not None:
        query = db.query(models.Termin).filter_by(id=payment.termin_id)
        reservation = _locked(query, db).first()

    refund_status_before = payment.refund_status
    reservation_payments.ensure_reservation_cancellation_refund(
        db,
        payment,
        reservation=reservation,
        now=now,
    )
    reservation_payments.ensure_superseded_payment_refund(
        db,
        payment,
        now=now,
    )
    if payment.refund_status != refund_status_before:
        changed = True

    # The cancellation command remains the durable refund intent after a hard
    # delete, even though there is no longer a Termin projection to synchronize.
    if reservation is None:
        return changed
    if payment.status == "oplacona":
        deposit = int(payment.przechwycono_minor or 0) / 100
        if reservation.zadatek != deposit:
            reservation.zadatek = deposit
            changed = True
    elif payment.status == "zwrocona" and reservation.zadatek != 0.0:
        reservation.zadatek = 0.0
        changed = True

    snapshot = payment.policy_snapshot if isinstance(payment.policy_snapshot, Mapping) else {}
    should_release = (
        payment.status in {"nieudana", "wygasla"}
        and snapshot.get("po_niepowodzeniu") == "zwolnij"
        and reservation.status in {"rezerwacja", "potwierdzona"}
    )
    if should_release:
        guards = tuple(day_guards) or reservation_service.lock_days_in_current_transaction(
            db, (reservation.data,)
        )
        before = reservation_audit.reservation_snapshot(reservation)
        reservation.status = "odwolana"
        reservation.odwolano_at = now
        reservation_service.release_termin_allocation(db, reservation.id)
        reservation_service.touch_days(guards)
        reservation_audit.add_reservation_audit(
            db,
            termin=reservation,
            action="cancel",
            actor_kind="system",
            reason="system_automation",
            before=before,
            after=reservation_audit.reservation_snapshot(reservation),
            now=now,
        )
        changed = True
    return changed


def _apply_provider_projection(
    db,
    payment,
    result: ProviderCommandResult,
    *,
    now: datetime,
    day_guards=(),
) -> bool:
    _validate_provider_contract(db, payment, result)
    if _immutable_conflict(payment, result):
        raise ProviderCommandContractError("Provider identity changed.")

    changed = False
    for attribute, new_value in (
        ("provider_checkout_session_id", result.checkout_session_id),
        ("provider_payment_intent_id", result.payment_intent_id),
        ("provider_charge_id", result.charge_id),
    ):
        if new_value is not None and getattr(payment, attribute) is None:
            setattr(payment, attribute, new_value)
            changed = True
    if result.checkout_url is not None and payment.link != result.checkout_url:
        payment.link = result.checkout_url
        changed = True
    if (
        result.checkout_expires_at is not None
        and payment.status == "oczekuje"
        and payment.expires_at != result.checkout_expires_at
    ):
        payment.expires_at = result.checkout_expires_at
        changed = True

    version_before = int(payment.version or 0)
    if result.payment_target is not None:
        if (
            result.payment_target == "zwrocona"
            and payment.status != "zwrocona"
        ):
            if (
                result.captured_minor is None
                or result.captured_minor <= 0
            ):
                raise ProviderCommandContractError(
                    "A terminal refund has no canonical amount."
                )
            if payment.status == "oplacona":
                remaining = int(payment.przechwycono_minor or 0) - int(
                    payment.zwrocono_minor or 0
                )
                if result.captured_minor != remaining:
                    raise ProviderCommandContractError(
                        "Refund amount does not match the remaining captured balance."
                    )
            else:
                if result.captured_minor > int(payment.kwota_minor or 0):
                    raise ProviderCommandContractError(
                        "Refund arrived before a valid captured amount."
                    )
                # Webhook delivery is unordered. A full refund may be observed
                # before the capture event even after local expiry/cancellation.
                reservation_payments.apply_payment_status(
                    payment,
                    "oplacona",
                    now=now,
                    captured_minor=result.captured_minor,
                    error_code=None,
                    strict=False,
                )
        reservation_payments.apply_payment_status(
            payment,
            result.payment_target,
            now=now,
            captured_minor=result.captured_minor,
            authorization_expires_at=result.authorization_expires_at,
            error_code=None,
            strict=False,
        )
    if result.refund_status is not None:
        current = payment.refund_status
        refund_rank = {
            "brak": 0,
            "oczekuje": 1,
            "nieudana": 2,
            "czesciowy": 2,
            "zwrocona": 3,
        }
        terminal_refund_without_terminal_payment = (
            result.refund_status == "zwrocona" and payment.status != "zwrocona"
        )
        if (
            not terminal_refund_without_terminal_payment
            and current != "zwrocona"
            and current != result.refund_status
            and refund_rank.get(result.refund_status, -1)
            >= refund_rank.get(current, -1)
        ):
            payment.refund_status = result.refund_status
            changed = True
    if changed and int(payment.version or 0) == version_before:
        payment.version = version_before + 1
        payment.zaktualizowano_at = now
    reservation_changed = reconcile_payment_reservation(
        db, payment, now=now, day_guards=day_guards
    )
    return changed or reservation_changed or int(payment.version or 0) != version_before


def finalize_claim(
    claim: ClaimedPaymentCommand,
    result: ProviderCommandResult,
    *,
    now: datetime | None = None,
) -> str | None:
    """Commit one result if the lease is still owned; return its final row state."""

    effective_now = _now(now)
    db = SessionLocal()
    try:
        _begin_worker_write(db)
        day_guards = _lock_projection_reservation_day(
            db, claim.payment_id, result.payment_target
        )
        query = db.query(models.RezerwacjaPlatnoscPolecenie).filter_by(id=claim.id)
        row = _locked(query, db).first()
        if (
            row is None
            or row.stan != "processing"
            or row.lease_token != claim.lease_token
            or row.liczba_prob != claim.attempt_number
        ):
            db.rollback()
            return None
        payment_query = db.query(models.Platnosc).filter_by(id=claim.payment_id)
        payment = _locked(payment_query, db).first()
        if payment is None:
            _finish_without_io(
                row,
                state="uncertain",
                code="PAYMENT_OWNER_MISSING_AFTER_IO",
                now=effective_now,
            )
            db.commit()
            return row.stan

        effective_result = result
        reconcile_source = None
        source_contract_valid = True
        if claim.command_type == "reconcile" and claim.reconcile_source_id is not None:
            source_query = db.query(
                models.RezerwacjaPlatnoscPolecenie
            ).filter_by(
                id=claim.reconcile_source_id,
                platnosc_id=claim.payment_id,
            )
            reconcile_source = _locked(source_query, db).first()
            source_contract_valid = bool(
                reconcile_source is not None
                and reconcile_source.id != row.id
                and reconcile_source.typ == claim.reconcile_source_type
                and reconcile_source.provider_idempotency_key
                == claim.reconcile_source_ref
                and (
                    int(reconcile_source.kwota_minor)
                    if reconcile_source.kwota_minor is not None
                    else None
                )
                == claim.reconcile_source_amount_minor
                and (
                    reconcile_source.provider_object_id is None
                    or result.provider_object_id is None
                    or reconcile_source.provider_object_id
                    == result.provider_object_id
                )
            )
        try:
            if not source_contract_valid:
                raise ProviderCommandContractError(
                    "Reconciliation source identity changed."
                )
            _apply_provider_projection(
                db,
                payment,
                result,
                now=effective_now,
                day_guards=day_guards,
            )
        except (ProviderCommandContractError, reservation_payments.PaymentDomainError):
            effective_result = ProviderCommandResult(
                outcome="uncertain", code="PAYMENT_PROJECTION_CONFLICT"
            )

        if effective_result.provider_object_id is not None:
            row.provider_object_id = effective_result.provider_object_id
            if (
                reconcile_source is not None
                and source_contract_valid
                and reconcile_source.provider_object_id is None
            ):
                # Once an ambiguous POST yields an object, future attempts read
                # its live canonical state instead of replaying Stripe's cached
                # idempotency response forever.
                reconcile_source.provider_object_id = (
                    effective_result.provider_object_id
                )

        if effective_result.outcome == "succeeded":
            state = "succeeded"
            row.last_error_code = None
            row.finished_at = effective_now
        elif effective_result.outcome == "failed":
            state = "failed"
            row.last_error_code = effective_result.code or "PROVIDER_COMMAND_FAILED"
            row.finished_at = effective_now
        elif effective_result.outcome == "retry":
            retry_at = effective_now + timedelta(
                seconds=backoff_seconds(row.id, row.liczba_prob)
            )
            if row.liczba_prob < row.maks_prob and retry_at < row.expires_at:
                state = "retry"
                row.available_at = retry_at
                row.last_error_code = effective_result.code or "PROVIDER_RETRY"
                row.finished_at = None
            else:
                state = "uncertain"
                row.last_error_code = "PROVIDER_RECONCILIATION_REQUIRED"
                row.uncertain_at = effective_now
                row.finished_at = effective_now
        else:
            state = "uncertain"
            row.last_error_code = effective_result.code or "PROVIDER_RESULT_UNCERTAIN"
            row.uncertain_at = effective_now
            row.finished_at = effective_now

        source_resolved = False
        if (
            reconcile_source is not None
            and source_contract_valid
            and effective_result.outcome in {"succeeded", "failed"}
        ):
            source_state = effective_result.outcome
            if reconcile_source.stan == "uncertain":
                _finish_without_io(
                    reconcile_source,
                    state=source_state,
                    code=(
                        effective_result.code or "PROVIDER_COMMAND_FAILED"
                        if source_state == "failed"
                        else "RECONCILED_BY_CANONICAL_REPLAY"
                    ),
                    now=effective_now,
                )
                if source_state == "succeeded":
                    reconcile_source.last_error_code = None
                if effective_result.provider_object_id is not None:
                    reconcile_source.provider_object_id = (
                        effective_result.provider_object_id
                    )
                source_resolved = True
            elif reconcile_source.stan in {"succeeded", "failed", "cancelled"}:
                # A concurrent idempotent reconciliation may have completed the
                # same source while this provider call was in flight.
                source_resolved = True

        if state == "succeeded" and source_resolved:
            remaining_source = db.query(
                models.RezerwacjaPlatnoscPolecenie.id
            ).filter(
                models.RezerwacjaPlatnoscPolecenie.platnosc_id == payment.id,
                models.RezerwacjaPlatnoscPolecenie.id != reconcile_source.id,
                models.RezerwacjaPlatnoscPolecenie.typ.in_({
                    "create_checkout", "capture", "cancel_authorization", "refund",
                }),
                models.RezerwacjaPlatnoscPolecenie.stan == "uncertain",
            ).order_by(models.RezerwacjaPlatnoscPolecenie.id).first()
            if remaining_source is not None:
                # Keep one operator request/audit record and advance it through
                # every ambiguous source.  Each next claim gets a fresh retry
                # budget but still replays the source's immutable provider key.
                state = "queued"
                row.available_at = effective_now
                row.liczba_prob = 0
                row.last_error_code = None
                row.finished_at = None

        row.stan = state
        row.lease_token = None
        row.lease_expires_at = None
        row.updated_at = effective_now
        db.commit()
        return state
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _find_event_payment(
    db,
    *,
    payment_id: int | None,
    object_type: str,
    object_id: str,
    payment_ref: str | None = None,
    related_payment_intent_id: str | None = None,
):
    if payment_id is not None:
        payment = db.get(models.Platnosc, payment_id)
        if payment is not None:
            return payment
    if payment_ref:
        payment = db.query(models.Platnosc).filter(
            models.Platnosc.provider == "stripe",
            models.Platnosc.external_id == payment_ref,
        ).first()
        if payment is not None:
            return payment
    if object_type == "checkout.session":
        return db.query(models.Platnosc).filter(
            models.Platnosc.provider == "stripe",
            models.Platnosc.provider_checkout_session_id == object_id,
        ).first()
    if object_type == "payment_intent":
        return db.query(models.Platnosc).filter(
            models.Platnosc.provider == "stripe",
            models.Platnosc.provider_payment_intent_id == object_id,
        ).first()
    if object_type == "refund":
        payment = db.query(models.Platnosc).join(
            models.RezerwacjaPlatnoscPolecenie,
            models.RezerwacjaPlatnoscPolecenie.platnosc_id == models.Platnosc.id,
        ).filter(
            models.Platnosc.provider == "stripe",
            models.RezerwacjaPlatnoscPolecenie.typ == "refund",
            models.RezerwacjaPlatnoscPolecenie.provider_object_id == object_id,
        ).order_by(models.RezerwacjaPlatnoscPolecenie.id.desc()).first()
        if payment is not None:
            return payment
        if related_payment_intent_id:
            return db.query(models.Platnosc).filter(
                models.Platnosc.provider == "stripe",
                models.Platnosc.provider_payment_intent_id
                == related_payment_intent_id,
            ).one_or_none()
    return None


def ingest_payment_webhook(
    raw_body: bytes,
    stripe_signature: str,
    *,
    driver: StripePaymentDriver | None = None,
    received_at: datetime | None = None,
) -> IngestedPaymentWebhook:
    """Verify a raw Stripe event and durably deduplicate its metadata.

    The raw JSON is used for signature verification and SHA-256 fencing only.  It
    is never persisted; processing later retrieves the canonical provider object.
    """

    if not integracje.skonfigurowane("platnosci"):
        raise PaymentIntegrationDisabled(PaymentIntegrationDisabled.code)
    effective_now = _now(received_at)
    active_driver = driver or StripePaymentDriver.from_environment()
    event = active_driver.construct_webhook_event(raw_body, stripe_signature)
    event_id = _value(event, "id")
    event_type = _value(event, "type")
    api_version = _value(event, "api_version")
    livemode = _value(event, "livemode")
    provider_object = _nested(event, "data", "object")
    object_id = _value(provider_object, "id")
    object_type = _value(provider_object, "object")
    metadata = _value(provider_object, "metadata")
    payment_ref = (
        _value(metadata, "lokalo_payment_ref")
        if isinstance(metadata, Mapping) or metadata is not None
        else None
    )
    provider_created_at = _from_epoch(_value(event, "created"))
    related_payment_intent_id = (
        _provider_id(_value(provider_object, "payment_intent"), "pi_")
        if object_type == "refund"
        else None
    )

    db = SessionLocal()
    try:
        payment = _find_event_payment(
            db,
            payment_id=None,
            object_type=object_type,
            object_id=object_id,
            payment_ref=payment_ref if isinstance(payment_ref, str) else None,
            related_payment_intent_id=related_payment_intent_id,
        )
        row, duplicate = reservation_payments.record_signed_event(
            db,
            provider="stripe",
            event_id=event_id,
            event_type=event_type,
            api_version=api_version,
            livemode=livemode,
            object_id=object_id,
            object_type=object_type,
            raw_payload=raw_body,
            received_at=effective_now,
            provider_created_at=provider_created_at,
            payment_id=payment.id if payment is not None else None,
        )
        db.commit()
        return IngestedPaymentWebhook(
            id=row.id, duplicate=duplicate, state=row.stan
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _recover_expired_webhook_leases(db, now: datetime) -> int:
    query = db.query(models.RezerwacjaPlatnoscWebhook).filter(
        models.RezerwacjaPlatnoscWebhook.stan == "processing",
        models.RezerwacjaPlatnoscWebhook.lease_expires_at <= now,
    ).order_by(models.RezerwacjaPlatnoscWebhook.id)
    rows = _locked(query, db, skip_locked=True).all()
    for row in rows:
        row.lease_token = None
        row.lease_expires_at = None
        if row.liczba_prob < row.maks_prob:
            row.stan = "queued"
            row.available_at = now
            row.last_error_code = "WEBHOOK_LEASE_EXPIRED_RETRY"
        else:
            row.stan = "failed"
            row.last_error_code = "WEBHOOK_ATTEMPTS_EXHAUSTED"
            row.processed_at = now
    return len(rows)


def claim_next_webhook(
    *, now: datetime | None = None
) -> ClaimedPaymentWebhook | None:
    effective_now = _now(now)
    db = SessionLocal()
    try:
        _begin_worker_write(db)
        _recover_expired_webhook_leases(db, effective_now)
        db.flush()
        query = db.query(models.RezerwacjaPlatnoscWebhook).filter(
            models.RezerwacjaPlatnoscWebhook.stan == "queued",
            models.RezerwacjaPlatnoscWebhook.available_at <= effective_now,
        ).order_by(
            models.RezerwacjaPlatnoscWebhook.available_at,
            models.RezerwacjaPlatnoscWebhook.id,
        )
        while True:
            row = _locked(query, db, skip_locked=True).first()
            if row is None:
                db.commit()
                return None
            if row.liczba_prob >= row.maks_prob:
                row.stan = "failed"
                row.last_error_code = "WEBHOOK_ATTEMPTS_EXHAUSTED"
                row.processed_at = effective_now
                db.flush()
                continue
            break

        payment = _find_event_payment(
            db,
            payment_id=row.platnosc_id,
            object_type=row.object_type,
            object_id=row.object_id,
        )
        if payment is not None and row.platnosc_id is None:
            row.platnosc_id = payment.id

        token = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
        row.liczba_prob += 1
        row.stan = "processing"
        row.lease_token = token
        row.lease_expires_at = effective_now + timedelta(
            seconds=WEBHOOK_LEASE_SECONDS
        )
        claim = ClaimedPaymentWebhook(
            id=row.id,
            payment_id=payment.id if payment is not None else row.platnosc_id,
            attempt_number=row.liczba_prob,
            lease_token=token,
            event_id=row.event_id,
            event_type=row.event_type,
            object_id=row.object_id,
            object_type=row.object_type,
        )
        db.commit()
        return claim
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _webhook_exception_result(exc: Exception) -> WebhookProcessingResult:
    status = getattr(exc, "http_status", None)
    if isinstance(status, int) and 400 <= status < 500 and status not in {
        408,
        409,
        425,
        429,
    }:
        return WebhookProcessingResult("failed", f"STRIPE_HTTP_{status}")
    if isinstance(status, int):
        return WebhookProcessingResult("retry", f"STRIPE_HTTP_{status}_RETRY")
    return WebhookProcessingResult("retry", "STRIPE_CANONICAL_RETRIEVE_FAILED")


def execute_webhook_claim(
    claim: ClaimedPaymentWebhook,
    driver: StripePaymentDriver,
) -> WebhookProcessingResult:
    """Retrieve canonical Stripe state without holding an inbox/database lock."""

    expected_object = WEBHOOK_EVENT_OBJECTS.get(claim.event_type)
    if expected_object is None:
        return WebhookProcessingResult("ignored", "WEBHOOK_EVENT_NOT_ACTIONABLE")
    if claim.object_type != expected_object:
        return WebhookProcessingResult("failed", "WEBHOOK_OBJECT_TYPE_MISMATCH")
    try:
        if expected_object == "checkout.session":
            projection = _checkout_result(
                driver.retrieve_checkout_session(claim.object_id),
                payment_amount_minor=0,
            )
            if claim.event_type == "checkout.session.async_payment_succeeded":
                if projection.payment_target != "oplacona":
                    return WebhookProcessingResult(
                        "retry", "CHECKOUT_CANONICAL_STATE_NOT_READY"
                    )
            elif claim.event_type == "checkout.session.async_payment_failed":
                if projection.payment_target != "oplacona":
                    projection = replace(
                        projection,
                        payment_target="nieudana",
                        captured_minor=None,
                        code="CHECKOUT_ASYNC_PAYMENT_FAILED",
                    )
            elif claim.event_type == "checkout.session.expired":
                if projection.payment_target not in {"oplacona", "autoryzowana"}:
                    projection = replace(
                        projection,
                        payment_target="wygasla",
                        captured_minor=None,
                        code="CHECKOUT_EXPIRED",
                    )
            return WebhookProcessingResult("processed", projection=projection)

        if expected_object == "payment_intent":
            projection = _payment_intent_result(
                driver.retrieve_payment_intent(claim.object_id)
            )
            if (
                claim.event_type == "payment_intent.succeeded"
                and projection.payment_target != "oplacona"
            ):
                return WebhookProcessingResult(
                    "retry", "PAYMENT_INTENT_CANONICAL_STATE_NOT_READY"
                )
            # payment_intent.payment_failed is an attempt-level signal while a
            # hosted Checkout Session can still accept another method.  A terminal
            # failure is projected only by async_payment_failed/expired Checkout.
            return WebhookProcessingResult("processed", projection=projection)

        projection = _refund_result(driver.retrieve_refund(claim.object_id))
        if projection.outcome == "retry":
            return WebhookProcessingResult(
                "retry", projection.code, projection=projection,
            )
        return WebhookProcessingResult("processed", projection=projection)
    except ProviderCommandContractError:
        return WebhookProcessingResult("failed", "PROVIDER_RESPONSE_CONTRACT_MISMATCH")
    except StripeSDKUnavailable:
        return WebhookProcessingResult("retry", "STRIPE_SDK_UNAVAILABLE")
    except ValueError:
        return WebhookProcessingResult("failed", "LOCAL_PROVIDER_REQUEST_INVALID")
    except StripePaymentsError:
        return WebhookProcessingResult("retry", "STRIPE_DRIVER_ERROR")
    except Exception as exc:
        logger.warning(
            "Stripe R5c canonical retrieve failed with %s; message omitted.",
            type(exc).__name__,
        )
        return _webhook_exception_result(exc)


def finalize_webhook_claim(
    claim: ClaimedPaymentWebhook,
    result: WebhookProcessingResult,
    *,
    now: datetime | None = None,
) -> str | None:
    effective_now = _now(now)
    db = SessionLocal()
    try:
        _begin_worker_write(db)
        resolved_payment_id = claim.payment_id
        if resolved_payment_id is None:
            resolved = _find_event_payment(
                db,
                payment_id=None,
                object_type=claim.object_type,
                object_id=claim.object_id,
                related_payment_intent_id=(
                    result.projection.payment_intent_id
                    if result.projection is not None
                    and claim.object_type == "refund"
                    else None
                ),
            )
            resolved_payment_id = resolved.id if resolved is not None else None
        day_guards = _lock_projection_reservation_day(
            db,
            resolved_payment_id,
            result.projection.payment_target if result.projection is not None else None,
        )
        query = db.query(models.RezerwacjaPlatnoscWebhook).filter_by(id=claim.id)
        row = _locked(query, db).first()
        if (
            row is None
            or row.stan != "processing"
            or row.lease_token != claim.lease_token
            or row.liczba_prob != claim.attempt_number
        ):
            db.rollback()
            return None

        outcome = result.outcome
        code = result.code
        if outcome in {"processed", "retry"} and result.projection is not None:
            payment = _find_event_payment(
                db,
                payment_id=claim.payment_id,
                object_type=claim.object_type,
                object_id=claim.object_id,
                related_payment_intent_id=(
                    result.projection.payment_intent_id
                    if claim.object_type == "refund"
                    else None
                ),
            )
            if payment is None:
                if row.liczba_prob < min(row.maks_prob, 3):
                    outcome = "retry"
                    code = "PAYMENT_OWNER_NOT_READY"
                else:
                    outcome = "ignored"
                    code = "PAYMENT_OWNER_NOT_FOUND"
            else:
                row.platnosc_id = payment.id
                try:
                    _apply_provider_projection(
                        db,
                        payment,
                        result.projection,
                        now=effective_now,
                        day_guards=day_guards,
                    )
                except (
                    ProviderCommandContractError,
                    reservation_payments.PaymentDomainError,
                ):
                    outcome = "failed"
                    code = "PAYMENT_PROJECTION_CONFLICT"

        if outcome == "processed":
            state = "processed"
            row.last_error_code = None
            row.processed_at = effective_now
        elif outcome == "ignored":
            state = "ignored"
            row.last_error_code = code or "WEBHOOK_IGNORED"
            row.processed_at = effective_now
        elif outcome == "retry" and row.liczba_prob < row.maks_prob:
            state = "queued"
            row.available_at = effective_now + timedelta(
                seconds=backoff_seconds(row.id, row.liczba_prob)
            )
            row.last_error_code = code or "WEBHOOK_RETRY"
            row.processed_at = None
        else:
            state = "failed"
            row.last_error_code = code or "WEBHOOK_PROCESSING_FAILED"
            row.processed_at = effective_now

        row.stan = state
        row.lease_token = None
        row.lease_expires_at = None
        db.commit()
        return state
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def run_payment_webhooks_once(
    *,
    limit: int = 50,
    driver: StripePaymentDriver | None = None,
    now: datetime | None = None,
) -> dict[str, int | bool]:
    result: dict[str, int | bool] = {
        "enabled": False,
        "processed": 0,
        "ignored": 0,
        "retry": 0,
        "failed": 0,
    }
    if not integracje.skonfigurowane("platnosci"):
        return result
    result["enabled"] = True
    active_driver = driver or StripePaymentDriver.from_environment()
    for _ in range(max(0, limit)):
        claim = claim_next_webhook(now=now)
        if claim is None:
            break
        provider_result = execute_webhook_claim(claim, active_driver)
        state = finalize_webhook_claim(claim, provider_result, now=now)
        if state is None:
            continue
        if state == "queued":
            state = "retry"
        if state in {"processed", "ignored", "retry", "failed"}:
            result[state] = int(result[state]) + 1
    return result


def run_payment_commands_once(
    *,
    limit: int = 20,
    driver: StripePaymentDriver | None = None,
    now: datetime | None = None,
) -> dict[str, int | bool]:
    """Run a bounded batch; a disabled integration never claims durable work."""

    result: dict[str, int | bool] = {
        "enabled": False,
        "processed": 0,
        "succeeded": 0,
        "retry": 0,
        "failed": 0,
        "uncertain": 0,
    }
    if not integracje.skonfigurowane("platnosci"):
        return result

    result["enabled"] = True
    active_driver = driver or StripePaymentDriver.from_environment()
    for _ in range(max(0, limit)):
        claim = claim_next(now=now)
        if claim is None:
            break
        provider_result = execute_claim(claim, active_driver, now=now)
        state = finalize_claim(claim, provider_result, now=now)
        if state is None:
            continue
        result["processed"] = int(result["processed"]) + 1
        if state in {"succeeded", "retry", "failed", "uncertain"}:
            result[state] = int(result[state]) + 1
    return result


def run_payment_work_once(
    *,
    command_limit: int = 20,
    webhook_limit: int = 50,
    driver: StripePaymentDriver | None = None,
) -> dict[str, Any]:
    """Run both bounded queues with one lazily created Stripe client."""

    if not integracje.skonfigurowane("platnosci"):
        return {
            "enabled": False,
            "commands": run_payment_commands_once(limit=0),
            "webhooks": run_payment_webhooks_once(limit=0),
        }
    active_driver = driver or StripePaymentDriver.from_environment()
    return {
        "enabled": True,
        "commands": run_payment_commands_once(
            limit=command_limit, driver=active_driver
        ),
        "webhooks": run_payment_webhooks_once(
            limit=webhook_limit, driver=active_driver
        ),
    }


def _ephemeral_sqlite() -> bool:
    bind = SessionLocal.kw.get("bind")
    if bind is None or bind.dialect.name != "sqlite":
        return False
    database = bind.url.database
    value = str(database or "").casefold()
    return not value or ":memory:" in value or "mode=memory" in value


def _worker_loop(
    *,
    interval_seconds: float,
    command_limit: int,
    webhook_limit: int,
) -> None:
    driver = None
    while not _stop_event.is_set():
        try:
            if integracje.skonfigurowane("platnosci"):
                driver = driver or StripePaymentDriver.from_environment()
                run_payment_work_once(
                    command_limit=command_limit,
                    webhook_limit=webhook_limit,
                    driver=driver,
                )
            else:
                driver = None
        except Exception as exc:
            logger.error(
                "R5c payment worker iteration failed with %s; message omitted.",
                type(exc).__name__,
            )
        _stop_event.wait(max(0.25, float(interval_seconds)))


def start_worker(
    *,
    interval_seconds: float = 2.0,
    command_limit: int = 20,
    webhook_limit: int = 50,
) -> bool:
    """Start one daemon loop; never starts for in-memory/ephemeral SQLite."""

    global _thread
    if _ephemeral_sqlite() or not integracje.skonfigurowane("platnosci"):
        return False
    with _state_lock:
        if _thread is not None and _thread.is_alive():
            return False
        _stop_event.clear()
        _thread = threading.Thread(
            target=_worker_loop,
            kwargs={
                "interval_seconds": interval_seconds,
                "command_limit": max(0, int(command_limit)),
                "webhook_limit": max(0, int(webhook_limit)),
            },
            name="reservation-payment-worker",
            daemon=True,
        )
        _thread.start()
        return True


def worker_running() -> bool:
    """Return payment-loop liveness without exposing the thread object."""
    with _state_lock:
        return bool(_thread is not None and _thread.is_alive())


def stop_worker(*, timeout_seconds: float = 5.0) -> bool:
    """Stop the optional daemon loop; bounded runners remain independently usable."""

    global _thread
    with _state_lock:
        thread = _thread
        if thread is None:
            return False
        _stop_event.set()
    thread.join(timeout=max(0.0, float(timeout_seconds)))
    stopped = not thread.is_alive()
    if stopped:
        with _state_lock:
            if _thread is thread:
                _thread = None
    return stopped
