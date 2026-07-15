"""Strażnik anti-drift model↔migracja. conftest robi create_all → maskuje rozjazd migracji z modelem.
Ten test buduje bazę PRZEZ Alembic (upgrade head) i porównuje kolumny kluczowych tabel z modelem —
to jedyny sposób złapać drift, którego create_all nie pokaże (np. osierocone/brakujące pole)."""

import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import database
import models
import pytest

BACKEND = Path(__file__).resolve().parent.parent
HEAD = "0060_r4_allocator_core"

# Tabele pod nadzorem (rozszerzane w rezerwacjach; drift tu najgroźniejszy).
_TABELE = [
    "lokal_config", "wyjatki_kalendarza", "godziny_otwarcia", "stoliki", "kombinacje_stolow",
    "terminy", "profile_gosci", "rejestracje_lokalu", "lista_oczekujacych",
    "rezerwacje_idempotencja", "rezerwacje_dni_ledger", "rezerwacje_stoliki_claims",
    "rezerwacje_pacing_ledger", "reservation_audit", "users",
    "sale_rezerwacyjne", "plany_sali", "wersje_planu_sali",
    "pozycje_stolikow_planu", "krawedzie_sasiedztwa_planu",
    "kombinacje_stolow_planu", "skladniki_kombinacji_planu",
    "reguly_dostepnosci_rezerwacji", "rezerwacje_oblozenie_ledger",
    "reservation_override_context",
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


def _insert_valid_r22_topology(con):
    version_id = con.execute(
        "SELECT pos.wersja_id FROM pozycje_stolikow_planu pos "
        "JOIN wersje_planu_sali w ON w.id=pos.wersja_id "
        "WHERE pos.stolik_id=1 AND w.status='published'"
    ).fetchone()[0]
    assert con.execute(
        "SELECT count(*) FROM pozycje_stolikow_planu "
        "WHERE wersja_id=? AND stolik_id IN (1,2)",
        (version_id,),
    ).fetchone()[0] == 2
    con.execute(
        "INSERT INTO krawedzie_sasiedztwa_planu "
        "(wersja_id,stolik_a_id,stolik_b_id) VALUES (?,?,?)",
        (version_id, 1, 2),
    )
    combination_id = con.execute(
        "INSERT INTO kombinacje_stolow_planu "
        "(wersja_id,nazwa,sklad_klucz,pojemnosc_min,pojemnosc_max,"
        " priorytet,kanal,aktywna_w_planie) VALUES (?,?,?,?,?,?,?,?)",
        (version_id, "S1 + S2", "1,2", 5, 8, 0, "oba", 1),
    ).lastrowid
    con.executemany(
        "INSERT INTO skladniki_kombinacji_planu "
        "(kombinacja_id,wersja_id,stolik_id) VALUES (?,?,?)",
        [(combination_id, version_id, 1), (combination_id, version_id, 2)],
    )
    con.commit()
    return version_id, combination_id


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
        "pozycje_stolikow_planu", "krawedzie_sasiedztwa_planu",
        "kombinacje_stolow_planu", "skladniki_kombinacji_planu",
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


def test_migracja_0057_backfilluje_topologie_i_round_tripuje_published(tmp_path):
    db_file = tmp_path / "_r22_topology_round_trip.db"
    env = _prepare_r2_0052(db_file)
    con = sqlite3.connect(str(db_file))
    try:
        con.execute(
            "UPDATE stoliki SET pojemnosc_min=?, ksztalt=?, cechy=?, priorytet=?, sekcja=? "
            "WHERE id=1",
            (2, "okragly", '["okno"]', 4, "A"),
        )
        con.execute(
            "INSERT INTO sasiedztwo_stolow (stolik_a, stolik_b) VALUES (?, ?)",
            (1, 2),
        )
        con.execute(
            "INSERT INTO kombinacje_stolow "
            "(nazwa, stoliki, pojemnosc_min, pojemnosc_max, aktywna, priorytet) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("S1 + S2", "[1, 2]", 5, 8, 1, 3),
        )
        con.commit()
    finally:
        con.close()

    upgraded = _alembic(env, "upgrade", HEAD)
    assert upgraded.returncode == 0, upgraded.stderr
    con = sqlite3.connect(str(db_file))
    try:
        properties = con.execute(
            "SELECT nazwa, kolejnosc, pojemnosc, pojemnosc_min, ksztalt, cechy, "
            "priorytet, sekcja FROM pozycje_stolikow_planu WHERE stolik_id=1"
        ).fetchall()
        edges = con.execute(
            "SELECT e.stolik_a_id, e.stolik_b_id "
            "FROM krawedzie_sasiedztwa_planu e "
            "JOIN wersje_planu_sali w ON w.id=e.wersja_id "
            "WHERE w.status='published'"
        ).fetchall()
        combinations = con.execute(
            "SELECT k.nazwa, k.sklad_klucz, k.pojemnosc_min, k.pojemnosc_max, "
            "k.priorytet, k.kanal, k.aktywna_w_planie, "
            "group_concat(s.stolik_id, ',') "
            "FROM kombinacje_stolow_planu k "
            "JOIN wersje_planu_sali w ON w.id=k.wersja_id "
            "JOIN skladniki_kombinacji_planu s ON s.kombinacja_id=k.id "
            "WHERE w.status='published' GROUP BY k.id"
        ).fetchall()
        fk_errors = con.execute("PRAGMA foreign_key_check").fetchall()
        con.execute(
            "UPDATE pozycje_stolikow_planu SET "
            "nazwa=?, kolejnosc=?, pojemnosc=?, pojemnosc_min=?, ksztalt=?, "
            "cechy=?, priorytet=?, sekcja=? "
            "WHERE stolik_id=1 AND wersja_id IN ("
            "  SELECT id FROM wersje_planu_sali WHERE status='published'"
            ")",
            ("S1 VIP", 7, 6, 3, "prostokat", '["okno", "vip"]', 9, "VIP"),
        )
        con.commit()
    finally:
        con.close()
    assert properties == [("S1", 0, 4, 2, "okragly", '["okno"]', 4, "A")]
    assert edges == [(1, 2)]
    assert combinations == [("S1 + S2", "1,2", 5, 8, 3, "oba", 1, "1,2")]
    assert fk_errors == []

    downgraded = _alembic(env, "downgrade", "0056_impreza_sale_min2_neutralny")
    assert downgraded.returncode == 0, downgraded.stderr
    con = sqlite3.connect(str(db_file))
    try:
        position_columns = {
            row[1] for row in con.execute("PRAGMA table_info(pozycje_stolikow_planu)")
        }
        legacy_edges = con.execute(
            "SELECT stolik_a, stolik_b FROM sasiedztwo_stolow"
        ).fetchall()
        legacy_combination = con.execute(
            "SELECT nazwa, stoliki, pojemnosc_min, pojemnosc_max, aktywna, priorytet "
            "FROM kombinacje_stolow"
        ).fetchall()
        legacy_properties = con.execute(
            "SELECT nazwa,kolejnosc,pojemnosc,pojemnosc_min,ksztalt,cechy,"
            "priorytet,sekcja,plan_x,plan_y FROM stoliki WHERE id=1"
        ).fetchone()
        version = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    finally:
        con.close()
    assert not {
        "nazwa", "kolejnosc", "pojemnosc", "pojemnosc_min", "ksztalt",
        "cechy", "priorytet", "sekcja",
    } & position_columns
    assert legacy_edges == [(1, 2)]
    assert legacy_combination == [("S1 + S2", "[1, 2]", 5, 8, 1, 3)]
    assert legacy_properties == (
        "S1 VIP", 7, 6, 3, "prostokat", '["okno", "vip"]', 9, "VIP", 12, 34,
    )
    assert version == "0056_impreza_sale_min2_neutralny"

    upgraded_again = _alembic(env, "upgrade", HEAD)
    assert upgraded_again.returncode == 0, upgraded_again.stderr
    con = sqlite3.connect(str(db_file))
    try:
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
        assert con.execute(
            "SELECT count(*) FROM kombinacje_stolow_planu"
        ).fetchone()[0] == 1
        assert con.execute(
            "SELECT nazwa,kolejnosc,pojemnosc,pojemnosc_min,ksztalt,cechy,"
            "priorytet,sekcja FROM pozycje_stolikow_planu WHERE stolik_id=1"
        ).fetchone() == (
            "S1 VIP", 7, 6, 3, "prostokat", '["okno", "vip"]', 9, "VIP",
        )
    finally:
        con.close()


def test_migracja_0058_strategia_i_proweniencja_round_trip(tmp_path):
    db_file = tmp_path / "_r22b_strategy_provenance.db"
    env = _prepare_r2_0052(db_file)
    upgraded_0057 = _alembic(env, "upgrade", "0057_r22_topologia_planu")
    assert upgraded_0057.returncode == 0, upgraded_0057.stderr

    con = sqlite3.connect(str(db_file))
    try:
        version_id, combination_id = _insert_valid_r22_topology(con)
        other_version_id = con.execute(
            "SELECT id FROM wersje_planu_sali WHERE id<>? ORDER BY id LIMIT 1",
            (version_id,),
        ).fetchone()[0]
        room_id = con.execute(
            "SELECT id FROM sale_rezerwacyjne ORDER BY id LIMIT 1"
        ).fetchone()[0]
        con.execute(
            "UPDATE sale_rezerwacyjne SET kolejnosc=7 WHERE id=?", (room_id,)
        )
        con.execute(
            "INSERT INTO terminy (data,nazwisko,status,zadatek,kanal,rodzaj) "
            "VALUES ('2030-01-03','Historyczny','potwierdzona',0,'reczna','stolik')"
        )
        termin_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
        con.commit()
    finally:
        con.close()

    upgraded = _alembic(env, "upgrade", HEAD)
    assert upgraded.returncode == 0, upgraded.stderr
    con = sqlite3.connect(str(db_file))
    try:
        con.execute("PRAGMA foreign_keys=ON")
        assert con.execute(
            "SELECT strategia_zapelniania,priorytet FROM sale_rezerwacyjne WHERE id=?",
            (room_id,),
        ).fetchone() == ("preferuj", 7)
        assert con.execute(
            "SELECT przydzial_wersja_planu_id,przydzial_kombinacja_planu_id "
            "FROM terminy WHERE id=?",
            (termin_id,),
        ).fetchone() == (None, None)
        con.execute(
            "UPDATE terminy SET przydzial_wersja_planu_id=?, "
            "przydzial_kombinacja_planu_id=? WHERE id=?",
            (version_id, combination_id, termin_id),
        )
        con.commit()
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                "UPDATE terminy SET przydzial_wersja_planu_id=? WHERE id=?",
                (other_version_id, termin_id),
            )
        con.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                "UPDATE terminy SET przydzial_wersja_planu_id=999999 WHERE id=?",
                (termin_id,),
            )
        con.rollback()
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        con.close()

    downgraded = _alembic(env, "downgrade", "0057_r22_topologia_planu")
    assert downgraded.returncode == 0, downgraded.stderr
    con = sqlite3.connect(str(db_file))
    try:
        room_columns = {
            row[1] for row in con.execute("PRAGMA table_info(sale_rezerwacyjne)")
        }
        termin_columns = {row[1] for row in con.execute("PRAGMA table_info(terminy)")}
        assert not {"strategia_zapelniania", "priorytet"} & room_columns
        assert not {
            "przydzial_wersja_planu_id", "przydzial_kombinacja_planu_id",
        } & termin_columns
    finally:
        con.close()

    upgraded_again = _alembic(env, "upgrade", HEAD)
    assert upgraded_again.returncode == 0, upgraded_again.stderr


