"""Sale rezerwacyjne i publikowalna wersja bazowa planu.

Revision ID: 0053_sale_i_wersje_planu
Revises: 0052_reservation_audit
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0053_sale_i_wersje_planu"
down_revision: Union[str, None] = "0052_reservation_audit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MAIN_ROOM = "Sala główna"


def _clean_room_name(value: Any, *, code: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RuntimeError(code)
    cleaned = " ".join(value.split())
    if len(cleaned) > 32:
        raise RuntimeError(code)
    return cleaned or None


def _configured_room_values(value: Any) -> list[Any]:
    if value is None:
        return []
    # Tolerujemy historyczny pojedynczy string, choć bieżący kontrakt to JSON listy.
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return list(value)
    raise RuntimeError("R2_BACKFILL_INVALID_LOKAL_SALE")


def _coordinate(value: Any, *, table_id: int, axis: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise RuntimeError(f"R2_BACKFILL_INVALID_{axis} table_id={table_id}")
    try:
        integer = int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            f"R2_BACKFILL_INVALID_{axis} table_id={table_id}"
        ) from exc
    if integer != value or not 0 <= integer <= 100:
        raise RuntimeError(f"R2_BACKFILL_INVALID_{axis} table_id={table_id}")
    return integer


def _grid_coordinates(index: int, count: int) -> tuple[int, int]:
    """Stabilna siatka 1..99%, niezależna od rozmiaru sali."""
    columns = max(1, math.ceil(math.sqrt(count)))
    rows = max(1, math.ceil(count / columns))
    column = index % columns
    row = index // columns
    x = round((column + 1) * 100 / (columns + 1))
    y = round((row + 1) * 100 / (rows + 1))
    return x, y


def _insert_chunks(bind, table, rows: Iterable[dict], size: int = 2_000) -> None:
    chunk: list[dict] = []
    for row in rows:
        chunk.append(row)
        if len(chunk) >= size:
            bind.execute(table.insert(), chunk)
            chunk = []
    if chunk:
        bind.execute(table.insert(), chunk)


def _prepare_backfill(bind) -> dict[str, Any]:
    """Waliduje dane przed pierwszym DDL (SQLite nie ma transakcyjnego DDL)."""
    lokal_config = sa.table(
        "lokal_config",
        sa.column("id", sa.Integer()),
        sa.column("sale", sa.JSON()),
    )
    stoliki = sa.table(
        "stoliki",
        sa.column("id", sa.Integer()),
        sa.column("strefa", sa.String()),
        sa.column("kolejnosc", sa.Integer()),
        sa.column("plan_x", sa.Integer()),
        sa.column("plan_y", sa.Integer()),
        sa.column("aktywny", sa.Boolean()),
    )

    config_rows = bind.execute(
        sa.select(lokal_config.c.id, lokal_config.c.sale).order_by(lokal_config.c.id)
    ).mappings().all()
    table_rows = bind.execute(
        sa.select(stoliki).order_by(stoliki.c.kolejnosc, stoliki.c.id)
    ).mappings().all()

    room_names: dict[str, str] = {}
    main_key = _MAIN_ROOM.casefold()

    def register(value: Any, *, code: str) -> str | None:
        cleaned = _clean_room_name(value, code=code)
        if cleaned is None:
            return None
        key = cleaned.casefold()
        # Jedna stabilna pisownia nazwy domyślnej także przy danych legacy.
        if key == main_key:
            room_names[key] = _MAIN_ROOM
        else:
            room_names.setdefault(key, cleaned)
        return key

    empty_config_value = False
    for config in config_rows:
        for value in _configured_room_values(config["sale"]):
            key = register(value, code="R2_BACKFILL_INVALID_LOKAL_SALE_NAME")
            empty_config_value = empty_config_value or key is None

    prepared_tables: list[dict[str, Any]] = []
    for row in table_rows:
        table_id = int(row["id"])
        room_key = register(
            row["strefa"], code=f"R2_BACKFILL_INVALID_STREFA table_id={table_id}",
        )
        if room_key is None:
            room_key = main_key
            room_names[main_key] = _MAIN_ROOM
        prepared_tables.append({
            "id": table_id,
            "room_key": room_key,
            "plan_x": _coordinate(row["plan_x"], table_id=table_id, axis="PLAN_X"),
            "plan_y": _coordinate(row["plan_y"], table_id=table_id, axis="PLAN_Y"),
            "aktywny": bool(row["aktywny"]),
        })

    if empty_config_value or not room_names:
        room_names[main_key] = _MAIN_ROOM

    ordered_rooms = sorted(
        room_names.items(),
        key=lambda item: (item[0] != main_key, item[1].casefold(), item[1]),
    )
    tables_by_room: dict[str, list[dict[str, Any]]] = {
        key: [] for key, _name in ordered_rooms
    }
    for table in prepared_tables:
        tables_by_room[table["room_key"]].append(table)

    for room_key, tables in tables_by_room.items():
        count = len(tables)
        for index, table in enumerate(tables):
            x, y = table["plan_x"], table["plan_y"]
            if x is None or y is None:
                x, y = _grid_coordinates(index, count)
            table["plan_x"] = x
            table["plan_y"] = y

    return {
        "rooms": ordered_rooms,
        "tables": prepared_tables,
        "timestamp": datetime.now(timezone.utc).replace(tzinfo=None),
    }


def _apply_backfill(bind, prepared: dict[str, Any]) -> None:
    sale = sa.table(
        "sale_rezerwacyjne",
        sa.column("id", sa.Integer()),
        sa.column("nazwa", sa.String()),
        sa.column("aktywna", sa.Boolean()),
        sa.column("kolejnosc", sa.Integer()),
    )
    stoliki = sa.table(
        "stoliki",
        sa.column("id", sa.Integer()),
        sa.column("sala_id", sa.Integer()),
    )
    plany = sa.table(
        "plany_sali",
        sa.column("id", sa.Integer()),
        sa.column("sala_id", sa.Integer()),
        sa.column("nazwa", sa.String()),
    )
    wersje = sa.table(
        "wersje_planu_sali",
        sa.column("id", sa.Integer()),
        sa.column("plan_id", sa.Integer()),
        sa.column("numer", sa.Integer()),
        sa.column("status", sa.String()),
        sa.column("rewizja", sa.Integer()),
        sa.column("autor_id", sa.Integer()),
        sa.column("opublikowal_id", sa.Integer()),
        sa.column("utworzono_at", sa.DateTime()),
        sa.column("zaktualizowano_at", sa.DateTime()),
        sa.column("opublikowano_at", sa.DateTime()),
    )
    pozycje = sa.table(
        "pozycje_stolikow_planu",
        sa.column("wersja_id", sa.Integer()),
        sa.column("stolik_id", sa.Integer()),
        sa.column("plan_x", sa.Integer()),
        sa.column("plan_y", sa.Integer()),
        sa.column("szerokosc", sa.Integer()),
        sa.column("wysokosc", sa.Integer()),
        sa.column("obrot", sa.Integer()),
        sa.column("aktywny_w_planie", sa.Boolean()),
    )

    room_rows = [
        {"nazwa": name, "aktywna": True, "kolejnosc": order}
        for order, (_key, name) in enumerate(prepared["rooms"])
    ]
    _insert_chunks(bind, sale, room_rows)
    room_ids_by_name = {
        row.nazwa: int(row.id)
        for row in bind.execute(sa.select(sale.c.id, sale.c.nazwa))
    }
    room_ids = {
        key: room_ids_by_name[name] for key, name in prepared["rooms"]
    }

    for table in prepared["tables"]:
        bind.execute(
            stoliki.update().where(stoliki.c.id == table["id"]).values(
                sala_id=room_ids[table["room_key"]],
            )
        )

    _insert_chunks(bind, plany, (
        {"sala_id": room_ids[key], "nazwa": "Plan główny"}
        for key, _name in prepared["rooms"]
    ))
    plan_ids_by_room = {
        int(row.sala_id): int(row.id)
        for row in bind.execute(sa.select(plany.c.id, plany.c.sala_id))
    }

    timestamp = prepared["timestamp"]
    _insert_chunks(bind, wersje, (
        {
            "plan_id": plan_ids_by_room[room_ids[key]],
            "numer": 1,
            "status": "published",
            "rewizja": 0,
            "autor_id": None,
            "opublikowal_id": None,
            "utworzono_at": timestamp,
            "zaktualizowano_at": timestamp,
            "opublikowano_at": timestamp,
        }
        for key, _name in prepared["rooms"]
    ))
    version_ids_by_plan = {
        int(row.plan_id): int(row.id)
        for row in bind.execute(sa.select(wersje.c.id, wersje.c.plan_id))
    }

    _insert_chunks(bind, pozycje, (
        {
            "wersja_id": version_ids_by_plan[
                plan_ids_by_room[room_ids[table["room_key"]]]
            ],
            "stolik_id": table["id"],
            "plan_x": table["plan_x"],
            "plan_y": table["plan_y"],
            "szerokosc": 12,
            "wysokosc": 12,
            "obrot": 0,
            "aktywny_w_planie": table["aktywny"],
        }
        for table in prepared["tables"]
    ))


def upgrade() -> None:
    bind = op.get_bind()
    prepared = _prepare_backfill(bind)

    op.create_table(
        "sale_rezerwacyjne",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nazwa", sa.String(length=32), nullable=False),
        sa.Column("aktywna", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("kolejnosc", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("nazwa", name="uq_sale_rezerwacyjne_nazwa"),
        sa.CheckConstraint(
            "length(trim(nazwa)) > 0", name="ck_sale_rezerwacyjne_nazwa",
        ),
        sa.CheckConstraint(
            "kolejnosc >= 0", name="ck_sale_rezerwacyjne_kolejnosc",
        ),
    )
    op.create_index("ix_sale_rezerwacyjne_id", "sale_rezerwacyjne", ["id"])

    # Nie używamy batch_alter_table. Rebuild ``stoliki`` przy PRAGMA foreign_keys=ON
    # uruchamia akcje FK tabel potomnych (m.in. zerował historyczne terminy.stolik_id,
    # a przy claimach RESTRICT zostawiał częściowy schemat). SQLite i PostgreSQL
    # obsługują addytywne ALTER TABLE ADD COLUMN z nullable FK bez przebudowy tabeli.
    if bind.dialect.name == "sqlite":
        op.execute(
            "ALTER TABLE stoliki ADD COLUMN sala_id INTEGER "
            "REFERENCES sale_rezerwacyjne(id)"
        )
    else:
        op.add_column(
            "stoliki",
            sa.Column(
                "sala_id",
                sa.Integer(),
                sa.ForeignKey(
                    "sale_rezerwacyjne.id",
                    name="fk_stoliki_sala_id_sale_rezerwacyjne",
                ),
                nullable=True,
            ),
        )
    op.create_index("ix_stoliki_sala_id", "stoliki", ["sala_id"])

    op.create_table(
        "plany_sali",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "sala_id", sa.Integer(),
            sa.ForeignKey("sale_rezerwacyjne.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("nazwa", sa.String(length=64), nullable=False),
        # R2.1 nie ma jeszcze wskaźnika aktywnego planu, więc jeden kontener
        # planu na salę jest jedynym deterministycznym kontraktem odczytu.
        sa.UniqueConstraint("sala_id", name="uq_plany_sali_sala"),
        sa.CheckConstraint("length(trim(nazwa)) > 0", name="ck_plany_sali_nazwa"),
    )
    op.create_index("ix_plany_sali_id", "plany_sali", ["id"])
    op.create_index("ix_plany_sali_sala_id", "plany_sali", ["sala_id"])

    op.create_table(
        "wersje_planu_sali",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "plan_id", sa.Integer(),
            sa.ForeignKey("plany_sali.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("numer", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("rewizja", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "autor_id", sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "opublikowal_id", sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("utworzono_at", sa.DateTime(), nullable=False),
        sa.Column("zaktualizowano_at", sa.DateTime(), nullable=False),
        sa.Column("opublikowano_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint(
            "plan_id", "numer", name="uq_wersje_planu_sali_plan_numer",
        ),
        sa.CheckConstraint("numer >= 1", name="ck_wersje_planu_sali_numer"),
        sa.CheckConstraint("rewizja >= 0", name="ck_wersje_planu_sali_rewizja"),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'retired')",
            name="ck_wersje_planu_sali_status",
        ),
        sa.CheckConstraint(
            "(status = 'draft' AND opublikowano_at IS NULL AND opublikowal_id IS NULL) OR "
            "(status = 'published' AND opublikowano_at IS NOT NULL) OR "
            "status = 'retired'",
            name="ck_wersje_planu_sali_publikacja",
        ),
        sa.CheckConstraint(
            "zaktualizowano_at >= utworzono_at",
            name="ck_wersje_planu_sali_czas_aktualizacji",
        ),
        sa.CheckConstraint(
            "opublikowano_at IS NULL OR opublikowano_at >= utworzono_at",
            name="ck_wersje_planu_sali_czas_publikacji",
        ),
    )
    op.create_index("ix_wersje_planu_sali_id", "wersje_planu_sali", ["id"])
    op.create_index(
        "ix_wersje_planu_sali_plan_id", "wersje_planu_sali", ["plan_id"],
    )
    op.create_index(
        "ix_wersje_planu_sali_plan_status",
        "wersje_planu_sali", ["plan_id", "status"],
    )
    op.create_index(
        "uq_wersje_planu_sali_jeden_draft",
        "wersje_planu_sali", ["plan_id"], unique=True,
        sqlite_where=sa.text("status = 'draft'"),
        postgresql_where=sa.text("status = 'draft'"),
    )
    op.create_index(
        "uq_wersje_planu_sali_jeden_published",
        "wersje_planu_sali", ["plan_id"], unique=True,
        sqlite_where=sa.text("status = 'published'"),
        postgresql_where=sa.text("status = 'published'"),
    )

    op.create_table(
        "pozycje_stolikow_planu",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "wersja_id", sa.Integer(),
            sa.ForeignKey("wersje_planu_sali.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "stolik_id", sa.Integer(),
            sa.ForeignKey("stoliki.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("plan_x", sa.Integer(), nullable=False),
        sa.Column("plan_y", sa.Integer(), nullable=False),
        sa.Column("szerokosc", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("wysokosc", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("obrot", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "aktywny_w_planie", sa.Boolean(), nullable=False, server_default=sa.true(),
        ),
        sa.UniqueConstraint(
            "wersja_id", "stolik_id", name="uq_pozycje_stolikow_wersja_stolik",
        ),
        sa.CheckConstraint(
            "plan_x >= 0 AND plan_x <= 100", name="ck_pozycje_stolikow_plan_x",
        ),
        sa.CheckConstraint(
            "plan_y >= 0 AND plan_y <= 100", name="ck_pozycje_stolikow_plan_y",
        ),
        sa.CheckConstraint(
            "szerokosc >= 1 AND szerokosc <= 100",
            name="ck_pozycje_stolikow_szerokosc",
        ),
        sa.CheckConstraint(
            "wysokosc >= 1 AND wysokosc <= 100",
            name="ck_pozycje_stolikow_wysokosc",
        ),
        sa.CheckConstraint(
            "obrot >= 0 AND obrot < 360", name="ck_pozycje_stolikow_obrot",
        ),
    )
    op.create_index(
        "ix_pozycje_stolikow_planu_id", "pozycje_stolikow_planu", ["id"],
    )
    op.create_index(
        "ix_pozycje_stolikow_planu_wersja_id",
        "pozycje_stolikow_planu", ["wersja_id"],
    )
    op.create_index(
        "ix_pozycje_stolikow_planu_stolik_id",
        "pozycje_stolikow_planu", ["stolik_id"],
    )

    _apply_backfill(bind, prepared)


def downgrade() -> None:
    op.drop_index(
        "ix_pozycje_stolikow_planu_id", table_name="pozycje_stolikow_planu",
    )
    op.drop_index(
        "ix_pozycje_stolikow_planu_stolik_id", table_name="pozycje_stolikow_planu",
    )
    op.drop_index(
        "ix_pozycje_stolikow_planu_wersja_id", table_name="pozycje_stolikow_planu",
    )
    op.drop_table("pozycje_stolikow_planu")

    op.drop_index(
        "uq_wersje_planu_sali_jeden_published", table_name="wersje_planu_sali",
    )
    op.drop_index(
        "uq_wersje_planu_sali_jeden_draft", table_name="wersje_planu_sali",
    )
    op.drop_index(
        "ix_wersje_planu_sali_plan_status", table_name="wersje_planu_sali",
    )
    op.drop_index(
        "ix_wersje_planu_sali_plan_id", table_name="wersje_planu_sali",
    )
    op.drop_index("ix_wersje_planu_sali_id", table_name="wersje_planu_sali")
    op.drop_table("wersje_planu_sali")

    op.drop_index("ix_plany_sali_sala_id", table_name="plany_sali")
    op.drop_index("ix_plany_sali_id", table_name="plany_sali")
    op.drop_table("plany_sali")

    op.drop_index("ix_stoliki_sala_id", table_name="stoliki")
    # DROP COLUMN usuwa należący do kolumny FK bez przebudowy ``stoliki``.
    if op.get_bind().dialect.name == "sqlite":
        op.execute("ALTER TABLE stoliki DROP COLUMN sala_id")
    else:
        op.drop_column("stoliki", "sala_id")

    op.drop_index("ix_sale_rezerwacyjne_id", table_name="sale_rezerwacyjne")
    op.drop_table("sale_rezerwacyjne")
