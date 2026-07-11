"""Konfiguracja połączenia z bazą danych.

Silnik wybiera zmienna DATABASE_URL:
  - PostgreSQL (cel produkcyjny):  postgresql+psycopg2://user:pass@host:5432/db
  - SQLite (szybki dev/offline):   sqlite:///./scheduler.db
Kod jest niezależny od silnika dzięki SQLAlchemy.
"""

import os
import re

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
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


if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_foreign_keys(dbapi_connection, _connection_record):
        """SQLite domyślnie ignoruje FK; ledger wymaga realnego CASCADE/RESTRICT."""
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

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


_R0B_LEDGER_TABLES = {
    "rezerwacje_idempotencja",
    "rezerwacje_dni_ledger",
    "rezerwacje_stoliki_claims",
    "rezerwacje_pacing_ledger",
}
_R0B_REVISION = "0051_rezerwacje_atomic_ledger"
_PRE_R0B_REVISION = "0050_rezerwacje_source_identity"
_R1A_AUDIT_TABLE = "reservation_audit"
_R1A_REVISION = "0052_reservation_audit"
_R1A_AUDIT_COLUMNS = {
    "id", "created_at", "reservation_ref", "termin_id", "actor_kind",
    "actor_user_id", "actor_login", "action", "reason", "diff",
}
_R1A_AUDIT_MODEL = Base.metadata.tables[_R1A_AUDIT_TABLE]
_R1A_AUDIT_INDEXES = {
    index.name: (tuple(column.name for column in index.columns), bool(index.unique))
    for index in _R1A_AUDIT_MODEL.indexes
}
_R1A_AUDIT_CHECKS = {
    constraint.name: str(constraint.sqltext)
    for constraint in _R1A_AUDIT_MODEL.constraints
    if constraint.name and hasattr(constraint, "sqltext")
}
_R1A_AUDIT_NULLABLE = {
    column.name: bool(column.nullable) for column in _R1A_AUDIT_MODEL.columns
}


