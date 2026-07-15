"""Konfiguracja połączenia z bazą danych.

Silnik wybiera zmienna DATABASE_URL:
  - PostgreSQL (cel produkcyjny):  postgresql+psycopg2://user:pass@host:5432/db
  - SQLite (szybki dev/offline):   sqlite:///./scheduler.db
Kod jest niezależny od silnika dzięki SQLAlchemy.
"""

import os
import re

from dotenv import load_dotenv
from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.sql import sqltypes
from sqlalchemy.types import TypeDecorator
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


def _require_alembic_run(action):
    """R2 ma migrację danych, której ``create_all`` nie potrafi odtworzyć.

    Od 0053 brak Alembica nie może już cicho utworzyć samego schematu modeli i
    oznaczyć bazy jako aktualnej bez sal oraz opublikowanych planów.
    """
    if not _alembic_run(action):
        raise RuntimeError(
            "R2_MIGRATION_REQUIRES_ALEMBIC: zainstaluj Alembic i uruchom "
            "`alembic upgrade head`; create_all nie wykonuje backfillu planów sali."
        )


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
_R2_REVISION = "0058_r22b_strategia_proweniencja"
_R3_REVISION = "0059_r3_reguly_dostepnosci"
_R5A_REVISION = "0061_r5a_public_security"
_R5A_TABLES = {
    "rezerwacje_publiczne_holdy",
    "rezerwacje_tokeny_zarzadzania",
    "rezerwacje_zgody_publiczne",
    "rezerwacje_publiczne_kwoty",
}
_R5A_BASE_COLUMNS = {
    "lokal_config": {
        "rezerwacje_widget_v2", "rezerwacje_retencja_dni",
        "rezerwacje_rodo_kontakt", "rezerwacje_rodo_adres",
    },
    "rezerwacje_stoliki_claims": {"public_hold_id"},
}
_R5A_BASE_MODEL_TABLES = {
    table_name: Base.metadata.tables[table_name]
    for table_name in _R5A_BASE_COLUMNS
}
_R5A_BASE_INDEXES = {
    "rezerwacje_stoliki_claims": {
        index.name: (
            tuple(column.name for column in index.columns),
            bool(index.unique),
        )
        for index in Base.metadata.tables["rezerwacje_stoliki_claims"].indexes
        if index.name == "ix_rezerwacje_stolik_claim_public_hold_id"
    },
}
_R5A_BASE_UNIQUES = {
    "rezerwacje_stoliki_claims": {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in Base.metadata.tables[
            "rezerwacje_stoliki_claims"
        ].constraints
        if (
            isinstance(constraint, UniqueConstraint)
            and constraint.name == "uq_rezerwacje_stolik_claim_public_hold_owner"
        )
    },
}
_R5A_BASE_CHECK_NAMES = {
    "lokal_config": {"ck_lokal_config_rezerwacje_retencja_dni"},
    "rezerwacje_stoliki_claims": {"ck_rezerwacje_stolik_claim_owner"},
}
_R5A_BASE_CHECKS = {
    table_name: {
        constraint.name: str(constraint.sqltext)
        for constraint in _R5A_BASE_MODEL_TABLES[table_name].constraints
        if (
            isinstance(constraint, CheckConstraint)
            and constraint.name in constraint_names
        )
    }
    for table_name, constraint_names in _R5A_BASE_CHECK_NAMES.items()
}
_R5A_COLUMNS = {
    table_name: {
        column.name for column in Base.metadata.tables[table_name].columns
    }
    for table_name in _R5A_TABLES
}
_R5A_MODEL_TABLES = {
    table_name: Base.metadata.tables[table_name]
    for table_name in _R5A_TABLES
}
_R5A_INDEXES = {
    table_name: {
        index.name: (
            tuple(column.name for column in index.columns),
            bool(index.unique),
        )
        for index in model_table.indexes
        if index.name
    }
    for table_name, model_table in _R5A_MODEL_TABLES.items()
}
_R5A_UNIQUES = {
    table_name: {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in model_table.constraints
        if isinstance(constraint, UniqueConstraint) and constraint.name
    }
    for table_name, model_table in _R5A_MODEL_TABLES.items()
}
_R5A_CHECKS = {
    table_name: {
        constraint.name: str(constraint.sqltext)
        for constraint in model_table.constraints
        if isinstance(constraint, CheckConstraint) and constraint.name
    }
    for table_name, model_table in _R5A_MODEL_TABLES.items()
}
_R5A_FOREIGN_KEYS = {
    table_name: {
        (
            tuple(element.parent.name for element in constraint.elements),
            constraint.elements[0].column.table.name,
            tuple(element.column.name for element in constraint.elements),
            str(constraint.ondelete or "").upper(),
        )
        for constraint in model_table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }
    for table_name, model_table in _R5A_MODEL_TABLES.items()
}
_R2_TABLES = {
    "sale_rezerwacyjne",
    "plany_sali",
    "wersje_planu_sali",
    "pozycje_stolikow_planu",
    "krawedzie_sasiedztwa_planu",
    "kombinacje_stolow_planu",
    "skladniki_kombinacji_planu",
}
_R2_COLUMNS = {
    "sale_rezerwacyjne": {
        "id", "nazwa", "nazwa_klucz", "aktywna", "kolejnosc",
        "strategia_zapelniania", "priorytet",
    },
    "plany_sali": {"id", "sala_id", "nazwa"},
    "wersje_planu_sali": {
        "id", "plan_id", "numer", "status", "rewizja", "autor_id",
        "opublikowal_id", "utworzono_at", "zaktualizowano_at",
        "opublikowano_at",
    },
    "pozycje_stolikow_planu": {
        "id", "wersja_id", "stolik_id", "plan_x", "plan_y", "szerokosc",
        "wysokosc", "obrot", "aktywny_w_planie", "nazwa", "kolejnosc",
        "pojemnosc", "pojemnosc_min", "ksztalt", "cechy", "priorytet",
        "sekcja",
    },
    "krawedzie_sasiedztwa_planu": {
        "id", "wersja_id", "stolik_a_id", "stolik_b_id",
    },
    "kombinacje_stolow_planu": {
        "id", "wersja_id", "nazwa", "sklad_klucz", "pojemnosc_min",
        "pojemnosc_max", "priorytet", "kanal", "aktywna_w_planie",
    },
    "skladniki_kombinacji_planu": {
        "id", "kombinacja_id", "wersja_id", "stolik_id",
    },
}
_R3_TABLES = {
    "reguly_dostepnosci_rezerwacji",
    "rezerwacje_oblozenie_ledger",
    "reservation_override_context",
}
_R3_COLUMNS = {
    "reguly_dostepnosci_rezerwacji": {
        "id", "serwis_id", "sala_id", "kanal", "pacing_okno_min",
        "pacing_max_rez", "pacing_max_osob", "max_jednoczesnych_rez",
        "max_jednoczesnych_osob", "bufor_min", "okno_wyprzedzenia_dni",
        "cutoff_min", "min_grupa", "max_grupa", "duza_grupa_od",
        "duza_grupa_tryb",
    },
    "rezerwacje_oblozenie_ledger": {
        "id", "termin_id", "data", "minute", "sala_id", "kanal",
        "covers", "override", "created_at",
    },
    "reservation_override_context": {
        "id", "audit_id", "reason_code", "note",
    },
}
_R3_BASE_COLUMNS = {
    "godziny_otwarcia": {
        "krok_slotu_min", "domyslny_turn_time_min",
        "max_jednoczesnych_rez", "max_jednoczesnych_osob",
        "duza_grupa_od", "duza_grupa_tryb",
    },
    "wyjatki_kalendarza": {
        "krok_slotu_min", "domyslny_turn_time_min",
    },
    "sale_rezerwacyjne": {
        "online_aktywna", "wewnetrzna_aktywna",
        "limit_jednoczesnych_rez", "limit_jednoczesnych_osob",
        "domyslny_bufor_min",
    },
}
_R3_CHECK_TABLES = _R3_TABLES | set(_R3_BASE_COLUMNS)
_R3_CHECKS = {
    table_name: {
        constraint.name: str(constraint.sqltext)
        for constraint in Base.metadata.tables[table_name].constraints
        if constraint.name and hasattr(constraint, "sqltext")
        and (
            table_name in _R3_TABLES
            or any(
                column_name.casefold() in str(constraint.sqltext).casefold()
                for column_name in _R3_BASE_COLUMNS.get(table_name, set())
            )
        )
    }
    for table_name in _R3_CHECK_TABLES
}
_R3_NULLABLE = {
    table_name: {
        column.name: bool(column.nullable)
        for column in Base.metadata.tables[table_name].columns
        if column.name in _R3_COLUMNS.get(table_name, set())
    }
    for table_name in _R3_TABLES
}
def _strip_r2_outer_parentheses(sql: str) -> str:
    """Usuwa wyłącznie pary obejmujące całe wyrażenie, bez parsowania logiki."""
    while sql.startswith("(") and sql.endswith(")"):
        depth = 0
        closes_at_end = False
        for index, char in enumerate(sql):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    closes_at_end = index == len(sql) - 1
                    break
        if not closes_at_end:
            break
        sql = sql[1:-1]
    return sql


def _normalize_r2_index_predicate(value):
    if value is None:
        return None
    sql = re.sub(r"\s+", "", str(value).casefold())
    sql = sql.replace('"', "").replace("`", "").replace("[", "").replace("]", "")
    sql = _strip_r2_outer_parentheses(sql)
    sql = re.sub(r"::(?:text|charactervarying(?:\(\d+\))?)", "", sql)
    sql = _strip_r2_outer_parentheses(sql)
    sql = sql.replace("(status)", "status")
    return sql or None


