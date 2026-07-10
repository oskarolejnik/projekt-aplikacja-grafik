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
    "users",
]


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
