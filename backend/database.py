"""Konfiguracja połączenia z bazą danych.

Silnik wybiera zmienna DATABASE_URL:
  - PostgreSQL (cel produkcyjny):  postgresql+psycopg2://user:pass@host:5432/db
  - SQLite (szybki dev/offline):   sqlite:///./scheduler.db
Kod jest niezależny od silnika dzięki SQLAlchemy.
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base

load_dotenv()  # wczytuje zmienne środowiskowe z pliku .env (jeśli istnieje)

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg2://grafik:grafik@localhost:5432/grafik",
)

# check_same_thread dotyczy wyłącznie SQLite + FastAPI (dostęp wielowątkowy).
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,  # odporność na zerwane połączenia (ważne dla Postgresa)
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Generator sesji — używany jako FastAPI Dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_schema():
    """Lekka auto-migracja: dodaje brakujące kolumny w istniejących tabelach
    (create_all nie modyfikuje już istniejących tabel). Działa na SQLite i PostgreSQL."""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if "przydzialy_zmian" in insp.get_table_names():
        kolumny = {c["name"] for c in insp.get_columns("przydzialy_zmian")}
        with engine.begin() as conn:
            if "rewir" not in kolumny:
                conn.execute(text("ALTER TABLE przydzialy_zmian ADD COLUMN rewir VARCHAR"))
            if "zamyka" not in kolumny:
                conn.execute(text("ALTER TABLE przydzialy_zmian ADD COLUMN zamyka BOOLEAN NOT NULL DEFAULT FALSE"))
            if "zamyka_reczny" not in kolumny:
                conn.execute(text("ALTER TABLE przydzialy_zmian ADD COLUMN zamyka_reczny BOOLEAN NOT NULL DEFAULT FALSE"))
    if "dyspozycje" in insp.get_table_names():
        kolumny = {c["name"] for c in insp.get_columns("dyspozycje")}
        if "godz_do" not in kolumny:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE dyspozycje ADD COLUMN godz_do TIME"))
    if "pracownicy" in insp.get_table_names():
        kolumny = {c["name"] for c in insp.get_columns("pracownicy")}
        with engine.begin() as conn:
            if "kolejnosc" not in kolumny:
                conn.execute(text("ALTER TABLE pracownicy ADD COLUMN kolejnosc INTEGER NOT NULL DEFAULT 0"))
            if "kolor" not in kolumny:
                conn.execute(text("ALTER TABLE pracownicy ADD COLUMN kolor VARCHAR"))
            if "dzial" not in kolumny:
                conn.execute(text("ALTER TABLE pracownicy ADD COLUMN dzial VARCHAR NOT NULL DEFAULT 'obsluga'"))


def init_db():
    """Tworzy tabele jeśli nie istnieją i domyka schemat (auto-migracja)."""
    Base.metadata.create_all(bind=engine)
    _ensure_schema()
