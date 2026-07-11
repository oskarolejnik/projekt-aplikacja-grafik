"""Model, migracja i helper transakcyjnego audytu rezerwacji R1a."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from datetime import date, datetime, time, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

import models
import reservation_audit


BACKEND = Path(__file__).resolve().parent.parent


def _actor(db, *, login: str = "recepcja.anna") -> models.User:
    actor = models.User(
        login=login,
        haslo_hash="test-hash",
        rola="employee",
        aktywny=True,
    )
    db.add(actor)
    db.flush()
    return actor


def _termin(db, *, surname: str = "Bardzo Tajny Gość") -> models.Termin:
    termin = models.Termin(
        data=date(2030, 1, 2),
        nazwisko=surname,
        telefon="500600700",
        email="sekret@example.test",
        notatka="Alergia — nie kopiować do audytu",
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


def test_helper_dodaje_do_transakcji_bez_commit_i_filtruje_pii(db):
    actor = _actor(db)
    termin = _termin(db)
    before = {
        "data": date(2030, 1, 2),
        "godz_od": time(18, 0),
        "godz_do": time(20, 0),
        "liczba_osob": 4,
        "status": "potwierdzona",
        "nazwisko": "Bardzo Tajny Gość",
        "telefon": "500600700",
        "email": "sekret@example.test",
        "notatka": "Alergia — nie kopiować do audytu",
        "token_potwierdzenia": "tajny-token",
    }
    after = {
        **before,
        "godz_do": time(20, 30),
        "liczba_osob": 5,
        "telefon": "511611711",
        "notatka": "Inna tajna notatka",
    }

    audit = reservation_audit.add_reservation_audit(
        db,
        termin=termin,
        action="edit",
        actor=actor,
        reason="operator_correction",
        before=before,
        after=after,
        pii_changed={"telefon", "notatka"},
        now=datetime(2026, 7, 11, 11, 0, tzinfo=timezone.utc),
    )

    # Helper nie flushuje ani nie kończy transakcji wywołującego.
    assert audit.id is None
    assert audit in db.new
    assert audit.created_at == datetime(2026, 7, 11, 11, 0)
    assert audit.actor_user_id == actor.id
    assert audit.actor_login == actor.login
    assert audit.diff == {
        "changes": {
            "godz_do": {"before": "20:00:00", "after": "20:30:00"},
            "liczba_osob": {"before": 4, "after": 5},
        },
        "pii_changed": ["notatka", "telefon"],
    }
    encoded = json.dumps(audit.diff, ensure_ascii=False)
    for secret in (
        "Bardzo Tajny Gość",
        "500600700",
        "511611711",
        "sekret@example.test",
        "Alergia",
        "Inna tajna notatka",
        "tajny-token",
    ):
        assert secret not in encoded

    db.flush()
    raw_diff = db.execute(
        text("SELECT diff FROM reservation_audit WHERE id=:id"), {"id": audit.id},
    ).scalar_one()
    for secret in ("Bardzo Tajny Gość", "500600700", "sekret@example.test", "Alergia"):
        assert secret not in raw_diff

    db.rollback()
    assert db.query(models.ReservationAudit).count() == 0
    assert db.query(models.Termin).filter_by(id=termin.id).count() == 0


def test_audyt_i_rezerwacja_maja_wspolny_wynik_transakcji(db):
    actor = _actor(db)
    termin = _termin(db)
    audit = reservation_audit.add_reservation_audit(
        db,
        termin=termin,
        action="create",
        actor=actor,
        after=termin,
    )
    # Symulowany błąd audytu przy commit musi cofnąć również nowy Termin.
    audit.action = "nieznana"
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    assert db.query(models.ReservationAudit).count() == 0
    assert db.query(models.Termin).filter_by(id=termin.id).count() == 0


def test_helper_wymusza_bezpieczne_kody_i_powod_override(db):
    actor = _actor(db)
    termin = _termin(db)

    with pytest.raises(ValueError, match="requires a reason"):
        reservation_audit.add_reservation_audit(
            db, termin=termin, action="override", actor=actor,
        )
    with pytest.raises(ValueError, match="unsupported reservation audit reason"):
        reservation_audit.add_reservation_audit(
            db,
            termin=termin,
            action="cancel",
            actor=actor,
            reason="Telefon gościa 500600700",
        )
    with pytest.raises(ValueError, match="unsupported PII field"):
        reservation_audit.build_reservation_diff(
            {"status": "potwierdzona"},
            {"status": "odwolana"},
            pii_changed={"dowolny sekret"},
        )
    with pytest.raises(ValueError, match="invalid auditable token"):
        reservation_audit.build_reservation_diff(
            {"status": "potwierdzona"},
            {"status": "Nazwisko Gościa"},
        )
    with pytest.raises(ValueError, match="real limit breach"):
        reservation_audit.add_reservation_audit(
            db,
            termin=termin,
            action="override",
            actor=actor,
            reason="pacing_override",
            override_details={"violations": [{
                "rule": "pacing_reservations",
                "observed": 0,
                "limit": 2,
                "projected": 1,
            }]},
        )


def test_helper_pomija_pusty_retry_operacji(db):
    actor = _actor(db)
    termin = _termin(db)
    snapshot = reservation_audit.reservation_snapshot(termin)

    record = reservation_audit.add_reservation_audit(
        db,
        termin=termin,
        action="edit",
        actor=actor,
        before=snapshot,
        after=termin,
    )

    assert record is None
    db.commit()
    assert db.query(models.ReservationAudit).count() == 0


def test_helper_i_model_obsluguja_pelny_katalog_akcji(db):
    actor = _actor(db)
    termin = _termin(db)
    for action in sorted(reservation_audit.AUDIT_ACTIONS):
        reservation_audit.add_reservation_audit(
            db,
            termin=termin,
            action=action,
            actor=actor,
            reason="capacity_override" if action == "override" else None,
            before={"status": "potwierdzona"},
            after={"status": "odwolana"},
        )
    db.commit()
    assert {
        row.action for row in db.query(models.ReservationAudit).all()
    } == reservation_audit.AUDIT_ACTIONS

    with pytest.raises(ValueError, match="unsupported reservation audit action"):
        reservation_audit.add_reservation_audit(
            db, termin=termin, action="raw_pii_dump", actor=actor,
        )


def test_historia_przezywa_usuniecie_rezerwacji_i_aktora(tmp_path):
    db_file = tmp_path / "audit_fk.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}")

    @event.listens_for(engine, "connect")
    def _foreign_keys(connection, _record):
        cursor = connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

    models.Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    local_db = Session()
    try:
        actor = _actor(local_db)
        termin = _termin(local_db)
        audit = reservation_audit.add_reservation_audit(
            local_db,
            termin=termin,
            action="delete",
            actor=actor,
            reason="operator_correction",
            before=termin,
        )
        local_db.commit()
        audit_id = audit.id
        expected_ref = audit.reservation_ref
        expected_login = actor.login

        local_db.delete(termin)
        local_db.delete(actor)
        local_db.commit()
        local_db.expire_all()

        persisted = local_db.get(models.ReservationAudit, audit_id)
        assert persisted is not None
        assert persisted.termin_id is None
        assert persisted.actor_user_id is None
        assert persisted.actor_login == expected_login
        assert persisted.reservation_ref == expected_ref
        assert len(persisted.reservation_ref) == 64
    finally:
        local_db.close()
        engine.dispose()


def _migration_env(db_file: Path) -> dict[str, str]:
    return {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{db_file.as_posix()}",
        "SECRET_KEY": "reservation-audit-test-secret-key-0123456789",
        "ENCRYPTION_KEY": "reservation-audit-test-encryption-key-0123456789",
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


def test_migracja_0052_round_trip_bez_fabrykowania_historii(tmp_path):
    db_file = tmp_path / "reservation_audit_migration.db"
    up_0051 = _alembic(db_file, "upgrade", "0051_rezerwacje_atomic_ledger")
    assert up_0051.returncode == 0, up_0051.stderr
    con = sqlite3.connect(str(db_file))
    try:
        con.execute(
            "INSERT INTO users (id, login, haslo_hash, rola, aktywny) "
            "VALUES (1, 'legacy.operator', 'hash', 'employee', 1)"
        )
        con.execute(
            "INSERT INTO audit_log (id, ts, user_id, login, akcja, zasob) "
            "VALUES (1, '2026-07-11 10:00:00', 1, 'legacy.operator', "
            "'rodo_eksport_gosc', '600100200')"
        )
        con.execute(
            """INSERT INTO terminy
               (id, data, nazwisko, liczba_osob, status, zadatek, utworzono_at,
                godz_od, godz_do, kanal, rodzaj)
               VALUES (1, '2030-01-02', 'Dane istniejącego gościa', 2,
                       'potwierdzona', 0, '2026-07-11 10:00:00',
                       '18:00:00', '20:00:00', 'reczna', 'stolik')"""
        )
        con.commit()
    finally:
        con.close()

    up_0052 = _alembic(db_file, "upgrade", "0052_reservation_audit")
    assert up_0052.returncode == 0, up_0052.stderr
    con = sqlite3.connect(str(db_file))
    try:
        version = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        columns = {row[1] for row in con.execute("PRAGMA table_info(reservation_audit)")}
        foreign_keys = {
            (row[3], row[2], row[4], row[6])
            for row in con.execute("PRAGMA foreign_key_list(reservation_audit)")
        }
        indexes = {row[1] for row in con.execute("PRAGMA index_list(reservation_audit)")}
        ddl = con.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='reservation_audit'"
        ).fetchone()[0]
        audit_count = con.execute("SELECT count(*) FROM reservation_audit").fetchone()[0]
        legacy_counts = (
            con.execute("SELECT count(*) FROM users WHERE id=1").fetchone()[0],
            con.execute("SELECT count(*) FROM terminy WHERE id=1").fetchone()[0],
        )
        sanitized_rodo_resource = con.execute(
            "SELECT zasob FROM audit_log WHERE id=1"
        ).fetchone()[0]
    finally:
        con.close()

    assert version == "0052_reservation_audit"
    assert columns == {
        "id", "created_at", "reservation_ref", "termin_id", "actor_kind",
        "actor_user_id", "actor_login", "action", "reason", "diff",
    }
    assert foreign_keys == {
        ("termin_id", "terminy", "id", "SET NULL"),
        ("actor_user_id", "users", "id", "SET NULL"),
    }
    assert indexes == {
        "ix_reservation_audit_ref_created",
        "ix_reservation_audit_termin_created",
        "ix_reservation_audit_actor_created",
    }
    assert "ck_reservation_audit_action" in ddl
    assert "ck_reservation_audit_override_reason" in ddl
    assert audit_count == 0
    assert legacy_counts == (1, 1)
    assert sanitized_rodo_resource == "[redacted]"

    down = _alembic(db_file, "downgrade", "0051_rezerwacje_atomic_ledger")
    assert down.returncode == 0, down.stderr
    con = sqlite3.connect(str(db_file))
    try:
        tables = {
            row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        version_after_down = con.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0]
        legacy_counts_after_down = (
            con.execute("SELECT count(*) FROM users WHERE id=1").fetchone()[0],
            con.execute("SELECT count(*) FROM terminy WHERE id=1").fetchone()[0],
        )
    finally:
        con.close()
    assert "reservation_audit" not in tables
    assert version_after_down == "0051_rezerwacje_atomic_ledger"
    assert legacy_counts_after_down == (1, 1)

    up_again = _alembic(db_file, "upgrade", "0052_reservation_audit")
    assert up_again.returncode == 0, up_again.stderr