def _r2_index_predicate_matches(actual, expected) -> bool:
    actual_sql = _normalize_r2_index_predicate(actual)
    expected_sql = _normalize_r2_index_predicate(expected)
    if expected_sql is None:
        return actual_sql is None
    actual_match = re.fullmatch(r"status='(draft|published)'", actual_sql or "")
    expected_match = re.fullmatch(r"status='(draft|published)'", expected_sql)
    return bool(
        actual_match
        and expected_match
        and actual_match.group(1) == expected_match.group(1)
    )


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
    r4_hold_columns = {
        "hold_stoliki_dodatkowe", "hold_godz_od", "hold_godz_do", "hold_bufor_min",
    }
    has_r4_holds = r4_hold_columns.issubset(waitlist_columns)
    public_hold_columns = (
        {column["name"] for column in schema.get_columns("rezerwacje_publiczne_holdy")}
        if "rezerwacje_publiczne_holdy" in table_names else set()
    )
    has_r5_public_holds = {
        "id", "state", "data", "godz_od", "godz_do", "stolik_id",
        "stoliki_dodatkowe", "bufor_min", "expires_at",
    }.issubset(public_hold_columns)
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
        # Reservation slots remain local business wall time. Hold lifecycles are
        # instants stored as naive UTC, so startup must use the runtime UTC clock.
        now = reservation_service.lifecycle_now_utc()
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
        if has_r5_public_holds:
            dates.update(
                value for (value,) in db.query(models.RezerwacjaPublicznyHold.data).filter(
                    models.RezerwacjaPublicznyHold.state == "active",
                    models.RezerwacjaPublicznyHold.expires_at > now,
                ).all()
            )
        guards = reservation_service.begin_locked_write(db, dates) if dates else ()

        if has_r5_public_holds:
            # Remove stale owner rows before rebuilding. An expired claim no longer
            # counts as occupied, but still owns the unique table/date/minute key.
            reservation_service.cleanup_expired_holds(db, now)
        else:
            # A pre-R5 repair cannot query the absent public-hold table. It can still
            # clear the expired waitlist projection using only columns present here.
            expired_values = {"hold_stolik_id": None, "hold_do": None}
            if has_r4_holds:
                expired_values.update({
                    "hold_stoliki_dodatkowe": None,
                    "hold_godz_od": None,
                    "hold_godz_do": None,
                    "hold_bufor_min": None,
                })
            db.query(models.ListaOczekujacych).filter(
                models.ListaOczekujacych.hold_do <= now,
            ).update(expired_values, synchronize_session=False)

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

        # W ścieżce naprawczej baza może być jeszcze na 0050. Nie ładuj całego
        # bieżącego modelu Termin, bo nowsze kolumny zostaną dodane dopiero po
        # odbudowie i oznaczeniu ledgera 0051.
        reservations = db.query(
            models.Termin.id,
            models.Termin.data,
            models.Termin.godz_od,
            models.Termin.godz_do,
            models.Termin.stolik_id,
            models.Termin.stoliki_dodatkowe,
            models.Termin.liczba_osob,
        ).filter(
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
                # Ta funkcja obsługuje również bazy sprzed 0059, w których tabela
                # minutowego obłożenia jeszcze nie istnieje. R3 odbudowuje ją osobno.
                include_capacity=False,
                now=now,
                # Schemat naprawianej bazy może nie mieć jeszcze kolumn holdów R4.
                cleanup_holds=False,
            )

        hold_projection = [
            models.ListaOczekujacych.id,
            models.ListaOczekujacych.data,
            models.ListaOczekujacych.hold_stolik_id,
            models.ListaOczekujacych.hold_do,
        ]
        if has_r4_holds:
            hold_projection.extend((
                models.ListaOczekujacych.hold_stoliki_dodatkowe,
                models.ListaOczekujacych.hold_godz_od,
                models.ListaOczekujacych.hold_godz_do,
                models.ListaOczekujacych.hold_bufor_min,
            ))
        holds = db.query(*hold_projection).filter(
            models.ListaOczekujacych.status == "oczekuje",
            models.ListaOczekujacych.hold_stolik_id.isnot(None),
            models.ListaOczekujacych.hold_do > now,
        ).order_by(models.ListaOczekujacych.id).all()
        for hold in holds:
            raw_extra = hold.hold_stoliki_dodatkowe if has_r4_holds else None
            if raw_extra is None:
                raw_extra = []
            if not isinstance(raw_extra, list):
                raise RuntimeError(
                    f"R4_FALLBACK_CORRUPT_HOLD_TABLES waitlist_id={hold.id}"
                )
            hold_ids = []
            for value in [hold.hold_stolik_id, *raw_extra]:
                if isinstance(value, bool):
                    raise RuntimeError(
                        f"R4_FALLBACK_CORRUPT_HOLD_TABLE waitlist_id={hold.id}"
                    )
                try:
                    table_id = int(value)
                except (TypeError, ValueError) as exc:
                    raise RuntimeError(
                        f"R4_FALLBACK_CORRUPT_HOLD_TABLE waitlist_id={hold.id}"
                    ) from exc
                if table_id <= 0 or table_id in hold_ids:
                    raise RuntimeError(
                        f"R4_FALLBACK_DUPLICATE_HOLD_TABLE waitlist_id={hold.id}"
                    )
                if table_id not in known_tables:
                    raise RuntimeError(
                        f"R0B_FALLBACK_MISSING_TABLE table_id={table_id} "
                        f"waitlist_id={hold.id}"
                    )
                hold_ids.append(table_id)
            start = hold.hold_godz_od if has_r4_holds else None
            end = hold.hold_godz_do if has_r4_holds else None
            if (start is None) != (end is None):
                raise RuntimeError(
                    f"R4_FALLBACK_INCOMPLETE_HOLD_INTERVAL waitlist_id={hold.id}"
                )
            reservation_service.replace_waitlist_hold(
                db,
                waitlist_id=hold.id,
                table_ids=hold_ids,
                data=hold.data,
                expires_at=hold.hold_do,
                now=now,
                start=start,
                end=end,
                buffer_min=(hold.hold_bufor_min or 0) if has_r4_holds else 0,
                cleanup_holds=False,
            )

        if has_r5_public_holds:
            public_holds = db.query(
                models.RezerwacjaPublicznyHold.id,
                models.RezerwacjaPublicznyHold.data,
                models.RezerwacjaPublicznyHold.godz_od,
                models.RezerwacjaPublicznyHold.godz_do,
                models.RezerwacjaPublicznyHold.stolik_id,
                models.RezerwacjaPublicznyHold.stoliki_dodatkowe,
                models.RezerwacjaPublicznyHold.bufor_min,
                models.RezerwacjaPublicznyHold.expires_at,
            ).filter(
                models.RezerwacjaPublicznyHold.state == "active",
                models.RezerwacjaPublicznyHold.expires_at > now,
            ).order_by(models.RezerwacjaPublicznyHold.id).all()
            for public_hold in public_holds:
                ids = table_ids(public_hold)
                reservation_service.replace_public_hold_claims(
                    db,
                    public_hold_id=public_hold.id,
                    table_ids=ids,
                    data=public_hold.data,
                    start=public_hold.godz_od,
                    end=public_hold.godz_do,
                    buffer_min=public_hold.bufor_min or 0,
                    expires_at=public_hold.expires_at,
                    now=now,
                    cleanup_holds=False,
                )

        reservation_service.touch_days(guards)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _rebuild_rezerwacje_oblozenie_ledger() -> None:
    """Odbudowuje buckety R3 tylko wtedy, gdy pełny schemat 0059 już istnieje."""
    from datetime import time as time_value

    from sqlalchemy import inspect

    import models
    import reservation_service

    schema = inspect(engine)
    tables = set(schema.get_table_names())
    if not _R3_TABLES.issubset(tables):
        return
    for table_name, expected in _R3_COLUMNS.items():
        actual = {column["name"] for column in schema.get_columns(table_name)}
        if actual != expected:
            raise RuntimeError(
                f"R3_FALLBACK_INCOMPLETE_TABLE table={table_name}"
            )
    for table_name, expected in _R3_BASE_COLUMNS.items():
        actual = {column["name"] for column in schema.get_columns(table_name)}
        if not expected.issubset(actual):
            raise RuntimeError(
                f"R3_FALLBACK_INCOMPLETE_COLUMNS table={table_name}"
            )

    def minute(value, *, code: str) -> int:
        if isinstance(value, str):
            try:
                value = time_value.fromisoformat(value)
            except ValueError as exc:
                raise RuntimeError(code) from exc
        if (
            not isinstance(value, time_value)
            or value.tzinfo is not None
            or value.second
            or value.microsecond
        ):
            raise RuntimeError(code)
        return value.hour * 60 + value.minute

    db = SessionLocal()
    try:
        active = tuple(reservation_service.ACTIVE_STATUSES)
        reservations = db.query(
            models.Termin.id,
            models.Termin.data,
            models.Termin.godz_od,
            models.Termin.godz_do,
            models.Termin.stolik_id,
            models.Termin.stoliki_dodatkowe,
            models.Termin.kanal,
        ).filter(
            models.Termin.rodzaj == "stolik",
            models.Termin.status.in_(active),
        ).order_by(models.Termin.id).all()
        pacing_by_termin = {
            row.termin_id: row
            for row in db.query(models.RezerwacjaPacingLedger).all()
        }
        expected = {row.id for row in reservations if row.godz_od is not None}
        if expected != set(pacing_by_termin):
            raise RuntimeError("R3_FALLBACK_PACING_LEDGER_MISMATCH")

        room_by_table = {
            table_id: room_id for table_id, room_id in db.query(
                models.Stolik.id, models.Stolik.sala_id,
            ).all()
        }
        services_by_weekday: dict[int, list] = {}
        for service in db.query(models.GodzinyOtwarcia).filter_by(
            aktywny=True,
        ).order_by(
            models.GodzinyOtwarcia.dzien_tygodnia,
            models.GodzinyOtwarcia.godz_od,
        ).all():
            services_by_weekday.setdefault(service.dzien_tygodnia, []).append(service)
        exceptions_by_date = {
            row.data: row for row in db.query(models.WyjatekKalendarza).filter_by(
                typ="godziny_specjalne",
            ).order_by(models.WyjatekKalendarza.id).all()
        }

        def duration(record, start_minute: int) -> int:
            special = exceptions_by_date.get(record.data)
            if special is not None:
                value = (
                    special.domyslny_turn_time_min
                    or special.dlugosc_slotu_min
                )
                if value:
                    return int(value)
            services = services_by_weekday.get(record.data.weekday(), ())
            selected = None
            for service in services:
                service_start = minute(
                    service.godz_od, code="R3_FALLBACK_INVALID_SERVICE_TIME",
                )
                service_end = minute(
                    service.ostatni_zasiadek or service.godz_do,
                    code="R3_FALLBACK_INVALID_SERVICE_TIME",
                )
                if service_start <= start_minute <= service_end:
                    selected = service
                    break
            if selected is None and services:
                selected = services[0]
            return int(
                (selected.domyslny_turn_time_min or selected.dlugosc_slotu_min)
                if selected is not None else 120
            )

        db.query(models.RezerwacjaOblozenieLedger).delete(
            synchronize_session=False,
        )
        values = []
        for record in reservations:
            if record.godz_od is None:
                if record.stolik_id is not None or record.stoliki_dodatkowe:
                    raise RuntimeError(
                        f"R3_FALLBACK_MISSING_START record_id={record.id}"
                    )
                continue
            pacing = pacing_by_termin[record.id]
            start_minute = minute(
                record.godz_od,
                code=f"R3_FALLBACK_INVALID_START record_id={record.id}",
            )
            if start_minute != pacing.start_minute or record.data != pacing.data:
                raise RuntimeError(
                    f"R3_FALLBACK_PACING_MISMATCH record_id={record.id}"
                )
            end_minute = (
                minute(
                    record.godz_do,
                    code=f"R3_FALLBACK_INVALID_END record_id={record.id}",
                )
                if record.godz_do is not None
                else start_minute + duration(record, start_minute)
            )
            if end_minute <= start_minute or end_minute > 1440:
                raise RuntimeError(
                    f"R3_FALLBACK_INVALID_INTERVAL record_id={record.id}"
                )

            raw_extra = record.stoliki_dodatkowe
            if raw_extra is None:
                extra = []
            elif isinstance(raw_extra, list):
                extra = raw_extra
            else:
                raise RuntimeError(
                    f"R3_FALLBACK_CORRUPT_EXTRA_TABLES record_id={record.id}"
                )
            ids = ([] if record.stolik_id is None else [record.stolik_id]) + extra
            normalized_ids = []
            for raw in ids:
                if isinstance(raw, bool):
                    raise RuntimeError(
                        f"R3_FALLBACK_INVALID_TABLE record_id={record.id}"
                    )
                try:
                    table_id = int(raw)
                except (TypeError, ValueError) as exc:
                    raise RuntimeError(
                        f"R3_FALLBACK_INVALID_TABLE record_id={record.id}"
                    ) from exc
                if table_id <= 0 or table_id in normalized_ids:
                    raise RuntimeError(
                        f"R3_FALLBACK_INVALID_TABLE record_id={record.id}"
                    )
                normalized_ids.append(table_id)
            if any(table_id not in room_by_table for table_id in normalized_ids):
                raise RuntimeError(
                    f"R3_FALLBACK_MISSING_TABLE record_id={record.id}"
                )
            rooms = {room_by_table[table_id] for table_id in normalized_ids}
            concrete_rooms = {room_id for room_id in rooms if room_id is not None}
            if len(concrete_rooms) > 1 or (concrete_rooms and None in rooms):
                raise RuntimeError(
                    f"R3_FALLBACK_CROSS_ROOM record_id={record.id}"
                )
            room_id = next(iter(concrete_rooms)) if concrete_rooms else None
            for bucket_minute in range(start_minute, end_minute):
                values.append({
                    "termin_id": record.id,
                    "data": record.data,
                    "minute": bucket_minute,
                    "sala_id": room_id,
                    "kanal": (
                        "online" if record.kanal == "online" else "wewnetrzna"
                    ),
                    "covers": int(pacing.covers or 0),
                    "override": bool(pacing.override),
                    "created_at": pacing.created_at,
                })
        table = models.RezerwacjaOblozenieLedger.__table__
        for offset in range(0, len(values), 2000):
            db.execute(table.insert(), values[offset:offset + 2000])
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


