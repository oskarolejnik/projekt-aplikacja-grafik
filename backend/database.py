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


def _ensure_schema(*, include_source_identity: bool = True):
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
            if "zamyka_rewir" not in kolumny:
                conn.execute(text("ALTER TABLE przydzialy_zmian ADD COLUMN zamyka_rewir BOOLEAN NOT NULL DEFAULT FALSE"))
            if "rozlicza_imprize" not in kolumny:
                conn.execute(text("ALTER TABLE przydzialy_zmian ADD COLUMN rozlicza_imprize BOOLEAN NOT NULL DEFAULT FALSE"))
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
    if "stanowiska" in insp.get_table_names():
        kolumny = {c["name"] for c in insp.get_columns("stanowiska")}
        with engine.begin() as conn:
            if "widoczny_dla_wszystkich" not in kolumny:
                conn.execute(text("ALTER TABLE stanowiska ADD COLUMN widoczny_dla_wszystkich BOOLEAN NOT NULL DEFAULT FALSE"))
            if "grupa_widocznosci" not in kolumny:
                conn.execute(text("ALTER TABLE stanowiska ADD COLUMN grupa_widocznosci VARCHAR"))
    if "rozliczenia_dnia" in insp.get_table_names():
        kolumny = {c["name"] for c in insp.get_columns("rozliczenia_dnia")}
        with engine.begin() as conn:
            if "zadatek_gotowka" not in kolumny:
                conn.execute(text("ALTER TABLE rozliczenia_dnia ADD COLUMN zadatek_gotowka FLOAT NOT NULL DEFAULT 0"))
            if "zadatek_karta" not in kolumny:
                conn.execute(text("ALTER TABLE rozliczenia_dnia ADD COLUMN zadatek_karta FLOAT NOT NULL DEFAULT 0"))
            if "imp_reczny" not in kolumny:
                conn.execute(text("ALTER TABLE rozliczenia_dnia ADD COLUMN imp_reczny BOOLEAN NOT NULL DEFAULT FALSE"))
            if "imp_gotowka" not in kolumny:
                conn.execute(text("ALTER TABLE rozliczenia_dnia ADD COLUMN imp_gotowka FLOAT NOT NULL DEFAULT 0"))
            if "imp_karta" not in kolumny:
                conn.execute(text("ALTER TABLE rozliczenia_dnia ADD COLUMN imp_karta FLOAT NOT NULL DEFAULT 0"))
            if "push_admin_at" not in kolumny:
                conn.execute(text("ALTER TABLE rozliczenia_dnia ADD COLUMN push_admin_at TIMESTAMP"))
            if "przelew" not in kolumny:
                conn.execute(text("ALTER TABLE rozliczenia_dnia ADD COLUMN przelew FLOAT NOT NULL DEFAULT 0"))
    if "kp_zadatki" in insp.get_table_names():
        kolumny = {c["name"] for c in insp.get_columns("kp_zadatki")}
        with engine.begin() as conn:
            if "nazwisko" not in kolumny:
                conn.execute(text("ALTER TABLE kp_zadatki ADD COLUMN nazwisko VARCHAR"))
            if "data_imprezy" not in kolumny:
                conn.execute(text("ALTER TABLE kp_zadatki ADD COLUMN data_imprezy DATE"))
            if "termin_id" not in kolumny:
                conn.execute(text("ALTER TABLE kp_zadatki ADD COLUMN termin_id INTEGER"))
    if "terminy" in insp.get_table_names():
        kolumny = {c["name"] for c in insp.get_columns("terminy")}
        with engine.begin() as conn:
            if "ical_uid" not in kolumny:
                conn.execute(text("ALTER TABLE terminy ADD COLUMN ical_uid VARCHAR"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_terminy_ical_uid ON terminy (ical_uid)"))
            if include_source_identity:
                if "source_type" not in kolumny:
                    conn.execute(text("ALTER TABLE terminy ADD COLUMN source_type VARCHAR(32)"))
                if "source_external_id" not in kolumny:
                    conn.execute(text("ALTER TABLE terminy ADD COLUMN source_external_id VARCHAR(512)"))
                conn.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_terminy_source_identity "
                    "ON terminy (source_type, source_external_id)"
                ))
    if "rozliczenia_dnia_kelnerzy" in insp.get_table_names():
        kolumny = {c["name"] for c in insp.get_columns("rozliczenia_dnia_kelnerzy")}
        with engine.begin() as conn:
            if "potwierdzone" not in kolumny:
                conn.execute(text("ALTER TABLE rozliczenia_dnia_kelnerzy ADD COLUMN potwierdzone BOOLEAN NOT NULL DEFAULT FALSE"))
            if "push_oczekuje_at" not in kolumny:
                conn.execute(text("ALTER TABLE rozliczenia_dnia_kelnerzy ADD COLUMN push_oczekuje_at TIMESTAMP"))


