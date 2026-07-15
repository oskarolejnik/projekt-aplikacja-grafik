"""Reguły dostępności, rozdzielony turn time i ledger obłożenia R3.

Revision ID: 0059_r3_reguly_dostepnosci
Revises: 0058_r22b_strategia_proweniencja
"""
from __future__ import annotations

import json
from datetime import date, datetime, time
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0059_r3_reguly_dostepnosci"
down_revision: Union[str, None] = "0058_r22b_strategia_proweniencja"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ACTIVE_STATUSES = ("rezerwacja", "potwierdzona")
_OVERRIDE_REASON_CODES = (
    "guest_request",
    "large_group_confirmed",
    "event_exception",
    "operational_decision",
    "walk_in",
    "other",
    "legacy_confirmation",
)
_LEGACY_ONLINE_SERVICE_NAME = "Cały dzień · zgodność R3"


def _as_date(value: Any, *, code: str) -> date:
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value)
        except ValueError as exc:
            raise RuntimeError(code) from exc
    if not isinstance(value, date):
        raise RuntimeError(code)
    return value


def _as_time(value: Any, *, code: str) -> time:
    if isinstance(value, str):
        try:
            value = time.fromisoformat(value)
        except ValueError as exc:
            raise RuntimeError(code) from exc
    if not isinstance(value, time) or value.tzinfo is not None:
        raise RuntimeError(code)
    return value


def _minute(value: Any, *, code: str) -> int:
    parsed = _as_time(value, code=code)
    if parsed.second or parsed.microsecond:
        raise RuntimeError(code)
    return parsed.hour * 60 + parsed.minute


def _table_ids(primary: Any, extra_raw: Any, *, record_id: int) -> list[int]:
    if extra_raw is None:
        extra: Any = []
    elif isinstance(extra_raw, str):
        try:
            extra = json.loads(extra_raw)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                f"R3_BACKFILL_CORRUPT_EXTRA_TABLES record_id={record_id}"
            ) from exc
    else:
        extra = extra_raw
    if not isinstance(extra, list):
        raise RuntimeError(f"R3_BACKFILL_CORRUPT_EXTRA_TABLES record_id={record_id}")

    values = ([] if primary is None else [primary]) + extra
    result: list[int] = []
    for raw in values:
        if isinstance(raw, bool):
            raise RuntimeError(f"R3_BACKFILL_INVALID_TABLE record_id={record_id}")
        try:
            table_id = int(raw)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                f"R3_BACKFILL_INVALID_TABLE record_id={record_id}"
            ) from exc
        if table_id <= 0 or table_id in result:
            raise RuntimeError(f"R3_BACKFILL_INVALID_TABLE record_id={record_id}")
        result.append(table_id)
    return result


def _legacy_duration(
    *,
    booking_date: date,
    start_minute: int,
    services_by_weekday: dict[int, list[dict[str, Any]]],
    exceptions_by_date: dict[date, list[dict[str, Any]]],
) -> int:
    special = next(
        (
            row for row in exceptions_by_date.get(booking_date, ())
            if row["typ"] == "godziny_specjalne"
            and row["godz_od"] is not None
            and row["godz_do"] is not None
        ),
        None,
    )
    if special is not None and special["dlugosc_slotu_min"] is not None:
        return int(special["dlugosc_slotu_min"])

    services = services_by_weekday.get(booking_date.weekday(), ())
    selected = None
    for row in services:
        start = _minute(row["godz_od"], code="R3_BACKFILL_INVALID_SERVICE_TIME")
        last = _minute(
            row["ostatni_zasiadek"] or row["godz_do"],
            code="R3_BACKFILL_INVALID_SERVICE_TIME",
        )
        if start <= start_minute <= last:
            selected = row
            break
    if selected is None and services:
        selected = services[0]
    return int(selected["dlugosc_slotu_min"] if selected is not None else 120)