def _r5a_type_signature(column_type):
    """Portable contract for the concrete SQL types used by the R5a schema."""
    while isinstance(column_type, TypeDecorator):
        implementation = column_type.impl
        if isinstance(implementation, type):
            implementation = implementation()
        if implementation is column_type:
            break
        column_type = implementation

    if isinstance(column_type, sqltypes.Text):
        return ("text",)
    if isinstance(column_type, sqltypes.String):
        return ("string", getattr(column_type, "length", None))
    if isinstance(column_type, sqltypes.JSON):
        return ("json",)
    if isinstance(column_type, sqltypes.Boolean):
        return ("boolean",)
    if isinstance(column_type, sqltypes.SmallInteger):
        return ("smallint",)
    if isinstance(column_type, sqltypes.BigInteger):
        return ("bigint",)
    if isinstance(column_type, sqltypes.Integer):
        return ("integer",)
    if isinstance(column_type, sqltypes.DateTime):
        return ("datetime", bool(getattr(column_type, "timezone", False)))
    if isinstance(column_type, sqltypes.Date):
        return ("date",)
    if isinstance(column_type, sqltypes.Time):
        return ("time", bool(getattr(column_type, "timezone", False)))
    return (
        "unsupported",
        type(column_type).__module__,
        type(column_type).__name__,
        str(column_type).casefold(),
    )


def _r5a_default_signature(value, type_signature):
    """Normalizes only static defaults used by R5a across SQLite/PostgreSQL."""
    if value is None:
        return None
    value = getattr(value, "arg", value)
    raw = str(value).strip().casefold()
    raw = _strip_r2_outer_parentheses(raw)
    raw = re.sub(
        r"::\s*[a-z_][a-z0-9_\s]*(?:\(\s*\d+\s*\))?(?:\[\])?$",
        "",
        raw,
    ).strip()
    raw = _strip_r2_outer_parentheses(raw)
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {"'", '"'}:
        raw = raw[1:-1].replace("''", "'")

    family = type_signature[0]
    if family == "boolean":
        if raw in {"0", "false", "f"}:
            return ("boolean", False)
        if raw in {"1", "true", "t"}:
            return ("boolean", True)
    elif family in {"integer", "smallint", "bigint"}:
        try:
            return ("integer", int(raw))
        except ValueError:
            pass
    elif family in {"string", "text"}:
        return ("string", raw)
    return ("raw", re.sub(r"\s+", "", raw))


def _validate_r5a_column_contract(
    inspector, table_name: str, column_names, *, exact: bool,
) -> None:
    model_table = Base.metadata.tables[table_name]
    actual = {
        column["name"]: column
        for column in inspector.get_columns(table_name)
    }
    expected_names = set(column_names)
    if (
        (exact and set(actual) != expected_names)
        or (not exact and not expected_names.issubset(actual))
    ):
        raise RuntimeError(f"Tabela {table_name} jest niekompletna dla R5a.")

    for column_name in expected_names:
        model_column = model_table.columns[column_name]
        reflected = actual[column_name]
        if bool(reflected.get("nullable")) != bool(model_column.nullable):
            raise RuntimeError(
                f"Kolumna {table_name}.{column_name} ma nieprawidlowa "
                "nullowalnosc R5a."
            )
        expected_type = _r5a_type_signature(model_column.type)
        if _r5a_type_signature(reflected["type"]) != expected_type:
            raise RuntimeError(
                f"Kolumna {table_name}.{column_name} ma nieprawidlowy typ R5a."
            )
        # PostgreSQL can expose the sequence behind an integer primary key as a
        # default. It is an implementation detail of SERIAL/IDENTITY, not drift.
        if model_column.primary_key:
            continue
        model_default = (
            model_column.server_default.arg
            if model_column.server_default is not None else None
        )
        if (
            _r5a_default_signature(reflected.get("default"), expected_type)
            != _r5a_default_signature(model_default, expected_type)
        ):
            raise RuntimeError(
                f"Kolumna {table_name}.{column_name} ma nieprawidlowy default R5a."
            )


def _r5a_check_signature(value, dialect_name: str) -> str:
    """Keeps SQLite grouping exact and tolerates PostgreSQL deparser casts/ANY."""
    if dialect_name == "sqlite":
        return _strip_r2_outer_parentheses(_normalise_check_sql(value))

    sql = str(value or "").casefold().replace('"', "").replace("`", "")
    sql = re.sub(r"\s+", "", sql)
    sql = re.sub(
        r"::[a-z_][a-z0-9_]*(?:\(\d+\))?(?:\[\])?",
        "",
        sql,
    )
    # pg_get_constraintdef deparses VARCHAR IN (...) as = ANY (ARRAY[...]).
    sql = sql.replace("=any", "in").replace("array[", "(").replace("]", ")")
    return sql.replace("(", "").replace(")", "")


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
    if not (
        model_tables - {_R1A_AUDIT_TABLE} - _R2_TABLES - _R3_TABLES
        - _R5A_TABLES
    ).issubset(tables):
        return False
    for table_name in _R0B_LEDGER_TABLES:
        expected = {
            column.name for column in Base.metadata.tables[table_name].columns
        }
        if table_name == "rezerwacje_stoliki_claims":
            expected.discard("public_hold_id")
        actual = {
            column["name"] for column in inspector.get_columns(table_name)
        }
        if actual != expected:
            return False
    return True


