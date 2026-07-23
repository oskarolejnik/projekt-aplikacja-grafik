"""R5b: transactional outbox and delivery lifecycle for reservation messages.

Network I/O never runs in the reservation transaction.  A durable, encrypted
message snapshot is committed with the domain change, then a short-lived worker
claims it, commits the lease and contacts the provider outside any database lock.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import hmac
import logging
import os
import secrets
import threading
import unicodedata
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import or_, text

import mailer
import models
import reservation_service
import sms
import settings as app_settings
from database import SessionLocal
from deps import utcnow_naive


logger = logging.getLogger(__name__)

WARSAW = ZoneInfo("Europe/Warsaw")
ACTIVE_RESERVATION_STATES = ("rezerwacja", "potwierdzona")
PENDING_STATES = ("queued", "retry")
ATTENTION_STATES = ("failed", "uncertain", "expired")
WAITLIST_STALE_DELIVERED_CODE = "WAITLIST_STALE_TABLE_READY_DELIVERED"
WAITLIST_SUPERSEDED_UNCERTAIN_CODE = "WAITLIST_SUPERSEDED_DELIVERY_UNCERTAIN"
WAITLIST_SUPERSEDED_NOT_SENT_CODE = "WAITLIST_SUPERSEDED_DELIVERY_NOT_SENT"
TEMPLATE_VERSION = "r5b-v1"
LEASE_SECONDS = 90
DEFAULT_MAX_ATTEMPTS = 5
_PLANNER_LOCK_ID = 1_281_315_152
_SUBJECT_INDEX_KEY_DOMAIN = b"lokalo:r5b:communication-subject:index-key:v1"
_SUBJECT_PHONE_DOMAIN = b"lokalo:r5b:communication-subject:phone:v1\x00"
_SUBJECT_EMAIL_DOMAIN = b"lokalo:r5b:communication-subject:email:v1\x00"

EVENT_LABELS = {
    "confirmation": "Potwierdzenie",
    "reminder": "Przypomnienie",
    "change": "Zmiana rezerwacji",
    "cancellation": "Anulowanie",
    "table_ready": "Stolik gotowy",
}

_stop_event = threading.Event()
_state_lock = threading.Lock()
_thread: Optional[threading.Thread] = None


@dataclass(frozen=True)
class ClaimedMessage:
    id: int
    attempt_number: int
    lease_token: str
    channel: str
    recipient: str
    subject: Optional[str]
    body: str
    provider_idempotency_key: str
    provider_supports_idempotency: bool
    provider_idempotency_header: Optional[str]


class CommunicationDeliveryInProgress(RuntimeError):
    """PII cannot be erased after provider I/O has started for an owner.

    The exception deliberately exposes only internal numeric identifiers and a
    stable code.  Message snapshots, recipients and provider errors must never
    reach an HTTP response or a log through this path.
    """

    code = "COMMUNICATION_DELIVERY_IN_PROGRESS"

    def __init__(self, *, reservation_ids=(), waitlist_ids=()):
        self.reservation_ids = tuple(sorted({int(value) for value in reservation_ids}))
        self.waitlist_ids = tuple(sorted({int(value) for value in waitlist_ids}))
        super().__init__(self.code)


@dataclass(frozen=True)
class PiiErasurePreparation:
    message_ids: tuple[int, ...]
    deferred_reservation_ids: tuple[int, ...]
    deferred_waitlist_ids: tuple[int, ...]


def _now(value: Optional[datetime] = None) -> datetime:
    return value or utcnow_naive()


def _actor_kind(actor=None, actor_kind: Optional[str] = None) -> str:
    if actor_kind in {"system", "user", "guest"}:
        return actor_kind
    return "user" if actor is not None else "system"


def dedupe_identity(value: str) -> str:
    value = str(value or "").strip()
    if not value:
        value = f"manual:{secrets.token_hex(16)}"
    # Ani klucz idempotencji żądania, ani opis zdarzenia nie trafia do bazy.
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def current_waitlist_offer_dedupe(waitlist) -> Optional[str]:
    if waitlist is None or not getattr(waitlist, "offer_key_hash", None):
        return None
    return dedupe_identity(
        f"waitlist:{waitlist.id}:offer:{int(waitlist.offer_version or 0)}:"
        f"{waitlist.offer_key_hash}"
    )


def _provider_key(dedupe_key: str, channel: str) -> str:
    return hashlib.sha256(f"{dedupe_key}:{channel}".encode("utf-8")).hexdigest()


def _subject_index_key() -> bytes:
    root_secret = os.environ.get("ENCRYPTION_KEY", "").strip()
    if not root_secret and app_settings.IS_DEV:
        # Wyłącznie lokalny fallback developerski; produkcja fail-closed.
        root_secret = os.environ.get("SECRET_KEY", "").strip()
    if not root_secret:
        raise RuntimeError("SUBJECT_REF_KEY_UNAVAILABLE")
    return hmac.new(
        root_secret.encode("utf-8"),
        _SUBJECT_INDEX_KEY_DOMAIN,
        hashlib.sha256,
    ).digest()


def _canonical_email(value: str) -> str:
    return unicodedata.normalize("NFKC", value or "").strip().casefold()


def _subject_ref(value: str, *, domain: bytes) -> Optional[str]:
    canonical = (value or "").strip()
    if not canonical:
        return None
    return hmac.new(
        _subject_index_key(),
        domain + canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def subject_refs_for_key(value: str) -> tuple[Optional[str], Optional[str]]:
    """Zwraca ref telefonu albo e-maila dla znormalizowanego klucza żądania."""
    raw = (value or "").strip()
    if "@" in raw:
        return None, _subject_ref(
            _canonical_email(raw), domain=_SUBJECT_EMAIL_DOMAIN,
        )
    phone = sms._normalizuj_numer(raw)
    if phone:
        return _subject_ref(phone, domain=_SUBJECT_PHONE_DOMAIN), None
    email = _canonical_email(raw)
    return None, _subject_ref(email, domain=_SUBJECT_EMAIL_DOMAIN)


def subject_refs_for_owner(owner) -> tuple[Optional[str], Optional[str]]:
    phone = sms._normalizuj_numer(getattr(owner, "telefon", None) or "")
    email = _canonical_email(getattr(owner, "email", None) or "")
    return (
        _subject_ref(phone, domain=_SUBJECT_PHONE_DOMAIN),
        _subject_ref(email, domain=_SUBJECT_EMAIL_DOMAIN),
    )


def _channels(owner) -> list[tuple[str, str]]:
    preference = (getattr(owner, "kanal_komunikacji", None) or "auto").strip()
    email = (getattr(owner, "email", None) or "").strip()
    phone = (getattr(owner, "telefon", None) or "").strip()
    if preference == "brak":
        return []
    if preference == "email":
        return [("email", email)] if email else []
    if preference == "sms":
        return [("sms", phone)] if phone else []
    if preference == "oba":
        result = []
        if email:
            result.append(("email", email))
        if phone:
            result.append(("sms", phone))
        return result
    # Automatycznie wybieramy jeden kanał, aby nie dublować komunikatu.
    if email:
        return [("email", email)]
    return [("sms", phone)] if phone else []


def available_delivery_channels(owner) -> tuple[str, ...]:
    """PII-free capability projection for operator views."""
    return tuple(channel for channel, _recipient in _channels(owner))


def _hm(value) -> str:
    return value.strftime("%H:%M") if value is not None else ""


def _reservation_details(owner) -> str:
    parts = [f"{owner.data}"]
    if getattr(owner, "godz_od", None):
        parts.append(f"o {_hm(owner.godz_od)}")
    if getattr(owner, "liczba_osob", None):
        parts.append(f"dla {owner.liczba_osob} os.")
    return " ".join(parts)


def render_message(event_type: str, owner, cfg, channel: str) -> tuple[Optional[str], str]:
    """Renders a versioned immutable snapshot; never embeds management tokens."""
    venue = (getattr(cfg, "nazwa_lokalu", None) or "Lokalo").strip()
    details = _reservation_details(owner)
    if event_type == "confirmation":
        subject = f"Potwierdzenie rezerwacji — {venue}"
        sentence = f"Twoja rezerwacja w {venue} ({details}) została przyjęta."
    elif event_type == "reminder":
        subject = f"Przypomnienie o rezerwacji — {venue}"
        sentence = f"Przypominamy o rezerwacji w {venue}: {details}."
    elif event_type == "change":
        subject = f"Zmiana rezerwacji — {venue}"
        sentence = f"Szczegóły Twojej rezerwacji w {venue} zostały zmienione: {details}."
    elif event_type == "cancellation":
        subject = f"Anulowanie rezerwacji — {venue}"
        sentence = f"Twoja rezerwacja w {venue} ({details}) została anulowana."
    elif event_type == "table_ready":
        subject = f"Stolik gotowy — {venue}"
        deadline = getattr(owner, "oferta_wygasa_at", None) or getattr(
            owner, "hold_do", None,
        )
        deadline_text = ""
        if deadline is not None:
            if deadline.tzinfo is None or deadline.utcoffset() is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            local_deadline = deadline.astimezone(WARSAW)
            deadline_text = f" Oferta jest ważna do {local_deadline:%H:%M}."
        sentence = (
            f"Twój stolik w {venue} jest gotowy.{deadline_text} Zapraszamy!"
        )
    else:
        raise ValueError(f"Nieznany szablon wiadomości: {event_type}")

    if channel == "sms":
        return None, sentence
    return subject, f"Dzień dobry,\n\n{sentence}\n\nDo zobaczenia!\n{venue}"


def _enqueue(
    db,
    *,
    owner,
    owner_kind: str,
    event_type: str,
    cfg,
    dedupe_key: Optional[str] = None,
    available_at: Optional[datetime] = None,
    expires_at: Optional[datetime] = None,
    actor=None,
    actor_kind: Optional[str] = None,
    now: Optional[datetime] = None,
) -> list[models.RezerwacjaWiadomoscOutbox]:
    if event_type not in EVENT_LABELS:
        raise ValueError("Nieznany typ wiadomości operacyjnej.")
    owner_id = getattr(owner, "id", None)
    if not owner_id:
        raise ValueError("Wiadomość wymaga zapisanego właściciela.")
    event_key = dedupe_identity(dedupe_key or (
        f"{owner_kind}:{owner_id}:{event_type}:{secrets.token_hex(16)}"
    ))
    effective_now = _now(now)
    effective_available_at = available_at or effective_now
    effective_expires_at = expires_at or (effective_available_at + timedelta(days=7))
    if effective_expires_at <= effective_available_at:
        return []
    # SessionLocal celowo ma autoflush=False. Dzięki temu ponowne enqueue
    # rozpoznaje również wpisy dodane wcześniej w tej samej transakcji.
    db.flush()
    subject_phone_ref, subject_email_ref = subject_refs_for_owner(owner)
    if not subject_phone_ref and not subject_email_ref:
        return []
    rows = []
    for channel, recipient in _channels(owner):
        existing = db.query(models.RezerwacjaWiadomoscOutbox).filter_by(
            dedupe_key=event_key, kanal=channel,
        ).first()
        if existing is not None:
            rows.append(existing)
            continue
        subject, body = render_message(event_type, owner, cfg, channel)
        provider_header = (
            sms.provider_idempotency_header()
            if channel == "sms" and sms.provider_supports_idempotency()
            else None
        )
        supports_idempotency = provider_header is not None
        row = models.RezerwacjaWiadomoscOutbox(
            termin_id=owner_id if owner_kind == "reservation" else None,
            waitlist_id=owner_id if owner_kind == "waitlist" else None,
            subject_phone_ref=subject_phone_ref,
            subject_email_ref=subject_email_ref,
            dedupe_key=event_key,
            typ_zdarzenia=event_type,
            kanal=channel,
            odbiorca=recipient,
            temat=subject,
            tresc=body,
            template_key=event_type,
            template_version=TEMPLATE_VERSION,
            provider="smtp" if channel == "email" else "sms_http",
            provider_idempotency_key=_provider_key(event_key, channel),
            provider_supports_idempotency=supports_idempotency,
            provider_idempotency_header=provider_header,
            stan="queued",
            liczba_prob=0,
            maks_prob=DEFAULT_MAX_ATTEMPTS,
            available_at=effective_available_at,
            expires_at=effective_expires_at,
            actor_kind=_actor_kind(actor, actor_kind),
            actor_user_id=getattr(actor, "id", None),
            created_at=effective_now,
            updated_at=effective_now,
        )
        db.add(row)
        rows.append(row)
    return rows


def enqueue_reservation(
    db,
    reservation,
    event_type: str,
    *,
    cfg=None,
    dedupe_key: Optional[str] = None,
    available_at: Optional[datetime] = None,
    expires_at: Optional[datetime] = None,
    actor=None,
    actor_kind: Optional[str] = None,
) -> list[models.RezerwacjaWiadomoscOutbox]:
    cfg = cfg or db.get(models.LokalConfig, 1) or models.LokalConfig(id=1)
    effective_now = _now()
    if expires_at is None:
        visit_at = _visit_utc(reservation)
        if event_type in {"confirmation", "change"} and visit_at is not None:
            expires_at = max(effective_now + timedelta(minutes=1), visit_at)
        elif event_type == "cancellation":
            expires_at = effective_now + timedelta(days=2)
    return _enqueue(
        db,
        owner=reservation,
        owner_kind="reservation",
        event_type=event_type,
        cfg=cfg,
        dedupe_key=dedupe_key,
        available_at=available_at,
        expires_at=expires_at,
        actor=actor,
        actor_kind=actor_kind,
    )


def enqueue_table_ready(
    db,
    waitlist,
    *,
    cfg=None,
    dedupe_key: Optional[str] = None,
    actor=None,
    now: Optional[datetime] = None,
) -> list[models.RezerwacjaWiadomoscOutbox]:
    cfg = cfg or db.get(models.LokalConfig, 1) or models.LokalConfig(id=1)
    effective_now = _now(now)
    deadline = getattr(waitlist, "hold_do", None)
    offer_deadline = getattr(waitlist, "oferta_wygasa_at", None)
    is_offer_generation = bool(
        getattr(waitlist, "status", None) == "zaoferowano"
        or offer_deadline is not None
        or getattr(waitlist, "offer_key_hash", None)
    )
    if is_offer_generation and (
        deadline is None
        or offer_deadline is None
        or deadline != offer_deadline
        or deadline <= effective_now
    ):
        # Oferta R6b.2 ma jeden zamrożony deadline dla holda i wiadomości.
        # Nie wolno odtwarzać go z czasu procesu ani przedłużać o kolejne 30 min.
        return []
    if not is_offer_generation and (deadline is None or deadline <= effective_now):
        # Kompatybilność wyłącznie dla historycznego, przed-R6b.2 wywołania.
        deadline = effective_now + timedelta(minutes=30)
    return _enqueue(
        db,
        owner=waitlist,
        owner_kind="waitlist",
        event_type="table_ready",
        cfg=cfg,
        # The persisted random incarnation prevents a reused SQLite owner id
        # from reusing a provider idempotency key after hard deletion. The
        # locked endpoint returns the existing group on request replay.
        dedupe_key=dedupe_key or (
            f"waitlist:{waitlist.id}:table_ready:{secrets.token_hex(16)}"
        ),
        available_at=effective_now,
        expires_at=deadline,
        actor=actor,
        now=effective_now,
    )


def cancel_pending(
    db,
    reservation_id: int,
    *,
    event_types: Optional[Iterable[str]] = None,
    now: Optional[datetime] = None,
) -> int:
    db.flush()
    cancellable_states = (*PENDING_STATES, "processing", "failed", "expired")
    query = db.query(models.RezerwacjaWiadomoscOutbox).filter(
        models.RezerwacjaWiadomoscOutbox.termin_id == reservation_id,
        models.RezerwacjaWiadomoscOutbox.stan.in_(cancellable_states),
    )
    if event_types:
        query = query.filter(
            models.RezerwacjaWiadomoscOutbox.typ_zdarzenia.in_(tuple(event_types)),
        )
    return _cancel_rows_before_io(db, query, _now(now))


def cancel_waitlist_pending(
    db,
    waitlist_id: int,
    *,
    now: Optional[datetime] = None,
) -> int:
    db.flush()
    query = db.query(models.RezerwacjaWiadomoscOutbox).filter(
        models.RezerwacjaWiadomoscOutbox.waitlist_id == waitlist_id,
        models.RezerwacjaWiadomoscOutbox.stan.in_(
            (*PENDING_STATES, "processing", "failed", "expired"),
        ),
    )
    return _cancel_rows_before_io(db, query, _now(now))


def _cancel_rows_before_io(db, query, effective_now: datetime) -> int:
    """Cancel queued work and claimed leases without hiding started provider I/O."""
    if db.get_bind().dialect.name == "postgresql":
        query = query.with_for_update()
    changed = 0
    for row in query.all():
        if row.stan == "processing":
            attempt = db.query(models.RezerwacjaWiadomoscProba).filter_by(
                wiadomosc_id=row.id,
                numer=row.liczba_prob,
                lease_token=row.lease_token,
            ).first()
            if attempt is None or attempt.wynik != "claimed":
                continue
            attempt.wynik = "failed"
            attempt.error_code = "CANCELLED_BEFORE_IO"
            attempt.finished_at = effective_now
            row.lease_token = None
            row.lease_expires_at = None
            row.last_error_code = "CANCELLED_BEFORE_IO"
        row.stan = "cancelled"
        row.updated_at = effective_now
        changed += 1
    return changed


def acquire_erasure_planner_lock(db) -> None:
    """Fences the reminder planner after callers have acquired owner-day locks."""
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": _PLANNER_LOCK_ID},
        )


def prepare_outboxes_for_pii_erasure(
    db,
    *,
    message_ids: Iterable[int] = (),
    reservation_ids: Iterable[int] = (),
    waitlist_ids: Iterable[int] = (),
    defer_started: bool = False,
    now: Optional[datetime] = None,
) -> PiiErasurePreparation:
    """Lock owner outboxes before deleting their encrypted PII snapshots.

    A claim whose attempt is still ``claimed`` is durably cancelled before any
    provider I/O and can then be deleted in the same transaction.  Once an
    attempt is ``processing`` (or its lifecycle is inconsistent), erasure must
    not commit: the worker already holds a plaintext snapshot outside the DB.

    PostgreSQL uses row locks shared with ``mark_claim_started``.  SQLite first
    performs a no-op UPDATE, which upgrades the current transaction to the
    single writer before inspecting lifecycle state.  This closes the race even
    when the caller already performed reads and therefore cannot issue a fresh
    ``BEGIN IMMEDIATE``.
    """
    message_ids = {int(value) for value in message_ids if value is not None}
    reservation_ids = {int(value) for value in reservation_ids if value is not None}
    waitlist_ids = {int(value) for value in waitlist_ids if value is not None}
    if not message_ids and not reservation_ids and not waitlist_ids:
        return PiiErasurePreparation((), (), ())

    conditions = []
    if message_ids:
        conditions.append(
            models.RezerwacjaWiadomoscOutbox.id.in_(message_ids),
        )
    if reservation_ids:
        conditions.append(
            models.RezerwacjaWiadomoscOutbox.termin_id.in_(reservation_ids),
        )
    if waitlist_ids:
        conditions.append(
            models.RezerwacjaWiadomoscOutbox.waitlist_id.in_(waitlist_ids),
        )
    owner_filter = or_(*conditions)
    db.flush()
    dialect = db.get_bind().dialect.name
    # Global order is owner day -> planner -> outbox. Reservation producers use
    # the same order, while the background scheduler only takes planner; it
    # therefore cannot append a stale reminder after the erasure scan.
    acquire_erasure_planner_lock(db)
    if dialect == "sqlite":
        # SQLite has no row-level FOR UPDATE.  Even a value-preserving UPDATE
        # obtains the database writer lock and serializes against claim/start.
        db.query(models.RezerwacjaWiadomoscOutbox).filter(owner_filter).update(
            {
                models.RezerwacjaWiadomoscOutbox.updated_at:
                    models.RezerwacjaWiadomoscOutbox.updated_at,
            },
            synchronize_session=False,
        )

    query = db.query(models.RezerwacjaWiadomoscOutbox).filter(owner_filter).order_by(
        models.RezerwacjaWiadomoscOutbox.id,
    )
    if dialect == "postgresql":
        query = query.with_for_update()
    rows = query.all()

    processing = [row for row in rows if row.stan == "processing"]
    attempts_by_key = {}
    if processing:
        attempt_query = db.query(models.RezerwacjaWiadomoscProba).filter(
            models.RezerwacjaWiadomoscProba.wiadomosc_id.in_(
                [row.id for row in processing],
            ),
        )
        if dialect == "postgresql":
            attempt_query = attempt_query.with_for_update()
        for attempt in attempt_query.all():
            attempts_by_key[
                (attempt.wiadomosc_id, attempt.numer, attempt.lease_token)
            ] = attempt

    blocked_reservations = set()
    blocked_waitlists = set()
    current_attempts = {}
    for row in processing:
        attempt = attempts_by_key.get((row.id, row.liczba_prob, row.lease_token))
        current_attempts[row.id] = attempt
        before_io = bool(
            attempt is not None
            and attempt.wynik == "claimed"
            and attempt.started_at is None
        )
        if before_io:
            continue
        if row.termin_id is not None:
            blocked_reservations.add(row.termin_id)
        else:
            blocked_waitlists.add(row.waitlist_id)

    if (blocked_reservations or blocked_waitlists) and not defer_started:
        raise CommunicationDeliveryInProgress(
            reservation_ids=blocked_reservations,
            waitlist_ids=blocked_waitlists,
        )

    effective_now = _now(now)
    safe_rows = [
        row for row in rows
        if row.termin_id not in blocked_reservations
        and row.waitlist_id not in blocked_waitlists
    ]
    for row in safe_rows:
        if row.stan != "processing":
            continue
        attempt = current_attempts[row.id]
        attempt.wynik = "failed"
        attempt.error_code = "ERASURE_CANCELLED_BEFORE_IO"
        attempt.finished_at = effective_now
        row.stan = "cancelled"
        row.lease_token = None
        row.lease_expires_at = None
        row.last_error_code = "ERASURE_CANCELLED_BEFORE_IO"
        row.updated_at = effective_now
    # Persist the lifecycle transition before the caller performs bulk deletes.
    db.flush()
    return PiiErasurePreparation(
        message_ids=tuple(row.id for row in safe_rows),
        deferred_reservation_ids=tuple(sorted(blocked_reservations)),
        deferred_waitlist_ids=tuple(sorted(blocked_waitlists)),
    )


def _visit_utc(reservation) -> Optional[datetime]:
    if reservation.godz_od is None:
        return None
    local = datetime.combine(reservation.data, reservation.godz_od).replace(tzinfo=WARSAW)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def reminder_dedupe_key(reservation, reminder_hours: int) -> str:
    return (
        f"reservation:{reservation.id}:reminder:{reservation.data}:"
        f"{_hm(reservation.godz_od)}:h{reminder_hours}:{TEMPLATE_VERSION}:"
        f"{secrets.token_hex(12)}"
    )


def schedule_reminder(
    db,
    reservation,
    *,
    cfg=None,
    actor=None,
    actor_kind: Optional[str] = None,
    now: Optional[datetime] = None,
    force_new: bool = False,
) -> list[models.RezerwacjaWiadomoscOutbox]:
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": _PLANNER_LOCK_ID},
        )
    db.flush()
    if cfg is None:
        # The planner lock may have waited for a concurrent config rollout.
        # Refresh the identity-map value so a long-lived reservation transaction
        # cannot schedule with the policy it read before acquiring that lock.
        cfg = db.query(models.LokalConfig).populate_existing().filter_by(id=1).first()
    cfg = cfg or models.LokalConfig(id=1)
    hours = int(getattr(cfg, "rezerwacje_przypomnienie_h", 0) or 0)
    visit_at = _visit_utc(reservation)
    effective_now = _now(now)
    if (
        hours <= 0
        or reservation.status not in ACTIVE_RESERVATION_STATES
        or reservation.kanal == "walk_in"
        or visit_at is None
        or visit_at <= effective_now
    ):
        cancel_pending(
            db, reservation.id, event_types=("reminder",), now=effective_now,
        )
        return []
    scheduled_at = visit_at - timedelta(hours=hours)
    desired_channels = set(_channels(reservation))
    if force_new:
        cancel_pending(
            db,
            reservation.id,
            event_types=("reminder",),
            now=effective_now,
        )
    latest_change = db.query(models.RezerwacjaWiadomoscOutbox.id).filter(
        models.RezerwacjaWiadomoscOutbox.termin_id == reservation.id,
        models.RezerwacjaWiadomoscOutbox.typ_zdarzenia == "change",
    ).order_by(models.RezerwacjaWiadomoscOutbox.id.desc()).first()
    existing_query = db.query(models.RezerwacjaWiadomoscOutbox).filter(
        models.RezerwacjaWiadomoscOutbox.termin_id == reservation.id,
        models.RezerwacjaWiadomoscOutbox.typ_zdarzenia == "reminder",
        models.RezerwacjaWiadomoscOutbox.stan != "cancelled",
    )
    if latest_change is not None:
        # Zmiana danych gościa/terminu rozpoczyna nową generację komunikacji.
        # Historyczne, już wysłane przypomnienie nie może blokować ani dublować
        # nowego kanału po edycji (np. email → SMS albo A → B → A).
        existing_query = existing_query.filter(
            models.RezerwacjaWiadomoscOutbox.id > latest_change[0],
        )
    existing = existing_query.all()
    matching = [
        row for row in existing
        if row.expires_at == visit_at
        and (
            row.stan != "queued"
            or row.available_at == scheduled_at
        )
    ]
    existing_channels = {(row.kanal, row.odbiorca) for row in matching}
    if (
        not force_new
        and matching
        and existing_channels == desired_channels
    ):
        return matching
    for row in existing:
        if row.stan in PENDING_STATES:
            row.stan = "cancelled"
            row.updated_at = effective_now
    return enqueue_reservation(
        db,
        reservation,
        "reminder",
        cfg=cfg,
        dedupe_key=reminder_dedupe_key(reservation, hours),
        available_at=scheduled_at,
        expires_at=visit_at,
        actor=actor,
        actor_kind=actor_kind,
    )


def reconcile_reminder_schedule(db, *, now: Optional[datetime] = None) -> int:
    """Repairs missing/upcoming reminders after restart or configuration change."""
    effective_now = _now(now)
    cfg = db.get(models.LokalConfig, 1)
    if cfg is None:
        return 0
    hours = int(cfg.rezerwacje_przypomnienie_h or 0)
    now_local = effective_now.replace(tzinfo=timezone.utc).astimezone(WARSAW)
    horizon = now_local + timedelta(hours=max(24, hours + 24))
    reservations = db.query(models.Termin).filter(
        models.Termin.rodzaj == "stolik",
        models.Termin.status.in_(ACTIVE_RESERVATION_STATES),
        models.Termin.data >= now_local.date(),
        models.Termin.data <= horizon.date(),
        models.Termin.godz_od.isnot(None),
    ).all()
    changed = 0
    for reservation in reservations:
        rows = schedule_reminder(db, reservation, cfg=cfg, now=effective_now)
        changed += sum(1 for row in rows if row in db.new)
    return changed


def acquire_planner_configuration_lock(db) -> None:
    """Serializes a config rollout with the planner and reservation producers."""
    if db.get_bind().dialect.name == "sqlite":
        _begin_worker_write(db)
    elif db.get_bind().dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": _PLANNER_LOCK_ID},
        )


def reconfigure_reminders(db, *, cfg, now: Optional[datetime] = None) -> int:
    """Atomically replaces every pending old-policy reminder after a config change."""
    effective_now = _now(now)
    query = db.query(models.RezerwacjaWiadomoscOutbox).filter(
        models.RezerwacjaWiadomoscOutbox.typ_zdarzenia == "reminder",
        models.RezerwacjaWiadomoscOutbox.stan.in_(
            (*PENDING_STATES, "processing", "failed", "expired"),
        ),
    )
    _cancel_rows_before_io(db, query, effective_now)
    db.flush()

    now_local = effective_now.replace(tzinfo=timezone.utc).astimezone(WARSAW)
    reservations = db.query(models.Termin).filter(
        models.Termin.rodzaj == "stolik",
        models.Termin.status.in_(ACTIVE_RESERVATION_STATES),
        models.Termin.data >= now_local.date(),
        models.Termin.godz_od.isnot(None),
    ).all()
    created = 0
    for reservation in reservations:
        rows = schedule_reminder(
            db, reservation, cfg=cfg, now=effective_now,
        )
        created += sum(1 for row in rows if row in db.new)
    return created


def _begin_worker_write(db) -> None:
    if db.get_bind().dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))


def _locked_query(query, db):
    if db.get_bind().dialect.name == "postgresql":
        return query.with_for_update(skip_locked=True)
    return query


def _cancel_stale_retry(row, attempt, *, code: str, now: datetime) -> None:
    """Stops work that no longer matches its current reservation/waitlist owner."""
    if attempt is not None:
        attempt.wynik = "failed"
        attempt.error_code = code
        attempt.finished_at = now
        attempt.retry_at = None
    row.stan = "cancelled"
    row.lease_token = None
    row.lease_expires_at = None
    row.last_error_code = code
    row.updated_at = now


def _recover_expired_leases(db, now: datetime) -> int:
    query = db.query(models.RezerwacjaWiadomoscOutbox).filter(
        models.RezerwacjaWiadomoscOutbox.stan == "processing",
        models.RezerwacjaWiadomoscOutbox.lease_expires_at <= now,
    ).order_by(models.RezerwacjaWiadomoscOutbox.id)
    rows = _locked_query(query, db).all()
    for row in rows:
        attempt = db.query(models.RezerwacjaWiadomoscProba).filter_by(
            wiadomosc_id=row.id,
            numer=row.liczba_prob,
        ).first()
        before_io = attempt is None or attempt.wynik == "claimed"
        effective_idempotency = bool(
            attempt is not None and attempt.provider_supports_idempotency
        )
        relevance_error = _retry_relevance_error(db, row, now=now)
        if relevance_error and before_io:
            _cancel_stale_retry(
                row, attempt, code=relevance_error, now=now,
            )
            continue
        if relevance_error:
            # Provider I/O started and no provider-status lookup proved the
            # outcome. Even an idempotency key cannot turn that into certainty;
            # keep an operator-visible fence before another waitlist offer.
            row.stan = "uncertain"
            row.uncertain_at = now
            row.last_error_code = "LEASE_EXPIRED_SUPERSEDED_AMBIGUOUS"
            if attempt is not None:
                attempt.wynik = "uncertain"
                attempt.error_code = row.last_error_code
                attempt.finished_at = now
            row.lease_token = None
            row.lease_expires_at = None
            row.updated_at = now
            continue
        if before_io and row.expires_at > now:
            row.stan = "retry"
            row.available_at = now
            row.last_error_code = "LEASE_EXPIRED_BEFORE_IO"
            if attempt is not None:
                attempt.wynik = "retry"
                attempt.error_code = row.last_error_code
                attempt.finished_at = now
                attempt.retry_at = now
        elif before_io:
            row.stan = "expired"
            row.last_error_code = "MESSAGE_EXPIRED"
            if attempt is not None:
                attempt.wynik = "failed"
                attempt.error_code = row.last_error_code
                attempt.finished_at = now
        elif row.expires_at <= now:
            row.stan = "uncertain"
            row.uncertain_at = now
            row.last_error_code = "LEASE_EXPIRED_AFTER_IO_DEADLINE_AMBIGUOUS"
            if attempt is not None:
                attempt.wynik = "uncertain"
                attempt.error_code = row.last_error_code
                attempt.finished_at = now
        elif effective_idempotency:
            row.stan = "retry"
            row.available_at = now
            row.last_error_code = "LEASE_EXPIRED_SAFE_RETRY"
            if attempt is not None:
                attempt.wynik = "retry"
                attempt.error_code = row.last_error_code
                attempt.finished_at = now
                attempt.retry_at = now
        else:
            row.stan = "uncertain"
            row.uncertain_at = now
            row.last_error_code = "LEASE_EXPIRED_AMBIGUOUS"
            if attempt is not None:
                attempt.wynik = "uncertain"
                attempt.error_code = row.last_error_code
                attempt.finished_at = now
        row.lease_token = None
        row.lease_expires_at = None
        row.updated_at = now
    return len(rows)


def claim_next(*, now: Optional[datetime] = None) -> Optional[ClaimedMessage]:
    effective_now = _now(now)
    db = SessionLocal()
    try:
        _begin_worker_write(db)
        _recover_expired_leases(db, effective_now)
        # Autoflush jest wyłączony; bez tego odzyskany wpis nadal wygląda w SQL
        # jak `processing` i worker pominąłby bezpieczny retry do kolejnego cyklu.
        db.flush()
        expired_query = db.query(models.RezerwacjaWiadomoscOutbox).filter(
            models.RezerwacjaWiadomoscOutbox.stan.in_(PENDING_STATES),
            models.RezerwacjaWiadomoscOutbox.expires_at <= effective_now,
        ).order_by(models.RezerwacjaWiadomoscOutbox.id)
        for expired in _locked_query(expired_query, db).all():
            expired.stan = "expired"
            expired.last_error_code = "MESSAGE_EXPIRED"
            expired.updated_at = effective_now
        query = db.query(models.RezerwacjaWiadomoscOutbox).filter(
            models.RezerwacjaWiadomoscOutbox.stan.in_(PENDING_STATES),
            models.RezerwacjaWiadomoscOutbox.available_at <= effective_now,
            models.RezerwacjaWiadomoscOutbox.expires_at > effective_now,
        ).order_by(
            models.RezerwacjaWiadomoscOutbox.available_at,
            models.RezerwacjaWiadomoscOutbox.id,
        )
        while True:
            row = _locked_query(query, db).first()
            if row is None:
                db.commit()
                return None
            relevance_error = _retry_relevance_error(
                db, row, now=effective_now,
            )
            if relevance_error:
                _cancel_stale_retry(
                    row, None, code=relevance_error, now=effective_now,
                )
                db.flush()
                continue
            if row.liczba_prob >= row.maks_prob:
                row.stan = "failed"
                row.last_error_code = "ATTEMPTS_EXHAUSTED"
                row.updated_at = effective_now
                db.flush()
                continue
            break

        token = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
        row.liczba_prob += 1
        row.stan = "processing"
        row.lease_token = token
        row.lease_expires_at = effective_now + timedelta(seconds=LEASE_SECONDS)
        row.updated_at = effective_now
        effective_idempotency = bool(row.provider_supports_idempotency)
        attempt = models.RezerwacjaWiadomoscProba(
            wiadomosc_id=row.id,
            numer=row.liczba_prob,
            provider=row.provider,
            provider_idempotency_key=row.provider_idempotency_key,
            provider_supports_idempotency=effective_idempotency,
            provider_idempotency_header=row.provider_idempotency_header,
            lease_token=token,
            claimed_at=effective_now,
            started_at=None,
            wynik="claimed",
        )
        db.add(attempt)
        claimed = ClaimedMessage(
            id=row.id,
            attempt_number=row.liczba_prob,
            lease_token=token,
            channel=row.kanal,
            recipient=row.odbiorca,
            subject=row.temat,
            body=row.tresc,
            provider_idempotency_key=row.provider_idempotency_key,
            provider_supports_idempotency=effective_idempotency,
            provider_idempotency_header=row.provider_idempotency_header,
        )
        db.commit()
        return claimed
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def mark_claim_started(
    claim: ClaimedMessage,
    *,
    now: Optional[datetime] = None,
) -> Optional[ClaimedMessage]:
    """Commits the fact that provider I/O is about to start before touching the network."""
    effective_now = _now(now)
    db = SessionLocal()
    try:
        _begin_worker_write(db)
        query = db.query(models.RezerwacjaWiadomoscOutbox).filter_by(id=claim.id)
        if db.get_bind().dialect.name == "postgresql":
            query = query.with_for_update()
        row = query.first()
        if (
            row is None
            or row.stan != "processing"
            or row.lease_token != claim.lease_token
            or row.expires_at <= effective_now
        ):
            db.rollback()
            return None
        attempt = db.query(models.RezerwacjaWiadomoscProba).filter_by(
            wiadomosc_id=row.id,
            numer=claim.attempt_number,
            lease_token=claim.lease_token,
        ).one()
        if attempt.wynik != "claimed":
            db.rollback()
            return None
        relevance_error = _retry_relevance_error(
            db, row, now=effective_now,
        )
        if relevance_error:
            _cancel_stale_retry(
                row, attempt, code=relevance_error, now=effective_now,
            )
            db.commit()
            return None
        effective_idempotency = bool(row.provider_supports_idempotency)
        if (
            attempt.provider_supports_idempotency != effective_idempotency
            or attempt.provider_idempotency_header != row.provider_idempotency_header
        ):
            db.rollback()
            return None
        attempt.wynik = "processing"
        attempt.started_at = effective_now
        db.commit()
        return ClaimedMessage(
            id=claim.id,
            attempt_number=claim.attempt_number,
            lease_token=claim.lease_token,
            channel=claim.channel,
            recipient=claim.recipient,
            subject=claim.subject,
            body=claim.body,
            provider_idempotency_key=claim.provider_idempotency_key,
            provider_supports_idempotency=effective_idempotency,
            provider_idempotency_header=row.provider_idempotency_header,
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def backoff_seconds(message_id: int, attempt_number: int) -> int:
    base = min(6 * 60 * 60, 30 * (4 ** max(0, attempt_number - 1)))
    # Stable jitter keeps tests deterministic and prevents a thundering herd.
    jitter = int(hashlib.sha256(
        f"{message_id}:{attempt_number}".encode("ascii")
    ).hexdigest()[:4], 16) % max(1, base // 5)
    return base + jitter


def _stamp_table_ready(db, row, when: datetime) -> bool:
    # Generational waitlist delivery state lives exclusively in the outbox.
    # Finalization intentionally never writes the owner: reservation mutations
    # lock day/owner before outbox, so an outbox->owner write would invert order.
    return False


def finalize_claim(claim: ClaimedMessage, result, *, now: Optional[datetime] = None) -> bool:
    effective_now = _now(now)
    db = SessionLocal()
    try:
        _begin_worker_write(db)
        query = db.query(models.RezerwacjaWiadomoscOutbox).filter_by(id=claim.id)
        if db.get_bind().dialect.name == "postgresql":
            query = query.with_for_update()
        row = query.first()
        if (
            row is None
            or row.stan != "processing"
            or row.lease_token != claim.lease_token
        ):
            db.rollback()
            return False
        attempt = db.query(models.RezerwacjaWiadomoscProba).filter_by(
            wiadomosc_id=row.id,
            numer=claim.attempt_number,
            lease_token=claim.lease_token,
        ).one()
        if attempt.wynik != "processing":
            db.rollback()
            return False
        outcome = result.outcome
        attempt.finished_at = effective_now
        attempt.error_code = result.code
        attempt.provider_message_id = result.provider_message_id
        attempt.status_code = result.status_code
        relevance_error = _retry_relevance_error(db, row, now=effective_now)
        waitlist_relevance_error = (
            relevance_error if row.waitlist_id is not None else None
        )

        if outcome == "sent" and waitlist_relevance_error is not None:
            # The provider truth remains "sent", but the owner changed while I/O
            # was in flight. Keep a durable operator-visible fence: the guest may
            # have received a table-ready message for a withdrawn/terminal offer.
            attempt.wynik = "sent"
            row.stan = "uncertain"
            row.sent_at = effective_now
            row.uncertain_at = effective_now
            row.last_error_code = WAITLIST_STALE_DELIVERED_CODE
            db.add(models.AuditLog(
                ts=effective_now,
                user_id=None,
                login=None,
                akcja="waitlist_stale_delivery_detected",
                zasob=f"message:{row.id}",
                szczegoly=reservation_service.canonical_json({
                    "waitlist_id": row.waitlist_id,
                    "relevance_error": waitlist_relevance_error,
                    "provider_outcome": "sent",
                }),
            ))
        elif outcome == "sent":
            attempt.wynik = "sent"
            row.stan = "sent"
            row.sent_at = effective_now
            row.last_error_code = None
            _stamp_table_ready(db, row, effective_now)
        elif (
            outcome == "retry"
            and relevance_error is not None
        ):
            _cancel_stale_retry(
                row, attempt, code=relevance_error, now=effective_now,
            )
        elif outcome == "retry" and row.liczba_prob < row.maks_prob:
            retry_at = effective_now + timedelta(
                seconds=backoff_seconds(row.id, row.liczba_prob),
            )
            if retry_at < row.expires_at:
                attempt.wynik = "retry"
                attempt.retry_at = retry_at
                row.stan = "retry"
                row.available_at = retry_at
                row.last_error_code = result.code
            else:
                attempt.wynik = "failed"
                row.stan = "expired"
                row.last_error_code = "MESSAGE_EXPIRED_BEFORE_RETRY"
        elif outcome == "uncertain":
            attempt.wynik = "uncertain"
            row.stan = "uncertain"
            row.uncertain_at = effective_now
            row.last_error_code = (
                WAITLIST_SUPERSEDED_UNCERTAIN_CODE
                if waitlist_relevance_error is not None
                else result.code
            )
        elif waitlist_relevance_error is not None:
            # A deterministic provider failure after the offer stopped being
            # current needs no operator action and must not become a permanent
            # terminal-inbox alert.
            attempt.wynik = "failed"
            row.stan = "cancelled"
            row.last_error_code = WAITLIST_SUPERSEDED_NOT_SENT_CODE
        else:
            attempt.wynik = "failed"
            row.stan = "failed"
            row.last_error_code = result.code or "DELIVERY_FAILED"

        row.lease_token = None
        row.lease_expires_at = None
        row.updated_at = effective_now
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def deliver_claim(claim: ClaimedMessage):
    from delivery_result import DeliveryResult

    try:
        if claim.channel == "email":
            return mailer.dostarcz_email(
                claim.recipient,
                claim.subject or "",
                claim.body,
                idempotency_key=claim.provider_idempotency_key,
            )
        return sms.dostarcz_sms(
            claim.recipient,
            claim.body,
            idempotency_key=claim.provider_idempotency_key,
            force_supports_idempotency=claim.provider_supports_idempotency,
            force_idempotency_header=claim.provider_idempotency_header,
        )
    except Exception as exc:
        # Tekst wyjątku providera może zawierać odbiorcę albo fragment wiadomości.
        # Logujemy tylko nazwę klasy, bez tracebacku i treści wyjątku.
        logger.error(
            "Provider wiadomości R5b zwrócił nieobsłużony błąd (%s).",
            type(exc).__name__,
        )
        return DeliveryResult(
            outcome=("retry" if claim.provider_supports_idempotency else "uncertain"),
            code="PROVIDER_UNHANDLED_EXCEPTION",
        )


def run_delivery_once(*, limit: int = 20) -> dict:
    sent = retry = failed = uncertain = 0
    processed = 0
    for _ in range(max(0, limit)):
        claim = claim_next()
        if claim is None:
            break
        started = mark_claim_started(claim)
        if started is None:
            continue
        result = deliver_claim(started)
        finalize_claim(started, result)
        processed += 1
        if result.outcome == "sent":
            sent += 1
        elif result.outcome == "retry":
            retry += 1
        elif result.outcome == "uncertain":
            uncertain += 1
        else:
            failed += 1
    return {
        "processed": processed,
        "sent": sent,
        "retry": retry,
        "failed": failed,
        "uncertain": uncertain,
    }


def run_waitlist_expiry_once(*, now: Optional[datetime] = None) -> int:
    """Expire offered inventory under the same ordered day locks as writers."""
    effective_now = _now(now)
    db = SessionLocal()
    try:
        dates = {
            value for (value,) in db.query(models.ListaOczekujacych.data).filter(
                models.ListaOczekujacych.status == "zaoferowano",
                models.ListaOczekujacych.hold_do <= effective_now,
            ).all()
        }
        dates.update(
            value for (value,) in db.query(models.RezerwacjaPublicznyHold.data).filter(
                models.RezerwacjaPublicznyHold.state == "active",
                models.RezerwacjaPublicznyHold.expires_at <= effective_now,
            ).all()
        )
        if not dates:
            db.rollback()
            return 0

        guards = reservation_service.begin_locked_write(db, dates)
        # Re-evaluate after acquiring every day anchor; the candidate scan above
        # was deliberately advisory and may have raced with acceptance/release.
        waitlist_count = db.query(models.ListaOczekujacych.id).filter(
            models.ListaOczekujacych.data.in_(dates),
            models.ListaOczekujacych.status == "zaoferowano",
            models.ListaOczekujacych.hold_do <= effective_now,
        ).count()
        public_count = db.query(models.RezerwacjaPublicznyHold.id).filter(
            models.RezerwacjaPublicznyHold.data.in_(dates),
            models.RezerwacjaPublicznyHold.state == "active",
            models.RezerwacjaPublicznyHold.expires_at <= effective_now,
        ).count()
        if not waitlist_count and not public_count:
            db.rollback()
            return 0
        reservation_service.cleanup_expired_holds(
            db, effective_now, dates=dates,
        )
        reservation_service.touch_days(guards)
        db.commit()
        return int(waitlist_count + public_count)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def run_communication_once(*, delivery_limit: int = 20) -> dict:
    expired_offers = run_waitlist_expiry_once()
    db = SessionLocal()
    try:
        _begin_worker_write(db)
        planner_locked = True
        if db.get_bind().dialect.name == "postgresql":
            planner_locked = bool(db.execute(
                text("SELECT pg_try_advisory_xact_lock(:lock_id)"),
                {"lock_id": _PLANNER_LOCK_ID},
            ).scalar())
        reminders = reconcile_reminder_schedule(db) if planner_locked else 0
        db.commit() if planner_locked else db.rollback()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return {
        "expired_offers": expired_offers,
        "reminders": reminders,
        **run_delivery_once(limit=delivery_limit),
    }


def _mask_recipient(channel: str, value: str) -> str:
    if channel == "email" and "@" in value:
        local, domain = value.split("@", 1)
        return f"{local[:1] or '*'}***@{domain}"
    digits = "".join(character for character in value if character.isdigit())
    return f"***{digits[-3:]}" if digits else "***"


def message_dict(
    row,
    *,
    attempts=(),
    retry_allowed: bool = False,
    attention_required: Optional[bool] = None,
) -> dict:
    effective_attention = (
        row.stan in ATTENTION_STATES
        if attention_required is None
        else bool(attention_required)
    )
    return {
        "id": row.id,
        "event": row.typ_zdarzenia,
        "event_label": EVENT_LABELS.get(row.typ_zdarzenia, row.typ_zdarzenia),
        "channel": row.kanal,
        "recipient": _mask_recipient(row.kanal, row.odbiorca),
        "state": row.stan,
        "attention_required": effective_attention,
        "attempt_count": row.liczba_prob,
        "max_attempts": row.maks_prob,
        "available_at": row.available_at.isoformat() if row.available_at else None,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "sent_at": row.sent_at.isoformat() if row.sent_at else None,
        "uncertain_at": row.uncertain_at.isoformat() if row.uncertain_at else None,
        "reconciled_at": row.reconciled_at.isoformat() if row.reconciled_at else None,
        "reconciled_by_user_id": row.reconciled_by_user_id,
        "reconciliation_note": row.reconciliation_note,
        "last_error_code": row.last_error_code,
        "retry_allowed": bool(retry_allowed),
        "attempts": [
            {
                "number": attempt.numer,
                "state": attempt.wynik,
                "claimed_at": attempt.claimed_at.isoformat() if attempt.claimed_at else None,
                "started_at": attempt.started_at.isoformat() if attempt.started_at else None,
                "finished_at": attempt.finished_at.isoformat() if attempt.finished_at else None,
                "retry_at": attempt.retry_at.isoformat() if attempt.retry_at else None,
                "error_code": attempt.error_code,
                "status_code": attempt.status_code,
            }
            for attempt in attempts
        ],
    }


def reservation_history(db, reservation_id: int) -> list[dict]:
    rows = db.query(models.RezerwacjaWiadomoscOutbox).filter_by(
        termin_id=reservation_id,
    ).order_by(
        models.RezerwacjaWiadomoscOutbox.created_at.desc(),
        models.RezerwacjaWiadomoscOutbox.id.desc(),
    ).all()
    attempts_by_message = {}
    if rows:
        attempts = db.query(models.RezerwacjaWiadomoscProba).filter(
            models.RezerwacjaWiadomoscProba.wiadomosc_id.in_([row.id for row in rows]),
        ).order_by(
            models.RezerwacjaWiadomoscProba.wiadomosc_id,
            models.RezerwacjaWiadomoscProba.numer,
        ).all()
        for attempt in attempts:
            attempts_by_message.setdefault(attempt.wiadomosc_id, []).append(attempt)
    effective_now = _now()
    return [
        message_dict(
            row,
            attempts=attempts_by_message.get(row.id, ()),
            retry_allowed=bool(
                row.stan in {"failed", "uncertain"}
                and row.expires_at > effective_now
                and _retry_relevance_error(db, row) is None
            ),
        )
        for row in rows
    ]


def waitlist_history(
    db,
    waitlist_id: int,
    *,
    now: Optional[datetime] = None,
) -> list[dict]:
    rows = db.query(models.RezerwacjaWiadomoscOutbox).filter_by(
        waitlist_id=waitlist_id,
    ).order_by(
        models.RezerwacjaWiadomoscOutbox.created_at.desc(),
        models.RezerwacjaWiadomoscOutbox.id.desc(),
    ).all()
    attempts_by_message = {}
    if rows:
        attempts = db.query(models.RezerwacjaWiadomoscProba).filter(
            models.RezerwacjaWiadomoscProba.wiadomosc_id.in_([row.id for row in rows]),
        ).order_by(
            models.RezerwacjaWiadomoscProba.wiadomosc_id,
            models.RezerwacjaWiadomoscProba.numer,
        ).all()
        for attempt in attempts:
            attempts_by_message.setdefault(attempt.wiadomosc_id, []).append(attempt)
    effective_now = _now(now)
    owner = db.get(models.ListaOczekujacych, waitlist_id)
    terminal_waitlist = bool(
        owner is not None
        and owner.status in reservation_service.WAITLIST_TERMINAL_STATUSES
    )
    return [
        message_dict(
            row,
            attempts=attempts_by_message.get(row.id, ()),
            retry_allowed=bool(
                row.stan in {"failed", "uncertain"}
                and row.expires_at > effective_now
                and _retry_relevance_error(db, row, now=effective_now) is None
            ),
            attention_required=(
                row.stan == "uncertain" if terminal_waitlist else None
            ),
        )
        for row in rows
    ]


def current_confirmation_state(db, reservation_id: int) -> Optional[str]:
    """Return the delivery state that must govern a manual confirmation request.

    Only the latest, still-relevant confirmation generation is considered.  This
    lets an operator send a fresh confirmation after a reservation edit while
    preventing two browser tabs from creating parallel deliveries for the same
    current snapshot.
    """
    rows = db.query(models.RezerwacjaWiadomoscOutbox).filter(
        models.RezerwacjaWiadomoscOutbox.termin_id == reservation_id,
        models.RezerwacjaWiadomoscOutbox.typ_zdarzenia == "confirmation",
        models.RezerwacjaWiadomoscOutbox.stan != "cancelled",
    ).order_by(models.RezerwacjaWiadomoscOutbox.id.desc()).all()
    current = [row for row in rows if _retry_relevance_error(db, row) is None]
    states = {row.stan for row in current}
    # A mixed two-channel group follows the safest outstanding state.  In
    # particular, one delivered channel plus one failed channel must use Retry,
    # not create a duplicate for the channel that already succeeded.
    for state in ("processing", "queued", "retry", "uncertain", "failed", "sent"):
        if state in states:
            return state
    # Expired delivery never reached an ambiguous provider state and cannot be
    # retried through the generic endpoint, so a new, confirmed queue is safe.
    return "expired" if "expired" in states else None


def _summary_for_messages(
    messages,
    *,
    terminal_waitlist: bool = False,
) -> Optional[dict]:
    if not messages:
        return None
    attention_states = {"uncertain"} if terminal_waitlist else set(ATTENTION_STATES)
    attention = [row for row in messages if row.stan in attention_states]
    pending = [
        row for row in messages
        if row.stan in {"processing", "retry", "queued"}
    ]
    selected = (attention or pending or messages)[-1]
    selected_group = [
        row for row in messages
        if row.dedupe_key == selected.dedupe_key
        and row.typ_zdarzenia == selected.typ_zdarzenia
    ]
    selected_channels = {row.kanal for row in selected_group}
    selected_channel = (
        "oba" if selected_channels == {"email", "sms"} else selected.kanal
    )
    next_attempts = [
        row.available_at
        for row in pending
        if row.stan in PENDING_STATES and row.available_at is not None
    ]
    return {
        "message_id": selected.id,
        "state": selected.stan,
        "attention_required": bool(attention),
        "attention_count": len(attention),
        "pending_count": len(pending),
        "channel": selected_channel,
        "event": selected.typ_zdarzenia,
        "last_event_at": selected.updated_at.isoformat() if selected.updated_at else None,
        "next_attempt_at": min(next_attempts).isoformat() if next_attempts else None,
        "legacy_delivery": False,
    }


def summaries_for_reservations(db, reservation_ids: Iterable[int]) -> dict[int, dict]:
    ids = {int(value) for value in reservation_ids if value is not None}
    if not ids:
        return {}
    rows = db.query(models.RezerwacjaWiadomoscOutbox).filter(
        models.RezerwacjaWiadomoscOutbox.termin_id.in_(ids),
        models.RezerwacjaWiadomoscOutbox.stan != "cancelled",
    ).order_by(
        models.RezerwacjaWiadomoscOutbox.created_at,
        models.RezerwacjaWiadomoscOutbox.id,
    ).all()
    grouped = {reservation_id: [] for reservation_id in ids}
    for row in rows:
        grouped.setdefault(row.termin_id, []).append(row)
    output = {}
    for reservation_id, messages in grouped.items():
        output[reservation_id] = _summary_for_messages(messages)
    return output


def summaries_for_waitlists(db, waitlist_ids: Iterable[int]) -> dict[int, dict]:
    ids = {int(value) for value in waitlist_ids if value is not None}
    if not ids:
        return {}
    owners = db.query(models.ListaOczekujacych).filter(
        models.ListaOczekujacych.id.in_(ids),
    ).all()
    owners_by_id = {owner.id: owner for owner in owners}
    offered_ids = {owner.id for owner in owners if owner.status == "zaoferowano"}
    current_offer_dedupe = {
        owner.id: current_waitlist_offer_dedupe(owner)
        for owner in owners
        if owner.status == "zaoferowano" and owner.offer_key_hash
    }
    rows = db.query(models.RezerwacjaWiadomoscOutbox).filter(
        models.RezerwacjaWiadomoscOutbox.waitlist_id.in_(ids),
        models.RezerwacjaWiadomoscOutbox.stan != "cancelled",
    ).order_by(
        models.RezerwacjaWiadomoscOutbox.created_at,
        models.RezerwacjaWiadomoscOutbox.id,
    ).all()
    grouped = {waitlist_id: [] for waitlist_id in ids}
    for row in rows:
        expected_dedupe = current_offer_dedupe.get(row.waitlist_id)
        if (
            row.waitlist_id in offered_ids
            and row.dedupe_key != expected_dedupe
            and row.stan != "uncertain"
        ):
            continue
        grouped.setdefault(row.waitlist_id, []).append(row)
    output = {
        waitlist_id: _summary_for_messages(
            messages,
            terminal_waitlist=bool(
                owners_by_id.get(waitlist_id) is not None
                and owners_by_id[waitlist_id].status
                in reservation_service.WAITLIST_TERMINAL_STATUSES
            ),
        )
        for waitlist_id, messages in grouped.items()
    }
    legacy_ids = [waitlist_id for waitlist_id, summary in output.items() if summary is None]
    if legacy_ids:
        legacy_rows = db.query(models.ListaOczekujacych).filter(
            models.ListaOczekujacych.id.in_(legacy_ids),
            models.ListaOczekujacych.status != "zaoferowano",
            models.ListaOczekujacych.powiadomiono_at.isnot(None),
        ).all()
        for row in legacy_rows:
            output[row.id] = {
                "message_id": None,
                "state": "sent",
                "attention_required": False,
                "attention_count": 0,
                "pending_count": 0,
                "channel": None,
                "event": "table_ready",
                "last_event_at": row.powiadomiono_at.isoformat(),
                "next_attempt_at": None,
                "legacy_delivery": True,
            }
    return output


def lock_message(db, message_id: int):
    """Locks one message for operator retry/reconciliation or returns ``None``."""
    _begin_worker_write(db)
    query = db.query(models.RezerwacjaWiadomoscOutbox).filter_by(id=message_id)
    if db.get_bind().dialect.name == "postgresql":
        query = query.with_for_update()
    return query.first()


def _retry_relevance_error(
    db,
    message,
    *,
    now: Optional[datetime] = None,
) -> Optional[str]:
    effective_now = _now(now)
    if message.termin_id is not None:
        owner = db.get(models.Termin, message.termin_id)
        if owner is None or owner.rodzaj != "stolik":
            return "MESSAGE_OWNER_MISSING"
        if message.typ_zdarzenia == "cancellation":
            if owner.status != "odwolana":
                return "MESSAGE_OWNER_NOT_CURRENT"
        elif owner.status not in ACTIVE_RESERVATION_STATES:
            return "MESSAGE_OWNER_NOT_CURRENT"
        if (message.kanal, message.odbiorca) not in set(_channels(owner)):
            return "MESSAGE_SUPERSEDED"
        if message.typ_zdarzenia == "reminder":
            cfg = db.get(models.LokalConfig, 1)
            if cfg is None or int(cfg.rezerwacje_przypomnienie_h or 0) <= 0:
                return "MESSAGE_OWNER_NOT_CURRENT"

        latest_event = db.query(models.RezerwacjaWiadomoscOutbox).filter(
            models.RezerwacjaWiadomoscOutbox.termin_id == owner.id,
            models.RezerwacjaWiadomoscOutbox.typ_zdarzenia == message.typ_zdarzenia,
        ).order_by(models.RezerwacjaWiadomoscOutbox.id.desc()).first()
        if latest_event is None or latest_event.dedupe_key != message.dedupe_key:
            return "MESSAGE_SUPERSEDED"

        latest_change = db.query(models.RezerwacjaWiadomoscOutbox).filter(
            models.RezerwacjaWiadomoscOutbox.termin_id == owner.id,
            models.RezerwacjaWiadomoscOutbox.typ_zdarzenia == "change",
        ).order_by(models.RezerwacjaWiadomoscOutbox.id.desc()).first()
        if message.typ_zdarzenia in {"confirmation", "reminder"} and (
            latest_change is not None and message.id <= latest_change.id
        ):
            return "MESSAGE_SUPERSEDED"
        if message.typ_zdarzenia == "change" and (
            latest_change is None or latest_change.dedupe_key != message.dedupe_key
        ):
            return "MESSAGE_SUPERSEDED"
        return None

    owner = db.get(models.ListaOczekujacych, message.waitlist_id)
    if owner is None:
        return "MESSAGE_OWNER_MISSING"
    if owner.status != "zaoferowano" or message.typ_zdarzenia != "table_ready":
        return "MESSAGE_OWNER_NOT_CURRENT"
    if (
        owner.hold_do is None
        or owner.oferta_wygasa_at is None
        or owner.hold_do != owner.oferta_wygasa_at
        or owner.hold_do <= effective_now
    ):
        return "MESSAGE_OWNER_NOT_CURRENT"
    if (message.kanal, message.odbiorca) not in set(_channels(owner)):
        return "MESSAGE_SUPERSEDED"
    current_dedupe = current_waitlist_offer_dedupe(owner)
    if current_dedupe is None or not secrets.compare_digest(
        current_dedupe, message.dedupe_key,
    ):
        return "MESSAGE_SUPERSEDED"
    return None


def retry_failed(db, message, *, actor, now: Optional[datetime] = None) -> None:
    effective_now = _now(now)
    if message.expires_at <= effective_now:
        raise ValueError("MESSAGE_EXPIRED")
    relevance_error = _retry_relevance_error(
        db, message, now=effective_now,
    )
    if relevance_error:
        raise ValueError(relevance_error)
    if message.stan == "uncertain":
        raise ValueError("UNCERTAIN_REQUIRES_RECONCILIATION")
    if message.stan != "failed":
        raise ValueError("MESSAGE_NOT_FAILED")
    message.stan = "queued"
    message.available_at = effective_now
    message.maks_prob = max(message.maks_prob, message.liczba_prob + 3)
    message.last_error_code = None
    message.updated_at = effective_now


def reconcile_uncertain(
    db,
    message,
    *,
    outcome: str,
    note: str,
    actor,
    now: Optional[datetime] = None,
) -> None:
    if message.stan != "uncertain":
        raise ValueError("MESSAGE_NOT_UNCERTAIN")
    if outcome not in {"sent", "failed", "retry"}:
        raise ValueError("INVALID_RECONCILIATION")
    effective_now = _now(now)
    stale_delivered = (
        message.waitlist_id is not None
        and message.sent_at is not None
        and message.last_error_code == WAITLIST_STALE_DELIVERED_CODE
    )
    if stale_delivered and outcome != "sent":
        raise ValueError("STALE_DELIVERY_REQUIRES_ACKNOWLEDGEMENT")
    waitlist_relevance_error = (
        _retry_relevance_error(db, message, now=effective_now)
        if message.waitlist_id is not None
        else None
    )
    if outcome == "retry" and message.expires_at <= effective_now:
        raise ValueError("MESSAGE_EXPIRED")
    if outcome == "retry":
        if waitlist_relevance_error:
            raise ValueError(waitlist_relevance_error)
        relevance_error = _retry_relevance_error(db, message, now=effective_now)
        if relevance_error:
            raise ValueError(relevance_error)
    message.reconciled_at = effective_now
    message.reconciled_by_user_id = getattr(actor, "id", None)
    message.reconciliation_note = note.strip()
    message.updated_at = effective_now
    if outcome == "sent":
        message.stan = "sent"
        # A stale-delivered acknowledgement closes the alert without rewriting
        # the actual provider delivery timestamp.
        message.sent_at = message.sent_at or effective_now
        message.last_error_code = None
        _stamp_table_ready(db, message, effective_now)
    elif outcome == "failed":
        if waitlist_relevance_error is not None:
            message.stan = "cancelled"
            message.last_error_code = WAITLIST_SUPERSEDED_NOT_SENT_CODE
        else:
            message.stan = "failed"
            message.last_error_code = "RECONCILED_NOT_SENT"
    else:
        # This is the only path that retries an ambiguous non-idempotent attempt:
        # the operator has explicitly acknowledged the possible duplicate.
        message.stan = "retry"
        message.available_at = effective_now
        message.maks_prob = max(message.maks_prob, message.liczba_prob + 3)
        message.last_error_code = "RECONCILED_RETRY_APPROVED"


def _interval_seconds() -> int:
    try:
        configured = int(os.environ.get("RESERVATION_DELIVERY_INTERVAL_SECONDS", "5"))
    except (TypeError, ValueError):
        configured = 5
    return max(1, configured)


def _uses_ephemeral_sqlite() -> bool:
    bind = SessionLocal.kw.get("bind")
    return bool(
        bind is not None
        and bind.dialect.name == "sqlite"
        and not bind.url.database
    )


def _run_safely() -> None:
    try:
        run_communication_once()
    except Exception:
        logger.exception("Worker komunikacji rezerwacji nie zakończył przebiegu.")


def _worker_loop() -> None:
    while not _stop_event.is_set():
        _run_safely()
        if _stop_event.wait(_interval_seconds()):
            return


def start_worker() -> None:
    global _thread
    with _state_lock:
        if _thread is not None and _thread.is_alive():
            return
        if _uses_ephemeral_sqlite():
            return
        _stop_event.clear()
        _thread = threading.Thread(
            target=_worker_loop,
            name="lokalo-reservation-delivery",
            daemon=True,
        )
        _thread.start()


def worker_running() -> bool:
    """Return the delivery-loop liveness without exposing mutable worker state."""
    with _state_lock:
        return bool(_thread is not None and _thread.is_alive())


def stop_worker() -> None:
    global _thread
    with _state_lock:
        thread = _thread
        _stop_event.set()
    if thread is not None:
        thread.join(timeout=2)
    with _state_lock:
        if _thread is thread and (thread is None or not thread.is_alive()):
            _thread = None