def _alembic_config():
    """Konfiguracja Alembica wskazująca na migrations/ obok tego pliku. W spakowanej appce
    (PyInstaller) pliki danych leżą w katalogu bundla `sys._MEIPASS`, nie obok źródła."""
    import os
    import sys
    from alembic.config import Config

    here = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    cfg = Config(os.path.join(here, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(here, "migrations"))
    return cfg


def _alembic_run(action):
    """Uruchamia akcję Alembica (stamp/upgrade) na silniku aplikacji.
    Zwraca True przy sukcesie, False gdy Alembic nie jest zainstalowany
    (wtedy wołający stosuje fallback create_all)."""
    try:
        from alembic import command  # noqa: F401
    except ImportError:
        return False
    from alembic import command
    cfg = _alembic_config()
    with engine.begin() as conn:           # transakcja domknięta po wyjściu (commit)
        cfg.attributes["connection"] = conn
        action(command, cfg)
    return True


def init_db():
    """Przygotowanie schematu, świadome Alembica (idempotentne).

    • Baza „legacy" (są tabele, brak alembic_version) — utworzona przed wprowadzeniem
      Alembica: domyka brakujące kolumny i ADOPTUJE bazę do Alembica (stamp head),
      bez odtwarzania danych. Dotyczy istniejącego wdrożenia produkcyjnego.
    • Pusta baza (nowy klient / dev / Electron) lub baza zarządzana przez Alembica:
      `upgrade head` — buduje schemat z migracji lub stosuje nowe migracje.
    • Brak zainstalowanego Alembica → bezpieczny fallback create_all + _ensure_schema
      (zachowanie jak dawniej).
    """
    from sqlalchemy import inspect

    insp = inspect(engine)
    tables = set(insp.get_table_names())

    if "alembic_version" not in tables and tables:
        # Baza bez metryki Alembica. Dwa przypadki:
        #  (a) schemat JUŻ kompletny (wszystkie tabele modeli istnieją — np. utworzony przez
        #      create_all bieżących modeli: testy / dev-fallback) → adoptuj wprost jako „head"
        #      (NIE odtwarzaj migracji, bo kolumny/tabele już są).
        #  (b) starsza baza (sprzed Alembica, bez nowszych tabel) → oznacz BASELINE
        #      i domigruj do head (0002+: nowe kolumny/tabele + backfill po nazwach).
        model_tables = set(Base.metadata.tables.keys())
        if model_tables.issubset(tables):
            _ensure_schema()
            _alembic_run(lambda command, cfg: command.stamp(cfg, "head"))
        else:
            # Nie dodawaj pól z najnowszych migracji przed upgrade: migracja doda je sama.
            # Jest to istotne dla 0050 (source identity), której ADD COLUMN nie jest idempotentne.
            _ensure_schema(include_source_identity=False)
        if not model_tables.issubset(tables):
            if _alembic_run(lambda command, cfg: command.stamp(cfg, "0001_baseline")):
                _alembic_run(lambda command, cfg: command.upgrade(cfg, "head"))
            else:
                # Pakiet bez Alembica: co najmniej utwórz brakujące tabele i domknij pola,
                # zamiast wracać z modelem wskazującym na nieistniejące source_*.
                Base.metadata.create_all(bind=engine)
                _ensure_schema()
        return

    # Pusta baza lub baza zarządzana przez Alembica → upgrade do najnowszej wersji.
    if not _alembic_run(lambda command, cfg: command.upgrade(cfg, "head")):
        # Fallback bez Alembica: utwórz schemat z modeli i domknij kolumny.
        Base.metadata.create_all(bind=engine)
        _ensure_schema()