def _r2_adoption_topology_is_valid(conn) -> bool:
    """Waliduje semantyke grafu, ktorej nie da sie wyrazic samymi CHECK/FK."""
    from sqlalchemy import text

    positions = {
        (int(row["wersja_id"]), int(row["stolik_id"])): {
            "pojemnosc": int(row["pojemnosc"]),
            "aktywny": bool(row["aktywny_w_planie"]),
        }
        for row in conn.execute(text(
            "SELECT wersja_id, stolik_id, pojemnosc, aktywny_w_planie "
            "FROM pozycje_stolikow_planu"
        )).mappings()
        if row["pojemnosc"] is not None
    }

    adjacency = {}
    for row in conn.execute(text(
        "SELECT wersja_id, stolik_a_id, stolik_b_id "
        "FROM krawedzie_sasiedztwa_planu"
    )).mappings():
        version_id = int(row["wersja_id"])
        a = int(row["stolik_a_id"])
        b = int(row["stolik_b_id"])
        if (
            a >= b
            or (version_id, a) not in positions
            or (version_id, b) not in positions
        ):
            return False
        version_adjacency = adjacency.setdefault(version_id, {})
        version_adjacency.setdefault(a, set()).add(b)
        version_adjacency.setdefault(b, set()).add(a)

    members_by_combination = {}
    for row in conn.execute(text(
        "SELECT kombinacja_id, wersja_id, stolik_id "
        "FROM skladniki_kombinacji_planu"
    )).mappings():
        members_by_combination.setdefault(int(row["kombinacja_id"]), []).append(
            (int(row["wersja_id"]), int(row["stolik_id"]))
        )

    seen_combinations = set()
    for row in conn.execute(text(
        "SELECT id, wersja_id, sklad_klucz, pojemnosc_min, pojemnosc_max, "
        "aktywna_w_planie FROM kombinacje_stolow_planu"
    )).mappings():
        combination_id = int(row["id"])
        version_id = int(row["wersja_id"])
        seen_combinations.add(combination_id)
        member_rows = members_by_combination.get(combination_id, [])
        member_ids = sorted(table_id for _, table_id in member_rows)
        if (
            len(member_ids) < 2
            or len(member_ids) != len(set(member_ids))
            or any(member_version != version_id for member_version, _ in member_rows)
            or any((version_id, table_id) not in positions for table_id in member_ids)
            or row["sklad_klucz"] != ",".join(str(value) for value in member_ids)
        ):
            return False

        physical_capacity = sum(
            positions[(version_id, table_id)]["pojemnosc"]
            for table_id in member_ids
        )
        minimum = int(row["pojemnosc_min"])
        maximum = int(row["pojemnosc_max"])
        if minimum < 1 or maximum < minimum or maximum > physical_capacity:
            return False
        if bool(row["aktywna_w_planie"]) and any(
            not positions[(version_id, table_id)]["aktywny"]
            for table_id in member_ids
        ):
            return False

        member_set = set(member_ids)
        visited = {member_ids[0]}
        pending = [member_ids[0]]
        version_adjacency = adjacency.get(version_id, {})
        while pending:
            current = pending.pop()
            for neighbour in version_adjacency.get(current, set()) & member_set:
                if neighbour not in visited:
                    visited.add(neighbour)
                    pending.append(neighbour)
        if visited != member_set:
            return False

    # FK moze istniec w definicji, ale historyczna baza SQLite mogla miec
    # ``foreign_keys=OFF`` podczas recznego zapisu. Nie stempluj sierot.
    if set(members_by_combination) - seen_combinations:
        return False
    return True