def _rebuild_rezerwacje_ledger():
    """Odbudowuje bieżący ledger po ``create_all`` fallbacku.

    Normalna ścieżka Alembica korzysta z backfillu migracji 0051. Ta funkcja zabezpiecza
    instalacje bez Alembica oraz niewersjonowane bazy utworzone wcześniej przez ``create_all``.
    Nie kopiuje PII do błędów i wykonuje całość w jednej transakcji startowej.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from sqlalchemy import inspect

    import models
    import reservation_service

    schema = inspect(engine)
    table_names = set(schema.get_table_names())
    required_tables = {"terminy", "stoliki", "lista_oczekujacych"} | _R0B_LEDGER_TABLES
    if not required_tables.issubset(table_names):
        return
    termin_columns = {column["name"] for column in schema.get_columns("terminy")}
    waitlist_columns = {
        column["name"] for column in schema.get_columns("lista_oczekujacych")
    }
    if not {
        "data", "rodzaj", "status", "godz_od", "godz_do", "stolik_id",
        "stoliki_dodatkowe", "liczba_osob",
    }.issubset(termin_columns) or not {
        "data", "status", "hold_stolik_id", "hold_do",
    }.issubset(waitlist_columns):
        # Bardzo stary fallback nie ma jeszcze domeny rezerwacji stolikowych; zachowaj
        # jego dotychczasowy start zamiast wykonywać zapytania do nieistniejących kolumn.
        return

    db = SessionLocal()
    try:
        now = datetime.now(ZoneInfo("Europe/Warsaw")).replace(tzinfo=None)
        active = tuple(reservation_service.ACTIVE_STATUSES)
        dates = {
            value for (value,) in db.query(models.Termin.data).filter(
                models.Termin.rodzaj == "stolik",
                models.Termin.status.in_(active),
            ).all()
        }
        dates.update(
            value for (value,) in db.query(models.ListaOczekujacych.data).filter(
                models.ListaOczekujacych.status == "oczekuje",
                models.ListaOczekujacych.hold_stolik_id.isnot(None),
                models.ListaOczekujacych.hold_do > now,
            ).all()
        )
        guards = reservation_service.begin_locked_write(db, dates) if dates else ()

        # Rebuild jest idempotentny; rollback przy błędzie przywraca poprzedni kompletny ledger.
        db.query(models.RezerwacjaStolikClaim).delete(synchronize_session=False)
        db.query(models.RezerwacjaPacingLedger).delete(synchronize_session=False)
        known_tables = {value for (value,) in db.query(models.Stolik.id).all()}

        def table_ids(record):
            raw = record.stoliki_dodatkowe
            if raw is None:
                extra = []
            elif isinstance(raw, list):
                extra = raw
            else:
                raise RuntimeError(
                    f"R0B_FALLBACK_CORRUPT_EXTRA_TABLES record_id={record.id}"
                )
            result = []
            for value in ([record.stolik_id] if record.stolik_id is not None else []) + extra:
                if isinstance(value, bool):
                    raise RuntimeError(
                        f"R0B_FALLBACK_CORRUPT_TABLE record_id={record.id}"
                    )
                try:
                    table_id = int(value)
                except (TypeError, ValueError) as exc:
                    raise RuntimeError(
                        f"R0B_FALLBACK_CORRUPT_TABLE record_id={record.id}"
                    ) from exc
                if table_id <= 0 or table_id in result:
                    raise RuntimeError(
                        f"R0B_FALLBACK_DUPLICATE_TABLE record_id={record.id}"
                    )
                if table_id not in known_tables:
                    raise RuntimeError(
                        f"R0B_FALLBACK_MISSING_TABLE table_id={table_id} record_id={record.id}"
                    )
                result.append(table_id)
            return result

        reservations = db.query(models.Termin).filter(
            models.Termin.rodzaj == "stolik",
            models.Termin.status.in_(active),
        ).order_by(models.Termin.id).all()
        for record in reservations:
            ids = table_ids(record)
            if ids and record.godz_od is None:
                raise RuntimeError(f"R0B_FALLBACK_MISSING_START record_id={record.id}")
            if ids and record.godz_do is None:
                raise RuntimeError(f"R0B_FALLBACK_MISSING_END record_id={record.id}")
            reservation_service.replace_termin_allocation(
                db,
                termin_id=record.id,
                data=record.data,
                start=record.godz_od,
                end=record.godz_do,
                table_ids=ids,
                party_size=record.liczba_osob or 0,
                enforce_pacing=False,
                now=now,
            )

        holds = db.query(models.ListaOczekujacych).filter(
            models.ListaOczekujacych.status == "oczekuje",
            models.ListaOczekujacych.hold_stolik_id.isnot(None),
            models.ListaOczekujacych.hold_do > now,
        ).order_by(models.ListaOczekujacych.id).all()
        for hold in holds:
            if hold.hold_stolik_id not in known_tables:
                raise RuntimeError(
                    f"R0B_FALLBACK_MISSING_TABLE table_id={hold.hold_stolik_id} "
                    f"waitlist_id={hold.id}"
                )
            reservation_service.replace_waitlist_hold(
                db,
                waitlist_id=hold.id,
                table_id=hold.hold_stolik_id,
                data=hold.data,
                expires_at=hold.hold_do,
                now=now,
            )

        reservation_service.touch_days(guards)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _mark_r0b_fallback_revision():
    """Zapobiega ponownemu CREATE TABLE 0051, gdy fallback rozbudował wersjonowaną bazę 0050."""
    from sqlalchemy import inspect, text

    if "alembic_version" not in inspect(engine).get_table_names():
        return
    with engine.begin() as conn:
        current = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
        if current == _PRE_R0B_REVISION:
            conn.execute(
                text("UPDATE alembic_version SET version_num=:revision"),
                {"revision": _R0B_REVISION},
            )


def _normalise_check_sql(value) -> str:
    value = str(value or "").lower().replace('"', "").replace("`", "")
    value = value.replace("[", "").replace("]", "")
    return re.sub(r"\s+", "", value)


def _assert_r1a_constraints_enforced() -> None:
    """Behawioralnie sprawdza CHECK-i w rollbackowanych savepointach.

    PostgreSQL normalizuje treść CHECK inaczej niż SQLite, dlatego same porównanie DDL nie
    wystarcza. Jawne ujemne identyfikatory nie zużywają sekwencji i każdy zapis jest cofany.
    """
    from datetime import datetime

    from sqlalchemy.exc import IntegrityError

    base = {
        "created_at": datetime(2026, 7, 11, 12, 0),
        "reservation_ref": "0" * 64,
        "termin_id": None,
        "actor_kind": "system",
        "actor_user_id": None,
        "actor_login": None,
        "action": "create",
        "reason": None,
        "diff": {"changes": {}},
    }
    invalid_rows = (
        {**base, "reservation_ref": "x"},
        {**base, "actor_kind": "evil"},
        {**base, "action": "evil"},
        {**base, "reason": "raw guest data"},
        {**base, "actor_kind": "user", "actor_login": None},
        {**base, "action": "override", "reason": None},
    )
    with engine.connect() as conn:
        outer = conn.begin()
        try:
            for offset, values in enumerate(invalid_rows, start=1):
                nested = conn.begin_nested()
                try:
                    conn.execute(
                        _R1A_AUDIT_MODEL.insert().values(id=-9_000_000 - offset, **values)
                    )
                except IntegrityError:
                    nested.rollback()
                else:
                    nested.rollback()
                    raise RuntimeError(
                        "Tabela reservation_audit nie egzekwuje wymaganych ograniczeń CHECK."
                    )
        finally:
            outer.rollback()


def _validate_r1a_audit_schema(inspector=None) -> bool:
    """Weryfikuje pełną strukturę i działanie tabeli 0052 przed oznaczeniem rewizji."""
    from sqlalchemy import inspect

    inspector = inspector or inspect(engine)
    tables = set(inspector.get_table_names())
    if _R1A_AUDIT_TABLE not in tables:
        raise RuntimeError(
            "Brak tabeli reservation_audit dla zadeklarowanej migracji 0052."
        )

    columns = {
        column["name"]: bool(column["nullable"])
        for column in inspector.get_columns(_R1A_AUDIT_TABLE)
    }
    indexes = {
        index["name"]: (
            tuple(index.get("column_names") or ()),
            bool(index.get("unique")),
        )
        for index in inspector.get_indexes(_R1A_AUDIT_TABLE)
    }
    checks = {
        constraint.get("name"): constraint.get("sqltext")
        for constraint in inspector.get_check_constraints(_R1A_AUDIT_TABLE)
    }
    foreign_keys = {
        (
            tuple(fk.get("constrained_columns") or ()),
            fk.get("referred_table"),
            tuple(fk.get("referred_columns") or ()),
            str((fk.get("options") or {}).get("ondelete") or "").upper(),
        )
        for fk in inspector.get_foreign_keys(_R1A_AUDIT_TABLE)
    }
    primary_key = tuple(
        inspector.get_pk_constraint(_R1A_AUDIT_TABLE).get("constrained_columns") or ()
    )
    complete = (
        set(columns) == _R1A_AUDIT_COLUMNS
        and columns == _R1A_AUDIT_NULLABLE
        and all(indexes.get(name) == expected for name, expected in _R1A_AUDIT_INDEXES.items())
        and set(_R1A_AUDIT_CHECKS).issubset(checks)
        and primary_key == ("id",)
        and (("termin_id",), "terminy", ("id",), "SET NULL") in foreign_keys
        and (("actor_user_id",), "users", ("id",), "SET NULL") in foreign_keys
    )
    if complete and engine.dialect.name == "sqlite":
        complete = all(
            _normalise_check_sql(checks[name]) == _normalise_check_sql(expected)
            for name, expected in _R1A_AUDIT_CHECKS.items()
        )
    if not complete:
        raise RuntimeError(
            "Tabela reservation_audit jest niekompletna; nie można bezpiecznie oznaczyć migracji 0052."
        )
    _assert_r1a_constraints_enforced()
    return True


def _sanitize_legacy_rodo_audit_resources() -> int:
    """Idempotentnie usuwa historyczne klucze gości także na ścieżkach bez Alembica."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "audit_log" not in inspector.get_table_names():
        return 0
    columns = {column["name"] for column in inspector.get_columns("audit_log")}
    if not {"akcja", "zasob"}.issubset(columns):
        return 0
    with engine.begin() as conn:
        result = conn.execute(text(
            "UPDATE audit_log SET zasob = '[redacted]' "
            "WHERE akcja IN ('rodo_eksport_gosc', 'rodo_anonimizuj_gosc') "
            "AND zasob IS NOT NULL AND zasob <> '[redacted]' "
            "AND zasob NOT LIKE 'guest_ref:%'"
        ))
        return int(result.rowcount or 0)


