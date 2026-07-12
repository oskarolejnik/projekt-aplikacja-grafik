"""Strażnik anti-drift model↔migracja. conftest robi create_all → maskuje rozjazd migracji z modelem.
Ten test buduje bazę PRZEZ Alembic (upgrade head) i porównuje kolumny kluczowych tabel z modelem —
to jedyny sposób złapać drift, którego create_all nie pokaże (np. osierocone/brakujące pole)."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import database
import models
import pytest

BACKEND = Path(__file__).resolve().parent.parent
HEAD = "0054_room_name_key"

# Tabele pod nadzorem (rozszerzane w rezerwacjach; drift tu najgroźniejszy).
_TABELE = [
    "lokal_config", "wyjatki_kalendarza", "godziny_otwarcia", "stoliki", "kombinacje_stolow",
    "terminy", "profile_gosci", "rejestracje_lokalu", "lista_oczekujacych",
    "rezerwacje_idempotencja", "rezerwacje_dni_ledger", "rezerwacje_stoliki_claims",
    "rezerwacje_pacing_ledger", "reservation_audit", "users",
    "sale_rezerwacyjne", "plany_sali", "wersje_planu_sali",
    "pozycje_stolikow_planu",
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


def _create_fake_audit_schema(db_file, *, drop_version=False):
    """Tabela o poprawnych nazwach, ale nieskutecznych CHECK-ach i błędnych indeksach."""
    con = sqlite3.connect(str(db_file))
    try:
        con.execute(
            """CREATE TABLE reservation_audit (
                id INTEGER NOT NULL PRIMARY KEY,
                created_at DATETIME NOT NULL,
                reservation_ref VARCHAR(64) NOT NULL,
                termin_id INTEGER REFERENCES terminy(id) ON DELETE SET NULL,
                actor_kind VARCHAR(16) NOT NULL,
                actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                actor_login VARCHAR(64),
                action VARCHAR(16) NOT NULL,
                reason VARCHAR(64),
                diff JSON NOT NULL,
                CONSTRAINT ck_reservation_audit_ref CHECK (1),
                CONSTRAINT ck_reservation_audit_actor_kind CHECK (1),
                CONSTRAINT ck_reservation_audit_action CHECK (1),
                CONSTRAINT ck_reservation_audit_reason CHECK (1),
                CONSTRAINT ck_reservation_audit_user_actor CHECK (1),
                CONSTRAINT ck_reservation_audit_override_reason CHECK (1)
            )"""
        )
        con.execute(
            "CREATE INDEX ix_reservation_audit_ref_created ON reservation_audit (id)"
        )
        con.execute(
            "CREATE INDEX ix_reservation_audit_termin_created ON reservation_audit (id)"
        )
        con.execute(
            "CREATE INDEX ix_reservation_audit_actor_created ON reservation_audit (id)"
        )
        if drop_version:
            con.execute("DROP TABLE alembic_version")
        con.commit()
    finally:
        con.close()


def _alembic(env, *args):
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )


@pytest.mark.parametrize(
    ("actual", "expected", "matches"),
    [
        (None, None, True),
        ("", None, True),
        ("status = 'draft'", None, False),
        ("((status)::text = 'draft'::text)", "status = 'draft'", True),
        (
            '(("status")::character varying(16) = \'published\'::text)',
            "status = 'published'",
            True,
        ),
        ("status = 'published'", "status = 'draft'", False),
        ("status IS NOT NULL AND 'draft'='draft'", "status = 'draft'", False),
        ("status LIKE 'draft'", "status = 'draft'", False),
    ],
)
def test_predykat_indeksu_r2_jest_dopasowany_fail_closed(
    actual, expected, matches,
):
    assert database._r2_index_predicate_matches(actual, expected) is matches


def test_adopcja_r2_postgresql_wymaga_zweryfikowanego_stampu(monkeypatch):
    class _PostgresDialect:
        name = "postgresql"

    class _PostgresEngine:
        dialect = _PostgresDialect()

    monkeypatch.setattr(database, "engine", _PostgresEngine())
    with pytest.raises(
        RuntimeError,
        match="R2_POSTGRES_ADOPTION_REQUIRES_VERIFIED_STAMP",
    ):
        database._validate_r2_adoption_schema(inspector=object())


def _prepare_r2_0052(db_file):
    """Realistyczny stan 0052: legacy sale, pozycje, rezerwacja i claimy R0b."""
    env = _env(db_file, "r2-migration")
    upgraded = _alembic(env, "upgrade", "0050_rezerwacje_source_identity")
    assert upgraded.returncode == 0, upgraded.stderr
    _insert_active_0050_reservation(db_file)

    con = sqlite3.connect(str(db_file))
    try:
        con.execute(
            "UPDATE stoliki SET strefa=?, plan_x=?, plan_y=? WHERE id=1",
            (" Ogród ", 12, 34),
        )
        con.execute(
            """INSERT INTO stoliki
               (id, nazwa, strefa, pojemnosc, laczy_sie, aktywny, kolejnosc)
               VALUES (2, 'S2', 'ogród', 4, 1, 1, 1)"""
        )
        con.execute(
            """INSERT INTO stoliki
               (id, nazwa, strefa, pojemnosc, laczy_sie, aktywny, kolejnosc)
               VALUES (3, 'S3', '   ', 2, 0, 0, 2)"""
        )
        con.commit()
    finally:
        con.close()

    config = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import database, models; db=database.SessionLocal(); "
                "db.add(models.LokalConfig(sale=['Ogród','Sala bankietowa'])); "
                "db.commit(); db.close()"
            ),
        ],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert config.returncode == 0, config.stderr

    upgraded = _alembic(env, "upgrade", "0052_reservation_audit")
    assert upgraded.returncode == 0, upgraded.stderr
    return env


def _legacy_r2_snapshot(con):
    return {
        "tables": con.execute(
            "SELECT id, strefa, plan_x, plan_y FROM stoliki ORDER BY id"
        ).fetchall(),
        "reservation": con.execute(
            "SELECT id, stolik_id FROM terminy WHERE id=1"
        ).fetchall(),
        "claims": con.execute(
            "SELECT stolik_id, count(*) FROM rezerwacje_stoliki_claims "
            "WHERE termin_id=1 GROUP BY stolik_id ORDER BY stolik_id"
        ).fetchall(),
    }


def _published_r2_snapshot(con):
    return {
        "rooms": con.execute(
            "SELECT nazwa, aktywna, kolejnosc FROM sale_rezerwacyjne "
            "ORDER BY kolejnosc, nazwa"
        ).fetchall(),
        "assignments": con.execute(
            "SELECT s.id, r.nazwa FROM stoliki s "
            "JOIN sale_rezerwacyjne r ON r.id=s.sala_id ORDER BY s.id"
        ).fetchall(),
        "versions": con.execute(
            "SELECT r.nazwa, p.nazwa, w.numer, w.status, w.rewizja "
            "FROM sale_rezerwacyjne r JOIN plany_sali p ON p.sala_id=r.id "
            "JOIN wersje_planu_sali w ON w.plan_id=p.id "
            "WHERE w.status='published' ORDER BY r.kolejnosc, r.nazwa"
        ).fetchall(),
        "positions": con.execute(
            "SELECT s.id, pos.plan_x, pos.plan_y, pos.szerokosc, pos.wysokosc, "
            "pos.obrot, pos.aktywny_w_planie "
            "FROM stoliki s JOIN pozycje_stolikow_planu pos ON pos.stolik_id=s.id "
            "JOIN wersje_planu_sali w ON w.id=pos.wersja_id "
            "WHERE w.status='published' ORDER BY s.id"
        ).fetchall(),
    }


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
        version = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    finally:
        con.close()
    assert version == HEAD


def test_init_db_podnosi_0052_do_0053_i_backfilluje_publikowany_plan(tmp_path):
    db_file = tmp_path / "_r2_init_db.db"
    env = _prepare_r2_0052(db_file)

    migrated = subprocess.run(
        [sys.executable, "-c", "import database; database.init_db()"],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert migrated.returncode == 0, migrated.stderr

    con = sqlite3.connect(str(db_file))
    try:
        version = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        snapshot = _published_r2_snapshot(con)
        reservation_table = con.execute(
            "SELECT stolik_id FROM terminy WHERE id=1"
        ).fetchone()[0]
        claim_count = con.execute(
            "SELECT count(*) FROM rezerwacje_stoliki_claims "
            "WHERE termin_id=1 AND stolik_id=1"
        ).fetchone()[0]
        fk_errors = con.execute("PRAGMA foreign_key_check").fetchall()
        temp_tables = con.execute(
            "SELECT name FROM sqlite_master WHERE name LIKE '_alembic_tmp_%'"
        ).fetchall()
        r2_indexes = {
            row[0] for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND tbl_name='wersje_planu_sali'"
            )
        }
        table_fk = con.execute("PRAGMA foreign_key_list(stoliki)").fetchall()
    finally:
        con.close()

    assert version == HEAD
    assert snapshot["rooms"] == [
        ("Sala główna", 1, 0),
        ("Ogród", 1, 1),
        ("Sala bankietowa", 1, 2),
    ]
    assert snapshot["assignments"] == [
        (1, "Ogród"), (2, "Ogród"), (3, "Sala główna"),
    ]
    assert snapshot["versions"] == [
        ("Sala główna", "Plan główny", 1, "published", 0),
        ("Ogród", "Plan główny", 1, "published", 0),
        ("Sala bankietowa", "Plan główny", 1, "published", 0),
    ]
    assert snapshot["positions"] == [
        (1, 12, 34, 12, 12, 0, 1),
        (2, 67, 50, 12, 12, 0, 1),
        (3, 50, 50, 12, 12, 0, 0),
    ]
    assert (reservation_table, claim_count) == (1, 120)
    assert fk_errors == [] and temp_tables == []
    assert any(row[2] == "sale_rezerwacyjne" and row[3] == "sala_id" for row in table_fk)
    assert {
        "uq_wersje_planu_sali_jeden_draft",
        "uq_wersje_planu_sali_jeden_published",
    } <= r2_indexes

    con = sqlite3.connect(str(db_file))
    try:
        plan_id = con.execute(
            "SELECT id FROM plany_sali ORDER BY id LIMIT 1"
        ).fetchone()[0]
        timestamp = "2026-07-12 12:00:00"
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                """INSERT INTO wersje_planu_sali
                   (plan_id,numer,status,rewizja,utworzono_at,zaktualizowano_at,opublikowano_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (plan_id, 2, "published", 0, timestamp, timestamp, timestamp),
            )
        con.rollback()
        con.execute(
            """INSERT INTO wersje_planu_sali
               (plan_id,numer,status,rewizja,utworzono_at,zaktualizowano_at)
               VALUES (?,?,?,?,?,?)""",
            (plan_id, 2, "draft", 0, timestamp, timestamp),
        )
        con.commit()
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                """INSERT INTO wersje_planu_sali
                   (plan_id,numer,status,rewizja,utworzono_at,zaktualizowano_at)
                   VALUES (?,?,?,?,?,?)""",
                (plan_id, 3, "draft", 0, timestamp, timestamp),
            )
        con.rollback()
    finally:
        con.close()


