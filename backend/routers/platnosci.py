"""Operator API for reservation payments.

Provider calls never happen in an HTTP request.  R5c mutations append durable
commands consumed by ``reservation_payment_worker``.  The legacy sandbox route is
kept for demos and old internal flows, but it is fail-closed when Stripe is active.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import integracje
import models
import platnosci
import reservation_payments
import schemas
import settings as app_settings
from auth import get_current_user
from database import get_db
from deps import modul_aktywny, utcnow_naive


router = APIRouter()
WARSAW = ZoneInfo("Europe/Warsaw")


class AnulowanieAutoryzacjiIn(BaseModel):
    powod: str = Field(default="operator_cancel", min_length=3, max_length=64)
    notatka: Optional[str] = Field(default=None, max_length=500)

    @field_validator("powod")
    @classmethod
    def _strip_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Powód anulowania nie może być pusty.")
        return value

    @field_validator("notatka")
    @classmethod
    def _strip_note(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip() or None


class UzgodnieniePlatnosciIn(AnulowanieAutoryzacjiIn):
    powod: str = Field(default="operator_reconcile", min_length=3, max_length=64)


def _wymagaj_rezerwacje(db: Session = Depends(get_db)):
    if not modul_aktywny(db, "modul_rezerwacje"):
        raise HTTPException(
            403,
            "Moduł rezerwacji jest niedostępny w tym planie — odblokujesz go w pakiecie Pro.",
        )


def _minor_units(value: float) -> int:
    try:
        amount = Decimal(str(value))
        minor = int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, TypeError, ValueError, ArithmeticError) as exc:
        raise HTTPException(400, "Kwota zadatku jest niepoprawna.") from exc
    if minor <= 0 or minor > reservation_payments.STRIPE_MAX_AMOUNT_MINOR:
        raise HTTPException(400, "Kwota zadatku musi być dodatnia i mieścić się w limicie płatności.")
    return minor


def _idempotency_digest(raw_key: str) -> str:
    key = str(raw_key or "").strip()
    if not key or len(key) > 128 or any(ord(char) < 33 or ord(char) > 126 for char in key):
        raise reservation_payments.PaymentDomainError(
            "INVALID_IDEMPOTENCY_KEY",
            "Klucz idempotencji musi mieć 1–128 drukowalnych znaków ASCII.",
        )
    # Only a one-way digest is persisted in operation keys and audit metadata.
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _lock_payment(db: Session, payment_id: int) -> models.Platnosc:
    payment = db.execute(
        select(models.Platnosc)
        .where(models.Platnosc.id == payment_id)
        .with_for_update()
    ).scalar_one_or_none()
    if payment is None:
        raise HTTPException(404, "Płatność nie istnieje.")
    return payment


def _existing_command(
    db: Session,
    payment: models.Platnosc,
    *,
    operation_key: str,
    command_type: str,
    requested_amount_minor: Optional[int],
    requested_reason_code: Optional[str],
    requested_note: Optional[str],
) -> Optional[models.RezerwacjaPlatnoscPolecenie]:
    command = db.execute(
        select(models.RezerwacjaPlatnoscPolecenie).where(
            models.RezerwacjaPlatnoscPolecenie.platnosc_id == payment.id,
            models.RezerwacjaPlatnoscPolecenie.operation_key == operation_key,
        )
    ).scalar_one_or_none()
    if command is None:
        return None
    amount_matches = command.kwota_minor == requested_amount_minor
    note = requested_note.strip() if requested_note and requested_note.strip() else None
    if (
        command.typ != command_type
        or not amount_matches
        or command.reason_code != requested_reason_code
        or command.note != note
    ):
        raise reservation_payments.PaymentDomainError(
            "PAYMENT_OPERATION_KEY_REUSED",
            "Klucz operacji płatniczej został użyty z inną treścią.",
        )
    return command


def _ensure_no_pending_mutation(
    db: Session,
    payment: models.Platnosc,
    *,
    allow_uncertain: bool = False,
) -> None:
    states = set(reservation_payments.ACTIVE_COMMAND_STATES)
    if allow_uncertain:
        states.discard("uncertain")
    active = db.execute(
        select(models.RezerwacjaPlatnoscPolecenie).where(
            models.RezerwacjaPlatnoscPolecenie.platnosc_id == payment.id,
            models.RezerwacjaPlatnoscPolecenie.typ.in_({
                "capture", "cancel_authorization", "refund",
            }),
            models.RezerwacjaPlatnoscPolecenie.stan.in_(states),
        ).order_by(models.RezerwacjaPlatnoscPolecenie.id)
    ).scalars().first()
    if active is not None:
        raise reservation_payments.PaymentDomainError(
            "PAYMENT_OPERATION_ALREADY_PENDING",
            "Inna operacja dla tej płatności jest już przetwarzana.",
        )


def _audit(
    db: Session,
    user: models.User,
    action: str,
    payment_id: int,
    *,
    now: datetime,
    details: Optional[dict] = None,
) -> None:
    db.add(models.AuditLog(
        ts=now,
        user_id=user.id,
        login=user.login,
        akcja=action,
        zasob=f"payment:{payment_id}",
        szczegoly=(
            json.dumps(details, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            if details else None
        ),
    ))


def _command_out(command: models.RezerwacjaPlatnoscPolecenie) -> dict:
    return schemas.PoleceniePlatnosciOut.model_validate(command).model_dump(mode="json")


def _operator_payment_dict(
    payment: models.Platnosc,
    *,
    latest_command: models.RezerwacjaPlatnoscPolecenie | None = None,
) -> dict:
    """R5c projection with a read-only bridge for rows predating minor units."""
    result = reservation_payments.payment_dict(payment)
    if int(payment.kwota_minor or 0) == 0 and float(payment.kwota or 0) > 0:
        legacy_minor = _minor_units(payment.kwota)
        result.update({
            "kwota_minor": legacy_minor,
            "amount_minor": legacy_minor,
            "kwota": legacy_minor / 100,
        })
    result["latest_command"] = (
        _command_out(latest_command) if latest_command is not None else None
    )
    return result


def _latest_commands_for_payments(
    db: Session,
    payment_ids: list[int],
) -> dict[int, models.RezerwacjaPlatnoscPolecenie]:
    if not payment_ids:
        return {}
    rows = db.execute(
        select(models.RezerwacjaPlatnoscPolecenie)
        .where(models.RezerwacjaPlatnoscPolecenie.platnosc_id.in_(payment_ids))
        .order_by(
            models.RezerwacjaPlatnoscPolecenie.platnosc_id,
            models.RezerwacjaPlatnoscPolecenie.id.desc(),
        )
    ).scalars().all()
    latest: dict[int, models.RezerwacjaPlatnoscPolecenie] = {}
    for row in rows:
        latest.setdefault(row.platnosc_id, row)
    return latest


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"
    vary = [part.strip() for part in response.headers.get("Vary", "").split(",") if part.strip()]
    if not any(part.casefold() == "authorization" for part in vary):
        vary.append("Authorization")
    response.headers["Vary"] = ", ".join(vary)


def _operation_out(
    payment: models.Platnosc,
    command: models.RezerwacjaPlatnoscPolecenie,
) -> dict:
    return {
        "payment": _operator_payment_dict(payment),
        "command": _command_out(command),
    }


def _commit_payment_operation(db: Session, payment: models.Platnosc, command=None) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Operacja płatnicza została już zapisana.") from exc
    db.refresh(payment)
    if command is not None:
        db.refresh(command)


def _sandbox_allowed(payment: models.Platnosc) -> None:
    if payment.provider == "sandbox" and not app_settings.IS_DEV:
        raise integracje.PaymentProviderConfigurationError(
            "Operacje demonstracyjne sandbox są wyłączone w środowisku produkcyjnym."
        )


def _finish_sandbox_command(
    command: models.RezerwacjaPlatnoscPolecenie,
    *,
    now: datetime,
) -> None:
    """Domknij lokalną operację demo bez pozostawiania martwej kolejki workera."""
    command.stan = "succeeded"
    command.provider_object_id = "sandbox"
    command.lease_token = None
    command.lease_expires_at = None
    command.last_error_code = None
    command.updated_at = now
    command.finished_at = now


@router.post(
    "/api/platnosci",
    status_code=201,
    dependencies=[Depends(_wymagaj_rezerwacje)],
)
def platnosc_utworz(
    dane: schemas.PlatnoscIn,
    response: Response,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Legacy demo payment. Real Stripe checkout is created only by the R5c worker."""
    provider = integracje.provider_platnosci_wymaganej()
    if provider == "stripe":
        raise HTTPException(
            409,
            "Przy aktywnym Stripe płatność musi wynikać z polityki rezerwacji; użyj checkoutu R5c.",
        )
    amount_minor = _minor_units(dane.kwota)
    reservation = None
    if dane.termin_id is not None:
        reservation = db.get(models.Termin, dane.termin_id)
        if reservation is None:
            raise HTTPException(404, "Rezerwacja nie istnieje.")
    now = utcnow_naive()
    payment = platnosci.utworz_platnosc(
        db,
        dane.termin_id,
        amount_minor / 100,
        commit=False,
    )
    if payment.provider != "sandbox":  # fail-closed if legacy provider selection changes
        db.rollback()
        raise HTTPException(409, "Legacy może tworzyć wyłącznie płatności sandbox.")
    payment.kwota_minor = amount_minor
    payment.przechwycono_minor = 0
    payment.zwrocono_minor = 0
    payment.waluta = "PLN"
    payment.rodzaj = "zadatek"
    payment.refund_status = "brak"
    payment.tryb_przechwycenia = "automatic"
    payment.expires_at = now + timedelta(minutes=30)
    payment.zaktualizowano_at = now
    payment.version = 0
    payment.policy_snapshot = {
        "version": 1,
        "policy_id": None,
        "source": "legacy_operator",
        "name": "Ręczny zadatek sandbox",
        "rodzaj": "zadatek",
        "kwota_minor": amount_minor,
        "waluta": "PLN",
        "sposob_kwoty": "stala",
        "waznosc_min": 30,
        "po_niepowodzeniu": "ponow",
        "zwrot_przy_anulowaniu": True,
        "reservation_date": reservation.data.isoformat() if reservation else None,
        "service_id": None,
        "people": int(reservation.liczba_osob or 1) if reservation else 1,
        "channel": reservation.kanal if reservation else "wewnetrzna",
    }
    _audit(
        db,
        user,
        "platnosc_sandbox_create",
        payment.id,
        now=now,
        details={"amount_minor": amount_minor, "reservation_id": dane.termin_id},
    )
    _commit_payment_operation(db, payment)
    _no_store(response)
    return _operator_payment_dict(payment)