def _validate_r2_adoption_schema(inspector=None) -> bool:
    """Weryfikuje niewersjonowaną bazę R2 przed stemplem bieżącego head.

    Sama obecność tabel nie dowodzi wykonania migracji danych: każdy stół musi
    należeć do sali, a sala musi mieć opublikowany plan. Walidator jest używany
    wyłącznie przy adopcji bazy bez ``alembic_version``.
    """
    from sqlalchemy import CheckConstraint, inspect, text
    from reservation_names import room_name_key

    inspector = inspector or inspect(engine)
    if engine.dialect.name == "postgresql":
        raise RuntimeError(
            "R2_POSTGRES_ADOPTION_REQUIRES_VERIFIED_STAMP: automatyczna adopcja "
            "niewersjonowanej bazy PostgreSQL jest zablokowana, ponieważ sama "
            "introspekcja nazw CHECK nie dowodzi ich działania. Zweryfikuj ręcznie "
            "CHECK/UNIQUE/FK oraz backfill R2, następnie wykonaj "
            "`alembic stamp 0058_r22b_strategia_proweniencja` i `alembic upgrade head`."
        )

    def normalized_sql(value) -> str:
        raw = "" if value is None else str(value)
        sql = re.sub(r"\s+", "", raw.casefold())
        sql = sql.replace('"', "").replace("`", "").replace("[", "").replace("]", "")
        while sql.startswith("(") and sql.endswith(")"):
            sql = sql[1:-1]
        return sql

    tables = set(inspector.get_table_names())
    if not _R2_TABLES.issubset(tables) or "stoliki" not in tables:
        raise RuntimeError(
            "Schemat R2 jest niekompletny; nie można oznaczyć bieżącej migracji."
        )

    has_complete_r3 = _R3_TABLES.issubset(tables)
    for table_name, expected in _R2_COLUMNS.items():
        actual = {
            column["name"] for column in inspector.get_columns(table_name)
        }
        allowed = expected | (
            _R3_BASE_COLUMNS.get(table_name, set()) if has_complete_r3 else set()
        )
        if actual != allowed:
            raise RuntimeError(
                f"Tabela {table_name} jest niekompletna; nie można oznaczyć bieżącej migracji."
            )
    termin_columns = {
        column["name"] for column in inspector.get_columns("terminy")
    }
    if not {
        "przydzial_wersja_planu_id",
        "przydzial_kombinacja_planu_id",
    }.issubset(termin_columns):
        raise RuntimeError(
            "Tabela terminy nie ma proweniencji R2.2b; nie można oznaczyć bieżącej migracji."
        )
    stoliki_columns = {
        column["name"] for column in inspector.get_columns("stoliki")
    }
    if "sala_id" not in stoliki_columns:
        raise RuntimeError(
            "Brak stoliki.sala_id; nie można oznaczyć bieżącej migracji."
        )

    required_indexes = {
        "sale_rezerwacyjne": {
            "ix_sale_rezerwacyjne_id", "uq_sale_rezerwacyjne_nazwa",
            "uq_sale_rezerwacyjne_nazwa_klucz",
        },
        "plany_sali": {
            "ix_plany_sali_id", "ix_plany_sali_sala_id",
            "uq_plany_sali_sala",
        },
        "wersje_planu_sali": {
            "ix_wersje_planu_sali_id",
            "ix_wersje_planu_sali_plan_id",
            "ix_wersje_planu_sali_plan_status",
            "uq_wersje_planu_sali_plan_numer",
            "uq_wersje_planu_sali_jeden_draft",
            "uq_wersje_planu_sali_jeden_published",
        },
        "pozycje_stolikow_planu": {
            "ix_pozycje_stolikow_planu_id",
            "ix_pozycje_stolikow_planu_wersja_id",
            "ix_pozycje_stolikow_planu_stolik_id",
            "uq_pozycje_stolikow_wersja_stolik",
        },
        "krawedzie_sasiedztwa_planu": {
            "ix_krawedzie_sasiedztwa_planu_id",
            "ix_krawedzie_sasiedztwa_planu_wersja_id",
            "uq_krawedzie_sasiedztwa_planu_para",
        },
        "kombinacje_stolow_planu": {
            "ix_kombinacje_stolow_planu_id",
            "ix_kombinacje_stolow_planu_wersja_id",
            "uq_kombinacje_stolow_planu_id_wersja",
            "uq_kombinacje_stolow_planu_wersja_sklad",
        },
        "skladniki_kombinacji_planu": {
            "ix_skladniki_kombinacji_planu_id",
            "ix_skladniki_kombinacji_planu_kombinacja_id",
            "ix_skladniki_kombinacji_planu_wersja_id",
            "ix_skladniki_kombinacji_planu_stolik_id",
            "uq_skladniki_kombinacji_planu_stolik",
        },
        "stoliki": {"ix_stoliki_sala_id"},
        "terminy": {
            "ix_terminy_przydzial_wersja_planu_id",
            "ix_terminy_przydzial_kombinacja_planu_id",
        },
    }
    for table_name, expected in required_indexes.items():
        actual = {
            index["name"] for index in inspector.get_indexes(table_name)
            if index.get("name")
        }
        unique_constraints = {
            constraint["name"]
            for constraint in inspector.get_unique_constraints(table_name)
            if constraint.get("name")
        }
        if not expected.issubset(actual | unique_constraints):
            raise RuntimeError(
                f"Tabela {table_name} nie ma wymaganych indeksów R2."
            )

    # Nazwa obiektu nie wystarcza do bezpiecznej adopcji: fałszywy zwykły
    # indeks o nazwie indeksu UNIQUE nie może pozwolić na stamp bieżącego head.
    expected_index_shapes = {
        "sale_rezerwacyjne": {
            "uq_sale_rezerwacyjne_nazwa_klucz": (
                ("nazwa_klucz",), True, None,
            ),
        },
        "wersje_planu_sali": {
            "ix_wersje_planu_sali_plan_status": (("plan_id", "status"), False, None),
            "uq_wersje_planu_sali_jeden_draft": (
                ("plan_id",), True, "status = 'draft'",
            ),
            "uq_wersje_planu_sali_jeden_published": (
                ("plan_id",), True, "status = 'published'",
            ),
        },
        "pozycje_stolikow_planu": {
            "ix_pozycje_stolikow_planu_wersja_id": (("wersja_id",), False, None),
            "ix_pozycje_stolikow_planu_stolik_id": (("stolik_id",), False, None),
        },
        "krawedzie_sasiedztwa_planu": {
            "ix_krawedzie_sasiedztwa_planu_wersja_id": (
                ("wersja_id",), False, None,
            ),
        },
        "kombinacje_stolow_planu": {
            "ix_kombinacje_stolow_planu_wersja_id": (
                ("wersja_id",), False, None,
            ),
        },
        "skladniki_kombinacji_planu": {
            "ix_skladniki_kombinacji_planu_kombinacja_id": (
                ("kombinacja_id",), False, None,
            ),
            "ix_skladniki_kombinacji_planu_wersja_id": (
                ("wersja_id",), False, None,
            ),
            "ix_skladniki_kombinacji_planu_stolik_id": (
                ("stolik_id",), False, None,
            ),
        },
        "stoliki": {
            "ix_stoliki_sala_id": (("sala_id",), False, None),
        },
        "terminy": {
            "ix_terminy_przydzial_wersja_planu_id": (
                ("przydzial_wersja_planu_id",), False, None,
            ),
            "ix_terminy_przydzial_kombinacja_planu_id": (
                ("przydzial_kombinacja_planu_id",), False, None,
            ),
        },
    }
    for table_name, shapes in expected_index_shapes.items():
        actual = {
            index["name"]: index for index in inspector.get_indexes(table_name)
            if index.get("name")
        }
        for name, (columns, unique, predicate) in shapes.items():
            index = actual.get(name)
            dialect_options = index.get("dialect_options", {}) if index else {}
            where = " ".join(
                str(value).casefold()
                for key, value in dialect_options.items()
                if key.endswith("_where") and value is not None
            )
            if (
                index is None
                or tuple(index.get("column_names") or ()) != columns
                or bool(index.get("unique")) is not unique
                or (
                    not _r2_index_predicate_matches(where, predicate)
                )
            ):
                raise RuntimeError(
                    f"Indeks {name} ma nieprawidłową definicję R2."
                )

    expected_uniques = {
        "sale_rezerwacyjne": {
            "uq_sale_rezerwacyjne_nazwa": ("nazwa",),
        },
        "plany_sali": {
            "uq_plany_sali_sala": ("sala_id",),
        },
        "wersje_planu_sali": {
            "uq_wersje_planu_sali_plan_numer": ("plan_id", "numer"),
        },
        "pozycje_stolikow_planu": {
            "uq_pozycje_stolikow_wersja_stolik": ("wersja_id", "stolik_id"),
        },
        "krawedzie_sasiedztwa_planu": {
            "uq_krawedzie_sasiedztwa_planu_para": (
                "wersja_id", "stolik_a_id", "stolik_b_id",
            ),
        },
        "kombinacje_stolow_planu": {
            "uq_kombinacje_stolow_planu_id_wersja": ("id", "wersja_id"),
            "uq_kombinacje_stolow_planu_wersja_sklad": (
                "wersja_id", "sklad_klucz",
            ),
        },
        "skladniki_kombinacji_planu": {
            "uq_skladniki_kombinacji_planu_stolik": (
                "kombinacja_id", "stolik_id",
            ),
        },
    }
    for table_name, expected in expected_uniques.items():
        actual = {
            item.get("name"): tuple(item.get("column_names") or ())
            for item in inspector.get_unique_constraints(table_name)
            if item.get("name")
        }
        if any(actual.get(name) != columns for name, columns in expected.items()):
            raise RuntimeError(
                f"Tabela {table_name} ma nieprawidłowe ograniczenie UNIQUE R2."
            )

    for table_name in _R2_TABLES:
        model_table = Base.metadata.tables[table_name]
        actual_columns = {
            column["name"]: column for column in inspector.get_columns(table_name)
        }
        r2_column_names = _R2_COLUMNS[table_name]
        if any(
            bool(actual_columns[column.name].get("nullable")) != bool(column.nullable)
            for column in model_table.columns
            if column.name in r2_column_names
        ):
            raise RuntimeError(
                f"Tabela {table_name} ma nieprawidłową nullowalność R2."
            )
        expected_checks = {
            constraint.name: normalized_sql(constraint.sqltext)
            for constraint in model_table.constraints
            if isinstance(constraint, CheckConstraint) and constraint.name
            and not any(
                column_name.casefold() in normalized_sql(constraint.sqltext)
                for column_name in _R3_BASE_COLUMNS.get(table_name, set())
            )
        }
        actual_checks = {
            constraint.get("name"): normalized_sql(constraint.get("sqltext"))
            for constraint in inspector.get_check_constraints(table_name)
            if constraint.get("name")
        }
        if engine.dialect.name == "sqlite":
            # Inspector SQLAlchemy potrafi skleić nazwy kilku CHECK-ów dodanych
            # natywnym ALTER TABLE ADD COLUMN. Baza nadal egzekwuje poprawne DDL;
            # weryfikujemy więc dokładny nazwany fragment źródłowego CREATE TABLE.
            missing_from_inspector = set(expected_checks) - set(actual_checks)
            if missing_from_inspector:
                with engine.connect() as conn:
                    table_sql = conn.execute(text(
                        "SELECT sql FROM sqlite_master "
                        "WHERE type='table' AND name=:table_name"
                    ), {"table_name": table_name}).scalar_one_or_none()
                normalized_table_sql = normalized_sql(table_sql)
                for name in missing_from_inspector:
                    marker = (
                        f"constraint{name}check({expected_checks[name]})"
                    )
                    if marker in normalized_table_sql:
                        actual_checks[name] = expected_checks[name]
        missing_checks = set(expected_checks) - set(actual_checks)
        # SQLite zwraca zapis CHECK bez przepisywania, więc możemy porównać go
        # dokładnie. PostgreSQL normalizuje IN do ANY i dodaje casty; tam pełne
        # bezpieczeństwo adopcji zapewniają nazwy ograniczeń oraz osobno
        # sprawdzane kolumny/nullowalność/UNIQUE/FK/indeksy i spójność danych.
        mismatched_checks = engine.dialect.name == "sqlite" and any(
            actual_checks.get(name) != sql for name, sql in expected_checks.items()
        )
        if missing_checks or mismatched_checks:
            raise RuntimeError(
                f"Tabela {table_name} nie ma wymaganych CHECK R2."
            )

    termin_model = Base.metadata.tables["terminy"]
    expected_termin_checks = {
        constraint.name: normalized_sql(constraint.sqltext)
        for constraint in termin_model.constraints
        if (
            isinstance(constraint, CheckConstraint)
            and constraint.name
            and constraint.name.startswith("ck_terminy_przydzial_")
        )
    }
    actual_termin_checks = {
        constraint.get("name"): normalized_sql(constraint.get("sqltext"))
        for constraint in inspector.get_check_constraints("terminy")
        if constraint.get("name")
    }
    if engine.dialect.name == "sqlite":
        with engine.connect() as conn:
            terminy_sql = conn.execute(text(
                "SELECT sql FROM sqlite_master "
                "WHERE type='table' AND name='terminy'"
            )).scalar_one_or_none()
        normalized_terminy_sql = normalized_sql(terminy_sql)
        for name, check_sql in expected_termin_checks.items():
            if (
                actual_termin_checks.get(name) != check_sql
                and f"constraint{name}check({check_sql})" in normalized_terminy_sql
            ):
                actual_termin_checks[name] = check_sql
    if any(
        actual_termin_checks.get(name) != sql
        for name, sql in expected_termin_checks.items()
    ):
        raise RuntimeError(
            "Tabela terminy nie ma wymaganych CHECK proweniencji R2.2b."
        )

    expected_fks = {
        "stoliki": {("sala_id",): ("sale_rezerwacyjne", ("id",), None)},
        "plany_sali": {("sala_id",): ("sale_rezerwacyjne", ("id",), "RESTRICT")},
        "wersje_planu_sali": {
            ("plan_id",): ("plany_sali", ("id",), "CASCADE"),
            ("autor_id",): ("users", ("id",), "SET NULL"),
            ("opublikowal_id",): ("users", ("id",), "SET NULL"),
        },
        "pozycje_stolikow_planu": {
            ("wersja_id",): ("wersje_planu_sali", ("id",), "CASCADE"),
            ("stolik_id",): ("stoliki", ("id",), "RESTRICT"),
        },
        "krawedzie_sasiedztwa_planu": {
            ("wersja_id",): ("wersje_planu_sali", ("id",), "CASCADE"),
            ("wersja_id", "stolik_a_id"): (
                "pozycje_stolikow_planu", ("wersja_id", "stolik_id"), "CASCADE",
            ),
            ("wersja_id", "stolik_b_id"): (
                "pozycje_stolikow_planu", ("wersja_id", "stolik_id"), "CASCADE",
            ),
        },
        "kombinacje_stolow_planu": {
            ("wersja_id",): ("wersje_planu_sali", ("id",), "CASCADE"),
        },
        "skladniki_kombinacji_planu": {
            ("kombinacja_id", "wersja_id"): (
                "kombinacje_stolow_planu", ("id", "wersja_id"), "CASCADE",
            ),
            ("wersja_id", "stolik_id"): (
                "pozycje_stolikow_planu", ("wersja_id", "stolik_id"), "CASCADE",
            ),
        },
    }
    for table_name, expected in expected_fks.items():
        actual = {}
        for foreign_key in inspector.get_foreign_keys(table_name):
            columns = tuple(foreign_key.get("constrained_columns") or ())
            options = foreign_key.get("options") or {}
            actual[columns] = (
                foreign_key.get("referred_table"),
                tuple(foreign_key.get("referred_columns") or ()),
                (options.get("ondelete") or "").upper() or None,
            )
        if any(actual.get(columns) != definition for columns, definition in expected.items()):
            raise RuntimeError(
                f"Tabela {table_name} ma nieprawidłowy klucz obcy R2."
            )

    termin_fks = {}
    for foreign_key in inspector.get_foreign_keys("terminy"):
        columns = tuple(foreign_key.get("constrained_columns") or ())
        options = foreign_key.get("options") or {}
        termin_fks[columns] = (
            foreign_key.get("referred_table"),
            tuple(foreign_key.get("referred_columns") or ()),
            (options.get("ondelete") or "").upper() or None,
        )
    version_fk = termin_fks.get(("przydzial_wersja_planu_id",))
    valid_version_fk = (
        version_fk is not None
        and version_fk[:2] == ("wersje_planu_sali", ("id",))
        and version_fk[2] in {None, "RESTRICT"}
    )
    composite_fk = termin_fks.get((
        "przydzial_kombinacja_planu_id", "przydzial_wersja_planu_id",
    ))
    valid_composite_fk = (
        composite_fk is not None
        and composite_fk[:2] == (
            "kombinacje_stolow_planu", ("id", "wersja_id"),
        )
        and composite_fk[2] in {None, "RESTRICT"}
    )
    if not valid_version_fk:
        raise RuntimeError(
            "Tabela terminy ma nieprawidłowy klucz obcy proweniencji R2.2b."
        )
    if not valid_composite_fk:
        # SQLite nie potrafi dodać kompozytowego FK bez niebezpiecznego rebuild.
        # Kanoniczna migracja używa FK do kombinacji oraz dwóch symetrycznych
        # triggerów sprawdzających zgodność wersji na INSERT i UPDATE.
        combination_fk = termin_fks.get(("przydzial_kombinacja_planu_id",))
        valid_combination_fk = (
            combination_fk is not None
            and combination_fk[:2] == ("kombinacje_stolow_planu", ("id",))
            and combination_fk[2] in {None, "RESTRICT"}
        )
        with engine.connect() as conn:
            triggers = {
                row["name"]: normalized_sql(row["sql"])
                for row in conn.execute(text(
                    "SELECT name, sql FROM sqlite_master "
                    "WHERE type='trigger' AND name IN ("
                    "'fk_terminy_przydzial_kombinacja_wersja_insert',"
                    "'fk_terminy_przydzial_kombinacja_wersja_update'"
                    ")"
                )).mappings()
            }
        expected_trigger_sql = {
            "fk_terminy_przydzial_kombinacja_wersja_insert": normalized_sql(
                "CREATE TRIGGER fk_terminy_przydzial_kombinacja_wersja_insert "
                "BEFORE INSERT ON terminy "
                "WHEN NEW.przydzial_kombinacja_planu_id IS NOT NULL "
                "AND NOT EXISTS ("
                "SELECT 1 FROM kombinacje_stolow_planu k "
                "WHERE k.id = NEW.przydzial_kombinacja_planu_id "
                "AND k.wersja_id = NEW.przydzial_wersja_planu_id"
                ") BEGIN SELECT RAISE(ABORT, "
                "'przydzial combination/version mismatch'); END"
            ),
            "fk_terminy_przydzial_kombinacja_wersja_update": normalized_sql(
                "CREATE TRIGGER fk_terminy_przydzial_kombinacja_wersja_update "
                "BEFORE UPDATE OF przydzial_kombinacja_planu_id, "
                "przydzial_wersja_planu_id ON terminy "
                "WHEN NEW.przydzial_kombinacja_planu_id IS NOT NULL "
                "AND NOT EXISTS ("
                "SELECT 1 FROM kombinacje_stolow_planu k "
                "WHERE k.id = NEW.przydzial_kombinacja_planu_id "
                "AND k.wersja_id = NEW.przydzial_wersja_planu_id"
                ") BEGIN SELECT RAISE(ABORT, "
                "'przydzial combination/version mismatch'); END"
            ),
        }
        valid_triggers = all(
            triggers.get(name) == expected_sql
            for name, expected_sql in expected_trigger_sql.items()
        )
        if not valid_combination_fk or not valid_triggers:
            raise RuntimeError(
                "Tabela terminy nie chroni pary proweniencji R2.2b."
            )

    with engine.connect() as conn:
        invalid_room_keys = sum(
            1
            for row in conn.execute(text(
                "SELECT nazwa, nazwa_klucz FROM sale_rezerwacyjne"
            )).mappings()
            if room_name_key(row["nazwa"] or "") != row["nazwa_klucz"]
        )
        missing_rooms = conn.execute(text(
            "SELECT count(*) FROM stoliki WHERE sala_id IS NULL"
        )).scalar_one()
        rooms_without_published_plan = conn.execute(text(
            "SELECT count(*) FROM sale_rezerwacyjne s "
            "WHERE (SELECT count(*) FROM plany_sali p WHERE p.sala_id = s.id) != 1 "
            "OR (SELECT count(*) FROM plany_sali p "
            "    JOIN wersje_planu_sali w ON w.plan_id = p.id "
            "    WHERE p.sala_id = s.id AND w.status = 'published') != 1"
        )).scalar_one()
        tables_without_position = conn.execute(text(
            "SELECT count(*) FROM stoliki s "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM pozycje_stolikow_planu pos "
            "  JOIN wersje_planu_sali w ON w.id = pos.wersja_id "
            "  JOIN plany_sali p ON p.id = w.plan_id "
            "  WHERE pos.stolik_id = s.id AND p.sala_id = s.sala_id "
            "    AND w.status = 'published'"
            ")"
        )).scalar_one()
        cross_room_positions = conn.execute(text(
            "SELECT count(*) FROM pozycje_stolikow_planu pos "
            "JOIN wersje_planu_sali w ON w.id = pos.wersja_id "
            "JOIN plany_sali p ON p.id = w.plan_id "
            "JOIN stoliki s ON s.id = pos.stolik_id "
            "WHERE p.sala_id <> s.sala_id"
        )).scalar_one()
        positions_without_snapshot_properties = conn.execute(text(
            "SELECT count(*) FROM pozycje_stolikow_planu "
            "WHERE nazwa IS NULL OR length(trim(nazwa)) = 0 "
            "OR kolejnosc IS NULL OR pojemnosc IS NULL"
        )).scalar_one()
        invalid_topology = not _r2_adoption_topology_is_valid(conn)
        invalid_provenance = conn.execute(text(
            "SELECT count(*) FROM terminy t "
            "WHERE (t.przydzial_wersja_planu_id IS NOT NULL AND NOT EXISTS ("
            "  SELECT 1 FROM wersje_planu_sali w "
            "  WHERE w.id = t.przydzial_wersja_planu_id"
            ")) OR (t.przydzial_kombinacja_planu_id IS NOT NULL AND NOT EXISTS ("
            "  SELECT 1 FROM kombinacje_stolow_planu k "
            "  WHERE k.id = t.przydzial_kombinacja_planu_id "
            "    AND k.wersja_id = t.przydzial_wersja_planu_id"
            "))"
        )).scalar_one()
    if (
        invalid_room_keys
        or missing_rooms
        or rooms_without_published_plan
        or tables_without_position
        or cross_room_positions
        or positions_without_snapshot_properties
        or invalid_topology
        or invalid_provenance
    ):
        raise RuntimeError(
            "Backfill R2 jest niekompletny; nie można oznaczyć bieżącej migracji."
        )
    return True


