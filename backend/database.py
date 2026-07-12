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
_R2_REVISION = "0054_room_name_key"
_R2_TABLES = {
    "sale_rezerwacyjne",
    "plany_sali",
    "wersje_planu_sali",
    "pozycje_stolikow_planu",
}
_R2_COLUMNS = {
    "sale_rezerwacyjne": {
        "id", "nazwa", "nazwa_klucz", "aktywna", "kolejnosc",
    },
    "plany_sali": {"id", "sala_id", "nazwa"},
    "wersje_planu_sali": {
        "id", "plan_id", "numer", "status", "rewizja", "autor_id",
        "opublikowal_id", "utworzono_at", "zaktualizowano_at",
        "opublikowano_at",
    },
    "pozycje_stolikow_planu": {
        "id", "wersja_id", "stolik_id", "plan_x", "plan_y", "szerokosc",
        "wysokosc", "obrot", "aktywny_w_planie",
    },
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
    if not (model_tables - {_R1A_AUDIT_TABLE} - _R2_TABLES).issubset(tables):
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
            "`alembic stamp 0054_room_name_key` i `alembic upgrade head`."
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

    for table_name, expected in _R2_COLUMNS.items():
        actual = {
            column["name"] for column in inspector.get_columns(table_name)
        }
        if actual != expected:
            raise RuntimeError(
                f"Tabela {table_name} jest niekompletna; nie można oznaczyć bieżącej migracji."
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
        "stoliki": {"ix_stoliki_sala_id"},
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
        "stoliki": {
            "ix_stoliki_sala_id": (("sala_id",), False, None),
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
        if any(
            bool(actual_columns[column.name].get("nullable")) != bool(column.nullable)
            for column in model_table.columns
        ):
            raise RuntimeError(
                f"Tabela {table_name} ma nieprawidłową nullowalność R2."
            )
        expected_checks = {
            constraint.name: normalized_sql(constraint.sqltext)
            for constraint in model_table.constraints
            if isinstance(constraint, CheckConstraint) and constraint.name
        }
        actual_checks = {
            constraint.get("name"): normalized_sql(constraint.get("sqltext"))
            for constraint in inspector.get_check_constraints(table_name)
            if constraint.get("name")
        }
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
    if (
        invalid_room_keys
        or missing_rooms
        or rooms_without_published_plan
        or tables_without_position
        or cross_room_positions
    ):
        raise RuntimeError(
            "Backfill R2 jest niekompletny; nie można oznaczyć bieżącej migracji."
        )
    return True


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
        complete_r0b = _is_complete_r0b_schema(insp, tables, model_tables)
        pre_r0b_tables = (
            model_tables - _R0B_LEDGER_TABLES - {_R1A_AUDIT_TABLE} - _R2_TABLES
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
            _ensure_schema()
            _rebuild_rezerwacje_ledger()
            _sanitize_legacy_rodo_audit_resources()
            if _R2_TABLES.issubset(tables):
                _validate_r2_adoption_schema(insp)
                revision = _R2_REVISION
            else:
                revision = _R1A_REVISION
            _require_alembic_run(
                lambda command, cfg: command.stamp(cfg, revision)
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