def test_migracja_0059_backfilluje_roomless_oblozenie_i_rozdziela_czas(tmp_path):
    db_file = tmp_path / "_r3_rules_occupancy.db"
    env = _env(db_file, "r3-rules-occupancy")
    upgraded_0058 = _alembic(env, "upgrade", "0058_r22b_strategia_proweniencja")
    assert upgraded_0058.returncode == 0, upgraded_0058.stderr

    con = sqlite3.connect(str(db_file))
    try:
        con.execute("PRAGMA foreign_keys=ON")
        con.execute(
            "INSERT INTO godziny_otwarcia "
            "(id,dzien_tygodnia,godz_od,godz_do,dlugosc_slotu_min,aktywny) "
            "VALUES (1,2,'12:00:00','23:00:00',90,1)"
        )
        # Historyczny stolik bez sali pozostaje legalny dla globalnych limitow R3.
        con.execute(
            "INSERT INTO stoliki "
            "(id,nazwa,pojemnosc,laczy_sie,aktywny,kolejnosc,sala_id) "
            "VALUES (1,'Legacy roomless',4,0,1,0,NULL)"
        )
        con.execute(
            "INSERT INTO terminy "
            "(id,data,nazwisko,liczba_osob,status,zadatek,godz_od,godz_do,"
            "kanal,rodzaj,stolik_id) VALUES "
            "(1,'2030-01-02','Historyczny',4,'potwierdzona',0,"
            "'18:00:00','19:30:00','reczna','stolik',1)"
        )
        con.execute(
            "INSERT INTO rezerwacje_pacing_ledger "
            "(termin_id,data,start_minute,covers,override,created_at) VALUES "
            "(1,'2030-01-02',1080,4,0,'2026-07-15 12:00:00')"
        )
        con.commit()
    finally:
        con.close()

    upgraded = _alembic(env, "upgrade", HEAD)
    assert upgraded.returncode == 0, upgraded.stderr
    con = sqlite3.connect(str(db_file))
    try:
        split = con.execute(
            "SELECT krok_slotu_min,domyslny_turn_time_min "
            "FROM godziny_otwarcia WHERE id=1"
        ).fetchone()
        occupancy = con.execute(
            "SELECT count(*),min(minute),max(minute),min(sala_id),min(kanal),"
            "min(covers) FROM rezerwacje_oblozenie_ledger WHERE termin_id=1"
        ).fetchone()
        version = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        tables = {
            row[0] for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        con.close()
    assert split == (90, 90)
    assert occupancy == (90, 1080, 1169, None, "wewnetrzna", 4)
    assert version == HEAD
    assert {
        "reguly_dostepnosci_rezerwacji",
        "rezerwacje_oblozenie_ledger",
        "reservation_override_context",
    } <= tables

    downgraded = _alembic(env, "downgrade", "0058_r22b_strategia_proweniencja")
    assert downgraded.returncode == 0, downgraded.stderr
    con = sqlite3.connect(str(db_file))
    try:
        service_columns = {
            row[1] for row in con.execute("PRAGMA table_info(godziny_otwarcia)")
        }
        tables = {
            row[0] for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    finally:
        con.close()
    assert not {"krok_slotu_min", "domyslny_turn_time_min"} & service_columns
    assert not {
        "reguly_dostepnosci_rezerwacji",
        "rezerwacje_oblozenie_ledger",
        "reservation_override_context",
    } & tables

    upgraded_again = _alembic(env, "upgrade", HEAD)
    assert upgraded_again.returncode == 0, upgraded_again.stderr


def test_migracja_0059_nie_zamyka_legacy_online_bez_serwisow(tmp_path):
    db_file = tmp_path / "_r3_legacy_online_services.db"
    env = _env(db_file, "r3-legacy-online-services")
    upgraded_0058 = _alembic(env, "upgrade", "0058_r22b_strategia_proweniencja")
    assert upgraded_0058.returncode == 0, upgraded_0058.stderr

    con = sqlite3.connect(str(db_file))
    try:
        con.execute(
            "INSERT INTO lokal_config "
            "(id,nazwa_lokalu,poczatek_tygodnia,modul_rozliczenia,modul_imprezy,"
            "modul_pos,modul_sprzatanie,rezerwacje_online) "
            "VALUES (1,'Legacy online',0,0,0,0,0,1)"
        )
        assert con.execute("SELECT count(*) FROM godziny_otwarcia").fetchone()[0] == 0
        con.commit()
    finally:
        con.close()

    upgraded = _alembic(env, "upgrade", HEAD)
    assert upgraded.returncode == 0, upgraded.stderr
    con = sqlite3.connect(str(db_file))
    try:
        rows = con.execute(
            "SELECT dzien_tygodnia,godz_od,godz_do,ostatni_zasiadek,"
            "krok_slotu_min,domyslny_turn_time_min,nazwa "
            "FROM godziny_otwarcia ORDER BY dzien_tygodnia"
        ).fetchall()
    finally:
        con.close()
    assert len(rows) == 7
    assert [row[0] for row in rows] == list(range(7))
    assert all(
        row[1].startswith("00:00:00")
        and row[2].startswith("23:59:00")
        and row[3].startswith("21:59:00")
        and row[4:6] == (120, 120)
        for row in rows
    )
    assert {row[6] for row in rows} == {"Cały dzień · zgodność R3"}

    downgraded = _alembic(env, "downgrade", "0058_r22b_strategia_proweniencja")
    assert downgraded.returncode == 0, downgraded.stderr
    con = sqlite3.connect(str(db_file))
    try:
        assert con.execute("SELECT count(*) FROM godziny_otwarcia").fetchone()[0] == 0
    finally:
        con.close()


@pytest.mark.parametrize(("mutation", "verification", "expected"), [
    (
        "UPDATE godziny_otwarcia SET max_jednoczesnych_rez=3 "
        "WHERE dzien_tygodnia=0",
        "SELECT max_jednoczesnych_rez FROM godziny_otwarcia "
        "WHERE dzien_tygodnia=0",
        3,
    ),
    (
        "INSERT INTO sale_rezerwacyjne "
        "(nazwa,aktywna,kolejnosc,online_aktywna) "
        "VALUES ('Sala z polityka R3',1,0,0)",
        "SELECT online_aktywna FROM sale_rezerwacyjne "
        "WHERE nazwa='Sala z polityka R3'",
        0,
    ),
])
def test_migracja_0059_blokuje_downgrade_z_utrata_konfiguracji(
    tmp_path, mutation, verification, expected,
):
    db_file = tmp_path / "_r3_unsafe_downgrade.db"
    env = _env(db_file, "r3-unsafe-downgrade")
    upgraded_0058 = _alembic(env, "upgrade", "0058_r22b_strategia_proweniencja")
    assert upgraded_0058.returncode == 0, upgraded_0058.stderr

    con = sqlite3.connect(str(db_file))
    try:
        con.execute(
            "INSERT INTO lokal_config "
            "(id,nazwa_lokalu,poczatek_tygodnia,modul_rozliczenia,modul_imprezy,"
            "modul_pos,modul_sprzatanie,rezerwacje_online) "
            "VALUES (1,'Legacy online',0,0,0,0,0,1)"
        )
        con.commit()
    finally:
        con.close()

    upgraded = _alembic(env, "upgrade", HEAD)
    assert upgraded.returncode == 0, upgraded.stderr
    con = sqlite3.connect(str(db_file))
    try:
        con.execute(mutation)
        con.commit()
    finally:
        con.close()

    downgraded = _alembic(env, "downgrade", "0058_r22b_strategia_proweniencja")
    assert downgraded.returncode != 0
    assert "R3_DOWNGRADE_CONFIGURATION_LOSS" in downgraded.stderr
    con = sqlite3.connect(str(db_file))
    try:
        assert con.execute(verification).fetchone()[0] == expected
        # 0060 nie zawiera danych R4 w tym scenariuszu, więc jego downgrade
        # kończy się poprawnie. Dopiero ochronny downgrade 0059 zatrzymuje
        # operację i pozostawia bazę dokładnie na tej rewizji.
        assert con.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0] == "0059_r3_reguly_dostepnosci"
    finally:
        con.close()


def test_migracja_0059_zachowuje_edytowany_legacy_pacing_przy_downgrade(tmp_path):
    db_file = tmp_path / "_r3_legacy_pacing_downgrade.db"
    env = _env(db_file, "r3-legacy-pacing-downgrade")
    upgraded_0058 = _alembic(env, "upgrade", "0058_r22b_strategia_proweniencja")
    assert upgraded_0058.returncode == 0, upgraded_0058.stderr

    con = sqlite3.connect(str(db_file))
    try:
        con.execute(
            "INSERT INTO lokal_config "
            "(id,nazwa_lokalu,poczatek_tygodnia,modul_rozliczenia,modul_imprezy,"
            "modul_pos,modul_sprzatanie,rezerwacje_online) "
            "VALUES (1,'Legacy online',0,0,0,0,0,1)"
        )
        con.commit()
    finally:
        con.close()

    upgraded = _alembic(env, "upgrade", HEAD)
    assert upgraded.returncode == 0, upgraded.stderr
    con = sqlite3.connect(str(db_file))
    try:
        con.execute(
            "UPDATE godziny_otwarcia SET pacing_max_rez=3 WHERE dzien_tygodnia=0"
        )
        con.commit()
    finally:
        con.close()

    downgraded = _alembic(env, "downgrade", "0058_r22b_strategia_proweniencja")
    assert downgraded.returncode == 0, downgraded.stderr
    con = sqlite3.connect(str(db_file))
    try:
        assert con.execute("SELECT count(*) FROM godziny_otwarcia").fetchone()[0] == 7
        assert con.execute(
            "SELECT pacing_max_rez FROM godziny_otwarcia WHERE dzien_tygodnia=0"
        ).fetchone()[0] == 3
    finally:
        con.close()


def test_adopcja_pelnego_create_all_r3_stampuje_0059(tmp_path):
    db_file = tmp_path / "_r3_create_all_adoption.db"
    env = _env(db_file, "r3-create-all-adoption")
    created = subprocess.run(
        [
            sys.executable,
            "-c",
            "import database, models; models.Base.metadata.create_all(database.engine)",
        ],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert created.returncode == 0, created.stderr

    # Create-all nie wykonuje backfillu. Adopcja peĹ‚nego, niewersjonowanego R3
    # musi odbudowaÄ‡ oba ledgery przed bezpiecznym stemplem 0059.
    con = sqlite3.connect(str(db_file))
    try:
        con.execute(
            "INSERT INTO terminy "
            "(id,data,nazwisko,liczba_osob,status,zadatek,utworzono_at,godz_od,godz_do,"
            "kanal,rodzaj) VALUES "
            "(1,'2030-01-02','Recovery',3,'potwierdzona',0,"
            "'2026-07-15 12:00:00','18:00:00','19:30:00','reczna','stolik')"
        )
        con.commit()
    finally:
        con.close()

    adopted = subprocess.run(
        [sys.executable, "-c", "import database; database.init_db()"],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert adopted.returncode == 0, adopted.stderr
    con = sqlite3.connect(str(db_file))
    try:
        version = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        pacing = con.execute(
            "SELECT count(*),min(start_minute),min(covers) "
            "FROM rezerwacje_pacing_ledger WHERE termin_id=1"
        ).fetchone()
        occupancy = con.execute(
            "SELECT count(*),min(minute),max(minute),min(sala_id),min(covers) "
            "FROM rezerwacje_oblozenie_ledger WHERE termin_id=1"
        ).fetchone()
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        con.close()
    assert version == HEAD
    assert pacing == (1, 1080, 3)
    assert occupancy == (90, 1080, 1169, None, 3)


def test_adopcja_pelnej_niewersjonowanej_bazy_0058_wykonuje_upgrade_r3(tmp_path):
    db_file = tmp_path / "_r3_adopt_0058.db"
    env = _env(db_file, "r3-adopt-0058")
    upgraded = _alembic(env, "upgrade", "0058_r22b_strategia_proweniencja")
    assert upgraded.returncode == 0, upgraded.stderr
    con = sqlite3.connect(str(db_file))
    try:
        con.execute("DROP TABLE alembic_version")
        con.commit()
    finally:
        con.close()

    adopted = subprocess.run(
        [sys.executable, "-c", "import database; database.init_db()"],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert adopted.returncode == 0, adopted.stderr
    con = sqlite3.connect(str(db_file))
    try:
        version = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        tables = {
            row[0] for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    finally:
        con.close()
    assert version == HEAD
    assert _TABELE[-3:] == [
        "reguly_dostepnosci_rezerwacji",
        "rezerwacje_oblozenie_ledger",
        "reservation_override_context",
    ]
    assert set(_TABELE[-3:]) <= tables


def test_migracja_0057_downgrade_zachowuje_topologie_niewersjonowanej_sali(tmp_path):
    db_file = tmp_path / "_r22_unversioned_legacy_downgrade.db"
    env = _prepare_r2_0052(db_file)
    upgraded = _alembic(env, "upgrade", HEAD)
    assert upgraded.returncode == 0, upgraded.stderr

    con = sqlite3.connect(str(db_file))
    try:
        con.execute(
            "INSERT INTO sale_rezerwacyjne "
            "(id,nazwa,nazwa_klucz,aktywna,kolejnosc) VALUES (?,?,?,?,?)",
            (901, "Sala legacy", "sala legacy", 1, 99),
        )
        con.executemany(
            "INSERT INTO stoliki "
            "(id,nazwa,strefa,sala_id,pojemnosc,laczy_sie,aktywny,kolejnosc) "
            "VALUES (?,?,?,?,?,?,?,?)",
            [
                (901, "L1", "Sala legacy", 901, 4, 1, 1, 0),
                (902, "L2", "Sala legacy", 901, 4, 1, 1, 1),
            ],
        )
        con.execute(
            "INSERT INTO sasiedztwo_stolow (stolik_a,stolik_b) VALUES (?,?)",
            (901, 902),
        )
        con.execute(
            "INSERT INTO kombinacje_stolow "
            "(nazwa,stoliki,pojemnosc_min,pojemnosc_max,aktywna,priorytet) "
            "VALUES (?,?,?,?,?,?)",
            ("L1 + L2", "[901, 902]", 5, 8, 1, 7),
        )
        con.commit()
    finally:
        con.close()

    downgraded = _alembic(env, "downgrade", "0056_impreza_sale_min2_neutralny")
    assert downgraded.returncode == 0, downgraded.stderr

    con = sqlite3.connect(str(db_file))
    try:
        assert con.execute(
            "SELECT stolik_a,stolik_b FROM sasiedztwo_stolow "
            "WHERE stolik_a=901 AND stolik_b=902"
        ).fetchall() == [(901, 902)]
        assert con.execute(
            "SELECT nazwa,stoliki,pojemnosc_min,pojemnosc_max,aktywna,priorytet "
            "FROM kombinacje_stolow WHERE nazwa='L1 + L2'"
        ).fetchall() == [("L1 + L2", "[901, 902]", 5, 8, 1, 7)]
    finally:
        con.close()


def test_migracja_0057_domykaja_graf_minimalnie_i_dezaktywuje_zestaw_per_wersja(
    tmp_path,
):
    db_file = tmp_path / "_r22_legacy_combination_graph.db"
    env = _prepare_r2_0052(db_file)
    con = sqlite3.connect(str(db_file))
    try:
        room_name = con.execute(
            "SELECT strefa FROM stoliki WHERE id=2"
        ).fetchone()[0]
        con.execute(
            "INSERT INTO stoliki "
            "(id,nazwa,strefa,pojemnosc,laczy_sie,aktywny,kolejnosc) "
            "VALUES (?,?,?,?,?,?,?)",
            (4, "S4", room_name, 4, 1, 1, 3),
        )
        con.execute("UPDATE stoliki SET aktywny=0 WHERE id=2")
        con.execute(
            "INSERT INTO sasiedztwo_stolow (stolik_a,stolik_b) VALUES (?,?)",
            (1, 4),
        )
        con.execute(
            "INSERT INTO kombinacje_stolow "
            "(nazwa,stoliki,pojemnosc_min,pojemnosc_max,aktywna,priorytet) "
            "VALUES (?,?,?,?,?,?)",
            ("S1 + S2 + S4", "[1, 2, 4]", 7, 12, 1, 0),
        )
        con.commit()
    finally:
        con.close()

    upgraded = _alembic(env, "upgrade", HEAD)
    assert upgraded.returncode == 0, upgraded.stderr
    con = sqlite3.connect(str(db_file))
    try:
        edges = con.execute(
            "SELECT e.stolik_a_id,e.stolik_b_id "
            "FROM krawedzie_sasiedztwa_planu e "
            "JOIN wersje_planu_sali w ON w.id=e.wersja_id "
            "JOIN pozycje_stolikow_planu p ON p.wersja_id=w.id AND p.stolik_id=4 "
            "WHERE w.status='published' ORDER BY e.stolik_a_id,e.stolik_b_id"
        ).fetchall()
        combination = con.execute(
            "SELECT k.sklad_klucz,k.aktywna_w_planie "
            "FROM kombinacje_stolow_planu k "
            "JOIN wersje_planu_sali w ON w.id=k.wersja_id "
            "WHERE w.status='published' AND k.sklad_klucz='1,2,4'"
        ).fetchone()
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        con.close()

    # Istniejaca krawedz 1-4 tworzy jedna skladowa; migracja dodaje tylko 1-2.
    assert edges == [(1, 2), (1, 4)]
    assert combination == ("1,2,4", 0)


def test_migracja_0057_odrzuca_krawedz_miedzy_salami_przed_ddl(tmp_path):
    db_file = tmp_path / "_r22_cross_room_edge.db"
    env = _prepare_r2_0052(db_file)
    con = sqlite3.connect(str(db_file))
    try:
        con.execute(
            "INSERT INTO sasiedztwo_stolow (stolik_a, stolik_b) VALUES (?, ?)",
            (1, 3),
        )
        con.commit()
    finally:
        con.close()
    base = _alembic(env, "upgrade", "0056_impreza_sale_min2_neutralny")
    assert base.returncode == 0, base.stderr

    failed = _alembic(env, "upgrade", HEAD)
    assert failed.returncode != 0
    assert "R22_MIGRATION_CROSS_ROOM_EDGE" in failed.stderr
    con = sqlite3.connect(str(db_file))
    try:
        position_columns = {
            row[1] for row in con.execute("PRAGMA table_info(pozycje_stolikow_planu)")
        }
        topology_tables = {
            row[0] for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        version = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    finally:
        con.close()
    assert "nazwa" not in position_columns
    assert "krawedzie_sasiedztwa_planu" not in topology_tables
    assert version == "0056_impreza_sale_min2_neutralny"


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


def test_adopcja_r22_waliduje_semantyke_topologii_i_prosty_fk_krawedzi(tmp_path):
    base_file = tmp_path / "_r22_adoption_valid_base.db"
    base_env = _prepare_r2_0052(base_file)
    upgraded = _alembic(base_env, "upgrade", HEAD)
    assert upgraded.returncode == 0, upgraded.stderr
    con = sqlite3.connect(str(base_file))
    try:
        version_id, combination_id = _insert_valid_r22_topology(con)
    finally:
        con.close()

    # Kontrola dodatnia: identyczna, kompletna baza bez metryki Alembica ma byc
    # bezpiecznie adoptowana przed testami celowych uszkodzen.
    valid_file = tmp_path / "_r22_adoption_valid.db"
    shutil.copy2(base_file, valid_file)
    con = sqlite3.connect(str(valid_file))
    try:
        con.execute("DROP TABLE alembic_version")
        con.commit()
    finally:
        con.close()
    valid_adoption = subprocess.run(
        [sys.executable, "-c", "import database; database.init_db()"],
        cwd=str(BACKEND), env=_env(valid_file, "r22-valid-adoption"),
        capture_output=True, text=True,
    )
    assert valid_adoption.returncode == 0, valid_adoption.stderr

    corruptions = {
        "noncanonical-key": (
            "UPDATE kombinacje_stolow_planu SET sklad_klucz='2,1' WHERE id=?",
            (combination_id,),
        ),
        "disconnected-combination": (
            "DELETE FROM krawedzie_sasiedztwa_planu WHERE wersja_id=?",
            (version_id,),
        ),
        "capacity-above-physical": (
            "UPDATE kombinacje_stolow_planu SET pojemnosc_max=99 WHERE id=?",
            (combination_id,),
        ),
        "active-combination-with-inactive-table": (
            "UPDATE pozycje_stolikow_planu SET aktywny_w_planie=0 "
            "WHERE wersja_id=? AND stolik_id=2",
            (version_id,),
        ),
    }
    for name, (statement, params) in corruptions.items():
        db_file = tmp_path / f"_r22_adoption_{name}.db"
        shutil.copy2(base_file, db_file)
        con = sqlite3.connect(str(db_file))
        try:
            con.execute(statement, params)
            con.execute("DROP TABLE alembic_version")
            con.commit()
        finally:
            con.close()
        adoption = subprocess.run(
            [sys.executable, "-c", "import database; database.init_db()"],
            cwd=str(BACKEND), env=_env(db_file, f"r22-{name}"),
            capture_output=True, text=True,
        )
        assert adoption.returncode != 0, name
        assert "Backfill R2 jest niekompletny" in (
            adoption.stdout + adoption.stderr
        ), name

    missing_fk_file = tmp_path / "_r22_adoption_missing_edge_version_fk.db"
    shutil.copy2(base_file, missing_fk_file)
    con = sqlite3.connect(str(missing_fk_file))
    try:
        con.execute("PRAGMA foreign_keys=OFF")
        con.execute(
            """CREATE TABLE krawedzie_sasiedztwa_planu_new (
                id INTEGER NOT NULL,
                wersja_id INTEGER NOT NULL,
                stolik_a_id INTEGER NOT NULL,
                stolik_b_id INTEGER NOT NULL,
                PRIMARY KEY (id),
                CONSTRAINT ck_krawedzie_sasiedztwa_planu_kolejnosc CHECK (stolik_a_id < stolik_b_id),
                CONSTRAINT fk_krawedzie_sasiedztwa_planu_stolik_a FOREIGN KEY(wersja_id, stolik_a_id) REFERENCES pozycje_stolikow_planu (wersja_id, stolik_id) ON DELETE CASCADE,
                CONSTRAINT fk_krawedzie_sasiedztwa_planu_stolik_b FOREIGN KEY(wersja_id, stolik_b_id) REFERENCES pozycje_stolikow_planu (wersja_id, stolik_id) ON DELETE CASCADE,
                CONSTRAINT uq_krawedzie_sasiedztwa_planu_para UNIQUE (wersja_id, stolik_a_id, stolik_b_id)
            )"""
        )
        con.execute(
            "INSERT INTO krawedzie_sasiedztwa_planu_new "
            "SELECT * FROM krawedzie_sasiedztwa_planu"
        )
        con.execute("DROP TABLE krawedzie_sasiedztwa_planu")
        con.execute(
            "ALTER TABLE krawedzie_sasiedztwa_planu_new "
            "RENAME TO krawedzie_sasiedztwa_planu"
        )
        con.execute(
            "CREATE INDEX ix_krawedzie_sasiedztwa_planu_id "
            "ON krawedzie_sasiedztwa_planu (id)"
        )
        con.execute(
            "CREATE INDEX ix_krawedzie_sasiedztwa_planu_wersja_id "
            "ON krawedzie_sasiedztwa_planu (wersja_id)"
        )
        con.execute("DROP TABLE alembic_version")
        con.commit()
    finally:
        con.close()
    missing_fk_adoption = subprocess.run(
        [sys.executable, "-c", "import database; database.init_db()"],
        cwd=str(BACKEND), env=_env(missing_fk_file, "r22-missing-edge-fk"),
        capture_output=True, text=True,
    )
    assert missing_fk_adoption.returncode != 0
    assert "klucz obcy R2" in (
        missing_fk_adoption.stdout + missing_fk_adoption.stderr
    )


def test_adopcja_r22b_odrzuca_brak_ochrony_proweniencji(tmp_path):
    base_file = tmp_path / "_r22b_provenance_adoption_base.db"
    base_env = _prepare_r2_0052(base_file)
    upgraded = _alembic(base_env, "upgrade", HEAD)
    assert upgraded.returncode == 0, upgraded.stderr

    corruptions = {
        "missing-trigger": (
            "DROP TRIGGER fk_terminy_przydzial_kombinacja_wersja_update",
            "nie chroni pary proweniencji R2.2b",
        ),
        "missing-index": (
            "DROP INDEX ix_terminy_przydzial_kombinacja_planu_id",
            "nie ma wymaganych indeksów R2",
        ),
        "dead-trigger": (
            "DROP TRIGGER fk_terminy_przydzial_kombinacja_wersja_update; "
            "CREATE TRIGGER fk_terminy_przydzial_kombinacja_wersja_update "
            "BEFORE UPDATE OF przydzial_kombinacja_planu_id, "
            "przydzial_wersja_planu_id ON terminy "
            "WHEN 0 AND NEW.przydzial_kombinacja_planu_id IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM kombinacje_stolow_planu k "
            "WHERE k.id = NEW.przydzial_kombinacja_planu_id "
            "AND k.wersja_id = NEW.przydzial_wersja_planu_id) "
            "BEGIN SELECT RAISE(ABORT, "
            "'przydzial combination/version mismatch'); END",
            "nie chroni pary proweniencji R2.2b",
        ),
    }
    for name, (statement, expected_error) in corruptions.items():
        db_file = tmp_path / f"_r22b_provenance_adoption_{name}.db"
        shutil.copy2(base_file, db_file)
        con = sqlite3.connect(str(db_file))
        try:
            con.executescript(statement)
            con.execute("DROP TABLE alembic_version")
            con.commit()
        finally:
            con.close()

        adoption = subprocess.run(
            [sys.executable, "-c", "import database; database.init_db()"],
            cwd=str(BACKEND), env=_env(db_file, f"r22b-{name}"),
            capture_output=True, text=True,
        )
        assert adoption.returncode != 0, name
        assert expected_error in (adoption.stdout + adoption.stderr), name


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


def _insert_waitlist_hold(
    db_file,
    *,
    r4=False,
):
    con = sqlite3.connect(str(db_file))
    try:
        con.executemany(
            """INSERT INTO stoliki
               (id, nazwa, pojemnosc, laczy_sie, aktywny, kolejnosc)
               VALUES (?, ?, 4, 0, 1, ?)""",
            [(1, "H1", 0), (2, "H2", 1)],
        )
        columns = (
            "id, data, nazwisko, status, utworzono_at, "
            "hold_stolik_id, hold_do, kanal"
        )
        values = [
            1,
            "2035-07-16",
            "Hold migracyjny",
            "oczekuje",
            "2026-07-15 12:00:00",
            1,
            "2090-07-16 12:30:00",
            "reczna",
        ]
        if r4:
            columns += (
                ", hold_stoliki_dodatkowe, hold_godz_od, "
                "hold_godz_do, hold_bufor_min"
            )
            values.extend(("[2]", "18:00:00", "20:00:00", 30))
        placeholders = ", ".join("?" for _ in values)
        con.execute(
            f"INSERT INTO lista_oczekujacych ({columns}) VALUES ({placeholders})",
            values,
        )
        con.commit()
    finally:
        con.close()


def test_rebuild_ledgera_na_0059_nie_wymaga_kolumn_holdow_r4(tmp_path):
    """Fallback uruchomiony przed 0060 zachowuje legacy hold całego dnia."""
    db_file = tmp_path / "_pre_r4_hold_rebuild.db"
    env = _env(db_file, "pre-r4-hold")
    upgraded = _alembic(env, "upgrade", "0059_r3_reguly_dostepnosci")
    assert upgraded.returncode == 0, upgraded.stderr
    _insert_waitlist_hold(db_file)

    rebuilt = subprocess.run(
        [
            sys.executable,
            "-c",
            "import database; database._rebuild_rezerwacje_ledger()",
        ],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert rebuilt.returncode == 0, rebuilt.stderr

    con = sqlite3.connect(str(db_file))
    try:
        columns = {
            row[1] for row in con.execute("PRAGMA table_info(lista_oczekujacych)")
        }
        claims = con.execute(
            "SELECT count(*), min(minute), max(minute) "
            "FROM rezerwacje_stoliki_claims WHERE waitlist_id=1"
        ).fetchone()
        revision = con.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0]
    finally:
        con.close()
    assert "hold_stoliki_dodatkowe" not in columns
    assert claims == (1440, 0, 1439)
    assert revision == "0059_r3_reguly_dostepnosci"


def test_rebuild_ledgera_0060_odtwarza_czasowy_wielostolowy_hold(tmp_path):
    db_file = tmp_path / "_r4_hold_rebuild.db"
    env = _env(db_file, "r4-hold")
    upgraded = _alembic(env, "upgrade", HEAD)
    assert upgraded.returncode == 0, upgraded.stderr
    _insert_waitlist_hold(db_file, r4=True)

    rebuilt = subprocess.run(
        [
            sys.executable,
            "-c",
            "import database; database._rebuild_rezerwacje_ledger()",
        ],
        cwd=str(BACKEND), env=env, capture_output=True, text=True,
    )
    assert rebuilt.returncode == 0, rebuilt.stderr

    con = sqlite3.connect(str(db_file))
    try:
        claims = con.execute(
            "SELECT stolik_id, count(*), min(minute), max(minute) "
            "FROM rezerwacje_stoliki_claims WHERE waitlist_id=1 "
            "GROUP BY stolik_id ORDER BY stolik_id"
        ).fetchall()
    finally:
        con.close()
    assert claims == [(1, 150, 1080, 1229), (2, 150, 1080, 1229)]


def test_migracja_0060_wznawia_sie_po_czesciowym_dodaniu_kolumn(tmp_path):
    db_file = tmp_path / "_r4_partial_columns.db"
    env = _env(db_file, "r4-partial")
    upgraded = _alembic(env, "upgrade", "0059_r3_reguly_dostepnosci")
    assert upgraded.returncode == 0, upgraded.stderr
    con = sqlite3.connect(str(db_file))
    try:
        con.execute(
            "ALTER TABLE lista_oczekujacych "
            "ADD COLUMN hold_stoliki_dodatkowe JSON"
        )
        con.commit()
    finally:
        con.close()

    resumed = _alembic(env, "upgrade", HEAD)
    assert resumed.returncode == 0, resumed.stderr
    con = sqlite3.connect(str(db_file))
    try:
        columns = {
            row[1] for row in con.execute("PRAGMA table_info(lista_oczekujacych)")
        }
        revision = con.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0]
    finally:
        con.close()
    assert {
        "hold_stoliki_dodatkowe", "hold_godz_od",
        "hold_godz_do", "hold_bufor_min",
    } <= columns
    assert revision == HEAD
