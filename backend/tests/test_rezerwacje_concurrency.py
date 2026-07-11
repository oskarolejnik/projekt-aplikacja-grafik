"""Deterministyczne regresje atomowego zapisu rezerwacji R0b.

Testy celowo nie korzystają ze współdzielonego ``StaticPool`` z ``conftest``.
Każdy worker dostaje osobne połączenie do plikowego SQLite, dzięki czemu testuje
rzeczywistą blokadę transakcyjną, a nie dwa obiekty Session na jednym DBAPI connection.
"""

from __future__ import annotations

import os
import threading
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time
from queue import Queue

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import models
import reservation_service


BOOKING_DATE = date(2030, 1, 2)
START = time(18, 0)
END = time(20, 0)
NOW = datetime(2026, 7, 11, 12, 0)


@dataclass(frozen=True)
class _Outcome:
    worker: str
    status: str
    code: str | None = None
    termin_id: int | None = None


@pytest.fixture
def sqlite_concurrency_db(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'reservation-race.db').as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 15},
        poolclass=NullPool,
    )

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=15000")

    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA journal_mode=WAL")
    models.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    try:
        yield engine, factory
    finally:
        engine.dispose()


@pytest.fixture
def postgres_concurrency_db():
    url = os.environ.get("TEST_POSTGRES_URL", "").strip()
    if not url:
        pytest.skip("TEST_POSTGRES_URL is not configured")

    schema = f"test_rezerwacje_concurrency_{uuid.uuid4().hex}"
    admin_engine = create_engine(url, poolclass=NullPool)
    with admin_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        url,
        connect_args={"options": f"-csearch_path={schema}"},
        poolclass=NullPool,
    )
    models.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    try:
        yield engine, factory
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()


def _seed_tables(factory, count: int) -> list[int]:
    db = factory()
    try:
        tables = [
            models.Stolik(nazwa=f"S{index + 1}", pojemnosc=4, aktywny=True)
            for index in range(count)
        ]
        db.add_all(tables)
        db.commit()
        return [table.id for table in tables]
    finally:
        db.close()


def _new_termin(db, worker: str, table_id: int, booking_date: date) -> models.Termin:
    termin = models.Termin(
        data=booking_date,
        nazwisko=f"Worker {worker}",
        liczba_osob=2,
        status="potwierdzona",
        zadatek=0,
        utworzono_at=NOW,
        godz_od=START,
        godz_do=END,
        kanal="reczna",
        rodzaj="stolik",
        stolik_id=table_id,
    )
    db.add(termin)
    db.flush()
    return termin


