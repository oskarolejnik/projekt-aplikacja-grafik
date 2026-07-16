"""R5c domain model for reservation deposits and preauthorisations.

This module deliberately contains no provider client. It only resolves policy, mutates
local aggregates and appends durable commands/events. A worker must commit its claim,
perform Stripe I/O without database locks, then open a short finalisation transaction.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import secrets
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

import models
import reservation_audit


PAYMENT_STATUSES = frozenset({
    "oczekuje", "autoryzowana", "oplacona", "nieudana",
    "wygasla", "anulowana", "zwrocona",
})
COMMAND_TYPES = frozenset({
    "create_checkout", "capture", "cancel_authorization", "refund", "reconcile",
})
ACTIVE_COMMAND_STATES = frozenset({"queued", "processing", "retry", "uncertain"})
PREAUTH_MAX_LEAD_DAYS = 6
STRIPE_MAX_AMOUNT_MINOR = 99_999_999


class PaymentDomainError(ValueError):
    """Stable domain failure that routers can map without parsing Polish copy."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ResolvedPaymentPolicy:
    policy_id: int | None
    source: str
    name: str
    kind: str
    amount_minor: int
    currency: str
    validity_minutes: int
    failure_policy: str
    refund_on_cancel: bool
    amount_mode: str

    @property
    def required(self) -> bool:
        return self.kind != "brak" and self.amount_minor > 0

    def snapshot(
        self,
        *,
        reservation_date: date,
        service_id: int | None,
        people: int,
        channel: str,
    ) -> dict[str, Any]:
        return {
            "version": 1,
            "policy_id": self.policy_id,
            "source": self.source,
            "name": self.name,
            "rodzaj": self.kind,
            "kwota_minor": self.amount_minor,
            "waluta": self.currency,
            "sposob_kwoty": self.amount_mode,
            "waznosc_min": self.validity_minutes,
            "po_niepowodzeniu": self.failure_policy,
            "zwrot_przy_anulowaniu": self.refund_on_cancel,
            "reservation_date": reservation_date.isoformat(),
            "service_id": service_id,
            "people": people,
            "channel": channel,
        }


def _legacy_minor(value: Any) -> int:
    try:
        amount = Decimal(str(value or 0))
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise PaymentDomainError("INVALID_PAYMENT_AMOUNT", "Kwota płatności jest niepoprawna.") from exc
    minor = int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if minor < 0:
        raise PaymentDomainError("INVALID_PAYMENT_AMOUNT", "Kwota płatności nie może być ujemna.")
    return minor


def legacy_fallback_public_dict(config: models.LokalConfig | None) -> dict[str, Any]:
    """Expose only the normalized, non-sensitive legacy deposit fallback.

    The old singleton fields remain an operational compatibility path until every
    instance has typed R5c policies.  Admin UI needs to know that the path exists,
    but it should not infer behavior independently from raw floats/defaults.
    """

    try:
        amount_minor = _legacy_minor(config.zadatek_kwota_os) if config is not None else 0
    except (PaymentDomainError, ArithmeticError, OverflowError, TypeError, ValueError):
        amount_minor = 0
    try:
        min_people = max(1, int(config.zadatek_prog_osob or 0)) if config is not None else 1
    except (TypeError, ValueError, OverflowError):
        min_people = 1
    active = bool(
        config is not None
        and config.zadatek_wymagany
        and 0 < amount_minor <= STRIPE_MAX_AMOUNT_MINOR
    )
    return {
        "aktywna": active,
        "kwota_minor": amount_minor if active else 0,
        "min_osob": min_people,
        "sposob_kwoty": "od_osoby",
        "waluta": "PLN",
    }


def _normalise_channel(channel: str) -> str:
    value = str(channel or "").strip().lower()
    aliases = {"reczna": "wewnetrzna", "walk_in": "wewnetrzna"}
    value = aliases.get(value, value)
    if value not in {"online", "wewnetrzna"}:
        raise PaymentDomainError("INVALID_PAYMENT_CHANNEL", "Nieznany kanał polityki płatności.")
    return value


def _policy_sort_key(policy: models.PolitykaPlatnosciRezerwacji) -> tuple[int, ...]:
    date_specific = int(policy.data is not None)
    service_specific = int(policy.serwis_id is not None)
    max_people = int(policy.max_osob or 0)
    range_width = (max_people - int(policy.min_osob)) if max_people else 1_000_000
    return (
        -(date_specific + service_specific),
        -date_specific,
        int(policy.priorytet or 0),
        range_width,
        -int(policy.min_osob),
        int(policy.id or 0),
    )


