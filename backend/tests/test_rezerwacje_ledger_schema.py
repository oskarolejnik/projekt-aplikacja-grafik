"""Schemat i migracja atomowego ledgera rezerwacji R0b."""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

import models

BACKEND = Path(__file__).resolve().parent.parent


def _termin(db, *, nazwisko: str = "Gość") -> models.Termin:
    termin = models.Termin(
        data=date(2030, 1, 2),
        nazwisko=nazwisko,
        liczba_osob=4,
        status="potwierdzona",
        zadatek=0,
        utworzono_at=datetime(2026, 7, 11, 10, 0),
        godz_od=time(18, 0),
        godz_do=time(20, 0),
        kanal="reczna",
        rodzaj="stolik",
    )
    db.add(termin)
    db.flush()
    return termin


def _migration_env(db_file: Path) -> dict[str, str]:
    return {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{db_file.as_posix()}",
        "SECRET_KEY": "ledger-test-secret-key-0123456789abcd",
        "ENCRYPTION_KEY": "ledger-test-encryption-key-0123456789",
        "APP_ENV": "development",
    }


def _alembic(db_file: Path, action: str, revision: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "alembic", action, revision],
        cwd=str(BACKEND),
        env=_migration_env(db_file),
        capture_output=True,
        text=True,
    )


def _upgrade_0050(db_file: Path) -> None:
    result = _alembic(db_file, "upgrade", "0050_rezerwacje_source_identity")
    assert result.returncode == 0, result.stderr


def _insert_table(con: sqlite3.Connection, table_id: int, name: str) -> None:
    con.execute(
        """INSERT INTO stoliki
           (id, nazwa, pojemnosc, laczy_sie, aktywny, kolejnosc)
           VALUES (?, ?, 4, 0, 1, 0)""",
        (table_id, name),
    )


def _insert_active_reservation(
    con: sqlite3.Connection,
    *,
    record_id: int,
    booking_date: str,
    table_id: int | None,
    start: str | None = "18:00:00",
    end: str | None = "20:00:00",
    extras: str | None = None,
    status: str = "potwierdzona",
    surname: str = "Sekretne Nazwisko",
) -> None:
    con.execute(
        """INSERT INTO terminy
           (id, data, nazwisko, liczba_osob, status, zadatek, utworzono_at,
            godz_od, godz_do, kanal, rodzaj, stolik_id, stoliki_dodatkowe)
           VALUES (?, ?, ?, 4, ?, 0, ?, ?, ?, 'reczna', 'stolik', ?, ?)""",
        (
            record_id,
            booking_date,
            surname,
            status,
            "2026-07-11 10:00:00",
            start,
            end,
            table_id,
            extras,
        ),
    )


def test_idempotencja_szyfruje_wynik_i_wymusza_stan(db):
    termin = _termin(db)
    now = datetime(2026, 7, 11, 10, 0)
    payload = '{"token":"sekretny","telefon":"500600700"}'
    entry = models.RezerwacjaIdempotencja(
        operation="reservation.create.online:v1",
        key_hash="a" * 64,
        request_fingerprint="b" * 64,
        status="succeeded",
        http_status=201,
        response_enc=payload,
        termin_id=termin.id,
        created_at=now,
        completed_at=now,
        expires_at=now + timedelta(days=2),
    )
    db.add(entry)
    db.commit()

    raw = db.execute(
        sa.text("SELECT response_enc FROM rezerwacje_idempotencja WHERE id=:id"),
        {"id": entry.id},
    ).scalar_one()
    assert raw.startswith("enc:v1:")
    assert entry.response_enc == payload

    invalid = models.RezerwacjaIdempotencja(
        operation="reservation.create.online:v1",
        key_hash="c" * 64,
        request_fingerprint="d" * 64,
        status="processing",
        http_status=201,
        response_enc="{}",
        created_at=now,
        expires_at=now + timedelta(days=2),
    )
    db.add(invalid)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_claim_stolika_wymusza_jednego_wlasciciela_i_brak_kolizji(db):
    table = models.Stolik(nazwa="S1", pojemnosc=4, aktywny=True, kolejnosc=0)
    db.add(table)
    first = _termin(db, nazwisko="Pierwszy")
    second = _termin(db, nazwisko="Drugi")
    now = datetime(2026, 7, 11, 10, 0)
    db.add(models.RezerwacjaStolikClaim(
        termin_id=first.id,
        stolik_id=table.id,
        data=first.data,
        minute=18 * 60,
        created_at=now,
    ))
    db.commit()

    db.add(models.RezerwacjaStolikClaim(
        termin_id=second.id,
        stolik_id=table.id,
        data=second.data,
        minute=18 * 60,
        created_at=now,
    ))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    db.add(models.RezerwacjaStolikClaim(
        stolik_id=table.id,
        data=first.data,
        minute=18 * 60 + 1,
        created_at=now,
    ))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_pacing_jest_jeden_na_termin_i_ma_poprawny_zakres(db):
    termin = _termin(db)
    now = datetime(2026, 7, 11, 10, 0)
    db.add(models.RezerwacjaPacingLedger(
        termin_id=termin.id,
        data=termin.data,
        start_minute=18 * 60,
        covers=4,
        override=False,
        created_at=now,
    ))
    db.commit()

    db.add(models.RezerwacjaPacingLedger(
        termin_id=termin.id,
        data=termin.data,
        start_minute=18 * 60 + 30,
        covers=4,
        override=True,
        created_at=now,
    ))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    other = _termin(db, nazwisko="Inny")
    db.add(models.RezerwacjaPacingLedger(
        termin_id=other.id,
        data=other.data,
        start_minute=1440,
        covers=4,
        override=False,
        created_at=now,
    ))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_migracja_backfilluje_wszystkie_aktywne_rezerwacje_i_hold(tmp_path):
    db_file = tmp_path / "ledger_backfill.db"
    _upgrade_0050(db_file)
    con = sqlite3.connect(str(db_file))
    try:
        _insert_table(con, 1, "S1")
        _insert_table(con, 2, "S2")
        # Historyczna, ale nadal aktywna: ledger ma być jedynym źródłem także dla takich wpisów.
        _insert_active_reservation(
            con,
            record_id=1,
            booking_date="2020-01-02",
            table_id=1,
            extras="[2]",
        )
        _insert_active_reservation(
            con,
            record_id=2,
            booking_date="2020-01-02",
            table_id=1,
            start="21:00:00",
            end="22:00:00",
            status="odwolana",
        )
        con.execute(
            """INSERT INTO lista_oczekujacych
               (id, data, nazwisko, status, utworzono_at, hold_stolik_id, hold_do, kanal)
               VALUES (1, '2030-01-03', 'Hold', 'oczekuje', '2026-07-11 10:00:00',
                       1, '2099-01-01 00:00:00', 'reczna')"""
        )
        con.commit()
    finally:
        con.close()

    result = _alembic(db_file, "upgrade", "head")
    assert result.returncode == 0, result.stderr

    con = sqlite3.connect(str(db_file))
    try:
        days = con.execute(
            "SELECT data, revision FROM rezerwacje_dni_ledger ORDER BY data"
        ).fetchall()
        pacing = con.execute(
            "SELECT termin_id, data, start_minute, covers, override "
            "FROM rezerwacje_pacing_ledger"
        ).fetchall()
        reservation_claims = con.execute(
            "SELECT count(*) FROM rezerwacje_stoliki_claims WHERE termin_id=1"
        ).fetchone()[0]
        terminal_claims = con.execute(
            "SELECT count(*) FROM rezerwacje_stoliki_claims WHERE termin_id=2"
        ).fetchone()[0]
        hold_claims, first_minute, last_minute = con.execute(
            "SELECT count(*), min(minute), max(minute) "
            "FROM rezerwacje_stoliki_claims WHERE waitlist_id=1"
        ).fetchone()
    finally:
        con.close()

    assert days == [("2020-01-02", 0), ("2030-01-03", 0)]
    assert pacing == [(1, "2020-01-02", 18 * 60, 4, 0)]
    assert reservation_claims == 2 * 120
    assert terminal_claims == 0
    assert (hold_claims, first_minute, last_minute) == (1440, 0, 1439)