def _prepare_occupancy_backfill(bind) -> list[dict[str, Any]]:
    """Waliduje komplet danych przed pierwszym nietransakcyjnym DDL SQLite."""
    terminy = sa.table(
        "terminy",
        sa.column("id", sa.Integer()),
        sa.column("data", sa.Date()),
        sa.column("status", sa.String()),
        sa.column("rodzaj", sa.String()),
        sa.column("godz_od", sa.Time()),
        sa.column("godz_do", sa.Time()),
        sa.column("stolik_id", sa.Integer()),
        sa.column("stoliki_dodatkowe", sa.JSON()),
        sa.column("kanal", sa.String()),
    )
    pacing = sa.table(
        "rezerwacje_pacing_ledger",
        sa.column("termin_id", sa.Integer()),
        sa.column("data", sa.Date()),
        sa.column("start_minute", sa.Integer()),
        sa.column("covers", sa.Integer()),
        sa.column("override", sa.Boolean()),
        sa.column("created_at", sa.DateTime()),
    )
    stoliki = sa.table(
        "stoliki",
        sa.column("id", sa.Integer()),
        sa.column("sala_id", sa.Integer()),
    )
    serwisy = sa.table(
        "godziny_otwarcia",
        sa.column("dzien_tygodnia", sa.Integer()),
        sa.column("godz_od", sa.Time()),
        sa.column("godz_do", sa.Time()),
        sa.column("ostatni_zasiadek", sa.Time()),
        sa.column("dlugosc_slotu_min", sa.Integer()),
        sa.column("aktywny", sa.Boolean()),
    )
    wyjatki = sa.table(
        "wyjatki_kalendarza",
        sa.column("data", sa.Date()),
        sa.column("typ", sa.String()),
        sa.column("godz_od", sa.Time()),
        sa.column("godz_do", sa.Time()),
        sa.column("dlugosc_slotu_min", sa.Integer()),
    )

    service_rows = bind.execute(
        sa.select(serwisy).order_by(
            serwisy.c.dzien_tygodnia, serwisy.c.godz_od,
        )
    ).mappings().all()
    services_by_weekday: dict[int, list[dict[str, Any]]] = {}
    for row in service_rows:
        duration = int(row["dlugosc_slotu_min"] or 0)
        if duration < 1 or duration > 1439:
            raise RuntimeError("R3_BACKFILL_INVALID_LEGACY_DURATION")
        if row["aktywny"]:
            services_by_weekday.setdefault(int(row["dzien_tygodnia"]), []).append(
                dict(row)
            )

    exception_rows = bind.execute(sa.select(wyjatki)).mappings().all()
    exceptions_by_date: dict[date, list[dict[str, Any]]] = {}
    for row in exception_rows:
        duration = row["dlugosc_slotu_min"]
        if duration is not None and not 1 <= int(duration) <= 1439:
            raise RuntimeError("R3_BACKFILL_INVALID_LEGACY_EXCEPTION_DURATION")
        day = _as_date(row["data"], code="R3_BACKFILL_INVALID_EXCEPTION_DATE")
        exceptions_by_date.setdefault(day, []).append(dict(row))

    active_rows = bind.execute(
        sa.select(terminy).where(
            terminy.c.rodzaj == "stolik",
            terminy.c.status.in_(_ACTIVE_STATUSES),
        ).order_by(terminy.c.id)
    ).mappings().all()
    pacing_rows = bind.execute(sa.select(pacing).order_by(pacing.c.termin_id)).mappings().all()
    pacing_by_termin = {int(row["termin_id"]): row for row in pacing_rows}
    expected = {
        int(row["id"]) for row in active_rows if row["godz_od"] is not None
    }
    if expected != set(pacing_by_termin):
        raise RuntimeError("R3_BACKFILL_PACING_LEDGER_MISMATCH")

    room_by_table = {
        int(row["id"]): row["sala_id"]
        for row in bind.execute(sa.select(stoliki)).mappings().all()
    }
    values: list[dict[str, Any]] = []
    for termin in active_rows:
        record_id = int(termin["id"])
        if termin["godz_od"] is None:
            if termin["stolik_id"] is not None or termin["stoliki_dodatkowe"]:
                raise RuntimeError(f"R3_BACKFILL_MISSING_START record_id={record_id}")
            continue
        pacing_row = pacing_by_termin[record_id]
        booking_date = _as_date(
            pacing_row["data"], code=f"R3_BACKFILL_INVALID_DATE record_id={record_id}",
        )
        if booking_date != _as_date(
            termin["data"], code=f"R3_BACKFILL_INVALID_DATE record_id={record_id}",
        ):
            raise RuntimeError(f"R3_BACKFILL_DATE_MISMATCH record_id={record_id}")
        start_minute = int(pacing_row["start_minute"])
        if start_minute != _minute(
            termin["godz_od"], code=f"R3_BACKFILL_INVALID_START record_id={record_id}",
        ):
            raise RuntimeError(f"R3_BACKFILL_START_MISMATCH record_id={record_id}")

        if termin["godz_do"] is not None:
            end_minute = _minute(
                termin["godz_do"], code=f"R3_BACKFILL_INVALID_END record_id={record_id}",
            )
        else:
            duration = _legacy_duration(
                booking_date=booking_date,
                start_minute=start_minute,
                services_by_weekday=services_by_weekday,
                exceptions_by_date=exceptions_by_date,
            )
            end_minute = start_minute + duration
        if end_minute <= start_minute or end_minute > 1440:
            raise RuntimeError(
                f"R3_BACKFILL_INVALID_INTERVAL record_id={record_id}"
            )

        table_ids = _table_ids(
            termin["stolik_id"], termin["stoliki_dodatkowe"], record_id=record_id,
        )
        missing = [table_id for table_id in table_ids if table_id not in room_by_table]
        if missing:
            raise RuntimeError(f"R3_BACKFILL_MISSING_TABLE record_id={record_id}")
        rooms = {room_by_table[table_id] for table_id in table_ids}
        concrete_rooms = {room_id for room_id in rooms if room_id is not None}
        # Historyczne, w całości roomless przydziały uczestniczą w limicie
        # globalnym/kanałowym z ``sala_id=NULL``. Mieszany albo wielosalowy zestaw
        # jest niejednoznaczny i musi zostać naprawiony przed migracją.
        if len(concrete_rooms) > 1 or (concrete_rooms and None in rooms):
            raise RuntimeError(f"R3_BACKFILL_CROSS_ROOM record_id={record_id}")
        room_id = next(iter(concrete_rooms)) if concrete_rooms else None

        covers = int(pacing_row["covers"] or 0)
        if covers < 0:
            raise RuntimeError(f"R3_BACKFILL_INVALID_COVERS record_id={record_id}")
        channel = "online" if termin["kanal"] == "online" else "wewnetrzna"
        for minute in range(start_minute, end_minute):
            values.append({
                "termin_id": record_id,
                "data": booking_date,
                "minute": minute,
                "sala_id": room_id,
                "kanal": channel,
                "covers": covers,
                "override": bool(pacing_row["override"]),
                "created_at": pacing_row["created_at"],
            })
    return values


