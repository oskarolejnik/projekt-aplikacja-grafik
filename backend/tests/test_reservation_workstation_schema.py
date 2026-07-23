"""Alembic contract for the R6a workstation milestone."""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


BACKEND = Path(__file__).resolve().parent.parent
R6A_TABLES = {
    "reservation_operator_credentials",
    "reservation_workstations",
    "reservation_operator_sessions",
    "reservation_workstation_audit",
}


def _alembic(db_file: Path, action: str, revision: str) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{db_file.as_posix()}",
        "SECRET_KEY": "r6a-test-secret-key-0123456789abcdef",
        "ENCRYPTION_KEY": "r6a-test-encryption-key-0123456789abcdef",
        "WORKSTATION_PIN_PEPPER": "r6a-test-pin-pepper-0123456789abcdef",
        "APP_ENV": "development",
    }
    return subprocess.run(
        [sys.executable, "-m", "alembic", action, revision],
        cwd=str(BACKEND),
        env=env,
        capture_output=True,
        text=True,
    )


def _env(db_file: Path) -> dict[str, str]:
    return {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{db_file.as_posix()}",
        "SECRET_KEY": "r6a-test-secret-key-0123456789abcdef",
        "ENCRYPTION_KEY": "r6a-test-encryption-key-0123456789abcdef",
        "WORKSTATION_PIN_PEPPER": "r6a-test-pin-pepper-0123456789abcdef",
        "APP_ENV": "development",
    }


def _python(db_file: Path, source: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", source],
        cwd=str(BACKEND),
        env=_env(db_file),
        capture_output=True,
        text=True,
    )


def test_r6a_migration_round_trip_on_empty_database(tmp_path):
    db_file = tmp_path / "r6a.sqlite"
    up = _alembic(db_file, "upgrade", "head")
    assert up.returncode == 0, up.stderr

    with sqlite3.connect(db_file) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0]
        session_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' "
            "AND name='reservation_operator_sessions'"
        ).fetchone()[0]
        session_columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(reservation_operator_sessions)"
            )
        }
        audit_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' "
            "AND name='reservation_workstation_audit'"
        ).fetchone()[0]
    assert R6A_TABLES <= tables
    assert revision == "0068_reservation_closure"
    assert "uq_reservation_operator_session_token_hash" in session_sql
    assert "ck_reservation_operator_session_secret_hashes" in session_sql
    assert "ck_reservation_operator_session_reauth_grant" in session_sql
    assert {
        "reauth_grant_hash", "reauth_scope", "reauth_expires_at",
    } <= session_columns
    assert "'reauth'" in audit_sql
    assert "'reauth_use'" in audit_sql

    down = _alembic(db_file, "downgrade", "0063_r5c_reservation_payments")
    assert down.returncode == 0, down.stderr
    with sqlite3.connect(db_file) as connection:
        tables_after_down = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert not (R6A_TABLES & tables_after_down)

    up_again = _alembic(db_file, "upgrade", "head")
    assert up_again.returncode == 0, up_again.stderr


def test_r6a_adopts_complete_unversioned_current_schema(tmp_path):
    db_file = tmp_path / "r6a-current-unversioned.sqlite"
    created = _python(
        db_file,
        "import database, models; models.Base.metadata.create_all(database.engine)",
    )
    assert created.returncode == 0, created.stderr

    adopted = _python(db_file, "import database; database.init_db()")
    assert adopted.returncode == 0, adopted.stderr
    with sqlite3.connect(db_file) as connection:
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0]
    assert revision == "0068_reservation_closure"


def test_r6a_adoption_rejects_partial_unversioned_schema(tmp_path):
    db_file = tmp_path / "r6a-partial-unversioned.sqlite"
    created = _python(
        db_file,
        "import database, models; models.Base.metadata.create_all(database.engine)",
    )
    assert created.returncode == 0, created.stderr
    with sqlite3.connect(db_file) as connection:
        connection.execute("DROP TABLE reservation_workstation_audit")
        connection.commit()

    rejected = _python(db_file, "import database; database.init_db()")
    assert rejected.returncode != 0
    assert "Schemat R6a jest czesciowy" in (rejected.stdout + rejected.stderr)


def test_r6a_upgrades_complete_unversioned_0063_schema(tmp_path):
    db_file = tmp_path / "r6a-from-unversioned-0063.sqlite"
    upgraded = _alembic(db_file, "upgrade", "0063_r5c_reservation_payments")
    assert upgraded.returncode == 0, upgraded.stderr
    with sqlite3.connect(db_file) as connection:
        connection.execute("DROP TABLE alembic_version")
        connection.commit()

    adopted = _python(db_file, "import database; database.init_db()")
    assert adopted.returncode == 0, adopted.stderr
    with sqlite3.connect(db_file) as connection:
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0]
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert revision == "0068_reservation_closure"
    assert R6A_TABLES <= tables