def resolve_policy(
    db,
    reservation_date: date,
    service_id: int | None,
    people: int,
    channel: str,
) -> ResolvedPaymentPolicy | None:
    """Resolve exact-date/service/group policy with deterministic precedence.

    Exact date + service wins, then exact date, then service, then global. Lower
    ``priorytet`` wins inside the same scope. A matching ``brak`` is intentional and
    suppresses the legacy singleton fallback.
    """
    if not isinstance(reservation_date, date):
        raise PaymentDomainError("INVALID_PAYMENT_DATE", "Data rezerwacji jest niepoprawna.")
    if isinstance(people, bool) or not isinstance(people, int) or people < 1:
        raise PaymentDomainError("INVALID_PARTY_SIZE", "Liczba gości musi być dodatnia.")
    channel = _normalise_channel(channel)
    policies = db.execute(
        select(models.PolitykaPlatnosciRezerwacji).where(
            models.PolitykaPlatnosciRezerwacji.aktywna.is_(True),
        )
    ).scalars().all()
    matches = [
        policy for policy in policies
        if (policy.data is None or policy.data == reservation_date)
        and (policy.serwis_id is None or policy.serwis_id == service_id)
        and policy.kanal in {"oba", channel}
        and int(policy.min_osob) <= people
        and (int(policy.max_osob or 0) == 0 or people <= int(policy.max_osob))
    ]
    if matches:
        policy = min(matches, key=_policy_sort_key)
        if policy.waluta != "PLN":
            raise PaymentDomainError(
                "UNSUPPORTED_PAYMENT_CURRENCY",
                "Płatności rezerwacji R5c obsługują wyłącznie PLN.",
            )
        unit_amount = int(policy.kwota_minor)
        amount = unit_amount * people if policy.sposob_kwoty == "od_osoby" else unit_amount
        if amount > STRIPE_MAX_AMOUNT_MINOR:
            raise PaymentDomainError(
                "PAYMENT_AMOUNT_TOO_LARGE",
                "Kwota płatności przekracza limit ośmiu cyfr Stripe.",
            )
        return ResolvedPaymentPolicy(
            policy_id=policy.id,
            source="policy",
            name=policy.nazwa,
            kind=policy.rodzaj,
            amount_minor=amount,
            currency=policy.waluta,
            validity_minutes=int(policy.waznosc_min),
            failure_policy=policy.po_niepowodzeniu,
            refund_on_cancel=bool(policy.zwrot_przy_anulowaniu),
            amount_mode=policy.sposob_kwoty,
        )

    # Compatibility bridge for migration 0048. It is used only when no typed R5c
    # policy matched; creating a typed ``brak`` policy explicitly disables payment.
    config = db.get(models.LokalConfig, 1)
    if config is None or not bool(config.zadatek_wymagany):
        return None
    threshold = int(config.zadatek_prog_osob or 0)
    if threshold and people < threshold:
        return None
    unit_minor = _legacy_minor(config.zadatek_kwota_os)
    if unit_minor <= 0:
        return None
    if unit_minor * people > STRIPE_MAX_AMOUNT_MINOR:
        raise PaymentDomainError(
            "PAYMENT_AMOUNT_TOO_LARGE",
            "Kwota płatności przekracza limit ośmiu cyfr Stripe.",
        )
    return ResolvedPaymentPolicy(
        policy_id=None,
        source="legacy_lokal_config",
        name="Legacy: zadatek per osoba",
        kind="zadatek",
        amount_minor=unit_minor * people,
        currency="PLN",
        validity_minutes=30,
        failure_policy="ponow",
        refund_on_cancel=True,
        amount_mode="od_osoby",
    )


def _validate_operation_key(operation_key: str) -> str:
    key = str(operation_key or "").strip()
    if not key or len(key) > 96 or any(ord(char) < 33 or ord(char) > 126 for char in key):
        raise PaymentDomainError(
            "INVALID_PAYMENT_OPERATION_KEY",
            "Klucz operacji płatniczej musi mieć 1–96 drukowalnych znaków ASCII.",
        )
    return key