def _insert_chunks(bind, table, values: list[dict[str, Any]], size: int = 2000) -> None:
    for offset in range(0, len(values), size):
        bind.execute(sa.insert(table), values[offset:offset + size])


def _add_r3_columns(bind) -> None:
    if bind.dialect.name == "sqlite":
        statements = (
            "ALTER TABLE godziny_otwarcia ADD COLUMN krok_slotu_min INTEGER NOT NULL "
            "DEFAULT 120 CONSTRAINT ck_godziny_otwarcia_krok_slotu_min "
            "CHECK (krok_slotu_min >= 1 AND krok_slotu_min <= 1440)",
            "ALTER TABLE godziny_otwarcia ADD COLUMN domyslny_turn_time_min INTEGER NOT NULL "
            "DEFAULT 120 CONSTRAINT ck_godziny_otwarcia_domyslny_turn_time_min "
            "CHECK (domyslny_turn_time_min >= 1 AND domyslny_turn_time_min <= 1439)",
            "ALTER TABLE godziny_otwarcia ADD COLUMN max_jednoczesnych_rez INTEGER "
            "CONSTRAINT ck_godziny_otwarcia_max_jednoczesnych_rez "
            "CHECK (max_jednoczesnych_rez IS NULL OR max_jednoczesnych_rez >= 0)",
            "ALTER TABLE godziny_otwarcia ADD COLUMN max_jednoczesnych_osob INTEGER "
            "CONSTRAINT ck_godziny_otwarcia_max_jednoczesnych_osob "
            "CHECK (max_jednoczesnych_osob IS NULL OR max_jednoczesnych_osob >= 0)",
            "ALTER TABLE godziny_otwarcia ADD COLUMN duza_grupa_od INTEGER "
            "CONSTRAINT ck_godziny_otwarcia_duza_grupa_od "
            "CHECK (duza_grupa_od IS NULL OR duza_grupa_od > 0)",
            "ALTER TABLE godziny_otwarcia ADD COLUMN duza_grupa_tryb VARCHAR(24) "
            "CONSTRAINT ck_godziny_otwarcia_duza_grupa_tryb CHECK "
            "(duza_grupa_tryb IS NULL OR duza_grupa_tryb IN "
            "('online', 'do_zatwierdzenia', 'telefon')) "
            "CONSTRAINT ck_godziny_otwarcia_duza_grupa_spojnosc CHECK "
            "((duza_grupa_od IS NULL AND duza_grupa_tryb IS NULL) OR "
            "(duza_grupa_od IS NOT NULL AND duza_grupa_tryb IS NOT NULL))",
            "ALTER TABLE wyjatki_kalendarza ADD COLUMN krok_slotu_min INTEGER "
            "CONSTRAINT ck_wyjatki_kalendarza_krok_slotu_min CHECK "
            "(krok_slotu_min IS NULL OR (krok_slotu_min >= 1 AND krok_slotu_min <= 1440))",
            "ALTER TABLE wyjatki_kalendarza ADD COLUMN domyslny_turn_time_min INTEGER "
            "CONSTRAINT ck_wyjatki_kalendarza_domyslny_turn_time_min CHECK "
            "(domyslny_turn_time_min IS NULL OR "
            "(domyslny_turn_time_min >= 1 AND domyslny_turn_time_min <= 1439))",
            "ALTER TABLE sale_rezerwacyjne ADD COLUMN online_aktywna BOOLEAN NOT NULL "
            "DEFAULT TRUE",
            "ALTER TABLE sale_rezerwacyjne ADD COLUMN wewnetrzna_aktywna BOOLEAN NOT NULL "
            "DEFAULT TRUE",
            "ALTER TABLE sale_rezerwacyjne ADD COLUMN limit_jednoczesnych_rez INTEGER "
            "CONSTRAINT ck_sale_rezerwacyjne_limit_jednoczesnych_rez CHECK "
            "(limit_jednoczesnych_rez IS NULL OR limit_jednoczesnych_rez >= 0)",
            "ALTER TABLE sale_rezerwacyjne ADD COLUMN limit_jednoczesnych_osob INTEGER "
            "CONSTRAINT ck_sale_rezerwacyjne_limit_jednoczesnych_osob CHECK "
            "(limit_jednoczesnych_osob IS NULL OR limit_jednoczesnych_osob >= 0)",
            "ALTER TABLE sale_rezerwacyjne ADD COLUMN domyslny_bufor_min INTEGER "
            "CONSTRAINT ck_sale_rezerwacyjne_domyslny_bufor_min CHECK "
            "(domyslny_bufor_min IS NULL OR domyslny_bufor_min >= 0)",
        )
        for statement in statements:
            op.execute(statement)
    else:
        op.add_column("godziny_otwarcia", sa.Column(
            "krok_slotu_min", sa.Integer(), nullable=False, server_default="120",
        ))
        op.add_column("godziny_otwarcia", sa.Column(
            "domyslny_turn_time_min", sa.Integer(), nullable=False, server_default="120",
        ))
        for name in (
            "max_jednoczesnych_rez", "max_jednoczesnych_osob", "duza_grupa_od",
        ):
            op.add_column("godziny_otwarcia", sa.Column(name, sa.Integer(), nullable=True))
        op.add_column("godziny_otwarcia", sa.Column(
            "duza_grupa_tryb", sa.String(length=24), nullable=True,
        ))
        service_checks = {
            "ck_godziny_otwarcia_krok_slotu_min":
                "krok_slotu_min >= 1 AND krok_slotu_min <= 1440",
            "ck_godziny_otwarcia_domyslny_turn_time_min":
                "domyslny_turn_time_min >= 1 AND domyslny_turn_time_min <= 1439",
            "ck_godziny_otwarcia_max_jednoczesnych_rez":
                "max_jednoczesnych_rez IS NULL OR max_jednoczesnych_rez >= 0",
            "ck_godziny_otwarcia_max_jednoczesnych_osob":
                "max_jednoczesnych_osob IS NULL OR max_jednoczesnych_osob >= 0",
            "ck_godziny_otwarcia_duza_grupa_od":
                "duza_grupa_od IS NULL OR duza_grupa_od > 0",
            "ck_godziny_otwarcia_duza_grupa_tryb":
                "duza_grupa_tryb IS NULL OR duza_grupa_tryb IN "
                "('online', 'do_zatwierdzenia', 'telefon')",
            "ck_godziny_otwarcia_duza_grupa_spojnosc":
                "(duza_grupa_od IS NULL AND duza_grupa_tryb IS NULL) OR "
                "(duza_grupa_od IS NOT NULL AND duza_grupa_tryb IS NOT NULL)",
        }
        for name, condition in service_checks.items():
            op.create_check_constraint(name, "godziny_otwarcia", condition)

        for name in ("krok_slotu_min", "domyslny_turn_time_min"):
            op.add_column("wyjatki_kalendarza", sa.Column(name, sa.Integer(), nullable=True))
        op.create_check_constraint(
            "ck_wyjatki_kalendarza_krok_slotu_min", "wyjatki_kalendarza",
            "krok_slotu_min IS NULL OR "
            "(krok_slotu_min >= 1 AND krok_slotu_min <= 1440)",
        )
        op.create_check_constraint(
            "ck_wyjatki_kalendarza_domyslny_turn_time_min", "wyjatki_kalendarza",
            "domyslny_turn_time_min IS NULL OR "
            "(domyslny_turn_time_min >= 1 AND domyslny_turn_time_min <= 1439)",
        )

        op.add_column("sale_rezerwacyjne", sa.Column(
            "online_aktywna", sa.Boolean(), nullable=False, server_default=sa.true(),
        ))
        op.add_column("sale_rezerwacyjne", sa.Column(
            "wewnetrzna_aktywna", sa.Boolean(), nullable=False, server_default=sa.true(),
        ))
        for name in (
            "limit_jednoczesnych_rez", "limit_jednoczesnych_osob", "domyslny_bufor_min",
        ):
            op.add_column("sale_rezerwacyjne", sa.Column(name, sa.Integer(), nullable=True))
            op.create_check_constraint(
                f"ck_sale_rezerwacyjne_{name}", "sale_rezerwacyjne",
                f"{name} IS NULL OR {name} >= 0",
            )

    op.execute(sa.text(
        "UPDATE godziny_otwarcia SET "
        "krok_slotu_min = dlugosc_slotu_min, "
        "domyslny_turn_time_min = dlugosc_slotu_min"
    ))
    op.execute(sa.text(
        "UPDATE wyjatki_kalendarza SET "
        "krok_slotu_min = dlugosc_slotu_min, "
        "domyslny_turn_time_min = dlugosc_slotu_min "
        "WHERE dlugosc_slotu_min IS NOT NULL"
    ))