def test_migracja_0053_round_trip_zachowuje_legacy_i_historyczne_fk(tmp_path):
    db_file = tmp_path / "_r2_round_trip.db"
    env = _prepare_r2_0052(db_file)
    con = sqlite3.connect(str(db_file))
    try:
        legacy_before = _legacy_r2_snapshot(con)
    finally:
        con.close()

    upgraded = _alembic(env, "upgrade", HEAD)
    assert upgraded.returncode == 0, upgraded.stderr
    con = sqlite3.connect(str(db_file))
    try:
        published_before = _published_r2_snapshot(con)
    finally:
        con.close()

    downgraded = _alembic(env, "downgrade", "0052_reservation_audit")
    assert downgraded.returncode == 0, downgraded.stderr
    con = sqlite3.connect(str(db_file))
    try:
        downgraded_tables = {
            row[0] for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        downgraded_columns = {
            row[1] for row in con.execute("PRAGMA table_info(stoliki)")
        }
        assert _legacy_r2_snapshot(con) == legacy_before
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        con.close()
    assert not {
        "sale_rezerwacyjne", "plany_sali", "wersje_planu_sali",
        "pozycje_stolikow_planu",
    } & downgraded_tables
    assert "sala_id" not in downgraded_columns

    upgraded_again = _alembic(env, "upgrade", HEAD)
    assert upgraded_again.returncode == 0, upgraded_again.stderr
    con = sqlite3.connect(str(db_file))
    try:
        assert _legacy_r2_snapshot(con) == legacy_before
        assert _published_r2_snapshot(con) == published_before
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
        assert con.execute(
            "SELECT name FROM sqlite_master WHERE name LIKE '_alembic_tmp_%'"
        ).fetchall() == []
        version = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    finally:
        con.close()
    assert version == HEAD


def test_migracja_0054_fail_closed_dla_unicode_duplikatu_nazwy_sali(tmp_path):
    db_file = tmp_path / "_r2_room_name_conflict.db"
    env = _env(db_file, "r2-room-name")
    base = _alembic(env, "upgrade", "0053_sale_i_wersje_planu")
    assert base.returncode == 0, base.stderr

    con = sqlite3.connect(str(db_file))
    try:
        con.execute(
            "INSERT INTO sale_rezerwacyjne (nazwa, aktywna, kolejnosc) VALUES (?, 1, 0)",
            ("Żółta",),
        )
        con.execute(
            "INSERT INTO sale_rezerwacyjne (nazwa, aktywna, kolejnosc) VALUES (?, 1, 1)",
            ("żółta",),
        )
        con.commit()
    finally:
        con.close()

    failed = _alembic(env, "upgrade", "head")
    assert failed.returncode != 0
    assert "R2_ROOM_NAME_CANONICAL_CONFLICT" in failed.stderr

    con = sqlite3.connect(str(db_file))
    try:
        columns = {
            row[1] for row in con.execute("PRAGMA table_info(sale_rezerwacyjne)")
        }
        version = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    finally:
        con.close()
    assert "nazwa_klucz" not in columns
    assert version == "0053_sale_i_wersje_planu"


def test_adopcja_r2_odrzuca_partial_unique_zamiast_pelnego_indeksu(tmp_path):
    db_file = tmp_path / "_r2_partial_room_key_unique.db"
    env = _env(db_file, "r2-partial-room-key")
    upgraded = _alembic(env, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr

    con = sqlite3.connect(str(db_file))
    try:
        con.execute("DROP INDEX uq_sale_rezerwacyjne_nazwa_klucz")
        con.execute(
            "CREATE UNIQUE INDEX uq_sale_rezerwacyjne_nazwa_klucz "
            "ON sale_rezerwacyjne (nazwa_klucz) WHERE aktywna = 1"
        )
        con.execute("DROP TABLE alembic_version")
        con.commit()
    finally:
        con.close()

    adoption = subprocess.run(
        [sys.executable, "-c", "import database; database.init_db()"],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert adoption.returncode != 0
    assert "uq_sale_rezerwacyjne_nazwa_klucz" in (
        adoption.stdout + adoption.stderr
    )


def test_adopcja_r2_odrzuca_dodatkowa_pozycje_stolika_w_innej_sali(tmp_path):
    db_file = tmp_path / "_r2_cross_room_position.db"
    env = _env(db_file, "r2-cross-room-position")
    upgraded = _alembic(env, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr

    con = sqlite3.connect(str(db_file))
    try:
        room_a = con.execute(
            "INSERT INTO sale_rezerwacyjne "
            "(nazwa,nazwa_klucz,aktywna,kolejnosc) VALUES (?,?,?,?)",
            ("Sala A", "sala a", 1, 100),
        ).lastrowid
        room_b = con.execute(
            "INSERT INTO sale_rezerwacyjne "
            "(nazwa,nazwa_klucz,aktywna,kolejnosc) VALUES (?,?,?,?)",
            ("Sala B", "sala b", 1, 101),
        ).lastrowid
        plan_a = con.execute(
            "INSERT INTO plany_sali (sala_id,nazwa) VALUES (?,?)",
            (room_a, "Plan A"),
        ).lastrowid
        plan_b = con.execute(
            "INSERT INTO plany_sali (sala_id,nazwa) VALUES (?,?)",
            (room_b, "Plan B"),
        ).lastrowid
        version_a = con.execute(
            "INSERT INTO wersje_planu_sali "
            "(plan_id,numer,status,rewizja,utworzono_at,zaktualizowano_at,opublikowano_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (plan_a, 1, "published", 0, "2026-07-12 12:00:00",
             "2026-07-12 12:00:00", "2026-07-12 12:00:00"),
        ).lastrowid
        version_b = con.execute(
            "INSERT INTO wersje_planu_sali "
            "(plan_id,numer,status,rewizja,utworzono_at,zaktualizowano_at,opublikowano_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (plan_b, 1, "published", 0, "2026-07-12 12:00:00",
             "2026-07-12 12:00:00", "2026-07-12 12:00:00"),
        ).lastrowid
        table_id = con.execute(
            "INSERT INTO stoliki "
            "(nazwa,strefa,sala_id,pojemnosc,laczy_sie,aktywny,kolejnosc) "
            "VALUES (?,?,?,?,?,?,?)",
            ("S-cross-room", "Sala A", room_a, 4, 0, 1, 100),
        ).lastrowid
        con.executemany(
            "INSERT INTO pozycje_stolikow_planu "
            "(wersja_id,stolik_id,plan_x,plan_y,szerokosc,wysokosc,obrot,aktywny_w_planie) "
            "VALUES (?,?,?,?,?,?,?,?)",
            [
                (version_a, table_id, 20, 20, 12, 12, 0, 1),
                (version_b, table_id, 80, 80, 12, 12, 0, 1),
            ],
        )
        con.execute("DROP TABLE alembic_version")
        con.commit()
    finally:
        con.close()

    adoption = subprocess.run(
        [sys.executable, "-c", "import database; database.init_db()"],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert adoption.returncode != 0
    assert "Backfill R2 jest niekompletny" in (
        adoption.stdout + adoption.stderr
    )


def test_adopcja_r2_odrzuca_niekanoniczny_klucz_nazwy_sali(tmp_path):
    db_file = tmp_path / "_r2_bad_room_key.db"
    env = _env(db_file, "r2-bad-room-key")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import database, models; from sqlalchemy import text; "
                "models.Base.metadata.create_all(database.engine); "
                "conn=database.engine.connect(); tx=conn.begin(); "
                "conn.execute(text(\"INSERT INTO sale_rezerwacyjne "
                "(id,nazwa,nazwa_klucz,aktywna,kolejnosc) "
                "VALUES (1,'Żółta','wrong',1,0)\")); "
                "conn.execute(text(\"INSERT INTO plany_sali (id,sala_id,nazwa) "
                "VALUES (1,1,'Plan główny')\")); "
                "conn.execute(text(\"INSERT INTO wersje_planu_sali "
                "(id,plan_id,numer,status,rewizja,utworzono_at,zaktualizowano_at,opublikowano_at) "
                "VALUES (1,1,1,'published',0,'2026-07-12 12:00:00',"
                "'2026-07-12 12:00:00','2026-07-12 12:00:00')\")); "
                "tx.commit(); conn.close(); database.init_db()"
            ),
        ],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "Backfill R2 jest niekompletny" in (result.stdout + result.stderr)


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
    assert version == HEAD


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
    assert version == HEAD
    assert (table_claims, pacing) == (120, 1)

    resumed = subprocess.run(
        [sys.executable, "-c", "import database; database.init_db()"],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert resumed.returncode == 0, resumed.stderr


def test_adopcja_pelnej_niewersjonowanej_bazy_0051_nie_powtarza_create_ledger(tmp_path):
    """Pełny ledger 0051 bez metryki ma dojść do head bez duplikacji tabel."""
    db_file = tmp_path / "_r0b_adoption.db"
    env = _env(db_file, "r0b-adoption")
    upgraded = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0051_rezerwacje_atomic_ledger"],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert upgraded.returncode == 0, upgraded.stderr
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
        tables = {
            row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        con.close()
    assert version == HEAD
    assert "reservation_audit" in tables

    resumed = subprocess.run(
        [sys.executable, "-c", "import database; database.init_db()"],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert resumed.returncode == 0, resumed.stderr


@pytest.mark.parametrize("drop_version", [False, True])
def test_adopcja_odrzuca_falszywa_tabele_audytu(tmp_path, drop_version):
    """Ani 0051, ani pełna baza bez metryki nie mogą ostemplować atrap ograniczeń 0052."""
    db_file = tmp_path / f"_fake_audit_{drop_version}.db"
    env = _env(db_file, f"fake-audit-{drop_version}")
    upgraded = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0051_rezerwacje_atomic_ledger"],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert upgraded.returncode == 0, upgraded.stderr
    _create_fake_audit_schema(db_file, drop_version=drop_version)

    adoption = subprocess.run(
        [sys.executable, "-c", "import database; database.init_db()"],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert adoption.returncode != 0
    assert "reservation_audit" in (adoption.stdout + adoption.stderr)

    con = sqlite3.connect(str(db_file))
    try:
        tables = {
            row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        version = (
            con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            if "alembic_version" in tables else None
        )
    finally:
        con.close()
    assert version in {None, "0051_rezerwacje_atomic_ledger"}


def test_recovery_0050_z_ledgerem_konczy_head_w_pierwszym_starcie(tmp_path):
    """Crash między create_all ledgera i stemplem nie może wymagać drugiego restartu."""
    db_file = tmp_path / "_r0b_crash_recovery.db"
    env = _env(db_file, "r0b-crash-recovery")
    upgraded = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0050_rezerwacje_source_identity"],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert upgraded.returncode == 0, upgraded.stderr
    create_ledger = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import database; "
                "names=('rezerwacje_idempotencja','rezerwacje_dni_ledger',"
                "'rezerwacje_stoliki_claims','rezerwacje_pacing_ledger'); "
                "[database.Base.metadata.tables[name].create(database.engine) for name in names]"
            ),
        ],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert create_ledger.returncode == 0, create_ledger.stderr

    recovery = subprocess.run(
        [sys.executable, "-c", "import database; database.init_db()"],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert recovery.returncode == 0, recovery.stderr
    con = sqlite3.connect(str(db_file))
    try:
        version = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        tables = {
            row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        con.close()
    assert version == HEAD
    assert "reservation_audit" in tables


def test_brak_alembica_fail_closed_a_kolejny_start_dochodzi_do_head(tmp_path):
    db_file = tmp_path / "_pre_r0b_without_alembic.db"
    env = _env(db_file, "pre-r0b-fallback")
    upgraded = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0050_rezerwacje_source_identity"],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert upgraded.returncode == 0, upgraded.stderr
    _insert_active_0050_reservation(db_file)
    con = sqlite3.connect(str(db_file))
    try:
        con.execute(
            "INSERT INTO audit_log (ts, akcja, zasob) VALUES (?, ?, ?)",
            ("2026-07-11 10:00:00", "rodo_anonimizuj_gosc", "600100200"),
        )
        con.commit()
    finally:
        con.close()

    fallback = subprocess.run(
        [
            sys.executable,
            "-c",
            "import database; database._alembic_run=lambda action: False; database.init_db()",
        ],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert fallback.returncode != 0
    assert "R2_MIGRATION_REQUIRES_ALEMBIC" in (fallback.stdout + fallback.stderr)
    con = sqlite3.connect(str(db_file))
    try:
        version = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        rodo_resource = con.execute(
            "SELECT zasob FROM audit_log WHERE akcja='rodo_anonimizuj_gosc'"
        ).fetchone()[0]
    finally:
        con.close()
    assert version == "0050_rezerwacje_source_identity"
    assert rodo_resource == "[redacted]"

    resumed = subprocess.run(
        [sys.executable, "-c", "import database; database.init_db()"],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert resumed.returncode == 0, resumed.stderr
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
    assert version == HEAD
    assert (table_claims, pacing) == (120, 1)


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


def test_adopcja_legacy_bez_alembica_fail_closed_i_wznawia_z_alembikiem(tmp_path):
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
    assert fallback.returncode != 0
    assert "R2_MIGRATION_REQUIRES_ALEMBIC" in (fallback.stdout + fallback.stderr)

    resumed = subprocess.run(
        [sys.executable, "-c", "import database; database.init_db()"],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert resumed.returncode == 0, resumed.stderr
    con = sqlite3.connect(str(db_file))
    try:
        columns = {row[1] for row in con.execute("PRAGMA table_info(terminy)")}
        indexes = {row[1] for row in con.execute("PRAGMA index_list(terminy)")}
        version = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    finally:
        con.close()
    assert {"source_type", "source_external_id"} <= columns
    assert "uq_terminy_source_identity" in indexes
    assert version == HEAD


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