def queue_command(
    db,
    payment: models.Platnosc,
    command_type: str,
    *,
    operation_key: str,
    now: datetime,
    amount_minor: int | None = None,
    available_at: datetime | None = None,
    expires_at: datetime | None = None,
    actor_kind: str = "system",
    actor_user_id: int | None = None,
    reason_code: str | None = None,
    note: str | None = None,
) -> models.RezerwacjaPlatnoscPolecenie:
    """Append an idempotent provider command without committing or doing I/O."""
    if payment.id is None:
        db.flush()
    if command_type not in COMMAND_TYPES:
        raise PaymentDomainError("INVALID_PAYMENT_COMMAND", "Nieznany typ polecenia płatności.")
    operation_key = _validate_operation_key(operation_key)
    if actor_kind not in {"system", "user", "guest"}:
        raise PaymentDomainError("INVALID_PAYMENT_ACTOR", "Nieznany typ aktora płatności.")
    if amount_minor is not None and (
        isinstance(amount_minor, bool) or not isinstance(amount_minor, int)
        or amount_minor <= 0 or amount_minor > STRIPE_MAX_AMOUNT_MINOR
    ):
        raise PaymentDomainError("INVALID_PAYMENT_AMOUNT", "Kwota polecenia musi być dodatnia.")
    available_at = available_at or now
    expires_at = expires_at or (now + timedelta(hours=23))
    if available_at >= expires_at:
        raise PaymentDomainError("INVALID_PAYMENT_DEADLINE", "Termin polecenia płatności wygasł.")

    existing = db.execute(
        select(models.RezerwacjaPlatnoscPolecenie).where(
            models.RezerwacjaPlatnoscPolecenie.platnosc_id == payment.id,
            models.RezerwacjaPlatnoscPolecenie.operation_key == operation_key,
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.typ != command_type or existing.kwota_minor != amount_minor:
            raise PaymentDomainError(
                "PAYMENT_OPERATION_KEY_REUSED",
                "Klucz operacji płatniczej został użyty z inną treścią.",
            )
        return existing

    provider_key = hashlib.sha256(
        f"lokalo:r5c:{payment.id}:{operation_key}".encode("utf-8")
    ).hexdigest()
    command = models.RezerwacjaPlatnoscPolecenie(
        platnosc_id=payment.id,
        typ=command_type,
        operation_key=operation_key,
        provider_idempotency_key=provider_key,
        kwota_minor=amount_minor,
        stan="queued",
        liczba_prob=0,
        maks_prob=5,
        available_at=available_at,
        expires_at=expires_at,
        actor_kind=actor_kind,
        actor_user_id=actor_user_id,
        reason_code=reason_code,
        note=(note.strip() if note and note.strip() else None),
        created_at=now,
        updated_at=now,
    )
    db.add(command)
    db.flush()
    return command


def create_payment_for_reservation(
    db,
    reservation: models.Termin,
    policy: ResolvedPaymentPolicy | None,
    *,
    provider: str,
    now: datetime,
    business_today: date,
    service_id: int | None = None,
    operation_key: str = "initial-checkout",
    actor_kind: str = "guest",
    actor_user_id: int | None = None,
) -> tuple[models.Platnosc | None, models.RezerwacjaPlatnoscPolecenie | None]:
    """Create aggregate + checkout command in the caller's reservation transaction.

    Preauthorisation is intentionally rejected more than six local calendar days
    before the visit. Creating Checkout earlier would let a guest authorize before
    the standard online-card hold can safely survive until the reservation.
    """
    if policy is None or not policy.required:
        return None, None
    if reservation.id is None:
        db.flush()
    if reservation.rodzaj != "stolik":
        raise PaymentDomainError(
            "PAYMENT_OWNER_INVALID", "R5c obsługuje wyłącznie rezerwacje stolików.",
        )
    if provider not in {"stripe", "sandbox"}:
        raise PaymentDomainError("INVALID_PAYMENT_PROVIDER", "Provider płatności jest niepoprawny.")
    if policy.currency != "PLN":
        raise PaymentDomainError(
            "UNSUPPORTED_PAYMENT_CURRENCY",
            "Płatności rezerwacji R5c obsługują wyłącznie PLN.",
        )
    if provider == "stripe" and policy.amount_minor < 200:
        raise PaymentDomainError(
            "PAYMENT_AMOUNT_TOO_SMALL",
            "Kwota płatności Stripe musi wynosić co najmniej 2,00 PLN.",
        )
    if not isinstance(business_today, date):
        raise PaymentDomainError("INVALID_BUSINESS_DATE", "Lokalna data operacyjna jest wymagana.")
    if reservation.data < business_today:
        raise PaymentDomainError("PAYMENT_RESERVATION_PAST", "Nie można rozpocząć płatności wstecz.")
    if (
        policy.kind == "preautoryzacja"
        and reservation.data > business_today + timedelta(days=PREAUTH_MAX_LEAD_DAYS)
    ):
        raise PaymentDomainError(
            "PREAUTH_TOO_EARLY",
            "Preautoryzację można rozpocząć najwcześniej 6 dni przed wizytą.",
        )

    operation_key = _validate_operation_key(operation_key)
    reservation_ref = reservation_audit.reservation_reference(reservation)
    creation_key = hashlib.sha256(
        f"{reservation_ref}\0{operation_key}\0{policy.policy_id or policy.source}".encode("utf-8")
    ).hexdigest()
    existing = db.execute(
        select(models.Platnosc).where(models.Platnosc.creation_key == creation_key)
    ).scalar_one_or_none()
    if existing is not None:
        command = db.execute(
            select(models.RezerwacjaPlatnoscPolecenie).where(
                models.RezerwacjaPlatnoscPolecenie.platnosc_id == existing.id,
                models.RezerwacjaPlatnoscPolecenie.typ == "create_checkout",
            ).order_by(models.RezerwacjaPlatnoscPolecenie.id)
        ).scalars().first()
        return existing, command

    snapshot = policy.snapshot(
        reservation_date=reservation.data,
        service_id=service_id,
        people=int(reservation.liczba_osob or 1),
        channel=_normalise_channel(reservation.kanal),
    )
    expires_at = now + timedelta(minutes=policy.validity_minutes)
    payment = models.Platnosc(
        termin_id=reservation.id,
        polityka_id=policy.policy_id,
        kwota=policy.amount_minor / 100,
        kwota_minor=policy.amount_minor,
        przechwycono_minor=0,
        zwrocono_minor=0,
        waluta=policy.currency,
        rodzaj=policy.kind,
        status="oczekuje",
        refund_status="brak",
        tryb_przechwycenia=("manual" if policy.kind == "preautoryzacja" else "automatic"),
        provider=provider,
        external_id=secrets.token_urlsafe(24),
        link=None,
        reservation_ref=reservation_ref,
        creation_key=creation_key,
        policy_snapshot=snapshot,
        expires_at=expires_at,
        utworzono_at=now,
        zaktualizowano_at=now,
        version=0,
    )
    db.add(payment)
    db.flush()
    command = queue_command(
        db,
        payment,
        "create_checkout",
        operation_key=f"checkout:{operation_key}",
        now=now,
        expires_at=expires_at,
        actor_kind=actor_kind,
        actor_user_id=actor_user_id,
    )
    return payment, command


def retry_payment_for_reservation(
    db,
    payment: models.Platnosc,
    reservation: models.Termin,
    *,
    operation_key: str,
    now: datetime,
    business_today: date,
    actor_kind: str,
    actor_user_id: int | None = None,
) -> tuple[models.Platnosc, models.RezerwacjaPlatnoscPolecenie]:
    """Create an idempotent new checkout from the immutable policy snapshot.

    A terminal provider attempt is never moved backwards to ``oczekuje``.  Retrying
    creates a separate aggregate, which keeps the financial audit trail monotonic.
    """
    if payment.status not in {"nieudana", "wygasla"}:
        raise PaymentDomainError(
            "PAYMENT_RETRY_NOT_ALLOWED",
            "Tylko nieudaną lub wygasłą płatność można ponowić.",
        )
    if payment.termin_id != reservation.id or reservation.status not in {
        "rezerwacja", "potwierdzona",
    }:
        raise PaymentDomainError(
            "PAYMENT_RESERVATION_INACTIVE",
            "Rezerwacja nie jest już aktywna.",
        )
    snapshot = payment.policy_snapshot if isinstance(payment.policy_snapshot, Mapping) else {}
    if (
        snapshot.get("reservation_date") != reservation.data.isoformat()
        or int(snapshot.get("people") or 0) != int(reservation.liczba_osob or 1)
        or snapshot.get("channel") != _normalise_channel(reservation.kanal)
    ):
        raise PaymentDomainError(
            "PAYMENT_RETRY_NOT_ALLOWED",
            "Ta próba płatności dotyczy poprzednich warunków rezerwacji.",
        )
    if snapshot.get("po_niepowodzeniu") != "ponow":
        raise PaymentDomainError(
            "PAYMENT_RETRY_NOT_ALLOWED",
            "Polityka tej rezerwacji nie pozwala ponowić płatności.",
        )
    try:
        original_policy_ref = str(
            snapshot.get("policy_id") or snapshot.get("source") or "unknown"
        )
        policy = ResolvedPaymentPolicy(
            # Retry is governed by the immutable snapshot, not by a policy row that
            # an administrator may have changed or deleted since the booking.
            policy_id=None,
            source=f"retry_snapshot:{original_policy_ref}",
            name=str(snapshot.get("name") or "Ponowienie płatności"),
            kind=str(snapshot["rodzaj"]),
            amount_minor=int(snapshot["kwota_minor"]),
            currency=str(snapshot["waluta"]),
            validity_minutes=int(snapshot["waznosc_min"]),
            failure_policy=str(snapshot["po_niepowodzeniu"]),
            refund_on_cancel=bool(snapshot.get("zwrot_przy_anulowaniu", True)),
            amount_mode=str(snapshot.get("sposob_kwoty") or "stala"),
        )
        service_id = (
            int(snapshot["service_id"])
            if snapshot.get("service_id") is not None else None
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise PaymentDomainError(
            "PAYMENT_POLICY_SNAPSHOT_INVALID",
            "Nie można bezpiecznie odtworzyć polityki tej płatności.",
        ) from exc
    if (
        policy.kind not in {"zadatek", "preautoryzacja"}
        or policy.amount_minor <= 0
        or policy.amount_minor > STRIPE_MAX_AMOUNT_MINOR
        or policy.currency != "PLN"
        or policy.validity_minutes < 30
        or policy.validity_minutes > 1440
    ):
        raise PaymentDomainError(
            "PAYMENT_POLICY_SNAPSHOT_INVALID",
            "Nie można bezpiecznie odtworzyć polityki tej płatności.",
        )
    retry_key = _validate_operation_key(operation_key)
    retry_operation = "retry:" + hashlib.sha256(
        f"{payment.id}\0{retry_key}".encode("utf-8")
    ).hexdigest()
    mark_payment_superseded(
        db,
        payment,
        now=now,
        actor_kind=actor_kind,
        actor_user_id=actor_user_id,
    )
    retried, command = create_payment_for_reservation(
        db,
        reservation,
        policy,
        provider=payment.provider,
        now=now,
        business_today=business_today,
        service_id=service_id,
        operation_key=retry_operation,
        actor_kind=actor_kind,
        actor_user_id=actor_user_id,
    )
    if retried is None or command is None:  # pragma: no cover - invariant fence
        raise PaymentDomainError(
            "PAYMENT_RETRY_NOT_CREATED", "Nie udało się przygotować ponownej płatności.",
        )
    return retried, command


_ALLOWED_TRANSITIONS = {
    "oczekuje": frozenset({"autoryzowana", "oplacona", "nieudana", "wygasla", "anulowana"}),
    "autoryzowana": frozenset({"oplacona", "nieudana", "wygasla", "anulowana"}),
    "oplacona": frozenset({"zwrocona"}),
    # Failure/cancel/expiry describe the locally observed attempt, but cannot
    # overrule a later canonical provider fact that money was captured. Such a
    # correction is financially monotonic and may immediately trigger refund.
    "nieudana": frozenset({"oplacona"}),
    "wygasla": frozenset({"oplacona"}),
    "anulowana": frozenset({"oplacona"}),
    "zwrocona": frozenset(),
}


def apply_payment_status(
    payment: models.Platnosc,
    target: str,
    *,
    now: datetime,
    captured_minor: int | None = None,
    authorization_expires_at: datetime | None = None,
    error_code: str | None = None,
    strict: bool = False,
) -> bool:
    """Apply a monotonic provider projection; stale unordered events become no-ops."""
    if target not in PAYMENT_STATUSES:
        raise PaymentDomainError("INVALID_PAYMENT_STATUS", "Nieznany stan płatności.")
    current = payment.status
    if current == target:
        return False
    if target not in _ALLOWED_TRANSITIONS.get(current, frozenset()):
        if strict:
            raise PaymentDomainError(
                "INVALID_PAYMENT_TRANSITION", f"Niedozwolone przejście {current} → {target}.",
            )
        return False
    if target == "autoryzowana":
        payment.autoryzowano_at = now
        payment.authorization_expires_at = authorization_expires_at
    elif target == "oplacona":
        amount = payment.kwota_minor if captured_minor is None else captured_minor
        if amount <= 0 or amount > payment.kwota_minor:
            raise PaymentDomainError("INVALID_CAPTURE_AMOUNT", "Kwota przechwycenia jest niepoprawna.")
        payment.przechwycono_minor = amount
        payment.oplacono_at = now
    elif target == "nieudana":
        payment.nieudana_at = now
    elif target == "wygasla":
        payment.wygasla_at = now
    elif target == "anulowana":
        payment.anulowano_at = now
    elif target == "zwrocona":
        if payment.przechwycono_minor <= 0:
            raise PaymentDomainError("INVALID_REFUND_AMOUNT", "Brak przechwyconych środków.")
        payment.zwrocono_minor = payment.przechwycono_minor
        payment.refund_status = "zwrocona"
        payment.zwrocono_at = now
    payment.status = target
    payment.last_error_code = error_code
    payment.zaktualizowano_at = now
    payment.version = int(payment.version or 0) + 1
    return True


def request_capture(
    db,
    payment: models.Platnosc,
    *,
    amount_minor: int | None,
    operation_key: str,
    now: datetime,
    actor_user_id: int | None,
    reason_code: str,
    note: str | None = None,
) -> models.RezerwacjaPlatnoscPolecenie:
    if payment.status != "autoryzowana":
        raise PaymentDomainError("PAYMENT_NOT_AUTHORIZED", "Płatność nie jest autoryzowana.")
    amount = payment.kwota_minor if amount_minor is None else amount_minor
    if amount <= 0 or amount > payment.kwota_minor:
        raise PaymentDomainError("INVALID_CAPTURE_AMOUNT", "Kwota przechwycenia jest niepoprawna.")
    return queue_command(
        db, payment, "capture", operation_key=operation_key, now=now,
        amount_minor=amount, actor_kind="user", actor_user_id=actor_user_id,
        reason_code=reason_code, note=note,
    )


def request_refund(
    db,
    payment: models.Platnosc,
    *,
    amount_minor: int | None,
    operation_key: str,
    now: datetime,
    actor_user_id: int | None,
    reason_code: str,
    note: str | None = None,
    actor_kind: str = "user",
) -> models.RezerwacjaPlatnoscPolecenie:
    if payment.status != "oplacona":
        raise PaymentDomainError("PAYMENT_NOT_CAPTURED", "Płatność nie została przechwycona.")
    remaining = int(payment.przechwycono_minor or 0) - int(payment.zwrocono_minor or 0)
    amount = remaining if amount_minor is None else amount_minor
    if amount <= 0 or amount > remaining:
        raise PaymentDomainError("INVALID_REFUND_AMOUNT", "Kwota zwrotu przekracza saldo płatności.")
    if amount != remaining:
        raise PaymentDomainError(
            "PARTIAL_REFUND_UNSUPPORTED",
            "R5c obsługuje obecnie wyłącznie pełny zwrot pozostałego salda.",
        )
    command = queue_command(
        db, payment, "refund", operation_key=operation_key, now=now,
        amount_minor=amount, actor_kind=actor_kind, actor_user_id=actor_user_id,
        reason_code=reason_code, note=note,
    )
    if payment.refund_status != "oczekuje":
        payment.refund_status = "oczekuje"
        payment.zaktualizowano_at = now
        payment.version = int(payment.version or 0) + 1
    return command


_CANCELLATION_REASON_CODE = "reservation_cancelled"
_CANCELLATION_REFUND_OPERATION_KEY = "reservation-cancel-refund:v1"
_SUPERSEDED_REASON_CODE = "payment_superseded"
_SUPERSEDED_REFUND_OPERATION_KEY = "payment-superseded-refund:v1"


def mark_payment_superseded(
    db,
    payment: models.Platnosc,
    *,
    now: datetime,
    actor_kind: str,
    actor_user_id: int | None = None,
) -> models.RezerwacjaPlatnoscPolecenie | None:
    """Persist that a terminal attempt must never become a second net charge."""

    if payment.provider != "stripe":
        return None
    return queue_command(
        db,
        payment,
        "reconcile",
        operation_key="payment-superseded:v1",
        now=now,
        actor_kind=actor_kind,
        actor_user_id=actor_user_id,
        reason_code=_SUPERSEDED_REASON_CODE,
    )


def ensure_superseded_payment_refund(
    db,
    payment: models.Platnosc,
    *,
    now: datetime,
) -> models.RezerwacjaPlatnoscPolecenie | None:
    """Refund a late capture of an attempt replaced by retry/edit exactly once."""

    if payment.status != "oplacona":
        return None
    marker = db.execute(
        select(models.RezerwacjaPlatnoscPolecenie.id).where(
            models.RezerwacjaPlatnoscPolecenie.platnosc_id == payment.id,
            models.RezerwacjaPlatnoscPolecenie.reason_code
            == _SUPERSEDED_REASON_CODE,
        ).limit(1)
    ).scalar_one_or_none()
    if marker is None:
        return None
    existing = db.execute(
        select(models.RezerwacjaPlatnoscPolecenie).where(
            models.RezerwacjaPlatnoscPolecenie.platnosc_id == payment.id,
            models.RezerwacjaPlatnoscPolecenie.typ == "refund",
            models.RezerwacjaPlatnoscPolecenie.reason_code
            == _SUPERSEDED_REASON_CODE,
        ).order_by(models.RezerwacjaPlatnoscPolecenie.id)
    ).scalars().first()
    if existing is not None:
        return existing
    return request_refund(
        db,
        payment,
        amount_minor=None,
        operation_key=_SUPERSEDED_REFUND_OPERATION_KEY,
        now=now,
        actor_user_id=None,
        actor_kind="system",
        reason_code=_SUPERSEDED_REASON_CODE,
    )


def ensure_reservation_cancellation_refund(
    db,
    payment: models.Platnosc,
    *,
    reservation: models.Termin | None,
    now: datetime,
) -> models.RezerwacjaPlatnoscPolecenie | None:
    """Materialise a late full refund after a cancellation/payment race.

    The cancellation command is also the durable settlement intent.  It survives
    ``Termin`` hard deletion because commands belong to the payment aggregate.
    A later canonical Stripe projection can therefore turn an in-flight capture
    into exactly one full-refund command even when ``termin_id`` was set to NULL.
    """

    snapshot = payment.policy_snapshot if isinstance(payment.policy_snapshot, Mapping) else {}
    if payment.status != "oplacona" or not bool(snapshot.get("zwrot_przy_anulowaniu")):
        return None

    cancellation_recorded = bool(
        reservation is not None and reservation.status == "odwolana"
    )
    if not cancellation_recorded:
        cancellation_recorded = db.execute(
            select(models.RezerwacjaPlatnoscPolecenie.id).where(
                models.RezerwacjaPlatnoscPolecenie.platnosc_id == payment.id,
                models.RezerwacjaPlatnoscPolecenie.reason_code
                == _CANCELLATION_REASON_CODE,
                models.RezerwacjaPlatnoscPolecenie.typ.in_({
                    "cancel_authorization", "reconcile", "refund",
                }),
            ).limit(1)
        ).scalar_one_or_none() is not None
    if not cancellation_recorded:
        return None

    # Do not create another automatic refund after a retryable/uncertain provider
    # outcome. The one durable command retains its stable Stripe idempotency key.
    existing = db.execute(
        select(models.RezerwacjaPlatnoscPolecenie).where(
            models.RezerwacjaPlatnoscPolecenie.platnosc_id == payment.id,
            models.RezerwacjaPlatnoscPolecenie.typ == "refund",
            models.RezerwacjaPlatnoscPolecenie.reason_code
            == _CANCELLATION_REASON_CODE,
        ).order_by(models.RezerwacjaPlatnoscPolecenie.id)
    ).scalars().first()
    if existing is not None:
        return existing

    return request_refund(
        db,
        payment,
        amount_minor=None,
        operation_key=_CANCELLATION_REFUND_OPERATION_KEY,
        now=now,
        actor_user_id=None,
        actor_kind="system",
        reason_code=_CANCELLATION_REASON_CODE,
    )


def request_reservation_cancellation_settlement(
    db,
    reservation: models.Termin,
    *,
    now: datetime,
    actor_kind: str,
    actor_user_id: int | None = None,
    operation_key: str | None = None,
) -> models.RezerwacjaPlatnoscPolecenie | None:
    """Queue settlement for every provider attempt in the cancel transaction.

    Older failed/expired attempts still receive a durable reconciliation marker:
    an asynchronous method can succeed late, after the newest attempt and even
    after the reservation row itself has been deleted.
    """
    payment_query = select(models.Platnosc).where(
        models.Platnosc.termin_id == reservation.id,
    ).order_by(models.Platnosc.id)
    # Reservation writers already own the canonical day guard. Locking the
    # aggregate afterwards serializes them with the worker's projection phase.
    if db.get_bind().dialect.name == "postgresql":
        payment_query = payment_query.with_for_update()
    payments = db.execute(payment_query).scalars().all()
    if not payments:
        return None
    settlements: list[models.RezerwacjaPlatnoscPolecenie] = []
    for payment in payments:
        snapshot = (
            payment.policy_snapshot
            if isinstance(payment.policy_snapshot, Mapping)
            else None
        )
        # Legacy manual/no-show ledger rows share the historical table but are
        # not provider-managed R5c attempts and must not receive Stripe commands.
        if snapshot is None:
            continue
        base_key = _validate_operation_key(
            operation_key or f"reservation-cancel:{reservation.id}:{payment.id}"
        )
        if payment.status in {"oczekuje", "autoryzowana"}:
            if payment.provider == "sandbox":
                apply_payment_status(payment, "anulowana", now=now, strict=True)
                payment.link = None
                continue
            settlements.append(request_authorization_cancel(
                db,
                payment,
                operation_key=base_key,
                now=now,
                actor_kind=actor_kind,
                actor_user_id=actor_user_id,
                reason_code=_CANCELLATION_REASON_CODE,
            ))
            continue

        refund_required = bool(snapshot.get("zwrot_przy_anulowaniu"))
        if payment.status == "oplacona" and refund_required:
            if payment.provider == "sandbox":
                apply_payment_status(payment, "zwrocona", now=now, strict=True)
                reservation.zadatek = 0.0
                continue
            settlements.append(request_refund(
                db,
                payment,
                amount_minor=None,
                operation_key=_CANCELLATION_REFUND_OPERATION_KEY,
                now=now,
                actor_user_id=actor_user_id,
                actor_kind=actor_kind,
                reason_code=_CANCELLATION_REASON_CODE,
            ))
            continue

        if (
            payment.provider != "sandbox"
            and refund_required
            and payment.status in {"nieudana", "wygasla", "anulowana"}
        ):
            marker_key = "cancel-settlement:" + hashlib.sha256(
                base_key.encode("ascii")
            ).hexdigest()[:48]
            settlements.append(queue_command(
                db,
                payment,
                "reconcile",
                operation_key=marker_key,
                now=now,
                actor_kind=actor_kind,
                actor_user_id=actor_user_id,
                reason_code=_CANCELLATION_REASON_CODE,
            ))
    return settlements[-1] if settlements else None


def request_authorization_cancel(
    db,
    payment: models.Platnosc,
    *,
    operation_key: str,
    now: datetime,
    actor_kind: str,
    actor_user_id: int | None = None,
    reason_code: str | None = None,
    note: str | None = None,
) -> models.RezerwacjaPlatnoscPolecenie:
    if payment.status not in {"oczekuje", "autoryzowana"}:
        raise PaymentDomainError("PAYMENT_CANNOT_CANCEL", "Tej płatności nie można anulować.")
    return queue_command(
        db, payment, "cancel_authorization", operation_key=operation_key, now=now,
        actor_kind=actor_kind, actor_user_id=actor_user_id,
        reason_code=reason_code, note=note,
    )


def record_signed_event(
    db,
    *,
    provider: str,
    event_id: str,
    event_type: str,
    api_version: str | None,
    livemode: bool,
    object_id: str,
    object_type: str,
    raw_payload: bytes,
    received_at: datetime,
    provider_created_at: datetime | None = None,
    payment_id: int | None = None,
) -> tuple[models.RezerwacjaPlatnoscWebhook, bool]:
    """Persist metadata after signature verification; raw provider JSON is discarded."""
    if not isinstance(raw_payload, bytes) or not raw_payload:
        raise PaymentDomainError("INVALID_WEBHOOK_PAYLOAD", "Webhook ma pusty payload.")
    for value, limit, code in (
        (provider, 32, "INVALID_PAYMENT_PROVIDER"),
        (event_id, 255, "INVALID_WEBHOOK_EVENT_ID"),
        (event_type, 96, "INVALID_WEBHOOK_EVENT_TYPE"),
        (object_id, 255, "INVALID_WEBHOOK_OBJECT_ID"),
        (object_type, 32, "INVALID_WEBHOOK_OBJECT_TYPE"),
    ):
        if not value or len(value) > limit:
            raise PaymentDomainError(code, "Webhook zawiera niepoprawny identyfikator.")
    payload_sha256 = hashlib.sha256(raw_payload).hexdigest()
    existing = db.execute(
        select(models.RezerwacjaPlatnoscWebhook).where(
            models.RezerwacjaPlatnoscWebhook.provider == provider,
            models.RezerwacjaPlatnoscWebhook.event_id == event_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.payload_sha256 != payload_sha256:
            raise PaymentDomainError(
                "WEBHOOK_EVENT_PAYLOAD_MISMATCH",
                "Identyfikator webhooka został powtórzony z innym payloadem.",
            )
        return existing, True
    event = models.RezerwacjaPlatnoscWebhook(
        platnosc_id=payment_id,
        provider=provider,
        event_id=event_id,
        event_type=event_type,
        api_version=api_version,
        livemode=bool(livemode),
        object_id=object_id,
        object_type=object_type,
        payload_sha256=payload_sha256,
        provider_created_at=provider_created_at,
        stan="queued",
        liczba_prob=0,
        maks_prob=8,
        available_at=received_at,
        received_at=received_at,
    )
    try:
        # Two webhook deliveries can race on separate workers. The savepoint keeps
        # the caller's transaction usable after the unique(provider,event_id) fence.
        with db.begin_nested():
            db.add(event)
            db.flush()
    except IntegrityError:
        existing = db.execute(
            select(models.RezerwacjaPlatnoscWebhook).where(
                models.RezerwacjaPlatnoscWebhook.provider == provider,
                models.RezerwacjaPlatnoscWebhook.event_id == event_id,
            )
        ).scalar_one_or_none()
        if existing is None:
            raise
        if existing.payload_sha256 != payload_sha256:
            raise PaymentDomainError(
                "WEBHOOK_EVENT_PAYLOAD_MISMATCH",
                "Identyfikator webhooka został powtórzony z innym payloadem.",
            )
        return existing, True
    return event, False


def payment_public_dict(
    payment: models.Platnosc | None,
    *,
    reservation_active: bool = True,
) -> dict[str, Any]:
    """Guest-safe projection: no provider object IDs, actor data or internal errors."""
    if payment is None:
        return {"status": "niewymagana", "wymagana": False}
    snapshot = payment.policy_snapshot if isinstance(payment.policy_snapshot, Mapping) else {}
    retry_allowed = (
        reservation_active
        and payment.status in {"nieudana", "wygasla"}
        and snapshot.get("po_niepowodzeniu") == "ponow"
    )
    return {
        "id": payment.id,
        "status": payment.status,
        "wymagana": True,
        "rodzaj": payment.rodzaj,
        "kind": payment.rodzaj,
        "kwota_minor": int(payment.kwota_minor or 0),
        "amount_minor": int(payment.kwota_minor or 0),
        "kwota": int(payment.kwota_minor or 0) / 100,
        "waluta": payment.waluta,
        "currency": payment.waluta,
        "link": (
            payment.link
            if reservation_active and payment.status == "oczekuje"
            else None
        ),
        "wygasa_at": payment.expires_at.isoformat() if payment.expires_at else None,
        "zwrocono_minor": int(payment.zwrocono_minor or 0),
        "refund_status": payment.refund_status,
        "tryb_demo": payment.provider == "sandbox",
        "po_niepowodzeniu": snapshot.get("po_niepowodzeniu"),
        "mozna_ponowic": retry_allowed,
        "can_retry": retry_allowed,
    }


def payment_dict(payment: models.Platnosc) -> dict[str, Any]:
    """Operator projection with opaque provider references, never secrets or raw payloads."""
    result = payment_public_dict(payment)
    result.update({
        "id": payment.id,
        "termin_id": payment.termin_id,
        "provider": payment.provider,
        "provider_checkout_session_id": payment.provider_checkout_session_id,
        "provider_payment_intent_id": payment.provider_payment_intent_id,
        "przechwycono_minor": int(payment.przechwycono_minor or 0),
        "refund_status": payment.refund_status,
        "utworzono_at": payment.utworzono_at.isoformat() if payment.utworzono_at else None,
        "zaktualizowano_at": (
            payment.zaktualizowano_at.isoformat() if payment.zaktualizowano_at else None
        ),
    })
    return result