def _backfill_legacy_online_services(bind) -> None:
    """Nie zamykaj po migracji lokalu, który wcześniej sprzedawał bez grafiku.

    Historyczny publiczny endpoint dopuszczał dowolną godzinę, gdy online było
    włączone, ale tabela serwisów pozostawała pusta. R3 jest już rygorystyczny,
    dlatego taki lokal dostaje jawną, edytowalną konfigurację zgodności. Nowe
    lokale (online wyłączone podczas migracji) nadal muszą skonfigurować serwisy.
    """
    config = sa.table(
        "lokal_config",
        sa.column("rezerwacje_online", sa.Boolean()),
    )
    services = sa.table(
        "godziny_otwarcia",
        sa.column("dzien_tygodnia", sa.Integer()),
        sa.column("godz_od", sa.Time()),
        sa.column("godz_do", sa.Time()),
        sa.column("ostatni_zasiadek", sa.Time()),
        sa.column("dlugosc_slotu_min", sa.Integer()),
        sa.column("krok_slotu_min", sa.Integer()),
        sa.column("domyslny_turn_time_min", sa.Integer()),
        sa.column("max_jednoczesnych_rez", sa.Integer()),
        sa.column("max_jednoczesnych_osob", sa.Integer()),
        sa.column("duza_grupa_od", sa.Integer()),
        sa.column("duza_grupa_tryb", sa.String(length=24)),
        sa.column("aktywny", sa.Boolean()),
        sa.column("nazwa", sa.String(length=32)),
    )
    online_enabled = bool(bind.execute(
        sa.select(sa.func.count()).select_from(config).where(
            config.c.rezerwacje_online.is_(True),
        )
    ).scalar_one())
    has_services = bool(bind.execute(
        sa.select(sa.func.count()).select_from(services)
    ).scalar_one())
    if not online_enabled or has_services:
        return
    bind.execute(sa.insert(services), [
        {
            "dzien_tygodnia": weekday,
            "godz_od": time(0, 0),
            "godz_do": time(23, 59),
            "ostatni_zasiadek": time(21, 59),
            "dlugosc_slotu_min": 120,
            "krok_slotu_min": 120,
            "domyslny_turn_time_min": 120,
            "aktywny": True,
            "nazwa": _LEGACY_ONLINE_SERVICE_NAME,
        }
        for weekday in range(7)
    ])


