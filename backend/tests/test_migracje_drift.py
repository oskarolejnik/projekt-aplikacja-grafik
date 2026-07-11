"""Strażnik anti-drift model↔migracja. conftest robi create_all → maskuje rozjazd migracji z modelem.
Ten test buduje bazę PRZEZ Alembic (upgrade head) i porównuje kolumny kluczowych tabel z modelem —
to jedyny sposób złapać drift, którego create_all nie pokaże (np. osierocone/brakujące pole)."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import models

BACKEND = Path(__file__).resolve().parent.parent

# Tabele pod nadzorem (rozszerzane w rezerwacjach; drift tu najgroźniejszy).
_TABELE = [
    "lokal_config", "wyjatki_kalendarza", "godziny_otwarcia", "stoliki", "kombinacje_stolow",
    "terminy", "profile_gosci", "rejestracje_lokalu", "lista_oczekujacych",
    "rezerwacje_idempotencja", "rezerwacje_dni_ledger", "rezerwacje_stoliki_claims",
    "rezerwacje_pacing_ledger", "users",
]


def _env(db_file, prefix="ledger"):
    return {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{db_file.as_posix()}",
        "SECRET_KEY": f"{prefix}-test-secret-key-0123456789abcd",
        "ENCRYPTION_KEY": f"{prefix}-test-encryption-key-0123456789",
        "APP_ENV": "development",
    }


def _insert_active_0050_reservation(db_file):
    con = sqlite3.connect(str(db_file))
    try:
        con.execute(
            """INSERT INTO stoliki
               (id, nazwa, pojemnosc, laczy_sie, aktywny, kolejnosc)
               VALUES (1, 'S1', 4, 0, 1, 0)"""
        )
        con.execute(
            """INSERT INTO terminy
               (id, data, nazwisko, liczba_osob, status, zadatek, utworzono_at,
                godz_od, godz_do, kanal, rodzaj, stolik_id)
               VALUES (1, '2030-01-02', 'Gość migracyjny', 2, 'potwierdzona', 0,
                       '2026-07-11 10:00:00', '18:00:00', '20:00:00',
                       'reczna', 'stolik', 1)"""
        )
        con.commit()
    finally:
        con.close()


def test_migracje_zgodne_z_modelem(tmp_path):
    db_file = tmp_path / "_drift.db"
    env = {**os.environ,
           "DATABASE_URL": f"sqlite:///{db_file.as_posix()}",
           "SECRET_KEY": "drift-test-secret-key-0123456789abcd",
           "ENCRYPTION_KEY": "drift-test-encryption-key-0123456789",
           "APP_ENV": "development"}
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                       cwd=str(BACKEND), env=env, capture_output=True, text=True)
    assert r.returncode == 0, f"alembic upgrade head padło:\n{r.stderr}"

    con = sqlite3.connect(str(db_file))
    try:
        for tabela in _TABELE:
            model_cols = {c.name for c in models.Base.metadata.tables[tabela].columns}
            db_cols = {row[1] for row in con.execute(f"PRAGMA table_info({tabela})")}
            assert db_cols == model_cols, (
                f"DRIFT w '{tabela}': różnica model↔migracja = {model_cols ^ db_cols} "
                f"(tylko-model={model_cols - db_cols}, tylko-migracja={db_cols - model_cols})")
    finally:
        con.close()


def test_adopcja_niewersjonowanej_bazy_nie_dubluje_source_identity(tmp_path):
    """Legacy baseline bez alembic_version ma przejść do head bez podwójnego ADD COLUMN z 0050."""
    db_file = tmp_path / "_legacy_adoption.db"
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{db_file.as_posix()}",
        "SECRET_KEY": "legacy-test-secret-key-0123456789abcd",
        "ENCRYPTION_KEY": "legacy-test-encryption-key-0123456789",
        "APP_ENV": "development",
    }
    baseline = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0001_baseline"],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert baseline.returncode == 0, baseline.stderr
    con = sqlite3.connect(str(db_file))
    try:
        con.execute("DROP TABLE alembic_version")
        con.commit()
    finally:
        con.close()

    adoption = subprocess.run(
        [sys.executable, "-c", "import database; database.init_db()"],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert adoption.returncode == 0, adoption.stderr

    con = sqlite3.connect(str(db_file))
    try:
        columns = {row[1] for row in con.execute("PRAGMA table_info(terminy)")}
        version = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        indexes = {row[1] for row in con.execute("PRAGMA index_list(terminy)")}
    finally:
        con.close()
    assert {"source_type", "source_external_id"} <= columns
    assert "uq_terminy_source_identity" in indexes
    assert version == "0051_rezerwacje_atomic_ledger"


def test_adopcja_pelnej_niewersjonowanej_bazy_0050_backfilluje_ledger(tmp_path):
    """Dodanie tabel R0b nie może cofnąć kompletnego schematu 0050 do baseline."""
    db_file = tmp_path / "_pre_r0b_adoption.db"
    env = _env(db_file, "pre-r0b-adoption")
    upgraded = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0050_rezerwacje_source_identity"],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert upgraded.returncode == 0, upgraded.stderr
    _insert_active_0050_reservation(db_file)
    con = sqlite3.connect(str(db_file))
    try:
        con.execute("DROP TABLE alembic_version")
        con.commit()
    finally:
        con.close()

    adoption = subprocess.run(
        [sys.executable, "-c", "import database; database.init_db()"],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert adoption.returncode == 0, adoption.stderr
    con = sqlite3.connect(str(db_file))
    try:
        version = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        table_claims = con.execute(
            "SELECT count(*) FROM rezerwacje_stoliki_claims WHERE termin_id=1"
        ).fetchone()[0]
        pacing = con.execute(
            "SELECT count(*) FROM rezerwacje_pacing_ledger WHERE termin_id=1"
        ).fetchone()[0]
    finally:
        con.close()
    assert version == "0051_rezerwacje_atomic_ledger"
    assert (table_claims, pacing) == (120, 1)

    resumed = subprocess.run(
        [sys.executable, "-c", "import database; database.init_db()"],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert resumed.returncode == 0, resumed.stderr


def test_fallback_bez_alembica_backfilluje_i_oznacza_baze_0050(tmp_path):
    db_file = tmp_path / "_pre_r0b_without_alembic.db"
    env = _env(db_file, "pre-r0b-fallback")
    upgraded = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0050_rezerwacje_source_identity"],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert upgraded.returncode == 0, upgraded.stderr
    _insert_active_0050_reservation(db_file)

    fallback = subprocess.run(
        [
            sys.executable,
            "-c",
            "import database; database._alembic_run=lambda action: False; database.init_db()",
        ],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert fallback.returncode == 0, fallback.stderr
    con = sqlite3.connect(str(db_file))
    try:
        version = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        table_claims = con.execute(
            "SELECT count(*) FROM rezerwacje_stoliki_claims WHERE termin_id=1"
        ).fetchone()[0]
        pacing = con.execute(
            "SELECT count(*) FROM rezerwacje_pacing_ledger WHERE termin_id=1"
        ).fetchone()[0]
    finally:
        con.close()
    assert version == "0051_rezerwacje_atomic_ledger"
    assert (table_claims, pacing) == (120, 1)

    resumed = subprocess.run(
        [sys.executable, "-c", "import database; database.init_db()"],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert resumed.returncode == 0, resumed.stderr


def test_sqlite_engine_wymusza_klucze_obce(tmp_path):
    db_file = tmp_path / "_sqlite_foreign_keys.db"
    env = _env(db_file, "foreign-keys")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import database; "
                "c=database.engine.raw_connection(); "
                "print(c.execute('PRAGMA foreign_keys').fetchone()[0]); c.close()"
            ),
        ],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "1"


def test_adopcja_legacy_bez_alembica_domknie_source_identity(tmp_path):
    db_file = tmp_path / "_legacy_without_alembic.db"
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{db_file.as_posix()}",
        "SECRET_KEY": "fallback-test-secret-key-0123456789abcd",
        "ENCRYPTION_KEY": "fallback-test-encryption-key-0123456789",
        "APP_ENV": "development",
    }
    baseline = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0001_baseline"],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert baseline.returncode == 0, baseline.stderr
    con = sqlite3.connect(str(db_file))
    try:
        con.execute("DROP TABLE alembic_version")
        con.commit()
    finally:
        con.close()

    fallback = subprocess.run(
        [sys.executable, "-c",
         "import database; database._alembic_run=lambda action: False; database.init_db()"],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert fallback.returncode == 0, fallback.stderr
    con = sqlite3.connect(str(db_file))
    try:
        columns = {row[1] for row in con.execute("PRAGMA table_info(terminy)")}
        indexes = {row[1] for row in con.execute("PRAGMA index_list(terminy)")}
    finally:
        con.close()
    assert {"source_type", "source_external_id"} <= columns
    assert "uq_terminy_source_identity" in indexes


def test_programowe_migracje_nie_wyciszaja_loggerow_aplikacji(tmp_path):
    db_file = tmp_path / "_logger_startup.db"
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{db_file.as_posix()}",
        "SECRET_KEY": "logger-test-secret-key-0123456789abcd",
        "ENCRYPTION_KEY": "logger-test-encryption-key-0123456789",
        "APP_ENV": "development",
    }
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import logging, rezerwacje, database; "
                "logger=logging.getLogger('rezerwacje'); "
                "assert not logger.disabled; "
                "database.init_db(); "
                "assert not logger.disabled"
            ),
        ],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