@router.get("/api/platnosci", dependencies=[Depends(_wymagaj_rezerwacje)])
def platnosc_lista(
    response: Response,
    termin_id: Optional[int] = Query(default=None, gt=0),
    db: Session = Depends(get_db),
):
    query = db.query(models.Platnosc)
    if termin_id is not None:
        query = query.filter(models.Platnosc.termin_id == termin_id)
    payments = query.order_by(models.Platnosc.id.desc()).all()
    latest_commands = _latest_commands_for_payments(
        db, [payment.id for payment in payments],
    )
    _no_store(response)
    return [
        _operator_payment_dict(
            payment, latest_command=latest_commands.get(payment.id),
        )
        for payment in payments
    ]


@router.get("/api/platnosci/{pid}", dependencies=[Depends(_wymagaj_rezerwacje)])
def platnosc_szczegoly(
    pid: int,
    response: Response,
    db: Session = Depends(get_db),
):
    payment = db.get(models.Platnosc, pid)
    if payment is None:
        raise HTTPException(404, "Płatność nie istnieje.")
    latest_command = _latest_commands_for_payments(db, [payment.id]).get(payment.id)
    _no_store(response)
    return _operator_payment_dict(payment, latest_command=latest_command)


@router.post(
    "/api/platnosci/{pid}/retry",
    status_code=201,
    dependencies=[Depends(_wymagaj_rezerwacje)],
)
def ponow_platnosc(
    pid: int,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    source = _lock_payment(db, pid)
    _sandbox_allowed(source)
    digest = _idempotency_digest(idempotency_key)
    if source.termin_id is None:
        raise reservation_payments.PaymentDomainError(
            "PAYMENT_RESERVATION_INACTIVE",
            "Płatność nie jest już powiązana z rezerwacją.",
        )
    reservation = db.get(models.Termin, source.termin_id)
    if reservation is None:
        raise reservation_payments.PaymentDomainError(
            "PAYMENT_RESERVATION_INACTIVE",
            "Rezerwacja nie istnieje.",
        )
    now = utcnow_naive()
    retried, command = reservation_payments.retry_payment_for_reservation(
        db,
        source,
        reservation,
        operation_key=digest,
        now=now,
        business_today=datetime.now(WARSAW).date(),
        actor_kind="user",
        actor_user_id=user.id,
    )
    prior_audits = db.query(models.AuditLog).filter_by(
        akcja="platnosc_checkout_retry",
        zasob=f"payment:{source.id}",
    ).all()
    already_audited = False
    for audit in prior_audits:
        try:
            details = json.loads(audit.szczegoly or "{}")
        except (TypeError, ValueError):
            continue
        if details.get("new_payment_id") == retried.id:
            already_audited = True
            break
    if not already_audited:
        _audit(
            db,
            user,
            "platnosc_checkout_retry",
            source.id,
            now=now,
            details={"command_id": command.id, "new_payment_id": retried.id},
        )
    _commit_payment_operation(db, retried, command)
    _no_store(response)
    return _operation_out(retried, command)


@router.post(
    "/api/platnosci/{pid}/capture",
    status_code=202,
    dependencies=[Depends(_wymagaj_rezerwacje)],
)
def przechwyc_preautoryzacje(
    pid: int,
    dane: schemas.PrzechwyceniePreautoryzacjiIn,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    payment = _lock_payment(db, pid)
    _sandbox_allowed(payment)
    operation_key = f"capture:{_idempotency_digest(idempotency_key)}"
    effective_amount_minor = (
        dane.kwota_minor
        if dane.kwota_minor is not None
        else int(payment.kwota_minor or 0)
    )
    command = _existing_command(
        db,
        payment,
        operation_key=operation_key,
        command_type="capture",
        requested_amount_minor=effective_amount_minor,
        requested_reason_code=dane.powod.strip(),
        requested_note=dane.notatka,
    )
    if command is None:
        _ensure_no_pending_mutation(db, payment)
        now = utcnow_naive()
        command = reservation_payments.request_capture(
            db,
            payment,
            amount_minor=dane.kwota_minor,
            operation_key=operation_key,
            now=now,
            actor_user_id=user.id,
            reason_code=dane.powod.strip(),
            note=dane.notatka,
        )
        if payment.provider == "sandbox":
            captured_minor = command.kwota_minor or int(payment.kwota_minor)
            reservation_payments.apply_payment_status(
                payment,
                "oplacona",
                now=now,
                captured_minor=captured_minor,
                strict=True,
            )
            payment.link = None
            if payment.termin_id is not None:
                reservation = db.get(models.Termin, payment.termin_id)
                if reservation is not None:
                    reservation.zadatek = captured_minor / 100
            _finish_sandbox_command(command, now=now)
        _audit(
            db,
            user,
            "platnosc_capture_request",
            payment.id,
            now=now,
            details={"amount_minor": command.kwota_minor, "command_id": command.id},
        )
    _commit_payment_operation(db, payment, command)
    _no_store(response)
    return _operation_out(payment, command)


@router.post(
    "/api/platnosci/{pid}/anuluj-autoryzacje",
    status_code=202,
    dependencies=[Depends(_wymagaj_rezerwacje)],
)
def anuluj_autoryzacje(
    pid: int,
    dane: AnulowanieAutoryzacjiIn,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    payment = _lock_payment(db, pid)
    _sandbox_allowed(payment)
    operation_key = f"cancel:{_idempotency_digest(idempotency_key)}"
    command = _existing_command(
        db,
        payment,
        operation_key=operation_key,
        command_type="cancel_authorization",
        requested_amount_minor=None,
        requested_reason_code=dane.powod,
        requested_note=dane.notatka,
    )
    if command is None:
        _ensure_no_pending_mutation(db, payment)
        now = utcnow_naive()
        command = reservation_payments.request_authorization_cancel(
            db,
            payment,
            operation_key=operation_key,
            now=now,
            actor_kind="user",
            actor_user_id=user.id,
            reason_code=dane.powod,
            note=dane.notatka,
        )
        if payment.provider == "sandbox":
            reservation_payments.apply_payment_status(
                payment, "anulowana", now=now, strict=True,
            )
            payment.link = None
            _finish_sandbox_command(command, now=now)
        _audit(
            db,
            user,
            "platnosc_auth_cancel_request",
            payment.id,
            now=now,
            details={"command_id": command.id},
        )
    _commit_payment_operation(db, payment, command)
    _no_store(response)
    return _operation_out(payment, command)


@router.post(
    "/api/platnosci/{pid}/zwrot",
    status_code=202,
    dependencies=[Depends(_wymagaj_rezerwacje)],
)
def zwroc_platnosc(
    pid: int,
    dane: schemas.ZwrotPlatnosciIn,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    payment = _lock_payment(db, pid)
    _sandbox_allowed(payment)
    operation_key = f"refund:{_idempotency_digest(idempotency_key)}"
    effective_amount_minor = (
        dane.kwota_minor
        if dane.kwota_minor is not None
        else int(payment.przechwycono_minor or 0) - int(payment.zwrocono_minor or 0)
    )
    command = _existing_command(
        db,
        payment,
        operation_key=operation_key,
        command_type="refund",
        requested_amount_minor=effective_amount_minor,
        requested_reason_code=dane.powod,
        requested_note=dane.notatka,
    )
    if command is None:
        _ensure_no_pending_mutation(db, payment)
        now = utcnow_naive()
        command = reservation_payments.request_refund(
            db,
            payment,
            amount_minor=dane.kwota_minor,
            operation_key=operation_key,
            now=now,
            actor_user_id=user.id,
            reason_code=dane.powod,
            note=dane.notatka,
        )
        if payment.provider == "sandbox":
            reservation_payments.apply_payment_status(
                payment, "zwrocona", now=now, strict=True,
            )
            if payment.termin_id is not None:
                reservation = db.get(models.Termin, payment.termin_id)
                if reservation is not None:
                    reservation.zadatek = 0.0
            _finish_sandbox_command(command, now=now)
        _audit(
            db,
            user,
            "platnosc_refund_request",
            payment.id,
            now=now,
            details={"amount_minor": command.kwota_minor, "command_id": command.id},
        )
    _commit_payment_operation(db, payment, command)
    _no_store(response)
    return _operation_out(payment, command)


@router.post(
    "/api/platnosci/{pid}/reconcile",
    status_code=202,
    dependencies=[Depends(_wymagaj_rezerwacje)],
)
def uzgodnij_platnosc(
    pid: int,
    dane: UzgodnieniePlatnosciIn,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Queue a canonical Stripe read/replay for an ambiguous provider result."""

    payment = _lock_payment(db, pid)
    if payment.provider != "stripe":
        raise reservation_payments.PaymentDomainError(
            "PAYMENT_RECONCILIATION_UNSUPPORTED",
            "Uzgodnienie jest dostępne wyłącznie dla płatności Stripe.",
        )
    operation_key = f"reconcile:{_idempotency_digest(idempotency_key)}"
    reason_code = dane.powod or "operator_reconcile"
    command = _existing_command(
        db,
        payment,
        operation_key=operation_key,
        command_type="reconcile",
        requested_amount_minor=None,
        requested_reason_code=reason_code,
        requested_note=dane.notatka,
    )
    if command is None:
        _ensure_no_pending_mutation(db, payment, allow_uncertain=True)
        uncertain = db.execute(
            select(models.RezerwacjaPlatnoscPolecenie.id).where(
                models.RezerwacjaPlatnoscPolecenie.platnosc_id == payment.id,
                models.RezerwacjaPlatnoscPolecenie.stan == "uncertain",
            ).limit(1)
        ).scalar_one_or_none()
        if uncertain is None:
            raise reservation_payments.PaymentDomainError(
                "PAYMENT_RECONCILIATION_NOT_REQUIRED",
                "Ta płatność nie ma niepewnej operacji do uzgodnienia.",
            )
        now = utcnow_naive()
        command = reservation_payments.queue_command(
            db,
            payment,
            "reconcile",
            operation_key=operation_key,
            now=now,
            actor_kind="user",
            actor_user_id=user.id,
            reason_code=reason_code,
            note=dane.notatka,
        )
        _audit(
            db,
            user,
            "platnosc_reconcile_request",
            payment.id,
            now=now,
            details={"command_id": command.id},
        )
    _commit_payment_operation(db, payment, command)
    _no_store(response)
    return _operation_out(payment, command)


@router.post(
    "/api/platnosci/{pid}/oplacona",
    dependencies=[Depends(_wymagaj_rezerwacje)],
)
def platnosc_oplac(
    pid: int,
    response: Response,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Manual settlement for demo/ledger rows; Stripe only changes by webhook."""
    payment = _lock_payment(db, pid)
    _sandbox_allowed(payment)
    if payment.provider not in {"sandbox", "ledger"}:
        return JSONResponse(
            status_code=409,
            content={
                "detail": "Realnej płatności nie można ręcznie oznaczyć jako opłaconej.",
                "code": "MANUAL_PAYMENT_CONFIRMATION_FORBIDDEN",
            },
            headers={"Cache-Control": "private, no-store"},
        )
    if payment.status == "oplacona":
        db.commit()
        db.refresh(payment)
        _no_store(response)
        return _operator_payment_dict(payment)
    if payment.status != "oczekuje":
        return JSONResponse(
            status_code=409,
            content={
                "detail": "Tylko oczekującą płatność sandbox można ręcznie potwierdzić.",
                "code": "INVALID_PAYMENT_TRANSITION",
            },
            headers={"Cache-Control": "private, no-store"},
        )
    now = utcnow_naive()
    if int(payment.kwota_minor or 0) <= 0:
        payment.kwota_minor = _minor_units(payment.kwota)
    reservation_payments.apply_payment_status(
        payment,
        "oplacona",
        now=now,
        captured_minor=int(payment.kwota_minor),
        strict=True,
    )
    if payment.termin_id is not None and payment.rodzaj != "no_show":
        reservation = db.get(models.Termin, payment.termin_id)
        if reservation is not None:
            reservation.zadatek = int(payment.kwota_minor) / 100
    _audit(
        db,
        user,
        "platnosc_sandbox_paid" if payment.provider == "sandbox" else "platnosc_ledger_paid",
        payment.id,
        now=now,
        details={"amount_minor": int(payment.kwota_minor)},
    )
    _commit_payment_operation(db, payment)
    _no_store(response)
    return _operator_payment_dict(payment)