def _remove_untouched_legacy_online_services(bind) -> None:
    """Przywróć pustą konfigurację tylko gdy backfill nie był edytowany."""
    services = sa.table(
        "godziny_otwarcia",
        sa.column("dzien_tygodnia", sa.Integer()),
        sa.column("godz_od", sa.Time()),
        sa.column("godz_do", sa.Time()),
        sa.column("ostatni_zasiadek", sa.Time()),
        sa.column("dlugosc_slotu_min", sa.Integer()),
        sa.column("krok_slotu_min", sa.Integer()),
        sa.column("domyslny_turn_time_min", sa.Integer()),
        sa.column("max_jednoczesnych_rez", sa.Integer()),
        sa.column("max_jednoczesnych_osob", sa.Integer()),
        sa.column("duza_grupa_od", sa.Integer()),
        sa.column("duza_grupa_tryb", sa.String(length=24)),
        sa.column("turn_time_progi", sa.JSON()),
        sa.column("pacing_max_rez", sa.Integer()),
        sa.column("pacing_max_osob", sa.Integer()),
        sa.column("pacing_okno_min", sa.Integer()),
        sa.column("aktywny", sa.Boolean()),
        sa.column("nazwa", sa.String(length=32)),
    )
    untouched = sa.and_(
        services.c.nazwa == _LEGACY_ONLINE_SERVICE_NAME,
        services.c.godz_od == time(0, 0),
        services.c.godz_do == time(23, 59),
        services.c.ostatni_zasiadek == time(21, 59),
        services.c.dlugosc_slotu_min == 120,
        services.c.krok_slotu_min == 120,
        services.c.domyslny_turn_time_min == 120,
        services.c.max_jednoczesnych_rez.is_(None),
        services.c.max_jednoczesnych_osob.is_(None),
        services.c.duza_grupa_od.is_(None),
        services.c.duza_grupa_tryb.is_(None),
        services.c.turn_time_progi.is_(None),
        services.c.pacing_max_rez.is_(None),
        services.c.pacing_max_osob.is_(None),
        services.c.pacing_okno_min.is_(None),
        services.c.aktywny.is_(True),
    )
    weekdays = bind.execute(
        sa.select(services.c.dzien_tygodnia).where(untouched)
    ).scalars().all()
    if len(weekdays) == 7 and set(weekdays) == set(range(7)):
        bind.execute(sa.delete(services).where(untouched))


