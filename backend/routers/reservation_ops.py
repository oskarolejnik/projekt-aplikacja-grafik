"""PII-free production-readiness snapshot for the reservation module."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, inspect, text
from sqlalchemy.orm import Session

import integracje
import models
import database
import reservation_communication
import reservation_payment_worker
import reservation_service
from auth import require_admin
from database import get_db
from deps import get_lokal_config, modul_aktywny, utcnow_naive


router = APIRouter()

EXPECTED_MIGRATION = "0068_reservation_closure"
PUBLIC_PRIVACY_NOTICE_VERSION = reservation_service.PUBLIC_PRIVACY_NOTICE_VERSION

_SCHEMA_0068 = {
    "crm_consent_events": {
        "subject_hash",
        "decision",
        "document_version",
        "source",
        "captured_at",
        "event_key_hash",
        "request_fingerprint",
    },
    "crm_guest_merges": {
        "source_hash",
        "target_hash",
        "status",
        "version",
        "create_key_hash",
        "revert_key_hash",
    },
    "reservation_recommendation_reviews": {
        "recommendation_hash",
        "simulation_hash",
        "recommendation",
        "simulation",
        "status",
        "decision_key_hash",
    },
}

_CORE_TABLES = {
    "lokal_config",
    "terminy",
    "godziny_otwarcia",
    "sale_rezerwacyjne",
    "plany_sali",
    "rezerwacje_dni_ledger",
    "rezerwacje_stoliki_claims",
    "rezerwacje_pacing_ledger",
    "rezerwacje_oblozenie_ledger",
    "rezerwacje_publiczne_holdy",
    "rezerwacje_tokeny_zarzadzania",
    "rezerwacje_zgody_publiczne",
    "rezerwacje_wiadomosci_outbox",
    "rezerwacje_platnosci_polecenia",
    "rezerwacje_platnosci_webhooki",
}

_COMMUNICATION_STATES = (
    "queued",
    "processing",
    "retry",
    "sent",
    "failed",
    "uncertain",
    "cancelled",
    "expired",
)
_PAYMENT_COMMAND_STATES = (
    "queued",
    "processing",
    "retry",
    "succeeded",
    "failed",
    "uncertain",
    "cancelled",
)
_PAYMENT_WEBHOOK_STATES = (
    "queued",
    "processing",
    "processed",
    "ignored",
    "failed",
)


def _state_counts(
    db: Session,
    model,
    state_column,
    states: tuple[str, ...],
) -> dict[str, int]:
    rows = db.query(state_column, func.count(model.id)).group_by(state_column).all()
    found = {str(state): int(count) for state, count in rows}
    return {state: found.get(state, 0) for state in states}


def _oldest_due_seconds(
    db: Session,
    state_column,
    states: tuple[str, ...],
    available_column,
    now: datetime,
) -> int | None:
    oldest = (
        db.query(func.min(available_column))
        .filter(state_column.in_(states), available_column <= now)
        .scalar()
    )
    if oldest is None:
        return None
    if oldest.tzinfo is not None:
        oldest = oldest.astimezone(timezone.utc).replace(tzinfo=None)
    return max(0, int((now - oldest).total_seconds()))


def _queue_snapshot(db: Session, now: datetime) -> dict[str, Any]:
    communication = _state_counts(
        db,
        models.RezerwacjaWiadomoscOutbox,
        models.RezerwacjaWiadomoscOutbox.stan,
        _COMMUNICATION_STATES,
    )
    commands = _state_counts(
        db,
        models.RezerwacjaPlatnoscPolecenie,
        models.RezerwacjaPlatnoscPolecenie.stan,
        _PAYMENT_COMMAND_STATES,
    )
    webhooks = _state_counts(
        db,
        models.RezerwacjaPlatnoscWebhook,
        models.RezerwacjaPlatnoscWebhook.stan,
        _PAYMENT_WEBHOOK_STATES,
    )
    communication_by_channel = {
        str(channel): int(count)
        for channel, count in (
            db.query(
                models.RezerwacjaWiadomoscOutbox.kanal,
                func.count(models.RezerwacjaWiadomoscOutbox.id),
            )
            .filter(
                models.RezerwacjaWiadomoscOutbox.stan.in_(
                    ("queued", "processing", "retry", "failed", "uncertain")
                )
            )
            .group_by(models.RezerwacjaWiadomoscOutbox.kanal)
            .all()
        )
    }
    return {
        "communication": {
            "by_state": communication,
            "pending_by_channel": {
                "email": communication_by_channel.get("email", 0),
                "sms": communication_by_channel.get("sms", 0),
            },
            "oldest_due_seconds": _oldest_due_seconds(
                db,
                models.RezerwacjaWiadomoscOutbox.stan,
                ("queued", "retry"),
                models.RezerwacjaWiadomoscOutbox.available_at,
                now,
            ),
        },
        "payment_commands": {
            "by_state": commands,
            "oldest_due_seconds": _oldest_due_seconds(
                db,
                models.RezerwacjaPlatnoscPolecenie.stan,
                ("queued", "retry"),
                models.RezerwacjaPlatnoscPolecenie.available_at,
                now,
            ),
        },
        "payment_webhooks": {
            "by_state": webhooks,
            "oldest_due_seconds": _oldest_due_seconds(
                db,
                models.RezerwacjaPlatnoscWebhook.stan,
                ("queued",),
                models.RezerwacjaPlatnoscWebhook.available_at,
                now,
            ),
        },
    }


def _schema_snapshot(db: Session) -> dict[str, Any]:
    inspector = inspect(db.get_bind())
    tables = set(inspector.get_table_names())
    missing_tables = sorted((_CORE_TABLES | set(_SCHEMA_0068)) - tables)
    missing_columns: dict[str, list[str]] = {}
    for table, required in _SCHEMA_0068.items():
        if table not in tables:
            continue
        actual = {column["name"] for column in inspector.get_columns(table)}
        missing = sorted(required - actual)
        if missing:
            missing_columns[table] = missing

    revision = None
    revision_tracked = "alembic_version" in tables
    if revision_tracked:
        revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    contract_compatible = False
    if not missing_tables and not missing_columns:
        try:
            database._validate_r68_adoption_schema(inspector)
            contract_compatible = True
        except RuntimeError:
            contract_compatible = False

    return {
        "expected_revision": EXPECTED_MIGRATION,
        "tracked_revision": revision,
        "revision_tracked": revision_tracked,
        "missing_tables": missing_tables,
        "missing_columns": missing_columns,
        "contract_compatible": contract_compatible,
        "compatible": (
            not missing_tables
            and not missing_columns
            and contract_compatible
            and (not revision_tracked or revision == EXPECTED_MIGRATION)
        ),
    }


def _check(
    checks: list[dict[str, Any]],
    code: str,
    status: str,
    **evidence: Any,
) -> None:
    checks.append({"code": code, "status": status, **evidence})


def _gate(
    gates: list[dict[str, Any]],
    code: str,
    *,
    required: bool,
    satisfied: bool,
) -> None:
    gates.append(
        {
            "code": code,
            "status": (
                "satisfied" if satisfied else ("open" if required else "deferred")
            ),
            "required": required,
            "satisfied": satisfied,
        }
    )


@router.get(
    "/api/ops/rezerwacje/health",
    dependencies=[Depends(require_admin)],
)
def reservation_health(
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return an aggregate-only readiness report; it never calls external providers."""

    response.headers["Cache-Control"] = "no-store"
    checks: list[dict[str, Any]] = []
    gates: list[dict[str, Any]] = []
    now = utcnow_naive()

    try:
        db.execute(text("SELECT 1")).scalar_one()
    except Exception as exc:
        db.rollback()
        _check(checks, "DB_CONNECTIVITY", "blocked", error=type(exc).__name__)
        return {
            "status": "blocked",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "privacy_notice_version": PUBLIC_PRIVACY_NOTICE_VERSION,
            "checks": checks,
            "gates": gates,
            "queues": None,
            "workers": None,
        }
    _check(checks, "DB_CONNECTIVITY", "ok")

    schema = _schema_snapshot(db)
    _check(
        checks,
        "SCHEMA_0068",
        "ok" if schema["compatible"] else "blocked",
        **schema,
    )
    if not schema["compatible"]:
        return {
            "status": "blocked",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "privacy_notice_version": PUBLIC_PRIVACY_NOTICE_VERSION,
            "checks": checks,
            "gates": gates,
            "queues": None,
            "workers": None,
        }

    cfg = get_lokal_config(db)
    reservations_active = modul_aktywny(db, "modul_rezerwacje")
    widget_online = modul_aktywny(db, "rezerwacje_online")
    widget_v2 = bool(getattr(cfg, "rezerwacje_widget_v2", False))
    widget_privacy_ready = bool(
        (getattr(cfg, "rezerwacje_rodo_kontakt", None) or "").strip()
        and (getattr(cfg, "rezerwacje_rodo_adres", None) or "").strip()
    )
    _check(
        checks,
        "RESERVATIONS_MODULE",
        "ok" if reservations_active else "blocked",
        active=reservations_active,
    )
    widget_ready = widget_v2 and widget_privacy_ready
    if widget_online and not widget_ready:
        _check(
            checks,
            "PUBLIC_WIDGET_V2",
            "blocked",
            online=True,
            v2=widget_v2,
            privacy_ready=widget_privacy_ready,
        )
    else:
        _check(
            checks,
            "PUBLIC_WIDGET_V2",
            "ok",
            online=widget_online,
            v2=widget_v2,
            privacy_ready=widget_privacy_ready,
        )
    _gate(
        gates,
        "PUBLIC_WIDGET",
        required=widget_online,
        satisfied=widget_ready,
    )

    queues = _queue_snapshot(db, now)
    communication_counts = queues["communication"]["by_state"]
    payment_counts = queues["payment_commands"]["by_state"]
    webhook_counts = queues["payment_webhooks"]["by_state"]

    reminder_active = int(getattr(cfg, "rezerwacje_przypomnienie_h", 0) or 0) > 0
    communication_pending = sum(
        communication_counts[state]
        for state in ("queued", "processing", "retry")
    )
    communication_required = (
        widget_online or reminder_active or communication_pending > 0
    )
    email_required = (
        communication_required
        or queues["communication"]["pending_by_channel"]["email"] > 0
    )
    sms_required = (
        communication_required
        or queues["communication"]["pending_by_channel"]["sms"] > 0
    )
    email_configured = integracje.skonfigurowane("email")
    sms_configured = integracje.skonfigurowane("sms")
    _gate(
        gates,
        "EMAIL_PROVIDER",
        required=email_required,
        satisfied=email_configured,
    )
    _gate(
        gates,
        "SMS_PROVIDER",
        required=sms_required,
        satisfied=sms_configured,
    )
    if (email_required and not email_configured) or (
        sms_required and not sms_configured
    ):
        _check(
            checks,
            "COMMUNICATION_PROVIDERS",
            "attention",
            email_configured=email_configured,
            sms_configured=sms_configured,
        )
    else:
        _check(
            checks,
            "COMMUNICATION_PROVIDERS",
            "ok",
            email_configured=email_configured,
            sms_configured=sms_configured,
        )

    communication_worker = reservation_communication.worker_running()
    _check(
        checks,
        "COMMUNICATION_WORKER",
        (
            "attention"
            if communication_required and not communication_worker
            else "ok"
        ),
        running=communication_worker,
        required=communication_required,
    )
    if communication_counts["failed"] or communication_counts["uncertain"]:
        _check(
            checks,
            "COMMUNICATION_QUEUE_TERMINAL",
            "attention",
            failed=communication_counts["failed"],
            uncertain=communication_counts["uncertain"],
        )
    else:
        _check(checks, "COMMUNICATION_QUEUE_TERMINAL", "ok")

    payment_policy_active = bool(getattr(cfg, "zadatek_wymagany", False))
    payment_policy_active = payment_policy_active or bool(
        db.query(models.PolitykaPlatnosciRezerwacji.id)
        .filter(
            models.PolitykaPlatnosciRezerwacji.aktywna.is_(True),
            models.PolitykaPlatnosciRezerwacji.rodzaj != "brak",
        )
        .first()
    )
    payments_pending = sum(
        payment_counts[state]
        for state in ("queued", "processing", "retry", "uncertain")
    ) + sum(
        webhook_counts[state] for state in ("queued", "processing")
    )
    payments_required = payment_policy_active or payments_pending > 0
    payments_configured = integracje.skonfigurowane("platnosci")
    _gate(
        gates,
        "PAYMENT_PROVIDER",
        required=payments_required,
        satisfied=payments_configured,
    )
    _check(
        checks,
        "PAYMENT_PROVIDER",
        (
            "attention"
            if payments_required and not payments_configured
            else "ok"
        ),
        configured=payments_configured,
        required=payments_required,
    )
    payment_worker = reservation_payment_worker.worker_running()
    _check(
        checks,
        "PAYMENT_WORKER",
        (
            "attention"
            if payments_configured and not payment_worker
            else "ok"
        ),
        running=payment_worker,
        required=payments_configured,
    )
    if (
        payment_counts["failed"]
        or payment_counts["uncertain"]
        or webhook_counts["failed"]
    ):
        _check(
            checks,
            "PAYMENT_QUEUE_TERMINAL",
            "attention",
            commands_failed=payment_counts["failed"],
            commands_uncertain=payment_counts["uncertain"],
            webhooks_failed=webhook_counts["failed"],
        )
    else:
        _check(checks, "PAYMENT_QUEUE_TERMINAL", "ok")

    statuses = {item["status"] for item in checks}
    status = (
        "blocked"
        if "blocked" in statuses
        else ("attention" if "attention" in statuses else "ready")
    )
    return {
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "privacy_notice_version": PUBLIC_PRIVACY_NOTICE_VERSION,
        "checks": checks,
        "gates": gates,
        "queues": queues,
        "workers": {
            "communication": communication_worker,
            "payments": payment_worker,
        },
    }
