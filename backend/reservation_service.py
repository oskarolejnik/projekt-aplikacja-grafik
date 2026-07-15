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

from sqlalchemy import delete, func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError, OperationalError

import models


ACTIVE_STATUSES = frozenset({"rezerwacja", "potwierdzona"})
LIVE_HOST_PHASES = frozenset({"posadzony", "rachunek", "oplacony"})
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
    decision: str | None = None
    service: dict[str, Any] | None = None
    krok_slotu_min: int | None = None
    turn_time_min: int | None = None
    godz_do: str | None = None
    violations: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    checks: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    resource_allocation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "code": self.code,
            "rule": self.rule,
            "candidates": list(self.candidates),
            "alternatives": list(self.alternatives),
            "decision": self.decision,
            "service": self.service,
            "krok_slotu_min": self.krok_slotu_min,
            "turn_time_min": self.turn_time_min,
            "godz_do": self.godz_do,
            "violations": list(self.violations),
            "checks": list(self.checks),
            "resource_allocation": self.resource_allocation,
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
        decision: str | None = None,
        service: Mapping[str, Any] | None = None,
        krok_slotu_min: int | None = None,
        turn_time_min: int | None = None,
        godz_do: str | None = None,
        violations: Sequence[Mapping[str, Any]] = (),
        checks: Sequence[Mapping[str, Any]] = (),
        resource_allocation: str | None = None,
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
            decision=decision,
            service=dict(service) if service is not None else None,
            krok_slotu_min=krok_slotu_min,
            turn_time_min=turn_time_min,
            godz_do=godz_do,
            violations=tuple(dict(item) for item in violations),
            checks=tuple(dict(item) for item in checks),
            resource_allocation=resource_allocation,
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


def _projected_table_ids(primary: Any, additional: Any) -> set[int]:
    """Best-effort odczyt fizycznych stołów z kompatybilnej projekcji ``Termin``."""
    if isinstance(additional, str):
        try:
            additional = json.loads(additional)
        except (TypeError, ValueError):
            additional = ()
    values = [primary]
    if isinstance(additional, (list, tuple, set)):
        values.extend(additional)
    result = set()
    for value in values:
        if value is None or isinstance(value, bool):
            continue
        try:
            table_id = int(value)
        except (TypeError, ValueError):
            continue
        if table_id > 0:
            result.add(table_id)
    return result


def _configured_post_buffer_min(db, *, include_r3: bool = True) -> int:
    """Konserwatywny fallback dla claimów utworzonych przed materializacją R4.

    Stary ``Termin`` nie przechowuje rozstrzygniętej reguły bufora. W takim
    przypadku bezpieczniej jest użyć największej skonfigurowanej wartości niż
    przedwcześnie sprzedać zasób. ``include_r3=False`` pozostaje wyłącznie
    adapterem odbudowy schematu sprzed migracji 0059, gdzie tabele i kolumny R3
    jeszcze nie istnieją.
    """
    values = [db.query(models.LokalConfig.rez_bufor_min).limit(1).scalar()]
    if include_r3:
        values.extend((
            db.execute(
                select(func.max(models.SalaRezerwacyjna.domyslny_bufor_min))
            ).scalar_one_or_none(),
            db.execute(
                select(func.max(models.RegulaDostepnosciRezerwacji.bufor_min))
            ).scalar_one_or_none(),
        ))
    return max(0, *(int(value or 0) for value in values))