def _r3_occupancy_adoption_is_valid(conn) -> bool:
    """Sprawdza kompletność i ciągłość minutowych bucketów bez PII."""
    from datetime import time as time_value
    from sqlalchemy import text

    def minute(value):
        if value is None:
            return None
        if isinstance(value, str):
            try:
                value = time_value.fromisoformat(value)
            except ValueError:
                return None
        if (
            not isinstance(value, time_value)
            or value.tzinfo is not None
            or value.second
            or value.microsecond
        ):
            return None
        return value.hour * 60 + value.minute

    missing_pacing = conn.execute(text(
        "SELECT count(*) FROM terminy t "
        "LEFT JOIN rezerwacje_pacing_ledger p ON p.termin_id=t.id "
        "WHERE t.rodzaj='stolik' AND t.status IN ('rezerwacja','potwierdzona') "
        "AND t.godz_od IS NOT NULL AND p.termin_id IS NULL"
    )).scalar_one()
    extra_buckets = conn.execute(text(
        "SELECT count(*) FROM rezerwacje_oblozenie_ledger o "
        "JOIN terminy t ON t.id=o.termin_id "
        "WHERE t.rodzaj<>'stolik' OR t.status NOT IN ('rezerwacja','potwierdzona') "
        "OR t.godz_od IS NULL"
    )).scalar_one()
    invalid_context = conn.execute(text(
        "SELECT count(*) FROM reservation_override_context c "
        "JOIN reservation_audit a ON a.id=c.audit_id "
        "WHERE a.action<>'override'"
    )).scalar_one()
    if missing_pacing or extra_buckets or invalid_context:
        return False

    rows = conn.execute(text(
        "SELECT p.termin_id,p.data,p.start_minute,p.covers,t.godz_do,"
        "count(o.id) AS bucket_count,min(o.minute) AS first_minute,"
        "max(o.minute) AS last_minute,"
        "sum(CASE WHEN o.data<>p.data OR o.covers<>p.covers THEN 1 ELSE 0 END) "
        "AS mismatched_values, count(DISTINCT o.sala_id) AS room_count "
        "FROM rezerwacje_pacing_ledger p "
        "JOIN terminy t ON t.id=p.termin_id "
        "LEFT JOIN rezerwacje_oblozenie_ledger o ON o.termin_id=p.termin_id "
        "WHERE t.rodzaj='stolik' AND t.status IN ('rezerwacja','potwierdzona') "
        "AND t.godz_od IS NOT NULL "
        "GROUP BY p.termin_id,p.data,p.start_minute,p.covers,t.godz_do"
    )).mappings().all()
    for row in rows:
        count = int(row["bucket_count"] or 0)
        first = row["first_minute"]
        last = row["last_minute"]
        if (
            count <= 0
            or first != row["start_minute"]
            or last is None
            or count != int(last) - int(first) + 1
            or int(row["mismatched_values"] or 0)
            or int(row["room_count"] or 0) > 1
        ):
            return False
        end = minute(row["godz_do"])
        if row["godz_do"] is not None and (end is None or int(last) != end - 1):
            return False
    return True


