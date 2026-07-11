"""Środowisko migracji Alembic.

Źródłem prawdy o schemacie są modele SQLAlchemy (models.Base.metadata).
URL bazy pochodzi z DATABASE_URL (jak w aplikacji) — bez duplikowania konfiguracji.

Obsługuje dwa tryby online:
  • z połączeniem przekazanym przez config.attributes["connection"] — używane przy
    programowym wywołaniu z aplikacji (init_db → stamp/upgrade na silniku aplikacji),
  • bez połączenia — buduje własny silnik z DATABASE_URL (klasyczne `alembic upgrade head`).
"""

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

# Pozwala na `import models` / `import database` przy uruchomieniu z katalogu backend/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Base  # noqa: E402

config = context.config

# Logowanie wg alembic.ini (best-effort — nie wywracaj migracji przez konfig logów).
if config.config_file_name is not None:
    try:
        # Migracje są też uruchamiane programowo podczas startu aplikacji. Domyślne
        # ``disable_existing_loggers=True`` wyciszałoby wtedy m.in. raport shadow-read.
        fileConfig(config.config_file_name, disable_existing_loggers=False)
    except Exception:
        pass

target_metadata = Base.metadata


def _db_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    # Fallback: ta sama wartość domyślna co w database.py.
    import database  # import leniwy — unika tworzenia silnika, gdy niepotrzebny
    return database.DATABASE_URL


def run_migrations_offline() -> None:
    context.configure(
        url=_db_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=True,  # bezpieczne ALTER-y na SQLite (batch mode)
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    external = config.attributes.get("connection", None)
    if external is not None:
        # Połączenie dostarczone przez aplikację — transakcją zarządza wywołujący.
        context.configure(
            connection=external,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=True,
        )
        context.run_migrations()
        return

    engine = create_engine(_db_url(), poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
                render_as_batch=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
