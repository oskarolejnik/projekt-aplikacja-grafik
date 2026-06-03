"""Opcjonalna migracja danych ze starego SQLite (scheduler.db) do bazy docelowej
wskazanej przez DATABASE_URL (np. PostgreSQL).

Uruchom raz, po skonfigurowaniu .env:
    python migrate_sqlite_to_pg.py [sciezka_do_pliku.db]

Kopiuje rekordy zachowując identyfikatory i resetuje sekwencje w PostgreSQL.
"""

import sys

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import models
from database import engine as target_engine, init_db

SQLITE_PATH = sys.argv[1] if len(sys.argv) > 1 else "scheduler.db"

src_engine = create_engine(
    f"sqlite:///{SQLITE_PATH}", connect_args={"check_same_thread": False}
)
Src = sessionmaker(bind=src_engine)
Dst = sessionmaker(bind=target_engine)

# Kolejność uwzględnia klucze obce.
TABELE = [
    models.Stanowisko,
    models.Podkategoria,
    models.Pracownik,
    models.WymaganiaDnia,
    models.Dyspozycja,
    models.PrzydzialZmiany,
    models.Impreza,
    models.User,
]


def kopiuj():
    init_db()  # utwórz tabele w bazie docelowej
    src, dst = Src(), Dst()
    try:
        for Model in TABELE:
            rows = src.execute(select(Model)).scalars().all()
            for r in rows:
                dane = {c.name: getattr(r, c.name) for c in Model.__table__.columns}
                dst.merge(Model(**dane))  # merge = upsert po kluczu głównym
            print(f"{Model.__tablename__}: {len(rows)} rekordów")

        # Relacja wiele-do-wielu: kwalifikacje pracowników
        for row in src.execute(models.pracownik_stanowisko.select()).all():
            dst.execute(
                models.pracownik_stanowisko.insert().values(
                    pracownik_id=row.pracownik_id, stanowisko_id=row.stanowisko_id
                )
            )
        dst.commit()
    finally:
        src.close()
        dst.close()

    # Reset sekwencji ID w PostgreSQL (po wstawieniu rekordów z jawnym id).
    if target_engine.url.get_backend_name() == "postgresql":
        with target_engine.begin() as conn:
            for Model in TABELE:
                t = Model.__tablename__
                conn.exec_driver_sql(
                    f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {t}), 1))"
                )
    print("Migracja zakończona.")


if __name__ == "__main__":
    kopiuj()
