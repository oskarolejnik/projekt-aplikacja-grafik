"""Atomowy ledger dostępności rezerwacji stolikowych (R0b).

Routery nadal odpowiadają za politykę kanału i kształt odpowiedzi HTTP. Ten moduł
jest jedynym miejscem, które zajmuje lub zwalnia fizyczne zasoby i pacing.
Każda mutacja musi najpierw wywołać :func:`begin_locked_write`, a następnie wykonać
co najwyżej jeden commit obejmujący ``Termin`` i jego ledger.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import delete, insert, or_, select, update
from sqlalchemy.exc import IntegrityError, OperationalError

import models


ACTIVE_STATUSES = frozenset({"rezerwacja", "potwierdzona"})
IDEMPOTENCY_TTL_DAYS = 30


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass(frozen=True)
class AvailabilityResult:
    available: bool
    code: str | None = None
    rule: str | None = None
    message: str | None = None
    candidates: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    alternatives: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "code": self.code,
            "rule": self.rule,
            "candidates": list(self.candidates),
            "alternatives": list(self.alternatives),
        }


class ReservationError(Exception):
    """Błąd domenowy z kompatybilnym komunikatem i stabilnym kodem maszynowym."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        rule: str | None = None,
        candidates: Sequence[Mapping[str, Any]] = (),
        alternatives: Sequence[Mapping[str, Any]] = (),
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.availability = AvailabilityResult(
            available=False,
            code=code,
            rule=rule,
            message=message,
            candidates=tuple(dict(item) for item in candidates),
            alternatives=tuple(dict(item) for item in alternatives),
        )