def _validate_r3_adoption_schema(inspector=None, *, validate_data: bool = True) -> bool:
    """Waliduje pełny niewersjonowany schemat R3 przed stemplem 0059."""
    from sqlalchemy import inspect, text

    inspector = inspector or inspect(engine)
    if engine.dialect.name == "postgresql":
        raise RuntimeError(
            "R3_POSTGRES_ADOPTION_REQUIRES_VERIFIED_STAMP: automatyczna adopcja "
            "niewersjonowanej bazy PostgreSQL jest zablokowana. Zweryfikuj kolumny, "
            "CHECK/UNIQUE/FK, partial indexes i backfill oblozenia, nastepnie wykonaj "
            "`alembic stamp 0059_r3_reguly_dostepnosci` i `alembic upgrade head`."
        )

    tables = set(inspector.get_table_names())
    if not _R3_TABLES.issubset(tables):
        raise RuntimeError(
            "Schemat R3 jest niekompletny; nie mozna oznaczyc migracji 0059."
        )
    for table_name, expected in _R3_COLUMNS.items():
        columns = {
            column["name"]: bool(column["nullable"])
            for column in inspector.get_columns(table_name)
        }
        if set(columns) != expected or columns != _R3_NULLABLE[table_name]:
            raise RuntimeError(
                f"Tabela {table_name} jest niekompletna dla R3."
            )
    for table_name, expected in _R3_BASE_COLUMNS.items():
        actual = {column["name"] for column in inspector.get_columns(table_name)}
        if not expected.issubset(actual):
            raise RuntimeError(
                f"Tabela {table_name} nie ma wymaganych kolumn R3."
            )

    expected_indexes = {
        "reguly_dostepnosci_rezerwacji": {
            "uq_reguly_dostepnosci_global_kanal": (
                ("kanal",), True, "serwis_id IS NULL AND sala_id IS NULL",
            ),
            "uq_reguly_dostepnosci_serwis_kanal": (
                ("serwis_id", "kanal"), True,
                "serwis_id IS NOT NULL AND sala_id IS NULL",
            ),
            "uq_reguly_dostepnosci_sala_kanal": (
                ("sala_id", "kanal"), True,
                "serwis_id IS NULL AND sala_id IS NOT NULL",
            ),
            "uq_reguly_dostepnosci_serwis_sala_kanal": (
                ("serwis_id", "sala_id", "kanal"), True,
                "serwis_id IS NOT NULL AND sala_id IS NOT NULL",
            ),
        },
        "rezerwacje_oblozenie_ledger": {
            "ix_rezerwacje_oblozenie_data_minute_sala_kanal": (
                ("data", "minute", "sala_id", "kanal"), False, None,
            ),
            "ix_rezerwacje_oblozenie_termin_id": (
                ("termin_id",), False, None,
            ),
        },
        "reservation_override_context": {
            "ix_reservation_override_context_reason_code": (
                ("reason_code",), False, None,
            ),
        },
    }
    for table_name, shapes in expected_indexes.items():
        actual = {
            index["name"]: index for index in inspector.get_indexes(table_name)
            if index.get("name")
        }
        for name, (columns, unique, predicate) in shapes.items():
            index = actual.get(name)
            dialect_options = index.get("dialect_options", {}) if index else {}
            where = " ".join(
                str(value) for key, value in dialect_options.items()
                if key.endswith("_where") and value is not None
            )
            if (
                index is None
                or tuple(index.get("column_names") or ()) != columns
                or bool(index.get("unique")) is not unique
                or _normalize_r2_index_predicate(where)
                != _normalize_r2_index_predicate(predicate)
            ):
                raise RuntimeError(
                    f"Indeks {name} ma nieprawidlowa definicje R3."
                )

    expected_uniques = {
        "rezerwacje_oblozenie_ledger": {
            "uq_rezerwacje_oblozenie_termin_minute": ("termin_id", "minute"),
        },
        "reservation_override_context": {
            "uq_reservation_override_context_audit_id": ("audit_id",),
        },
    }
    for table_name, expected in expected_uniques.items():
        actual = {
            item.get("name"): tuple(item.get("column_names") or ())
            for item in inspector.get_unique_constraints(table_name)
        }
        if any(actual.get(name) != columns for name, columns in expected.items()):
            raise RuntimeError(
                f"Tabela {table_name} nie ma wymaganych UNIQUE R3."
            )

    expected_fks = {
        "reguly_dostepnosci_rezerwacji": {
            (("serwis_id",), "godziny_otwarcia", ("id",), "CASCADE"),
            (("sala_id",), "sale_rezerwacyjne", ("id",), "CASCADE"),
        },
        "rezerwacje_oblozenie_ledger": {
            (("termin_id",), "terminy", ("id",), "CASCADE"),
            (("sala_id",), "sale_rezerwacyjne", ("id",), "RESTRICT"),
        },
        "reservation_override_context": {
            (("audit_id",), "reservation_audit", ("id",), "CASCADE"),
        },
    }
    for table_name, expected in expected_fks.items():
        actual = {
            (
                tuple(fk.get("constrained_columns") or ()),
                fk.get("referred_table"),
                tuple(fk.get("referred_columns") or ()),
                str((fk.get("options") or {}).get("ondelete") or "").upper(),
            )
            for fk in inspector.get_foreign_keys(table_name)
        }
        if not expected.issubset(actual):
            raise RuntimeError(
                f"Tabela {table_name} nie ma wymaganych FK R3."
            )

    for table_name, expected in _R3_CHECKS.items():
        actual = {
            constraint.get("name"): constraint.get("sqltext")
            for constraint in inspector.get_check_constraints(table_name)
        }
        if engine.dialect.name == "sqlite":
            with engine.connect() as conn:
                table_sql = conn.execute(text(
                    "SELECT sql FROM sqlite_master "
                    "WHERE type='table' AND name=:table_name"
                ), {"table_name": table_name}).scalar_one_or_none()
            normalized_table_sql = _normalise_check_sql(table_sql)
            for name, sql in expected.items():
                marker = _normalise_check_sql(
                    f"CONSTRAINT {name} CHECK ({sql})"
                )
                if marker not in normalized_table_sql:
                    raise RuntimeError(
                        f"Tabela {table_name} nie ma kanonicznego CHECK {name} R3."
                    )
        elif (
            not set(expected).issubset(actual)
            or any(
                _normalise_check_sql(actual[name]) != _normalise_check_sql(sql)
                for name, sql in expected.items()
            )
        ):
            raise RuntimeError(
                f"Tabela {table_name} nie ma kanonicznych CHECK R3."
            )

    if validate_data:
        with engine.connect() as conn:
            if not _r3_occupancy_adoption_is_valid(conn):
                raise RuntimeError(
                    "Backfill R3 jest niekompletny; nie mozna oznaczyc migracji 0059."
                )
    return True