def _run_locked_race(
    factory,
    *,
    table_ids: tuple[int, int],
    enforce_pacing: bool,
    max_reservations: int | None,
    booking_date: date = BOOKING_DATE,
) -> list[_Outcome]:
    first_has_lock = threading.Event()
    second_is_attempting = threading.Event()
    release_first = threading.Event()
    outcomes: Queue[_Outcome] = Queue()

    def worker(name: str, table_id: int, first: bool) -> None:
        db = factory()
        try:
            if first:
                guards = reservation_service.begin_locked_write(db, [booking_date])
                first_has_lock.set()
                if not release_first.wait(timeout=15):
                    raise RuntimeError("test did not release the first writer")
            else:
                if not first_has_lock.wait(timeout=15):
                    raise RuntimeError("first writer did not acquire the day lock")
                second_is_attempting.set()
                guards = reservation_service.begin_locked_write(db, [booking_date])

            termin = _new_termin(db, name, table_id, booking_date)
            reservation_service.replace_termin_allocation(
                db,
                termin_id=termin.id,
                data=booking_date,
                start=START,
                end=END,
                table_ids=[table_id],
                party_size=2,
                enforce_pacing=enforce_pacing,
                max_reservations=max_reservations,
                max_covers=None,
                pacing_window_min=120,
                now=NOW,
            )
            reservation_service.touch_days(guards)
            db.commit()
            outcomes.put(_Outcome(name, "success", termin_id=termin.id))
        except reservation_service.ReservationError as exc:
            db.rollback()
            outcomes.put(_Outcome(name, "conflict", code=exc.code))
        except IntegrityError as exc:
            db.rollback()
            translated = reservation_service.translate_integrity_error(exc)
            outcomes.put(_Outcome(name, "conflict", code=translated.code))
        except Exception as exc:  # test raportuje nieoczekiwany typ, zamiast gubić wyjątek w wątku
            db.rollback()
            outcomes.put(_Outcome(name, "unexpected", code=type(exc).__name__))
        finally:
            db.close()

    first = threading.Thread(
        target=worker,
        args=("A", table_ids[0], True),
        name="reservation-writer-A",
        daemon=True,
    )
    second = threading.Thread(
        target=worker,
        args=("B", table_ids[1], False),
        name="reservation-writer-B",
        daemon=True,
    )
    first.start()
    assert first_has_lock.wait(timeout=15), "first writer did not acquire the day lock"
    second.start()
    try:
        assert second_is_attempting.wait(timeout=15), "second writer did not attempt the day lock"
    finally:
        release_first.set()
    first.join(timeout=20)
    second.join(timeout=20)
    assert not first.is_alive() and not second.is_alive(), "concurrency test deadlocked"
    return sorted((outcomes.get_nowait(), outcomes.get_nowait()), key=lambda item: item.worker)


def _assert_one_success_one_conflict(outcomes: list[_Outcome], expected_code: str) -> None:
    assert [outcome.status for outcome in outcomes].count("success") == 1
    conflicts = [outcome for outcome in outcomes if outcome.status == "conflict"]
    assert len(conflicts) == 1
    assert conflicts[0].code == expected_code


def _termin_count(factory, booking_date: date = BOOKING_DATE) -> int:
    db = factory()
    try:
        return db.query(models.Termin).filter_by(data=booking_date, rodzaj="stolik").count()
    finally:
        db.close()


def test_sqlite_day_lock_prevents_concurrent_double_booking(sqlite_concurrency_db):
    _engine, factory = sqlite_concurrency_db
    table_id = _seed_tables(factory, 1)[0]

    outcomes = _run_locked_race(
        factory,
        table_ids=(table_id, table_id),
        enforce_pacing=False,
        max_reservations=None,
    )

    _assert_one_success_one_conflict(outcomes, "TABLE_CONFLICT")
    assert _termin_count(factory) == 1


def test_sqlite_day_lock_prevents_concurrent_pacing_overflow(sqlite_concurrency_db):
    _engine, factory = sqlite_concurrency_db
    first_table, second_table = _seed_tables(factory, 2)

    outcomes = _run_locked_race(
        factory,
        table_ids=(first_table, second_table),
        enforce_pacing=True,
        max_reservations=1,
    )

    _assert_one_success_one_conflict(outcomes, "PACING_RESERVATION_LIMIT")
    assert _termin_count(factory) == 1


def test_postgres_day_lock_matches_sqlite_contract(postgres_concurrency_db):
    _engine, factory = postgres_concurrency_db
    first_table, second_table = _seed_tables(factory, 2)

    table_outcomes = _run_locked_race(
        factory,
        table_ids=(first_table, first_table),
        enforce_pacing=False,
        max_reservations=None,
    )
    _assert_one_success_one_conflict(table_outcomes, "TABLE_CONFLICT")
    assert _termin_count(factory) == 1

    # Drugi scenariusz używa osobnego dnia, aby pierwszy ledger nie wpływał na pacing.
    pacing_outcomes = _run_locked_race(
        factory,
        table_ids=(first_table, second_table),
        enforce_pacing=True,
        max_reservations=1,
        booking_date=date(2030, 1, 3),
    )
    _assert_one_success_one_conflict(pacing_outcomes, "PACING_RESERVATION_LIMIT")
    assert _termin_count(factory, date(2030, 1, 3)) == 1