@dataclass(frozen=True)
class IdempotencyDecision:
    record: models.RezerwacjaIdempotencja | None
    replayed: bool = False
    response: dict[str, Any] | None = None
    http_status: int | None = None


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    raise TypeError(f"unsupported canonical JSON type: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )


def request_fingerprint(operation: str, payload: Any, secret: str) -> str:
    body = canonical_json({"operation": operation, "payload": payload}).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _normalise_idempotency_key(raw_key: str | None) -> str | None:
    if raw_key is None:
        return None
    key = raw_key.strip()
    if not key:
        return None
    if len(key) > 128 or any(ord(char) < 33 or ord(char) > 126 for char in key):
        raise ReservationError(
            400,
            "INVALID_IDEMPOTENCY_KEY",
            "Klucz idempotencji musi mieć 1–128 drukowalnych znaków ASCII.",
            rule="idempotency",
        )
    return key


def begin_idempotency(
    db,
    *,
    operation: str,
    raw_key: str | None,
    payload: Any,
    secret: str,
    now: datetime,
) -> IdempotencyDecision:
    """Rejestruje próbę lub zwraca zaszyfrowany wynik wcześniejszego sukcesu.

    Wywołujący musi już posiadać blokadę dnia. W bazie trafia wyłącznie hash klucza
    i HMAC treści; PII z payloadu nie jest możliwe do odtworzenia z tych pól.
    """

    key = _normalise_idempotency_key(raw_key)
    if key is None:
        return IdempotencyDecision(record=None)
    operation = operation.strip()
    if not operation or len(operation) > 64:
        raise ValueError("idempotency operation must have 1-64 characters")
    key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
    fingerprint = request_fingerprint(operation, payload, secret)
    db.execute(
        delete(models.RezerwacjaIdempotencja).where(
            models.RezerwacjaIdempotencja.expires_at <= now,
        )
    )
    existing = db.execute(
        select(models.RezerwacjaIdempotencja).where(
            models.RezerwacjaIdempotencja.operation == operation,
            models.RezerwacjaIdempotencja.key_hash == key_hash,
        )
    ).scalar_one_or_none()
    if existing is not None:
        if not hmac.compare_digest(existing.request_fingerprint, fingerprint):
            raise ReservationError(
                409,
                "IDEMPOTENCY_KEY_REUSED",
                "Ten klucz idempotencji został już użyty z inną treścią żądania.",
                rule="idempotency",
            )
        if existing.status == "succeeded" and existing.response_enc:
            try:
                response = json.loads(existing.response_enc)
            except (TypeError, ValueError) as exc:
                raise ReservationError(
                    503,
                    "RESERVATION_BUSY",
                    "Zapisany wynik żądania jest chwilowo niedostępny. Spróbuj ponownie.",
                    rule="idempotency",
                ) from exc
            return IdempotencyDecision(
                record=existing,
                replayed=True,
                response=response,
                http_status=existing.http_status,
            )
        raise ReservationError(
            409,
            "IDEMPOTENCY_IN_PROGRESS",
            "Identyczne żądanie jest już przetwarzane. Spróbuj ponownie za chwilę.",
            rule="idempotency",
        )
    record = models.RezerwacjaIdempotencja(
        operation=operation,
        key_hash=key_hash,
        request_fingerprint=fingerprint,
        status="processing",
        created_at=now,
        expires_at=now + timedelta(days=IDEMPOTENCY_TTL_DAYS),
    )
    db.add(record)
    db.flush()
    return IdempotencyDecision(record=record)


def complete_idempotency(
    record: models.RezerwacjaIdempotencja | None,
    *,
    response: Mapping[str, Any],
    http_status: int,
    termin_id: int | None,
    now: datetime,
) -> None:
    if record is None:
        return
    record.status = "succeeded"
    record.http_status = int(http_status)
    record.response_enc = canonical_json(dict(response))
    record.termin_id = termin_id
    record.completed_at = now


def _dialect_name(db) -> str:
    return db.get_bind().dialect.name


def begin_floor_plan_write(db) -> None:
    """Serializuje publikację planu z zapisami rezerwacji na SQLite.

    PostgreSQL synchronizuje się później na tych samych wierszach ``stoliki``
    co rezerwacje i holdy. SQLite nie ma ``FOR UPDATE``, więc publikacja musi
    zdobyć blokadę zapisu przed pierwszym odczytem walidacyjnym.
    """
    if _dialect_name(db) != "sqlite":
        return
    db.rollback()
    try:
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    except OperationalError as exc:
        db.rollback()
        raise ReservationError(
            503,
            "RESERVATION_BUSY",
            "Inna zmiana rezerwacji jest w toku. Spróbuj ponownie za chwilę.",
            rule="transaction",
        ) from exc


def lock_tables(db, table_ids: Iterable[int]) -> tuple[models.Stolik, ...]:
    """Zwraca stabilnie posortowane stoły i blokuje je na PostgreSQL."""
    ids = tuple(sorted({int(value) for value in table_ids if value is not None}))
    if not ids:
        return ()
    statement = (
        select(models.Stolik)
        .where(models.Stolik.id.in_(ids))
        .order_by(models.Stolik.id)
        .execution_options(populate_existing=True)
    )
    if _dialect_name(db) == "postgresql":
        statement = statement.with_for_update()
    return tuple(db.execute(statement).scalars().all())


def begin_locked_write(db, dates: Iterable[date]) -> tuple[models.RezerwacjaDzienLedger, ...]:
    """Rozpoczyna świeżą transakcję zapisu i blokuje dni w kolejności rosnącej.

    SQLite nie implementuje ``FOR UPDATE``; ``BEGIN IMMEDIATE`` zdobywa jedyną
    blokadę zapisu przed pierwszym odczytem walidacyjnym. PostgreSQL blokuje trwałe
    wiersze-anchor przez ``SELECT FOR UPDATE``. Wywołujący wykonuje commit/rollback.
    """

    ordered = tuple(sorted(set(dates)))
    if not ordered:
        raise ValueError("at least one reservation date is required")
    db.rollback()
    dialect = _dialect_name(db)
    try:
        if dialect == "sqlite":
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")

        table = models.RezerwacjaDzienLedger.__table__
        locked_at = _utcnow_naive()
        if dialect == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as dialect_insert

            for day in ordered:
                db.execute(
                    dialect_insert(table)
                    .values(data=day, revision=0, updated_at=locked_at)
                    .on_conflict_do_nothing(index_elements=["data"])
                )
        elif dialect == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as dialect_insert

            for day in ordered:
                db.execute(
                    dialect_insert(table)
                    .values(data=day, revision=0, updated_at=locked_at)
                    .on_conflict_do_nothing(index_elements=["data"])
                )
        else:
            for day in ordered:
                if db.get(models.RezerwacjaDzienLedger, day) is None:
                    db.add(models.RezerwacjaDzienLedger(
                        data=day, revision=0, updated_at=locked_at,
                    ))
            db.flush()

        statement = (
            select(models.RezerwacjaDzienLedger)
            .where(models.RezerwacjaDzienLedger.data.in_(ordered))
            .order_by(models.RezerwacjaDzienLedger.data)
        )
        if dialect == "postgresql":
            statement = statement.with_for_update()
        guards = tuple(db.execute(statement).scalars().all())
    except OperationalError as exc:
        db.rollback()
        raise ReservationError(
            503,
            "RESERVATION_BUSY",
            "Inny zapis rezerwacji jest w toku. Spróbuj ponownie za chwilę.",
            rule="transaction",
        ) from exc
    if len(guards) != len(ordered):
        db.rollback()
        raise ReservationError(
            503,
            "RESERVATION_BUSY",
            "Nie udało się zablokować dnia rezerwacyjnego.",
            rule="transaction",
        )
    return guards


def touch_days(guards: Iterable[models.RezerwacjaDzienLedger]) -> None:
    now = _utcnow_naive()
    for guard in guards:
        guard.revision = int(guard.revision or 0) + 1
        guard.updated_at = now


def _minute(value: time, *, field_name: str) -> int:
    if value.tzinfo is not None or value.second or value.microsecond:
        raise ReservationError(
            400,
            "INVALID_RESERVATION_INTERVAL",
            f"{field_name} musi wskazywać pełną minutę czasu lokalnego.",
            rule="interval",
        )
    return value.hour * 60 + value.minute


def _interval(start: time, end: time) -> tuple[int, int]:
    start_minute = _minute(start, field_name="Godzina rozpoczęcia")
    end_minute = _minute(end, field_name="Godzina zakończenia")
    if end_minute <= start_minute:
        raise ReservationError(
            400,
            "INVALID_RESERVATION_INTERVAL",
            "Rezerwacja musi kończyć się po rozpoczęciu i nie może przechodzić przez północ.",
            rule="interval",
        )
    return start_minute, end_minute


def _active_hold_filter(now: datetime):
    claim = models.RezerwacjaStolikClaim
    return or_(claim.expires_at.is_(None), claim.expires_at > now)


def cleanup_expired_holds(db, now: datetime) -> int:
    db.execute(
        update(models.ListaOczekujacych)
        .where(models.ListaOczekujacych.hold_do <= now)
        .values(hold_stolik_id=None, hold_do=None)
    )
    result = db.execute(
        delete(models.RezerwacjaStolikClaim).where(
            models.RezerwacjaStolikClaim.waitlist_id.isnot(None),
            models.RezerwacjaStolikClaim.expires_at <= now,
        )
    )
    return int(result.rowcount or 0)


def occupied_table_ids(
    db,
    *,
    data: date,
    start: time,
    end: time,
    buffer_min: int = 0,
    exclude_termin_id: int | None = None,
    now: datetime | None = None,
) -> set[int]:
    start_minute, end_minute = _interval(start, end)
    buffer_min = max(0, int(buffer_min or 0))
    query_start = max(0, start_minute - buffer_min)
    query_end = min(1440, end_minute + buffer_min)
    claim = models.RezerwacjaStolikClaim
    statement = select(claim.stolik_id).where(
        claim.data == data,
        claim.minute >= query_start,
        claim.minute < query_end,
        _active_hold_filter(now or datetime.now()),
    )
    if exclude_termin_id is not None:
        statement = statement.where(
            or_(claim.termin_id.is_(None), claim.termin_id != exclude_termin_id)
        )
    return set(db.execute(statement).scalars().all())


def pacing_status(
    db,
    *,
    data: date,
    start: time,
    window_min: int,
    party_size: int,
    max_reservations: int | None,
    max_covers: int | None,
    exclude_termin_id: int | None = None,
) -> dict[str, Any]:
    start_minute = _minute(start, field_name="Godzina rozpoczęcia")
    window_min = max(1, int(window_min or 1))
    ledger = models.RezerwacjaPacingLedger
    statement = select(ledger).where(
        ledger.data == data,
        ledger.start_minute >= start_minute,
        ledger.start_minute < min(1440, start_minute + window_min),
    )
    if exclude_termin_id is not None:
        statement = statement.where(ledger.termin_id != exclude_termin_id)
    rows = db.execute(statement).scalars().all()
    reservations = len(rows)
    covers = sum(int(row.covers or 0) for row in rows)
    would_reservations = reservations + 1
    would_covers = covers + max(1, int(party_size or 1))
    reservation_full = bool(max_reservations and would_reservations > max_reservations)
    covers_full = bool(max_covers and would_covers > max_covers)
    return {
        "full": reservation_full or covers_full,
        "reservation_full": reservation_full,
        "covers_full": covers_full,
        "reservations": reservations,
        "covers": covers,
        "would_reservations": would_reservations,
        "would_covers": would_covers,
        "max_reservations": max_reservations,
        "max_covers": max_covers,
    }


def release_termin_allocation(db, termin_id: int) -> None:
    db.execute(
        delete(models.RezerwacjaStolikClaim).where(
            models.RezerwacjaStolikClaim.termin_id == termin_id
        )
    )
    db.execute(
        delete(models.RezerwacjaPacingLedger).where(
            models.RezerwacjaPacingLedger.termin_id == termin_id
        )
    )


def replace_termin_allocation(
    db,
    *,
    termin_id: int,
    data: date,
    start: time | None,
    end: time | None,
    table_ids: Iterable[int] = (),
    party_size: int = 1,
    buffer_min: int = 0,
    enforce_pacing: bool = False,
    max_reservations: int | None = None,
    max_covers: int | None = None,
    pacing_window_min: int = 1,
    override: bool = False,
    now: datetime | None = None,
    candidates: Sequence[Mapping[str, Any]] = (),
    alternatives: Sequence[Mapping[str, Any]] = (),
) -> AvailabilityResult:
    """Atomowo zastępuje wszystkie aktywne wpisy ledgera jednego ``Termin``.

    Funkcja nie wykonuje commita. Jeżeli późniejszy zapis się nie powiedzie, rollback
    przywraca stary przydział razem z jego claimami.
    """

    effective_now = now or datetime.now()
    cleanup_expired_holds(db, effective_now)
    release_termin_allocation(db, termin_id)
    if start is None:
        return AvailabilityResult(available=True)
    start_minute = _minute(start, field_name="Godzina rozpoczęcia")
    ids = tuple(sorted({int(value) for value in table_ids if value is not None}))
    interval: tuple[int, int] | None = None
    if ids:
        if end is None:
            raise ReservationError(
                400,
                "INVALID_RESERVATION_INTERVAL",
                "Przydział stołu wymaga godziny zakończenia.",
                rule="interval",
            )
        interval = _interval(start, end)
        occupied = occupied_table_ids(
            db,
            data=data,
            start=start,
            end=end,
            buffer_min=buffer_min,
            exclude_termin_id=termin_id,
            now=effective_now,
        )
        conflicts = sorted(set(ids) & occupied)
        if conflicts:
            raise ReservationError(
                409,
                "TABLE_CONFLICT",
                "Wybrany stolik jest już zajęty w tym czasie.",
                rule="table",
                candidates=candidates,
                alternatives=alternatives,
            )

    pacing = pacing_status(
        db,
        data=data,
        start=start,
        window_min=pacing_window_min,
        party_size=party_size,
        max_reservations=max_reservations,
        max_covers=max_covers,
        exclude_termin_id=termin_id,
    )
    if enforce_pacing and pacing["reservation_full"]:
        raise ReservationError(
            409,
            "PACING_RESERVATION_LIMIT",
            "Brak miejsc w wybranym czasie — osiągnięto limit nowych rezerwacji.",
            rule="pacing_reservations",
            candidates=candidates,
            alternatives=alternatives,
        )
    if enforce_pacing and pacing["covers_full"]:
        raise ReservationError(
            409,
            "PACING_COVERS_LIMIT",
            "Brak miejsc w wybranym czasie — osiągnięto limit nowych gości.",
            rule="pacing_covers",
            candidates=candidates,
            alternatives=alternatives,
        )

    db.add(
        models.RezerwacjaPacingLedger(
            termin_id=termin_id,
            data=data,
            start_minute=start_minute,
            covers=max(0, int(party_size or 0)),
            override=bool(override or (not enforce_pacing and pacing["full"])),
            created_at=_utcnow_naive(),
        )
    )
    if ids and interval is not None:
        start_raw, end_raw = interval
        created_at = _utcnow_naive()
        rows = [
            {
                "termin_id": termin_id,
                "waitlist_id": None,
                "stolik_id": table_id,
                "data": data,
                "minute": minute,
                "expires_at": None,
                "created_at": created_at,
            }
            for table_id in ids
            for minute in range(start_raw, end_raw)
        ]
        if rows:
            db.execute(insert(models.RezerwacjaStolikClaim), rows)
    return AvailabilityResult(
        available=True,
        candidates=tuple(dict(item) for item in candidates),
        alternatives=tuple(dict(item) for item in alternatives),
    )


def release_waitlist_hold(db, waitlist_id: int) -> None:
    db.execute(
        delete(models.RezerwacjaStolikClaim).where(
            models.RezerwacjaStolikClaim.waitlist_id == waitlist_id
        )
    )


def replace_waitlist_hold(
    db,
    *,
    waitlist_id: int,
    table_id: int,
    data: date,
    expires_at: datetime,
    now: datetime,
) -> None:
    cleanup_expired_holds(db, now)
    release_waitlist_hold(db, waitlist_id)
    claim = models.RezerwacjaStolikClaim
    conflict = db.execute(
        select(claim.id).where(
            claim.stolik_id == table_id,
            claim.data == data,
            _active_hold_filter(now),
            or_(claim.waitlist_id.is_(None), claim.waitlist_id != waitlist_id),
        ).limit(1)
    ).first()
    if conflict:
        raise ReservationError(
            409,
            "TABLE_CONFLICT",
            "Stolik jest już zajęty lub trzymany w tym dniu.",
            rule="table_hold",
        )
    created_at = _utcnow_naive()
    rows = [
        {
            "termin_id": None,
            "waitlist_id": waitlist_id,
            "stolik_id": int(table_id),
            "data": data,
            "minute": minute,
            "expires_at": expires_at,
            "created_at": created_at,
        }
        for minute in range(1440)
    ]
    db.execute(insert(models.RezerwacjaStolikClaim), rows)


def translate_integrity_error(exc: IntegrityError) -> ReservationError:
    text = str(getattr(exc, "orig", exc)).lower()
    if "rezerwacje_stolik_claim_slot" in text or (
        "stolik_id" in text and "minute" in text and "unique" in text
    ):
        return ReservationError(
            409,
            "TABLE_CONFLICT",
            "Wybrany stolik został właśnie zajęty. Wybierz inną propozycję.",
            rule="table",
        )
    if "rezerwacje_idempotencja" in text:
        return ReservationError(
            409,
            "IDEMPOTENCY_IN_PROGRESS",
            "Identyczne żądanie jest już przetwarzane. Spróbuj ponownie za chwilę.",
            rule="idempotency",
        )
    return ReservationError(
        503,
        "RESERVATION_BUSY",
        "Nie udało się bezpiecznie zatwierdzić rezerwacji. Spróbuj ponownie.",
        rule="transaction",
    )
