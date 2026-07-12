"""Unicode-safe klucz unikalności nazw sal rezerwacyjnych.

Revision ID: 0054_room_name_key
Revises: 0053_sale_i_wersje_planu
"""
from __future__ import annotations

import unicodedata
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0054_room_name_key"
down_revision: Union[str, None] = "0053_sale_i_wersje_planu"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _room_name_key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def upgrade() -> None:
    bind = op.get_bind()
    rooms = sa.table(
        "sale_rezerwacyjne",
        sa.column("id", sa.Integer()),
        sa.column("nazwa", sa.String()),
        sa.column("nazwa_klucz", sa.String()),
    )
    rows = bind.execute(
        sa.select(rooms.c.id, rooms.c.nazwa).order_by(rooms.c.id),
    ).mappings().all()

    prepared: list[tuple[int, str]] = []
    seen: dict[str, int] = {}
    for row in rows:
        key = _room_name_key(row["nazwa"] or "")
        if not key:
            raise RuntimeError(f"R2_ROOM_NAME_INVALID id={row['id']}")
        previous = seen.get(key)
        if previous is not None:
            raise RuntimeError(
                "R2_ROOM_NAME_CANONICAL_CONFLICT "
                f"ids={previous},{row['id']}"
            )
        seen[key] = int(row["id"])
        prepared.append((int(row["id"]), key))

    # SQLite wymaga stałej wartości domyślnej przy natywnym ADD COLUMN NOT NULL.
    # Zostawienie jej w SQLite nie wpływa na aplikację, która zawsze zapisuje klucz;
    # UNIQUE blokuje również wyścig równoległych zapisów.
    op.add_column(
        "sale_rezerwacyjne",
        sa.Column(
            "nazwa_klucz",
            sa.String(length=128),
            nullable=False,
            server_default=sa.text("''"),
        ),
    )
    for room_id, key in prepared:
        bind.execute(
            rooms.update().where(rooms.c.id == room_id).values(nazwa_klucz=key),
        )
    op.create_index(
        "uq_sale_rezerwacyjne_nazwa_klucz",
        "sale_rezerwacyjne",
        ["nazwa_klucz"],
        unique=True,
    )
    if bind.dialect.name != "sqlite":
        op.alter_column(
            "sale_rezerwacyjne",
            "nazwa_klucz",
            server_default=None,
        )


def downgrade() -> None:
    op.drop_index(
        "uq_sale_rezerwacyjne_nazwa_klucz",
        table_name="sale_rezerwacyjne",
    )
    if op.get_bind().dialect.name == "sqlite":
        op.execute("ALTER TABLE sale_rezerwacyjne DROP COLUMN nazwa_klucz")
    else:
        op.drop_column("sale_rezerwacyjne", "nazwa_klucz")