def _validate_r5a_adoption_schema(inspector=None) -> bool:
    """Fail-closed validation before adopting an unversioned create_all R5a schema."""
    from sqlalchemy import inspect

    inspector = inspector or inspect(engine)
    bind = getattr(inspector, "bind", None)
    dialect_name = getattr(getattr(bind, "dialect", None), "name", None)
    dialect_name = dialect_name or engine.dialect.name
    tables = set(inspector.get_table_names())
    if not _R5A_TABLES.issubset(tables):
        raise RuntimeError(
            "Schemat R5a jest niekompletny; nie mozna oznaczyc migracji 0061."
        )
    for table_name, expected_columns in _R5A_COLUMNS.items():
        _validate_r5a_column_contract(
            inspector, table_name, expected_columns, exact=True,
        )

        expected_pk = tuple(
            column.name for column in _R5A_MODEL_TABLES[table_name].primary_key.columns
        )
        actual_pk = tuple(
            inspector.get_pk_constraint(table_name).get("constrained_columns") or ()
        )
        if actual_pk != expected_pk:
            raise RuntimeError(
                f"Tabela {table_name} ma nieprawidlowy PRIMARY KEY R5a."
            )

        reflected_indexes = {
            item.get("name"): (
                tuple(item.get("column_names") or ()),
                bool(item.get("unique")),
            )
            for item in inspector.get_indexes(table_name)
            if item.get("name")
        }
        for name, expected_shape in _R5A_INDEXES[table_name].items():
            if reflected_indexes.get(name) != expected_shape:
                raise RuntimeError(
                    f"Indeks {name} ma nieprawidlowa definicje R5a."
                )

        reflected_uniques = {
            item.get("name"): tuple(item.get("column_names") or ())
            for item in inspector.get_unique_constraints(table_name)
            if item.get("name")
        }
        # Some PostgreSQL/driver combinations additionally expose a UNIQUE
        # constraint as an index. Accept that representation, but still require
        # the canonical name and conflict-target column order.
        for name, (columns, unique) in reflected_indexes.items():
            if unique:
                reflected_uniques.setdefault(name, columns)
        for name, expected_columns in _R5A_UNIQUES[table_name].items():
            if reflected_uniques.get(name) != expected_columns:
                raise RuntimeError(
                    f"Ograniczenie {name} ma nieprawidlowa definicje UNIQUE R5a."
                )

        reflected_fks = {
            (
                tuple(item.get("constrained_columns") or ()),
                item.get("referred_table"),
                tuple(item.get("referred_columns") or ()),
                str((item.get("options") or {}).get("ondelete") or "").upper(),
            )
            for item in inspector.get_foreign_keys(table_name)
        }
        if not _R5A_FOREIGN_KEYS[table_name].issubset(reflected_fks):
            raise RuntimeError(
                f"Tabela {table_name} nie ma wymaganych FK R5a."
            )

        reflected_checks = {
            item.get("name"): item.get("sqltext")
            for item in inspector.get_check_constraints(table_name)
            if item.get("name")
        }
        for name, expected_sql in _R5A_CHECKS[table_name].items():
            actual_sql = reflected_checks.get(name)
            if (
                actual_sql is None
                or _r5a_check_signature(actual_sql, dialect_name)
                != _r5a_check_signature(expected_sql, dialect_name)
            ):
                raise RuntimeError(
                    f"CHECK {name} ma nieprawidlowa definicje R5a."
                )

    for table_name, expected in _R5A_BASE_COLUMNS.items():
        if table_name not in tables:
            raise RuntimeError(f"Brak tabeli bazowej R5a: {table_name}.")
        _validate_r5a_column_contract(
            inspector, table_name, expected, exact=False,
        )

    claim_fks = {
        (
            tuple(fk.get("constrained_columns") or ()),
            fk.get("referred_table"),
            tuple(fk.get("referred_columns") or ()),
            str((fk.get("options") or {}).get("ondelete") or "").upper(),
        )
        for fk in inspector.get_foreign_keys("rezerwacje_stoliki_claims")
    }
    if (
        ("public_hold_id",), "rezerwacje_publiczne_holdy", ("id",), "CASCADE",
    ) not in claim_fks:
        raise RuntimeError(
            "Tabela rezerwacje_stoliki_claims nie ma wymaganego FK R5a."
        )
    claim_indexes = {
        item.get("name"): (
            tuple(item.get("column_names") or ()),
            bool(item.get("unique")),
        )
        for item in inspector.get_indexes("rezerwacje_stoliki_claims")
        if item.get("name")
    }
    for name, expected_shape in _R5A_BASE_INDEXES[
        "rezerwacje_stoliki_claims"
    ].items():
        if claim_indexes.get(name) != expected_shape:
            raise RuntimeError(
                f"Indeks {name} ma nieprawidlowa definicje R5a."
            )

    claim_uniques = {
        item.get("name"): tuple(item.get("column_names") or ())
        for item in inspector.get_unique_constraints("rezerwacje_stoliki_claims")
        if item.get("name")
    }
    # PostgreSQL can expose a named UNIQUE constraint as a unique index.
    for name, (columns, unique) in claim_indexes.items():
        if unique:
            claim_uniques.setdefault(name, columns)
    for name, expected_columns in _R5A_BASE_UNIQUES[
        "rezerwacje_stoliki_claims"
    ].items():
        if claim_uniques.get(name) != expected_columns:
            raise RuntimeError(
                f"Ograniczenie {name} ma nieprawidlowa definicje UNIQUE R5a."
            )

    for table_name, expected_checks in _R5A_BASE_CHECKS.items():
        reflected_checks = {
            item.get("name"): item.get("sqltext")
            for item in inspector.get_check_constraints(table_name)
            if item.get("name")
        }
        for name, expected_sql in expected_checks.items():
            actual_sql = reflected_checks.get(name)
            if (
                actual_sql is None
                or _r5a_check_signature(actual_sql, dialect_name)
                != _r5a_check_signature(expected_sql, dialect_name)
            ):
                raise RuntimeError(
                    f"CHECK {name} ma nieprawidlowa definicje R5a."
                )
    return True


def _invalidate_legacy_public_tokens() -> int:
    """Clears reversible plaintext public tokens on the stamp-only adoption path."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    statements = []
    if "terminy" in tables and "token_potwierdzenia" in {
        column["name"] for column in inspector.get_columns("terminy")
    }:
        statements.append(
            "UPDATE terminy SET token_potwierdzenia=NULL "
            "WHERE token_potwierdzenia IS NOT NULL"
        )
    if "lista_oczekujacych" in tables and "token" in {
        column["name"] for column in inspector.get_columns("lista_oczekujacych")
    }:
        statements.append(
            "UPDATE lista_oczekujacych SET token=NULL WHERE token IS NOT NULL"
        )
    changed = 0
    with engine.begin() as conn:
        for statement in statements:
            result = conn.execute(text(statement))
            changed += int(result.rowcount or 0)
    return changed


def init_db():
    """Przygotowanie schematu, świadome Alembica (idempotentne).

    • Baza „legacy" (są tabele, brak alembic_version) — utworzona przed wprowadzeniem
      Alembica: domyka brakujące kolumny i ADOPTUJE bazę do Alembica (stamp head),
      bez odtwarzania danych. Dotyczy istniejącego wdrożenia produkcyjnego.
    • Pusta baza (nowy klient / dev / Electron) lub baza zarządzana przez Alembica:
      `upgrade head` — buduje schemat z migracji lub stosuje nowe migracje.
    • Od 0053 brak Alembica kończy start kontrolowanym błędem: create_all nie
      wykonuje backfillu sal i opublikowanych wersji planu.
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
            _require_alembic_run(lambda command, cfg: command.upgrade(cfg, "head"))
            return
        if current_revision == _R0B_REVISION and _R1A_AUDIT_TABLE in tables:
            _mark_r1a_fallback_revision()
            _require_alembic_run(lambda command, cfg: command.upgrade(cfg, "head"))
            return
        if current_revision == _R1A_REVISION:
            _validate_r1a_audit_schema(insp)
            _require_alembic_run(lambda command, cfg: command.upgrade(cfg, "head"))
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
        r5a_tables_present = _R5A_TABLES & tables
        if r5a_tables_present and r5a_tables_present != _R5A_TABLES:
            raise RuntimeError(
                "Schemat R5a jest czesciowy; nie mozna bezpiecznie adoptowac bazy."
            )
        r3_tables_present = _R3_TABLES & tables
        if r3_tables_present and r3_tables_present != _R3_TABLES:
            raise RuntimeError(
                "Schemat R3 jest czesciowy; nie mozna bezpiecznie adoptowac bazy."
            )
        complete_r3 = (
            (model_tables - _R5A_TABLES).issubset(tables)
            and _R3_TABLES.issubset(tables)
            and not r5a_tables_present
        )
        complete_r2 = (
            (model_tables - _R3_TABLES - _R5A_TABLES).issubset(tables)
            and _R2_TABLES.issubset(tables)
            and not r3_tables_present
            and not r5a_tables_present
        )
        complete_r0b = _is_complete_r0b_schema(insp, tables, model_tables)
        pre_r0b_tables = (
            model_tables - _R0B_LEDGER_TABLES - {_R1A_AUDIT_TABLE}
            - _R2_TABLES - _R3_TABLES - _R5A_TABLES
        )
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
            # Walidacja struktury przed rebuildem chroni przed query do częściowo
            # utworzonego schematu. PostgreSQL kończy się tu kontrolowanym wymogiem stampu.
            _validate_r3_adoption_schema(insp, validate_data=False)
            _validate_r2_adoption_schema(insp)
            _validate_r5a_adoption_schema(insp)
            _ensure_schema()
            _rebuild_rezerwacje_ledger()
            _rebuild_rezerwacje_oblozenie_ledger()
            _sanitize_legacy_rodo_audit_resources()
            _invalidate_legacy_public_tokens()
            refreshed = inspect(engine)
            _validate_r3_adoption_schema(refreshed)
            _validate_r5a_adoption_schema(refreshed)
            _require_alembic_run(
                lambda command, cfg: command.stamp(cfg, _R5A_REVISION)
            )
            _require_alembic_run(lambda command, cfg: command.upgrade(cfg, "head"))
            return
        if complete_r3:
            # Pełny niewersjonowany schemat 0060: pozwól migracji 0061 wykonać
            # unieważnienie historycznych tokenów oraz dodać atomowe zasoby publiczne.
            _validate_r1a_audit_schema(insp)
            _validate_r2_adoption_schema(insp)
            _validate_r3_adoption_schema(insp)
            _require_alembic_run(
                lambda command, cfg: command.stamp(cfg, _R3_REVISION)
            )
            _require_alembic_run(lambda command, cfg: command.upgrade(cfg, "head"))
            return
        if complete_r2:
            # Pełna niewersjonowana baza 0058 nie może spaść do baseline ani
            # dostać create_all tabel R3 przed wykonaniem migracyjnego backfillu.
            _validate_r1a_audit_schema(insp)
            _validate_r2_adoption_schema(insp)
            _require_alembic_run(
                lambda command, cfg: command.stamp(cfg, _R2_REVISION)
            )
            _require_alembic_run(lambda command, cfg: command.upgrade(cfg, "head"))
            return
        if complete_r0b:
            # Schemat 0051 bez alembic_version ma już ledger. Stemplowanie go jako 0050
            # uruchomiłoby ponownie CREATE TABLE 0051 i przerwało start aplikacji.
            if _R1A_AUDIT_TABLE in tables:
                _validate_r1a_audit_schema(insp)
                revision = _R1A_REVISION
            else:
                revision = _R0B_REVISION
            _require_alembic_run(
                lambda command, cfg: command.stamp(cfg, revision)
            )
            _require_alembic_run(lambda command, cfg: command.upgrade(cfg, "head"))
            return
        else:
            if complete_pre_r0b:
                _ensure_schema()
                _require_alembic_run(
                    lambda command, cfg: command.stamp(cfg, _PRE_R0B_REVISION)
                )
                _require_alembic_run(lambda command, cfg: command.upgrade(cfg, "head"))
                return
            # Nie dodawaj pól z najnowszych migracji przed upgrade: migracja doda je sama.
            # Jest to istotne dla 0050 (source identity), której ADD COLUMN nie jest idempotentne.
            _ensure_schema(include_source_identity=False)
        if not model_tables.issubset(tables):
            _require_alembic_run(
                lambda command, cfg: command.stamp(cfg, "0001_baseline")
            )
            _require_alembic_run(lambda command, cfg: command.upgrade(cfg, "head"))
        return

    # Pusta baza lub baza zarządzana przez Alembica → upgrade do najnowszej wersji.
    _require_alembic_run(lambda command, cfg: command.upgrade(cfg, "head"))