def cleanup_expired_holds(db, now: datetime) -> int:
    db.execute(
        update(models.ListaOczekujacych)
        .where(models.ListaOczekujacych.hold_do <= now)
        .values(
            hold_stolik_id=None,
            hold_stoliki_dodatkowe=None,
            hold_godz_od=None,
            hold_godz_do=None,
            hold_bufor_min=None,
            hold_do=None,
        )
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
    include_r3_buffers: bool = True,
) -> set[int]:
    """Zwraca zasoby kolidujące z proponowanym przedziałem.

    ``buffer_min`` jest buforem *po* wizycie. Trwałe claimy nowych alokacji już
    zawierają własny bufor, a tutaj rozszerzamy wyłącznie koniec propozycji. Dzięki
    temu wynik nie zależy od kolejności utworzenia dwóch rezerwacji i bufor nie jest
    naliczany podwójnie.

    Aktywny obrót hosta jest konserwatywną blokadą live: dopóki gość nie wyjdzie,
    jego wszystkie stoły pozostają zajęte także po planowanym ``godz_do``.
    """
    start_minute, end_minute = _interval(start, end)
    buffer_min = max(0, int(buffer_min or 0))
    query_start = start_minute
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
    occupied = set(db.execute(statement).scalars().all())

    termin = models.Termin
    legacy_buffer = _configured_post_buffer_min(
        db, include_r3=include_r3_buffers,
    )
    materialized_termin_ids = set(db.execute(
        select(claim.termin_id).where(
            claim.data == data,
            claim.termin_id.isnot(None),
        ).distinct()
    ).scalars().all())
    scheduled_statement = select(
        termin.id,
        termin.stolik_id,
        termin.stoliki_dodatkowe,
        termin.godz_od,
        termin.godz_do,
    ).where(
        termin.data == data,
        termin.rodzaj == "stolik",
        termin.status.in_(ACTIVE_STATUSES),
        termin.godz_od.isnot(None),
        termin.godz_do.isnot(None),
    )
    if exclude_termin_id is not None:
        scheduled_statement = scheduled_statement.where(termin.id != exclude_termin_id)
    for termin_id, primary, additional, existing_start, existing_end in db.execute(
        scheduled_statement,
    ):
        if termin_id in materialized_termin_ids:
            continue
        existing_start_minute, existing_end_minute = _interval(
            existing_start,
            existing_end,
        )
        existing_blocked_end = min(1440, existing_end_minute + legacy_buffer)
        if existing_start_minute < query_end and query_start < existing_blocked_end:
            occupied.update(_projected_table_ids(primary, additional))

    live_statement = select(
        termin.stolik_id,
        termin.stoliki_dodatkowe,
    ).where(
        termin.data == data,
        termin.rodzaj == "stolik",
        termin.status.in_(ACTIVE_STATUSES),
        termin.faza_hosta.in_(LIVE_HOST_PHASES),
    )
    if exclude_termin_id is not None:
        live_statement = live_statement.where(termin.id != exclude_termin_id)
    for primary, additional in db.execute(live_statement):
        occupied.update(_projected_table_ids(primary, additional))
    return occupied


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
    bucket_start = (start_minute // window_min) * window_min
    statement = select(ledger).where(
        ledger.data == data,
        ledger.start_minute >= bucket_start,
        ledger.start_minute < min(1440, bucket_start + window_min),
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
        "bucket_start": bucket_start,
        "bucket_end": min(1440, bucket_start + window_min),
    }


def release_termin_allocation(
    db, termin_id: int, *, include_capacity: bool = True,
) -> None:
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
    if include_capacity:
        db.execute(
            delete(models.RezerwacjaOblozenieLedger).where(
                models.RezerwacjaOblozenieLedger.termin_id == termin_id
            )
        )


def normalise_reservation_channel(value: str | None) -> str:
    """Ledger reguł ma dwa kanały; historyczne źródła operatora są wewnętrzne."""
    return "online" if value == "online" else "wewnetrzna"


def replace_termin_allocation(
    db,
    *,
    termin_id: int,
    data: date,
    start: time | None,
    end: time | None,
    table_ids: Iterable[int] = (),
    party_size: int = 1,
    buffer_min: int | None = None,
    enforce_pacing: bool = False,
    max_reservations: int | None = None,
    max_covers: int | None = None,
    pacing_window_min: int = 1,
    override: bool = False,
    room_id: int | None = None,
    channel: str = "wewnetrzna",
    include_capacity: bool = True,
    now: datetime | None = None,
    candidates: Sequence[Mapping[str, Any]] = (),
    alternatives: Sequence[Mapping[str, Any]] = (),
    cleanup_holds: bool = True,
) -> AvailabilityResult:
    """Atomowo zastępuje wszystkie aktywne wpisy ledgera jednego ``Termin``.

    Funkcja nie wykonuje commita. Jeżeli późniejszy zapis się nie powiedzie, rollback
    przywraca stary przydział razem z jego claimami.
    """

    effective_now = now or datetime.now()
    if cleanup_holds:
        cleanup_expired_holds(db, effective_now)
    release_termin_allocation(
        db, termin_id, include_capacity=include_capacity,
    )
    if start is None:
        return AvailabilityResult(available=True)
    if buffer_min is None:
        # ``rez_bufor_min`` jest historycznym fizycznym fallbackiem także dla
        # zapisów wewnętrznych. Warstwa R3 przekazuje wartość bardziej szczegółową,
        # gdy ustawi ją serwis/sala/reguła.
        buffer_min = _configured_post_buffer_min(db, include_r3=cleanup_holds)
    buffer_min = max(0, int(buffer_min or 0))
    start_minute = _minute(start, field_name="Godzina rozpoczęcia")
    ids = tuple(sorted({int(value) for value in table_ids if value is not None}))
    interval: tuple[int, int] | None = _interval(start, end) if end is not None else None
    if ids:
        if end is None:
            raise ReservationError(
                400,
                "INVALID_RESERVATION_INTERVAL",
                "Przydział stołu wymaga godziny zakończenia.",
                rule="interval",
            )
        occupied = occupied_table_ids(
            db,
            data=data,
            start=start,
            end=end,
            buffer_min=buffer_min,
            exclude_termin_id=termin_id,
            now=effective_now,
            # ``cleanup_holds=False`` jest używane przez fallback odbudowujący
            # także schematy sprzed 0059; nie wolno wtedy odczytywać kolumn R3.
            include_r3_buffers=cleanup_holds,
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
            override=bool(override),
            created_at=_utcnow_naive(),
        )
    )
    if include_capacity and interval is not None:
        start_raw, end_raw = interval
        capacity_created_at = _utcnow_naive()
        capacity_rows = [
            {
                "termin_id": termin_id,
                "data": data,
                "minute": minute,
                "sala_id": room_id,
                "kanal": normalise_reservation_channel(channel),
                "covers": max(0, int(party_size or 0)),
                "override": bool(override),
                "created_at": capacity_created_at,
            }
            for minute in range(start_raw, end_raw)
        ]
        if capacity_rows:
            db.execute(insert(models.RezerwacjaOblozenieLedger), capacity_rows)
    if ids and interval is not None:
        start_raw, end_raw = interval
        blocked_end = min(1440, end_raw + buffer_min)
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
            for minute in range(start_raw, blocked_end)
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
    table_id: int | None = None,
    table_ids: Iterable[int] = (),
    data: date,
    expires_at: datetime,
    now: datetime,
    start: time | None = None,
    end: time | None = None,
    buffer_min: int = 0,
    cleanup_holds: bool = True,
) -> None:
    """Atomowo zastępuje hold jednym stołem lub pełną kombinacją.

    Nowe holdy zajmują wyłącznie okno wizyty wraz z buforem. Brak czasu jest
    zachowany jako kompatybilny, konserwatywny hold całego dnia.
    """
    if cleanup_holds:
        cleanup_expired_holds(db, now)
    release_waitlist_hold(db, waitlist_id)
    ids = tuple(sorted({
        int(value)
        for value in ((*table_ids, table_id) if table_id is not None else table_ids)
        if value is not None
    }))
    if not ids:
        raise ReservationError(
            400,
            "INVALID_HOLD_RESOURCE",
            "Hold wymaga co najmniej jednego stolika.",
            rule="table_hold",
        )
    if (start is None) != (end is None):
        raise ReservationError(
            400,
            "INVALID_RESERVATION_INTERVAL",
            "Czasowy hold wymaga początku i końca wizyty.",
            rule="interval",
        )
    if start is None:
        start_minute, blocked_end = 0, 1440
    else:
        start_minute, end_minute = _interval(start, end)
        blocked_end = min(1440, end_minute + max(0, int(buffer_min or 0)))

    claim = models.RezerwacjaStolikClaim
    conflicts = set(db.execute(
        select(claim.stolik_id).where(
            claim.stolik_id.in_(ids),
            claim.data == data,
            claim.minute >= start_minute,
            claim.minute < blocked_end,
            _active_hold_filter(now),
            or_(claim.waitlist_id.is_(None), claim.waitlist_id != waitlist_id),
        )
    ).scalars().all())
    if start is not None:
        conflicts |= set(ids) & occupied_table_ids(
            db,
            data=data,
            start=start,
            end=end,
            buffer_min=buffer_min,
            now=now,
        )
    if conflicts:
        raise ReservationError(
            409,
            "TABLE_CONFLICT",
            "Co najmniej jeden stolik zestawu jest już zajęty lub trzymany w tym czasie.",
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
        for table_id in ids
        for minute in range(start_minute, blocked_end)
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
