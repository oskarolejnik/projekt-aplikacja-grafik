"""Wersjonowane wlasciwosci stolow, sasiedztwo i jawne kombinacje R2.2a.

Revision ID: 0057_r22_topologia_planu
Revises: 0056_impreza_sale_min2_neutralny
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0057_r22_topologia_planu"
down_revision: Union[str, None] = "0056_impreza_sale_min2_neutralny"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _positive_int(value: Any, *, code: str, allow_none: bool = False) -> int | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool):
        raise RuntimeError(code)
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(code) from exc
    if parsed != value or parsed < 1:
        raise RuntimeError(code)
    return parsed


def _connected_components(
    members: list[int], edge_keys: set[tuple[int, int]],
) -> list[list[int]]:
    """Zwraca deterministyczne skladowe grafu indukowanego przez ``members``."""
    member_set = set(members)
    adjacency = {table_id: set() for table_id in members}
    for a, b in edge_keys:
        if a in member_set and b in member_set:
            adjacency[a].add(b)
            adjacency[b].add(a)

    components: list[list[int]] = []
    remaining = set(members)
    while remaining:
        first = min(remaining)
        component = {first}
        pending = [first]
        while pending:
            current = pending.pop()
            for neighbour in sorted(adjacency[current]):
                if neighbour not in component:
                    component.add(neighbour)
                    pending.append(neighbour)
        remaining -= component
        components.append(sorted(component))
    return components


def _prepare_backfill(bind) -> dict[str, Any]:
    """Waliduje legacy topologie przed pierwszym DDL (wazne dla SQLite)."""
    stoliki = sa.table(
        "stoliki",
        sa.column("id", sa.Integer()),
        sa.column("sala_id", sa.Integer()),
        sa.column("nazwa", sa.String()),
        sa.column("kolejnosc", sa.Integer()),
        sa.column("pojemnosc", sa.Integer()),
        sa.column("pojemnosc_min", sa.Integer()),
        sa.column("ksztalt", sa.String()),
        sa.column("cechy", sa.JSON()),
        sa.column("priorytet", sa.Integer()),
        sa.column("sekcja", sa.String()),
    )
    pozycje = sa.table(
        "pozycje_stolikow_planu",
        sa.column("wersja_id", sa.Integer()),
        sa.column("stolik_id", sa.Integer()),
        sa.column("aktywny_w_planie", sa.Boolean()),
    )
    sasiedztwo = sa.table(
        "sasiedztwo_stolow",
        sa.column("id", sa.Integer()),
        sa.column("stolik_a", sa.Integer()),
        sa.column("stolik_b", sa.Integer()),
    )
    kombinacje = sa.table(
        "kombinacje_stolow",
        sa.column("id", sa.Integer()),
        sa.column("nazwa", sa.String()),
        sa.column("stoliki", sa.JSON()),
        sa.column("pojemnosc_min", sa.Integer()),
        sa.column("pojemnosc_max", sa.Integer()),
        sa.column("aktywna", sa.Boolean()),
        sa.column("priorytet", sa.Integer()),
    )

    table_rows = bind.execute(sa.select(stoliki).order_by(stoliki.c.id)).mappings().all()
    tables: dict[int, dict[str, Any]] = {}
    for row in table_rows:
        table_id = int(row["id"])
        room_id = row["sala_id"]
        name = str(row["nazwa"] or "").strip()
        order = row["kolejnosc"]
        capacity = _positive_int(
            row["pojemnosc"], code=f"R22_MIGRATION_INVALID_TABLE_CAPACITY table_id={table_id}",
        )
        minimum = _positive_int(
            row["pojemnosc_min"],
            code=f"R22_MIGRATION_INVALID_TABLE_MIN table_id={table_id}",
            allow_none=True,
        )
        if room_id is None or not name or order is None or int(order) < 0:
            raise RuntimeError(f"R22_MIGRATION_INVALID_TABLE table_id={table_id}")
        if minimum is not None and minimum > capacity:
            raise RuntimeError(f"R22_MIGRATION_INVALID_TABLE_RANGE table_id={table_id}")
        tables[table_id] = {
            "sala_id": int(room_id),
            "nazwa": name,
            "kolejnosc": int(order),
            "pojemnosc": capacity,
            "pojemnosc_min": minimum,
            "ksztalt": row["ksztalt"],
            "cechy": row["cechy"],
            "priorytet": row["priorytet"],
            "sekcja": row["sekcja"],
        }

    positions_by_version: dict[int, dict[int, bool]] = defaultdict(dict)
    for version_id, table_id, active in bind.execute(
        sa.select(
            pozycje.c.wersja_id,
            pozycje.c.stolik_id,
            pozycje.c.aktywny_w_planie,
        ).order_by(
            pozycje.c.wersja_id, pozycje.c.stolik_id,
        )
    ):
        if int(table_id) not in tables:
            raise RuntimeError(f"R22_MIGRATION_ORPHAN_POSITION table_id={table_id}")
        positions_by_version[int(version_id)][int(table_id)] = bool(active)

    prepared_edges: list[dict[str, int]] = []
    edge_keys: set[tuple[int, int]] = set()
    for row in bind.execute(sa.select(sasiedztwo).order_by(sasiedztwo.c.id)).mappings():
        try:
            raw_a = int(row["stolik_a"])
            raw_b = int(row["stolik_b"])
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"R22_MIGRATION_INVALID_EDGE edge_id={row['id']}") from exc
        if raw_a == raw_b or raw_a not in tables or raw_b not in tables:
            raise RuntimeError(f"R22_MIGRATION_INVALID_EDGE edge_id={row['id']}")
        if tables[raw_a]["sala_id"] != tables[raw_b]["sala_id"]:
            raise RuntimeError(f"R22_MIGRATION_CROSS_ROOM_EDGE edge_id={row['id']}")
        a, b = sorted((raw_a, raw_b))
        if (a, b) in edge_keys:
            raise RuntimeError(f"R22_MIGRATION_DUPLICATE_EDGE edge_id={row['id']}")
        edge_keys.add((a, b))
        prepared_edges.append({"stolik_a_id": a, "stolik_b_id": b})

    prepared_combinations: list[dict[str, Any]] = []
    combination_keys: set[tuple[int, str]] = set()
    for row in bind.execute(sa.select(kombinacje).order_by(kombinacje.c.id)).mappings():
        raw_members = row["stoliki"]
        if not isinstance(raw_members, (list, tuple)) or len(raw_members) < 2:
            raise RuntimeError(f"R22_MIGRATION_INVALID_COMBINATION combination_id={row['id']}")
        members: list[int] = []
        for raw in raw_members:
            if isinstance(raw, bool):
                raise RuntimeError(
                    f"R22_MIGRATION_INVALID_COMBINATION combination_id={row['id']}"
                )
            try:
                member = int(raw)
            except (TypeError, ValueError) as exc:
                raise RuntimeError(
                    f"R22_MIGRATION_INVALID_COMBINATION combination_id={row['id']}"
                ) from exc
            if member != raw or member not in tables:
                raise RuntimeError(
                    f"R22_MIGRATION_ORPHAN_COMBINATION combination_id={row['id']}"
                )
            members.append(member)
        members = sorted(members)
        if len(members) != len(set(members)):
            raise RuntimeError(
                f"R22_MIGRATION_DUPLICATE_COMBINATION_MEMBER combination_id={row['id']}"
            )
        room_ids = {tables[table_id]["sala_id"] for table_id in members}
        if len(room_ids) != 1:
            raise RuntimeError(
                f"R22_MIGRATION_CROSS_ROOM_COMBINATION combination_id={row['id']}"
            )
        room_id = next(iter(room_ids))
        key = ",".join(str(table_id) for table_id in members)
        if (room_id, key) in combination_keys:
            raise RuntimeError(
                f"R22_MIGRATION_DUPLICATE_COMBINATION combination_id={row['id']}"
            )
        combination_keys.add((room_id, key))

        # Legacy jawna kombinacja jest dowodem, ze caly zestaw da sie fizycznie
        # polaczyc, ale starszy model nie zawsze mial komplet krawedzi. Laczymy
        # skladowe deterministycznym lancuchem reprezentantow. Dodajemy dokladnie
        # ``liczba_skladowych - 1`` krawedzi, czyli minimalne domkniecie grafu.
        components = _connected_components(members, edge_keys)
        for left, right in zip(components, components[1:]):
            a, b = sorted((left[0], right[0]))
            edge_keys.add((a, b))
            prepared_edges.append({"stolik_a_id": a, "stolik_b_id": b})

        name = str(row["nazwa"] or "").strip()
        if not name or len(name) > 64:
            raise RuntimeError(
                f"R22_MIGRATION_INVALID_COMBINATION_NAME combination_id={row['id']}"
            )
        physical_capacity = sum(tables[table_id]["pojemnosc"] for table_id in members)
        minimum = _positive_int(
            row["pojemnosc_min"],
            code=f"R22_MIGRATION_INVALID_COMBINATION_MIN combination_id={row['id']}",
            allow_none=True,
        ) or 1
        raw_maximum = row["pojemnosc_max"]
        maximum = physical_capacity if raw_maximum in (None, 0) else _positive_int(
            raw_maximum,
            code=f"R22_MIGRATION_INVALID_COMBINATION_MAX combination_id={row['id']}",
        )
        if minimum > maximum or maximum > physical_capacity:
            raise RuntimeError(
                f"R22_MIGRATION_INVALID_COMBINATION_RANGE combination_id={row['id']}"
            )
        prepared_combinations.append({
            "room_id": room_id,
            "nazwa": name,
            "stoliki": members,
            "sklad_klucz": key,
            "pojemnosc_min": minimum,
            "pojemnosc_max": maximum,
            "priorytet": int(row["priorytet"] or 0),
            "kanal": "oba",
            "aktywna_w_planie": bool(row["aktywna"]),
        })

    return {
        "tables": tables,
        "positions_by_version": dict(positions_by_version),
        "edges": prepared_edges,
        "combinations": prepared_combinations,
    }


def _create_topology_tables() -> None:
    op.create_table(
        "krawedzie_sasiedztwa_planu",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("wersja_id", sa.Integer(), nullable=False),
        sa.Column("stolik_a_id", sa.Integer(), nullable=False),
        sa.Column("stolik_b_id", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "stolik_a_id < stolik_b_id",
            name="ck_krawedzie_sasiedztwa_planu_kolejnosc",
        ),
        sa.ForeignKeyConstraint(
            ["wersja_id"], ["wersje_planu_sali.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["wersja_id", "stolik_a_id"],
            ["pozycje_stolikow_planu.wersja_id", "pozycje_stolikow_planu.stolik_id"],
            name="fk_krawedzie_sasiedztwa_planu_stolik_a",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["wersja_id", "stolik_b_id"],
            ["pozycje_stolikow_planu.wersja_id", "pozycje_stolikow_planu.stolik_id"],
            name="fk_krawedzie_sasiedztwa_planu_stolik_b",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "wersja_id", "stolik_a_id", "stolik_b_id",
            name="uq_krawedzie_sasiedztwa_planu_para",
        ),
    )
    op.create_index(
        "ix_krawedzie_sasiedztwa_planu_id",
        "krawedzie_sasiedztwa_planu", ["id"], unique=False,
    )
    op.create_index(
        "ix_krawedzie_sasiedztwa_planu_wersja_id",
        "krawedzie_sasiedztwa_planu", ["wersja_id"], unique=False,
    )

    op.create_table(
        "kombinacje_stolow_planu",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("wersja_id", sa.Integer(), nullable=False),
        sa.Column("nazwa", sa.String(length=64), nullable=False),
        sa.Column("sklad_klucz", sa.String(length=512), nullable=False),
        sa.Column("pojemnosc_min", sa.Integer(), nullable=False),
        sa.Column("pojemnosc_max", sa.Integer(), nullable=False),
        sa.Column("priorytet", sa.Integer(), nullable=False),
        sa.Column("kanal", sa.String(length=16), nullable=False),
        sa.Column("aktywna_w_planie", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "length(trim(nazwa)) > 0", name="ck_kombinacje_stolow_planu_nazwa",
        ),
        sa.CheckConstraint(
            "length(sklad_klucz) > 0", name="ck_kombinacje_stolow_planu_sklad",
        ),
        sa.CheckConstraint(
            "pojemnosc_min >= 1 AND pojemnosc_max >= pojemnosc_min",
            name="ck_kombinacje_stolow_planu_pojemnosc",
        ),
        sa.CheckConstraint(
            "kanal IN ('online', 'wewnetrzna', 'oba')",
            name="ck_kombinacje_stolow_planu_kanal",
        ),
        sa.ForeignKeyConstraint(
            ["wersja_id"], ["wersje_planu_sali.id"], ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id", "wersja_id", name="uq_kombinacje_stolow_planu_id_wersja",
        ),
        sa.UniqueConstraint(
            "wersja_id", "sklad_klucz",
            name="uq_kombinacje_stolow_planu_wersja_sklad",
        ),
    )
    op.create_index(
        "ix_kombinacje_stolow_planu_id",
        "kombinacje_stolow_planu", ["id"], unique=False,
    )
    op.create_index(
        "ix_kombinacje_stolow_planu_wersja_id",
        "kombinacje_stolow_planu", ["wersja_id"], unique=False,
    )

    op.create_table(
        "skladniki_kombinacji_planu",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kombinacja_id", sa.Integer(), nullable=False),
        sa.Column("wersja_id", sa.Integer(), nullable=False),
        sa.Column("stolik_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["kombinacja_id", "wersja_id"],
            ["kombinacje_stolow_planu.id", "kombinacje_stolow_planu.wersja_id"],
            name="fk_skladniki_kombinacji_planu_kombinacja",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["wersja_id", "stolik_id"],
            ["pozycje_stolikow_planu.wersja_id", "pozycje_stolikow_planu.stolik_id"],
            name="fk_skladniki_kombinacji_planu_stolik",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "kombinacja_id", "stolik_id",
            name="uq_skladniki_kombinacji_planu_stolik",
        ),
    )
    op.create_index(
        "ix_skladniki_kombinacji_planu_id",
        "skladniki_kombinacji_planu", ["id"], unique=False,
    )
    op.create_index(
        "ix_skladniki_kombinacji_planu_kombinacja_id",
        "skladniki_kombinacji_planu", ["kombinacja_id"], unique=False,
    )
    op.create_index(
        "ix_skladniki_kombinacji_planu_wersja_id",
        "skladniki_kombinacji_planu", ["wersja_id"], unique=False,
    )
    op.create_index(
        "ix_skladniki_kombinacji_planu_stolik_id",
        "skladniki_kombinacji_planu", ["stolik_id"], unique=False,
    )


def _apply_backfill(bind, prepared: dict[str, Any]) -> None:
    metadata = sa.MetaData()
    positions = sa.Table(
        "pozycje_stolikow_planu", metadata, autoload_with=bind,
    )
    edges = sa.Table(
        "krawedzie_sasiedztwa_planu", metadata, autoload_with=bind,
    )
    combinations = sa.Table(
        "kombinacje_stolow_planu", metadata, autoload_with=bind,
    )
    members = sa.Table(
        "skladniki_kombinacji_planu", metadata, autoload_with=bind,
    )

    for table_id, values in prepared["tables"].items():
        bind.execute(
            positions.update().where(positions.c.stolik_id == table_id).values(
                **{key: values[key] for key in (
                    "nazwa", "kolejnosc", "pojemnosc", "pojemnosc_min",
                    "ksztalt", "cechy", "priorytet", "sekcja",
                )}
            )
        )

    for version_id, position_states in prepared["positions_by_version"].items():
        table_ids = set(position_states)
        edge_rows = [
            {"wersja_id": version_id, **edge}
            for edge in prepared["edges"]
            if edge["stolik_a_id"] in table_ids and edge["stolik_b_id"] in table_ids
        ]
        if edge_rows:
            bind.execute(edges.insert(), edge_rows)

        for payload in prepared["combinations"]:
            if not set(payload["stoliki"]).issubset(table_ids):
                continue
            combination_values = {
                "wersja_id": version_id,
                **{key: payload[key] for key in (
                    "nazwa", "sklad_klucz", "pojemnosc_min", "pojemnosc_max",
                    "priorytet", "kanal",
                )},
                # Historyczna pozycja moze byc nieaktywna mimo aktywnego wpisu
                # legacy. Taki zestaw zachowujemy, ale nie publikujemy jako aktywny.
                "aktywna_w_planie": bool(payload["aktywna_w_planie"]) and all(
                    position_states[table_id] for table_id in payload["stoliki"]
                ),
            }
            result = bind.execute(combinations.insert().values(**combination_values))
            combination_id = int(result.inserted_primary_key[0])
            bind.execute(members.insert(), [
                {
                    "kombinacja_id": combination_id,
                    "wersja_id": version_id,
                    "stolik_id": table_id,
                }
                for table_id in payload["stoliki"]
            ])


def upgrade() -> None:
    bind = op.get_bind()
    prepared = _prepare_backfill(bind)

    with op.batch_alter_table("pozycje_stolikow_planu") as batch:
        batch.add_column(sa.Column("nazwa", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("kolejnosc", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("pojemnosc", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("pojemnosc_min", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("ksztalt", sa.String(length=16), nullable=True))
        batch.add_column(sa.Column("cechy", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("priorytet", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("sekcja", sa.String(length=32), nullable=True))
        batch.create_check_constraint(
            "ck_pozycje_stolikow_kolejnosc", "kolejnosc IS NULL OR kolejnosc >= 0",
        )
        batch.create_check_constraint(
            "ck_pozycje_stolikow_pojemnosc", "pojemnosc IS NULL OR pojemnosc >= 1",
        )
        batch.create_check_constraint(
            "ck_pozycje_stolikow_pojemnosc_min",
            "pojemnosc_min IS NULL OR pojemnosc_min >= 1",
        )
        batch.create_check_constraint(
            "ck_pozycje_stolikow_zakres_pojemnosci",
            "pojemnosc IS NULL OR pojemnosc_min IS NULL OR pojemnosc_min <= pojemnosc",
        )

    _create_topology_tables()
    _apply_backfill(bind, prepared)


def _project_published_to_legacy(bind) -> None:
    metadata = sa.MetaData()
    versions = sa.Table("wersje_planu_sali", metadata, autoload_with=bind)
    versioned_positions = sa.Table(
        "pozycje_stolikow_planu", metadata, autoload_with=bind,
    )
    versioned_edges = sa.Table(
        "krawedzie_sasiedztwa_planu", metadata, autoload_with=bind,
    )
    versioned_combinations = sa.Table(
        "kombinacje_stolow_planu", metadata, autoload_with=bind,
    )
    versioned_members = sa.Table(
        "skladniki_kombinacji_planu", metadata, autoload_with=bind,
    )
    legacy_edges = sa.Table("sasiedztwo_stolow", metadata, autoload_with=bind)
    legacy_combinations = sa.Table(
        "kombinacje_stolow", metadata, autoload_with=bind,
    )
    legacy_tables = sa.Table("stoliki", metadata, autoload_with=bind)

    published_ids = sa.select(versions.c.id).where(versions.c.status == "published")
    invalid_channel = bind.execute(
        sa.select(versioned_combinations.c.id).where(
            versioned_combinations.c.wersja_id.in_(published_ids),
            versioned_combinations.c.kanal != "oba",
        ).limit(1)
    ).scalar_one_or_none()
    if invalid_channel is not None:
        raise RuntimeError(
            "R22_DOWNGRADE_CHANNEL_NOT_REPRESENTABLE "
            f"combination_id={invalid_channel}"
        )

    published_properties = bind.execute(
        sa.select(
            versioned_positions.c.stolik_id,
            versioned_positions.c.aktywny_w_planie,
            versioned_positions.c.nazwa,
            versioned_positions.c.kolejnosc,
            versioned_positions.c.pojemnosc,
            versioned_positions.c.pojemnosc_min,
            versioned_positions.c.ksztalt,
            versioned_positions.c.cechy,
            versioned_positions.c.priorytet,
            versioned_positions.c.sekcja,
        ).join(
            versions, versions.c.id == versioned_positions.c.wersja_id,
        ).where(versions.c.status == "published").order_by(
            versioned_positions.c.stolik_id,
        )
    ).mappings().all()
    legacy_table_ids = set(bind.execute(sa.select(legacy_tables.c.id)).scalars())
    seen_table_ids: set[int] = set()
    for properties in published_properties:
        table_id = int(properties["stolik_id"])
        name = str(properties["nazwa"] or "").strip()
        order = properties["kolejnosc"]
        capacity = properties["pojemnosc"]
        minimum = properties["pojemnosc_min"]
        if (
            table_id in seen_table_ids
            or table_id not in legacy_table_ids
            or not name
            or len(name) > 32
            or order is None
            or int(order) < 0
            or capacity is None
            or int(capacity) < 1
            or (minimum is not None and int(minimum) < 1)
            or (minimum is not None and int(minimum) > int(capacity))
            or (
                properties["ksztalt"] is not None
                and len(str(properties["ksztalt"])) > 16
            )
            or (
                properties["sekcja"] is not None
                and len(str(properties["sekcja"])) > 32
            )
        ):
            raise RuntimeError(
                "R22_DOWNGRADE_PROPERTIES_NOT_REPRESENTABLE "
                f"table_id={table_id}"
            )
        seen_table_ids.add(table_id)

    # Downgrade ma byc samowystarczalny: published snapshot jest zrodlem prawdy
    # nawet wtedy, gdy dane nie byly publikowane przez aktualny proces aplikacji.
    # Nie projektujemy geometrii (plan_x/plan_y), bo nie nalezy do tego kontraktu.
    for properties in published_properties:
        table_id = int(properties["stolik_id"])
        result = bind.execute(
            legacy_tables.update().where(legacy_tables.c.id == table_id).values(
                aktywny=bool(properties["aktywny_w_planie"]),
                nazwa=str(properties["nazwa"]).strip(),
                kolejnosc=int(properties["kolejnosc"]),
                pojemnosc=int(properties["pojemnosc"]),
                pojemnosc_min=(
                    None if properties["pojemnosc_min"] is None
                    else int(properties["pojemnosc_min"])
                ),
                ksztalt=properties["ksztalt"],
                cechy=properties["cechy"],
                priorytet=properties["priorytet"],
                sekcja=properties["sekcja"],
            )
        )
        if result.rowcount != 1:
            raise RuntimeError(
                "R22_DOWNGRADE_PROPERTIES_NOT_REPRESENTABLE "
                f"table_id={table_id}"
            )

    # Legacy fallback nadal obsluguje sale, ktore nie maja wersjonowanego planu.
    # Downgrade moze zastapic tylko topologie nalezaca do zakresu R2.2; wpisy
    # niewersjonowanych sal musza pozostac nietkniete.
    versioned_table_ids = {
        int(table_id) for table_id in bind.execute(
            sa.select(versioned_positions.c.stolik_id).distinct()
        ).scalars()
    }
    versioned_legacy_edge_ids = [
        int(row["id"])
        for row in bind.execute(
            sa.select(
                legacy_edges.c.id,
                legacy_edges.c.stolik_a,
                legacy_edges.c.stolik_b,
            )
        ).mappings()
        if (
            int(row["stolik_a"]) in versioned_table_ids
            or int(row["stolik_b"]) in versioned_table_ids
        )
    ]
    if versioned_legacy_edge_ids:
        bind.execute(
            legacy_edges.delete().where(
                legacy_edges.c.id.in_(versioned_legacy_edge_ids)
            )
        )

    versioned_legacy_combination_ids: list[int] = []
    for row in bind.execute(
        sa.select(legacy_combinations.c.id, legacy_combinations.c.stoliki)
    ).mappings():
        raw_members = row["stoliki"]
        if isinstance(raw_members, (list, tuple)) and any(
            int(table_id) in versioned_table_ids for table_id in raw_members
        ):
            versioned_legacy_combination_ids.append(int(row["id"]))
    if versioned_legacy_combination_ids:
        bind.execute(
            legacy_combinations.delete().where(
                legacy_combinations.c.id.in_(versioned_legacy_combination_ids)
            )
        )
    published_edges = bind.execute(
        sa.select(
            versioned_edges.c.stolik_a_id,
            versioned_edges.c.stolik_b_id,
        ).join(
            versions, versions.c.id == versioned_edges.c.wersja_id,
        ).where(versions.c.status == "published").order_by(
            versioned_edges.c.stolik_a_id,
            versioned_edges.c.stolik_b_id,
        )
    ).mappings().all()
    for edge in published_edges:
        bind.execute(legacy_edges.insert().values(
            stolik_a=edge["stolik_a_id"],
            stolik_b=edge["stolik_b_id"],
        ))

    published_combinations = bind.execute(
        sa.select(
            versioned_combinations.c.id,
            versioned_combinations.c.nazwa,
            versioned_combinations.c.pojemnosc_min,
            versioned_combinations.c.pojemnosc_max,
            versioned_combinations.c.aktywna_w_planie,
            versioned_combinations.c.priorytet,
        ).join(
            versions, versions.c.id == versioned_combinations.c.wersja_id,
        ).where(versions.c.status == "published").order_by(
            versioned_combinations.c.priorytet,
            versioned_combinations.c.id,
        )
    ).mappings().all()
    for combination in published_combinations:
        table_ids = [
            int(table_id) for (table_id,) in bind.execute(
                sa.select(versioned_members.c.stolik_id).where(
                    versioned_members.c.kombinacja_id == combination["id"],
                ).order_by(versioned_members.c.stolik_id)
            )
        ]
        bind.execute(legacy_combinations.insert().values(
            nazwa=combination["nazwa"],
            stoliki=table_ids,
            pojemnosc_min=combination["pojemnosc_min"],
            pojemnosc_max=combination["pojemnosc_max"],
            aktywna=bool(combination["aktywna_w_planie"]),
            priorytet=combination["priorytet"],
        ))


def downgrade() -> None:
    bind = op.get_bind()
    _project_published_to_legacy(bind)

    op.drop_index(
        "ix_skladniki_kombinacji_planu_stolik_id",
        table_name="skladniki_kombinacji_planu",
    )
    op.drop_index(
        "ix_skladniki_kombinacji_planu_wersja_id",
        table_name="skladniki_kombinacji_planu",
    )
    op.drop_index(
        "ix_skladniki_kombinacji_planu_kombinacja_id",
        table_name="skladniki_kombinacji_planu",
    )
    op.drop_index(
        "ix_skladniki_kombinacji_planu_id",
        table_name="skladniki_kombinacji_planu",
    )
    op.drop_table("skladniki_kombinacji_planu")
    op.drop_index(
        "ix_kombinacje_stolow_planu_wersja_id",
        table_name="kombinacje_stolow_planu",
    )
    op.drop_index(
        "ix_kombinacje_stolow_planu_id",
        table_name="kombinacje_stolow_planu",
    )
    op.drop_table("kombinacje_stolow_planu")
    op.drop_index(
        "ix_krawedzie_sasiedztwa_planu_wersja_id",
        table_name="krawedzie_sasiedztwa_planu",
    )
    op.drop_index(
        "ix_krawedzie_sasiedztwa_planu_id",
        table_name="krawedzie_sasiedztwa_planu",
    )
    op.drop_table("krawedzie_sasiedztwa_planu")

    with op.batch_alter_table("pozycje_stolikow_planu") as batch:
        batch.drop_constraint("ck_pozycje_stolikow_zakres_pojemnosci", type_="check")
        batch.drop_constraint("ck_pozycje_stolikow_pojemnosc_min", type_="check")
        batch.drop_constraint("ck_pozycje_stolikow_pojemnosc", type_="check")
        batch.drop_constraint("ck_pozycje_stolikow_kolejnosc", type_="check")
        batch.drop_column("sekcja")
        batch.drop_column("priorytet")
        batch.drop_column("cechy")
        batch.drop_column("ksztalt")
        batch.drop_column("pojemnosc_min")
        batch.drop_column("pojemnosc")
        batch.drop_column("kolejnosc")
        batch.drop_column("nazwa")