def _mark_r1a_fallback_revision():
    """Oznacza 0052 wyłącznie dla kompletnej tabeli utworzonej przez ``create_all``."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "alembic_version" not in tables or _R1A_AUDIT_TABLE not in tables:
        return False
    _validate_r1a_audit_schema(inspector)
    _sanitize_legacy_rodo_audit_resources()
    with engine.begin() as conn:
        current = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
        if current == _R0B_REVISION:
            conn.execute(
                text("UPDATE alembic_version SET version_num=:revision"),
                {"revision": _R1A_REVISION},
            )
            return True
    return current == _R1A_REVISION


def _is_complete_r0b_schema(inspector, tables, model_tables) -> bool:
    """Rozpoznaje niewersjonowany schemat 0051 bez mylenia go z 0050.

    Sam zestaw nazw tabel nie wystarcza: częściowo utworzony fallback nie może zostać
    ostemplowany i pominięty przez Alembica. Dla tabel ledgera wymagamy dokładnego zestawu
    kolumn bieżącego modelu; pozostałe tabele muszą odpowiadać pełnemu schematowi sprzed 0052.
    """
    if not (model_tables - {_R1A_AUDIT_TABLE}).issubset(tables):
        return False
    for table_name in _R0B_LEDGER_TABLES:
        expected = {
            column.name for column in Base.metadata.tables[table_name].columns
        }
        actual = {
            column["name"] for column in inspector.get_columns(table_name)
        }
        if actual != expected:
            return False
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
    _sanitize_legacy_rodo_audit_resources()

    if "alembic_version" in tables and _R0B_LEDGER_TABLES.issubset(tables):
        # Poprzedni start bez Alembica mógł już utworzyć i wypełnić strukturę R0b,
        # ale zakończyć proces przed osobnym stemplem. Nie uruchamiaj wtedy CREATE TABLE 0051.
        from sqlalchemy import text
        with engine.connect() as conn:
            current_revision = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one_or_none()
        if current_revision == _PRE_R0B_REVISION:
            _rebuild_rezerwacje_ledger()
            _mark_r0b_fallback_revision()
            if _R1A_AUDIT_TABLE in tables:
                _mark_r1a_fallback_revision()
            elif not _alembic_run(lambda command, cfg: command.upgrade(cfg, "head")):
                Base.metadata.create_all(bind=engine)
                _ensure_schema()
                _rebuild_rezerwacje_ledger()
                _sanitize_legacy_rodo_audit_resources()
                _mark_r1a_fallback_revision()
            return
        if current_revision == _R0B_REVISION and _R1A_AUDIT_TABLE in tables:
            _mark_r1a_fallback_revision()
            return
        if current_revision == _R1A_REVISION:
            _validate_r1a_audit_schema(insp)
            return

    if "alembic_version" not in tables and tables:
        # Baza bez metryki Alembica. Dwa przypadki:
        #  (a) schemat JUŻ kompletny (wszystkie tabele modeli istnieją — np. utworzony przez
        #      create_all bieżących modeli: testy / dev-fallback) → adoptuj wprost jako „head"
        #      (NIE odtwarzaj migracji, bo kolumny/tabele już są).
        #  (b) starsza baza (sprzed Alembica, bez nowszych tabel) → oznacz BASELINE
        #      i domigruj do head (0002+: nowe kolumny/tabele + backfill po nazwach).
        model_tables = set(Base.metadata.tables.keys())
        complete_current = model_tables.issubset(tables)
        complete_r0b = _is_complete_r0b_schema(insp, tables, model_tables)
        pre_r0b_tables = model_tables - _R0B_LEDGER_TABLES - {_R1A_AUDIT_TABLE}
        termin_columns = (
            {column["name"] for column in insp.get_columns("terminy")}
            if "terminy" in tables else set()
        )
        complete_pre_r0b = (
            pre_r0b_tables.issubset(tables)
            and {"source_type", "source_external_id"}.issubset(termin_columns)
        )
        if complete_current:
            _validate_r1a_audit_schema(insp)
            _ensure_schema()
            _rebuild_rezerwacje_ledger()
            _sanitize_legacy_rodo_audit_resources()
            _alembic_run(lambda command, cfg: command.stamp(cfg, "head"))
            return
        if complete_r0b:
            # Schemat 0051 bez alembic_version ma już ledger. Stemplowanie go jako 0050
            # uruchomiłoby ponownie CREATE TABLE 0051 i przerwało start aplikacji.
            if _alembic_run(lambda command, cfg: command.stamp(cfg, _R0B_REVISION)):
                _alembic_run(lambda command, cfg: command.upgrade(cfg, "head"))
            else:
                Base.metadata.create_all(bind=engine)
                _ensure_schema()
                _rebuild_rezerwacje_ledger()
                _sanitize_legacy_rodo_audit_resources()
            return
        else:
            if complete_pre_r0b:
                _ensure_schema()
                if _alembic_run(
                    lambda command, cfg: command.stamp(cfg, _PRE_R0B_REVISION)
                ):
                    _alembic_run(lambda command, cfg: command.upgrade(cfg, "head"))
                else:
                    Base.metadata.create_all(bind=engine)
                    _ensure_schema()
                    _rebuild_rezerwacje_ledger()
                    _sanitize_legacy_rodo_audit_resources()
                return
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
                _rebuild_rezerwacje_ledger()
                _sanitize_legacy_rodo_audit_resources()
        return

    # Pusta baza lub baza zarządzana przez Alembica → upgrade do najnowszej wersji.
    if not _alembic_run(lambda command, cfg: command.upgrade(cfg, "head")):
        # Fallback bez Alembica: utwórz schemat z modeli i domknij kolumny.
        Base.metadata.create_all(bind=engine)
        _ensure_schema()
        _rebuild_rezerwacje_ledger()
        _sanitize_legacy_rodo_audit_resources()
        _mark_r0b_fallback_revision()
        _mark_r1a_fallback_revision()