def test_migracja_odrzuca_brak_konca_bez_wycieku_pii(tmp_path):
    db_file = tmp_path / "ledger_missing_end.db"
    _upgrade_0050(db_file)
    con = sqlite3.connect(str(db_file))
    try:
        _insert_table(con, 1, "S1")
        _insert_active_reservation(
            con,
            record_id=7,
            booking_date="2030-01-02",
            table_id=1,
            end=None,
            surname="Bardzo Tajne Nazwisko",
        )
        con.commit()
    finally:
        con.close()

    result = _alembic(db_file, "upgrade", "head")
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "R0B_BACKFILL_MISSING_END record_id=7" in output
    assert "Bardzo Tajne Nazwisko" not in output

    # SQLite DDL jest nietransakcyjne: preflight musi zawieść przed utworzeniem choćby
    # jednej tabeli 0051, aby poprawienie danych pozwalało zwyczajnie ponowić upgrade.
    con = sqlite3.connect(str(db_file))
    try:
        tables = {
            row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        version = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        con.execute("UPDATE terminy SET godz_do='20:00:00' WHERE id=7")
        con.commit()
    finally:
        con.close()
    assert not {
        "rezerwacje_idempotencja",
        "rezerwacje_dni_ledger",
        "rezerwacje_stoliki_claims",
        "rezerwacje_pacing_ledger",
    } & tables
    assert version == "0050_rezerwacje_source_identity"

    retry = _alembic(db_file, "upgrade", "head")
    assert retry.returncode == 0, retry.stderr


def test_migracja_odrzuca_istniejaca_kolizje_bez_wycieku_pii(tmp_path):
    db_file = tmp_path / "ledger_overlap.db"
    _upgrade_0050(db_file)
    con = sqlite3.connect(str(db_file))
    try:
        _insert_table(con, 1, "S1")
        _insert_active_reservation(
            con, record_id=1, booking_date="2030-01-02", table_id=1,
            surname="Pierwszy Sekret",
        )
        _insert_active_reservation(
            con, record_id=2, booking_date="2030-01-02", table_id=1,
            surname="Drugi Sekret",
        )
        con.commit()
    finally:
        con.close()

    result = _alembic(db_file, "upgrade", "head")
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "R0B_BACKFILL_TABLE_OVERLAP table_id=1 date=2030-01-02 minute=1080" in output
    assert "Pierwszy Sekret" not in output
    assert "Drugi Sekret" not in output


def test_migracja_round_trip_0051(tmp_path):
    db_file = tmp_path / "ledger_round_trip.db"
    up = _alembic(db_file, "upgrade", "head")
    assert up.returncode == 0, up.stderr

    down = _alembic(db_file, "downgrade", "0050_rezerwacje_source_identity")
    assert down.returncode == 0, down.stderr
    con = sqlite3.connect(str(db_file))
    try:
        tables_after_down = {
            row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        con.close()
    assert not {
        "rezerwacje_idempotencja",
        "rezerwacje_dni_ledger",
        "rezerwacje_stoliki_claims",
        "rezerwacje_pacing_ledger",
    } & tables_after_down

    up_again = _alembic(db_file, "upgrade", "head")
    assert up_again.returncode == 0, up_again.stderr