def _create_r3_tables(bind, occupancy_values: list[dict[str, Any]]) -> None:
    rule_columns = (
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "serwis_id", sa.Integer(),
            sa.ForeignKey("godziny_otwarcia.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column(
            "sala_id", sa.Integer(),
            sa.ForeignKey("sale_rezerwacyjne.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column("kanal", sa.String(length=16), nullable=False, server_default="oba"),
        sa.Column("pacing_okno_min", sa.Integer(), nullable=True),
        sa.Column("pacing_max_rez", sa.Integer(), nullable=True),
        sa.Column("pacing_max_osob", sa.Integer(), nullable=True),
        sa.Column("max_jednoczesnych_rez", sa.Integer(), nullable=True),
        sa.Column("max_jednoczesnych_osob", sa.Integer(), nullable=True),
        sa.Column("bufor_min", sa.Integer(), nullable=True),
        sa.Column("okno_wyprzedzenia_dni", sa.Integer(), nullable=True),
        sa.Column("cutoff_min", sa.Integer(), nullable=True),
        sa.Column("min_grupa", sa.Integer(), nullable=True),
        sa.Column("max_grupa", sa.Integer(), nullable=True),
        sa.Column("duza_grupa_od", sa.Integer(), nullable=True),
        sa.Column("duza_grupa_tryb", sa.String(length=24), nullable=True),
    )
    rule_checks = (
        ("ck_reguly_dostepnosci_kanal", "kanal IN ('oba', 'online', 'wewnetrzna')"),
        ("ck_reguly_dostepnosci_pacing_okno_min", "pacing_okno_min IS NULL OR pacing_okno_min > 0"),
        ("ck_reguly_dostepnosci_pacing_max_rez", "pacing_max_rez IS NULL OR pacing_max_rez >= 0"),
        ("ck_reguly_dostepnosci_pacing_max_osob", "pacing_max_osob IS NULL OR pacing_max_osob >= 0"),
        ("ck_reguly_dostepnosci_max_jednoczesnych_rez", "max_jednoczesnych_rez IS NULL OR max_jednoczesnych_rez >= 0"),
        ("ck_reguly_dostepnosci_max_jednoczesnych_osob", "max_jednoczesnych_osob IS NULL OR max_jednoczesnych_osob >= 0"),
        ("ck_reguly_dostepnosci_bufor_min", "bufor_min IS NULL OR bufor_min >= 0"),
        ("ck_reguly_dostepnosci_okno_wyprzedzenia_dni", "okno_wyprzedzenia_dni IS NULL OR okno_wyprzedzenia_dni >= 0"),
        ("ck_reguly_dostepnosci_cutoff_min", "cutoff_min IS NULL OR cutoff_min >= 0"),
        ("ck_reguly_dostepnosci_min_grupa", "min_grupa IS NULL OR min_grupa > 0"),
        ("ck_reguly_dostepnosci_max_grupa", "max_grupa IS NULL OR max_grupa >= 0"),
        ("ck_reguly_dostepnosci_zakres_grupy", "min_grupa IS NULL OR max_grupa IS NULL OR max_grupa = 0 OR max_grupa >= min_grupa"),
        ("ck_reguly_dostepnosci_duza_grupa_od", "duza_grupa_od IS NULL OR duza_grupa_od > 0"),
        ("ck_reguly_dostepnosci_duza_grupa_tryb", "duza_grupa_tryb IS NULL OR duza_grupa_tryb IN ('online', 'do_zatwierdzenia', 'telefon')"),
        ("ck_reguly_dostepnosci_duza_grupa_spojnosc", "(duza_grupa_od IS NULL AND duza_grupa_tryb IS NULL) OR (duza_grupa_od IS NOT NULL AND duza_grupa_tryb IS NOT NULL)"),
        ("ck_reguly_dostepnosci_nie_puste", "pacing_okno_min IS NOT NULL OR pacing_max_rez IS NOT NULL OR pacing_max_osob IS NOT NULL OR max_jednoczesnych_rez IS NOT NULL OR max_jednoczesnych_osob IS NOT NULL OR bufor_min IS NOT NULL OR okno_wyprzedzenia_dni IS NOT NULL OR cutoff_min IS NOT NULL OR min_grupa IS NOT NULL OR max_grupa IS NOT NULL OR duza_grupa_od IS NOT NULL OR duza_grupa_tryb IS NOT NULL"),
    )
    op.create_table(
        "reguly_dostepnosci_rezerwacji",
        *rule_columns,
        *(sa.CheckConstraint(condition, name=name) for name, condition in rule_checks),
    )
    predicates = {
        "uq_reguly_dostepnosci_global_kanal": (
            ["kanal"], "serwis_id IS NULL AND sala_id IS NULL",
        ),
        "uq_reguly_dostepnosci_serwis_kanal": (
            ["serwis_id", "kanal"], "serwis_id IS NOT NULL AND sala_id IS NULL",
        ),
        "uq_reguly_dostepnosci_sala_kanal": (
            ["sala_id", "kanal"], "serwis_id IS NULL AND sala_id IS NOT NULL",
        ),
        "uq_reguly_dostepnosci_serwis_sala_kanal": (
            ["serwis_id", "sala_id", "kanal"],
            "serwis_id IS NOT NULL AND sala_id IS NOT NULL",
        ),
    }
    for name, (columns, predicate) in predicates.items():
        op.create_index(
            name, "reguly_dostepnosci_rezerwacji", columns, unique=True,
            sqlite_where=sa.text(predicate), postgresql_where=sa.text(predicate),
        )

    op.create_table(
        "rezerwacje_oblozenie_ledger",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "termin_id", sa.Integer(),
            sa.ForeignKey("terminy.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("minute", sa.Integer(), nullable=False),
        sa.Column(
            "sala_id", sa.Integer(),
            sa.ForeignKey("sale_rezerwacyjne.id", ondelete="RESTRICT"), nullable=True,
        ),
        sa.Column("kanal", sa.String(length=16), nullable=False),
        sa.Column("covers", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("override", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "termin_id", "minute", name="uq_rezerwacje_oblozenie_termin_minute",
        ),
        sa.CheckConstraint(
            "minute >= 0 AND minute < 1440", name="ck_rezerwacje_oblozenie_minute",
        ),
        sa.CheckConstraint("covers >= 0", name="ck_rezerwacje_oblozenie_covers"),
        sa.CheckConstraint(
            "kanal IN ('online', 'wewnetrzna')", name="ck_rezerwacje_oblozenie_kanal",
        ),
    )
    op.create_index(
        "ix_rezerwacje_oblozenie_data_minute_sala_kanal",
        "rezerwacje_oblozenie_ledger", ["data", "minute", "sala_id", "kanal"],
    )
    op.create_index(
        "ix_rezerwacje_oblozenie_termin_id",
        "rezerwacje_oblozenie_ledger", ["termin_id"],
    )

    op.create_table(
        "reservation_override_context",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "audit_id", sa.Integer(),
            sa.ForeignKey("reservation_audit.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("reason_code", sa.String(length=32), nullable=False),
        # Fizyczny VARCHAR; ORM szyfruje i odszyfrowuje zawartość transparentnie.
        sa.Column("note", sa.String(length=1024), nullable=True),
        sa.UniqueConstraint(
            "audit_id", name="uq_reservation_override_context_audit_id",
        ),
        sa.CheckConstraint(
            "reason_code IN (" + ", ".join(f"'{code}'" for code in _OVERRIDE_REASON_CODES) + ")",
            name="ck_reservation_override_context_reason_code",
        ),
    )
    op.create_index(
        "ix_reservation_override_context_reason_code",
        "reservation_override_context", ["reason_code"],
    )

    occupancy = sa.table(
        "rezerwacje_oblozenie_ledger",
        sa.column("termin_id", sa.Integer()),
        sa.column("data", sa.Date()),
        sa.column("minute", sa.Integer()),
        sa.column("sala_id", sa.Integer()),
        sa.column("kanal", sa.String()),
        sa.column("covers", sa.Integer()),
        sa.column("override", sa.Boolean()),
        sa.column("created_at", sa.DateTime()),
    )
    _insert_chunks(bind, occupancy, occupancy_values)


def upgrade() -> None:
    bind = op.get_bind()
    occupancy_values = _prepare_occupancy_backfill(bind)
    _add_r3_columns(bind)
    _backfill_legacy_online_services(bind)
    _create_r3_tables(bind, occupancy_values)


def _assert_safe_downgrade(bind) -> None:
    divergent_services = bind.execute(sa.text(
        "SELECT count(*) FROM godziny_otwarcia "
        "WHERE krok_slotu_min <> domyslny_turn_time_min"
    )).scalar_one()
    divergent_exceptions = bind.execute(sa.text(
        "SELECT count(*) FROM wyjatki_kalendarza "
        "WHERE (krok_slotu_min IS NULL AND domyslny_turn_time_min IS NOT NULL) "
        "OR (krok_slotu_min IS NOT NULL AND domyslny_turn_time_min IS NULL) "
        "OR krok_slotu_min <> domyslny_turn_time_min"
    )).scalar_one()
    configured_rules = bind.execute(sa.text(
        "SELECT count(*) FROM reguly_dostepnosci_rezerwacji"
    )).scalar_one()
    override_contexts = bind.execute(sa.text(
        "SELECT count(*) FROM reservation_override_context"
    )).scalar_one()
    services = sa.table(
        "godziny_otwarcia",
        sa.column("max_jednoczesnych_rez", sa.Integer()),
        sa.column("max_jednoczesnych_osob", sa.Integer()),
        sa.column("duza_grupa_od", sa.Integer()),
        sa.column("duza_grupa_tryb", sa.String(length=24)),
    )
    configured_service_extensions = bind.execute(
        sa.select(sa.func.count()).select_from(services).where(sa.or_(
            services.c.max_jednoczesnych_rez.is_not(None),
            services.c.max_jednoczesnych_osob.is_not(None),
            services.c.duza_grupa_od.is_not(None),
            services.c.duza_grupa_tryb.is_not(None),
        ))
    ).scalar_one()
    rooms = sa.table(
        "sale_rezerwacyjne",
        sa.column("online_aktywna", sa.Boolean()),
        sa.column("wewnetrzna_aktywna", sa.Boolean()),
        sa.column("limit_jednoczesnych_rez", sa.Integer()),
        sa.column("limit_jednoczesnych_osob", sa.Integer()),
        sa.column("domyslny_bufor_min", sa.Integer()),
    )
    configured_room_extensions = bind.execute(
        sa.select(sa.func.count()).select_from(rooms).where(sa.or_(
            rooms.c.online_aktywna.is_(False),
            rooms.c.wewnetrzna_aktywna.is_(False),
            rooms.c.limit_jednoczesnych_rez.is_not(None),
            rooms.c.limit_jednoczesnych_osob.is_not(None),
            rooms.c.domyslny_bufor_min.is_not(None),
        ))
    ).scalar_one()
    if divergent_services or divergent_exceptions:
        raise RuntimeError("R3_DOWNGRADE_SPLIT_DURATION_LOSS")
    if (
        configured_rules
        or override_contexts
        or configured_service_extensions
        or configured_room_extensions
    ):
        raise RuntimeError("R3_DOWNGRADE_CONFIGURATION_LOSS")


def downgrade() -> None:
    bind = op.get_bind()
    _assert_safe_downgrade(bind)
    _remove_untouched_legacy_online_services(bind)
    op.execute(sa.text(
        "UPDATE godziny_otwarcia SET dlugosc_slotu_min = domyslny_turn_time_min"
    ))
    op.execute(sa.text(
        "UPDATE wyjatki_kalendarza SET dlugosc_slotu_min = domyslny_turn_time_min "
        "WHERE domyslny_turn_time_min IS NOT NULL"
    ))

    op.drop_index(
        "ix_reservation_override_context_reason_code",
        table_name="reservation_override_context",
    )
    op.drop_table("reservation_override_context")
    op.drop_index(
        "ix_rezerwacje_oblozenie_termin_id", table_name="rezerwacje_oblozenie_ledger",
    )
    op.drop_index(
        "ix_rezerwacje_oblozenie_data_minute_sala_kanal",
        table_name="rezerwacje_oblozenie_ledger",
    )
    op.drop_table("rezerwacje_oblozenie_ledger")
    for name in (
        "uq_reguly_dostepnosci_serwis_sala_kanal",
        "uq_reguly_dostepnosci_sala_kanal",
        "uq_reguly_dostepnosci_serwis_kanal",
        "uq_reguly_dostepnosci_global_kanal",
    ):
        op.drop_index(name, table_name="reguly_dostepnosci_rezerwacji")
    op.drop_table("reguly_dostepnosci_rezerwacji")

    if bind.dialect.name == "sqlite":
        for table_name, columns in (
            ("sale_rezerwacyjne", (
                "domyslny_bufor_min", "limit_jednoczesnych_osob",
                "limit_jednoczesnych_rez", "wewnetrzna_aktywna", "online_aktywna",
            )),
            ("wyjatki_kalendarza", (
                "domyslny_turn_time_min", "krok_slotu_min",
            )),
            ("godziny_otwarcia", (
                "duza_grupa_tryb", "duza_grupa_od", "max_jednoczesnych_osob",
                "max_jednoczesnych_rez", "domyslny_turn_time_min", "krok_slotu_min",
            )),
        ):
            for column in columns:
                op.execute(f"ALTER TABLE {table_name} DROP COLUMN {column}")
    else:
        for name in (
            "ck_sale_rezerwacyjne_domyslny_bufor_min",
            "ck_sale_rezerwacyjne_limit_jednoczesnych_osob",
            "ck_sale_rezerwacyjne_limit_jednoczesnych_rez",
        ):
            op.drop_constraint(name, "sale_rezerwacyjne", type_="check")
        for column in (
            "domyslny_bufor_min", "limit_jednoczesnych_osob",
            "limit_jednoczesnych_rez", "wewnetrzna_aktywna", "online_aktywna",
        ):
            op.drop_column("sale_rezerwacyjne", column)

        for name in (
            "ck_wyjatki_kalendarza_domyslny_turn_time_min",
            "ck_wyjatki_kalendarza_krok_slotu_min",
        ):
            op.drop_constraint(name, "wyjatki_kalendarza", type_="check")
        for column in ("domyslny_turn_time_min", "krok_slotu_min"):
            op.drop_column("wyjatki_kalendarza", column)

        for name in (
            "ck_godziny_otwarcia_duza_grupa_spojnosc",
            "ck_godziny_otwarcia_duza_grupa_tryb",
            "ck_godziny_otwarcia_duza_grupa_od",
            "ck_godziny_otwarcia_max_jednoczesnych_osob",
            "ck_godziny_otwarcia_max_jednoczesnych_rez",
            "ck_godziny_otwarcia_domyslny_turn_time_min",
            "ck_godziny_otwarcia_krok_slotu_min",
        ):
            op.drop_constraint(name, "godziny_otwarcia", type_="check")
        for column in (
            "duza_grupa_tryb", "duza_grupa_od", "max_jednoczesnych_osob",
            "max_jednoczesnych_rez", "domyslny_turn_time_min", "krok_slotu_min",
        ):
            op.drop_column("godziny_otwarcia", column)
