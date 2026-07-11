"""Atomowy ledger zasobów, pacingu i idempotencji rezerwacji.

Revision ID: 0051_rezerwacje_atomic_ledger
Revises: 0050_rezerwacje_source_identity
"""
from __future__ import annotations

import json
from datetime import date, datetime, time
from typing import Any, Iterable, Sequence, Union
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from alembic import op

revision: str = "0051_rezerwacje_atomic_ledger"
down_revision: Union[str, None] = "0050_rezerwacje_source_identity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ACTIVE_STATUSES = ("rezerwacja", "potwierdzona")
_WARSAW = ZoneInfo("Europe/Warsaw")


def _now_local_naive() -> datetime:
    return datetime.now(_WARSAW).replace(tzinfo=None)


def _as_date(value: Any, *, code: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise RuntimeError(code) from exc
    raise RuntimeError(code)


def _as_local_naive(value: Any, *, code: str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError as exc:
            raise RuntimeError(code) from exc
    if not isinstance(value, datetime):
        raise RuntimeError(code)
    if value.tzinfo is not None:
        return value.astimezone(_WARSAW).replace(tzinfo=None)
    return value


def _minute(value: Any, *, code: str) -> int:
    if isinstance(value, str):
        try:
            value = time.fromisoformat(value)
        except ValueError as exc:
            raise RuntimeError(code) from exc
    if not isinstance(value, time) or value.second or value.microsecond:
        raise RuntimeError(code)
    return value.hour * 60 + value.minute


def _extra_table_ids(value: Any, *, record_id: int) -> list[int]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                f"R0B_BACKFILL_CORRUPT_EXTRA_TABLES record_id={record_id}"
            ) from exc
    if not isinstance(value, list):
        raise RuntimeError(f"R0B_BACKFILL_CORRUPT_EXTRA_TABLES record_id={record_id}")

    result: list[int] = []
    for raw in value:
        if isinstance(raw, bool):
            raise RuntimeError(f"R0B_BACKFILL_CORRUPT_EXTRA_TABLES record_id={record_id}")
        try:
            table_id = int(raw)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                f"R0B_BACKFILL_CORRUPT_EXTRA_TABLES record_id={record_id}"
            ) from exc
        if table_id <= 0 or (isinstance(raw, float) and not raw.is_integer()):
            raise RuntimeError(f"R0B_BACKFILL_CORRUPT_EXTRA_TABLES record_id={record_id}")
        if table_id in result:
            raise RuntimeError(f"R0B_BACKFILL_DUPLICATE_TABLE record_id={record_id}")
        result.append(table_id)
    return result


def _insert_chunks(bind, table, rows: Iterable[dict], size: int = 2_000) -> None:
    chunk: list[dict] = []
    for row in rows:
        chunk.append(row)
        if len(chunk) >= size:
            bind.execute(table.insert(), chunk)
            chunk = []
    if chunk:
        bind.execute(table.insert(), chunk)


def _prepare_backfill(bind) -> tuple[list[dict], list[dict], list[dict]]:
    """Waliduje stary stan i buduje backfill, zanim SQLite wykona nieodwracalne DDL.

    Alembic traktuje SQLite DDL jako nietransakcyjne. Każdy błąd jakości danych musi więc
    wystąpić przed pierwszym ``CREATE TABLE``; inaczej baza zostałaby na rewizji 0050 z
    częściowo utworzonym schematem 0051, którego nie da się ponownie podnieść.
    """
    now = _now_local_naive()

    terminy = sa.table(
        "terminy",
        sa.column("id", sa.Integer()),
        sa.column("data", sa.Date()),
        sa.column("godz_od", sa.Time()),
        sa.column("godz_do", sa.Time()),
        sa.column("liczba_osob", sa.Integer()),
        sa.column("rodzaj", sa.String()),
        sa.column("status", sa.String()),
        sa.column("stolik_id", sa.Integer()),
        sa.column("stoliki_dodatkowe", sa.JSON()),
    )
    stoliki = sa.table("stoliki", sa.column("id", sa.Integer()))
    waitlista = sa.table(
        "lista_oczekujacych",
        sa.column("id", sa.Integer()),
        sa.column("data", sa.Date()),
        sa.column("status", sa.String()),
        sa.column("hold_stolik_id", sa.Integer()),
        sa.column("hold_do", sa.DateTime()),
    )
    known_tables = set(bind.execute(sa.select(stoliki.c.id)).scalars())
    reservation_rows = bind.execute(
        sa.select(terminy).where(
            terminy.c.rodzaj == "stolik",
            terminy.c.status.in_(_ACTIVE_STATUSES),
        ).order_by(terminy.c.id)
    ).mappings().all()
    hold_rows = bind.execute(
        sa.select(waitlista).where(
            waitlista.c.status == "oczekuje",
            waitlista.c.hold_stolik_id.is_not(None),
            waitlista.c.hold_do.is_not(None),
        ).order_by(waitlista.c.id)
    ).mappings().all()

    day_values: set[date] = set()
    pacing_values: list[dict] = []
    claim_values: list[dict] = []
    occupied: set[tuple[int, date, int]] = set()

    for row in reservation_rows:
        record_id = int(row["id"])
        booking_date = _as_date(
            row["data"], code=f"R0B_BACKFILL_INVALID_DATE record_id={record_id}",
        )
        day_values.add(booking_date)
        start_value = row["godz_od"]

        primary = row["stolik_id"]
        extra = _extra_table_ids(row["stoliki_dodatkowe"], record_id=record_id)
        table_ids: list[int] = []
        if primary is not None:
            try:
                primary_id = int(primary)
            except (TypeError, ValueError) as exc:
                raise RuntimeError(
                    f"R0B_BACKFILL_CORRUPT_PRIMARY_TABLE record_id={record_id}"
                ) from exc
            if primary_id <= 0 or primary_id in extra:
                raise RuntimeError(f"R0B_BACKFILL_DUPLICATE_TABLE record_id={record_id}")
            table_ids.append(primary_id)
        table_ids.extend(extra)

        if start_value is not None:
            start_minute = _minute(
                start_value, code=f"R0B_BACKFILL_INVALID_START record_id={record_id}",
            )
            try:
                covers = int(row["liczba_osob"] or 0)
            except (TypeError, ValueError) as exc:
                raise RuntimeError(
                    f"R0B_BACKFILL_INVALID_COVERS record_id={record_id}"
                ) from exc
            if covers < 0:
                raise RuntimeError(f"R0B_BACKFILL_INVALID_COVERS record_id={record_id}")
            pacing_values.append({
                "termin_id": record_id,
                "data": booking_date,
                "start_minute": start_minute,
                "covers": covers,
                "override": False,
                "created_at": now,
            })
        elif table_ids:
            raise RuntimeError(f"R0B_BACKFILL_MISSING_START record_id={record_id}")

        if not table_ids:
            continue
        missing = sorted(set(table_ids) - known_tables)
        if missing:
            raise RuntimeError(
                f"R0B_BACKFILL_MISSING_TABLE table_id={missing[0]} record_id={record_id}"
            )
        if row["godz_do"] is None:
            raise RuntimeError(f"R0B_BACKFILL_MISSING_END record_id={record_id}")
        end_minute = _minute(
            row["godz_do"], code=f"R0B_BACKFILL_INVALID_END record_id={record_id}",
        )
        if end_minute <= start_minute:
            raise RuntimeError(f"R0B_BACKFILL_INVALID_END record_id={record_id}")

        for table_id in sorted(table_ids):
            for minute in range(start_minute, end_minute):
                slot = (table_id, booking_date, minute)
                if slot in occupied:
                    raise RuntimeError(
                        "R0B_BACKFILL_TABLE_OVERLAP "
                        f"table_id={table_id} date={booking_date.isoformat()} minute={minute}"
                    )
                occupied.add(slot)
                claim_values.append({
                    "termin_id": record_id,
                    "waitlist_id": None,
                    "stolik_id": table_id,
                    "data": booking_date,
                    "minute": minute,
                    "expires_at": None,
                    "created_at": now,
                })

    for row in hold_rows:
        hold_id = int(row["id"])
        hold_until = _as_local_naive(
            row["hold_do"], code=f"R0B_BACKFILL_INVALID_HOLD_EXPIRY waitlist_id={hold_id}",
        )
        if hold_until <= now:
            continue
        booking_date = _as_date(
            row["data"], code=f"R0B_BACKFILL_INVALID_HOLD_DATE waitlist_id={hold_id}",
        )
        table_id = int(row["hold_stolik_id"])
        if table_id not in known_tables:
            raise RuntimeError(
                f"R0B_BACKFILL_MISSING_TABLE table_id={table_id} waitlist_id={hold_id}"
            )
        day_values.add(booking_date)
        for minute in range(1440):
            slot = (table_id, booking_date, minute)
            if slot in occupied:
                raise RuntimeError(
                    "R0B_BACKFILL_TABLE_OVERLAP "
                    f"table_id={table_id} date={booking_date.isoformat()} minute={minute}"
                )
            occupied.add(slot)
            claim_values.append({
                "termin_id": None,
                "waitlist_id": hold_id,
                "stolik_id": table_id,
                "data": booking_date,
                "minute": minute,
                "expires_at": hold_until,
                "created_at": now,
            })

    day_rows = [
        {"data": ledger_date, "revision": 0, "updated_at": now}
        for ledger_date in sorted(day_values)
    ]
    pacing_rows = sorted(pacing_values, key=lambda row: row["termin_id"])
    claim_rows = sorted(
        claim_values,
        key=lambda row: (
            row["stolik_id"], row["data"], row["minute"],
            row["termin_id"] or 0, row["waitlist_id"] or 0,
        ),
    )
    return day_rows, pacing_rows, claim_rows


def _apply_backfill(bind, prepared: tuple[list[dict], list[dict], list[dict]]) -> None:
    day_rows, pacing_rows, claim_rows = prepared
    dni = sa.table(
        "rezerwacje_dni_ledger",
        sa.column("data", sa.Date()),
        sa.column("revision", sa.Integer()),
        sa.column("updated_at", sa.DateTime()),
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
    claims = sa.table(
        "rezerwacje_stoliki_claims",
        sa.column("termin_id", sa.Integer()),
        sa.column("waitlist_id", sa.Integer()),
        sa.column("stolik_id", sa.Integer()),
        sa.column("data", sa.Date()),
        sa.column("minute", sa.Integer()),
        sa.column("expires_at", sa.DateTime()),
        sa.column("created_at", sa.DateTime()),
    )
    _insert_chunks(bind, dni, day_rows)
    _insert_chunks(bind, pacing, pacing_rows)
    _insert_chunks(
        bind,
        claims,
        claim_rows,
    )


def upgrade() -> None:
    # Preflight MUSI poprzedzać DDL — patrz _prepare_backfill.
    bind = op.get_bind()
    prepared = _prepare_backfill(bind)

    op.create_table(
        "rezerwacje_idempotencja",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="processing"),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("response_enc", sa.String(), nullable=True),
        sa.Column(
            "termin_id", sa.Integer(),
            sa.ForeignKey("terminy.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "operation", "key_hash", name="uq_rezerwacje_idempotencja_operation_key",
        ),
        sa.CheckConstraint(
            "length(operation) > 0", name="ck_rezerwacje_idempotencja_operation",
        ),
        sa.CheckConstraint(
            "length(key_hash) = 64", name="ck_rezerwacje_idempotencja_key_hash",
        ),
        sa.CheckConstraint(
            "length(request_fingerprint) = 64",
            name="ck_rezerwacje_idempotencja_fingerprint",
        ),
        sa.CheckConstraint(
            "status IN ('processing', 'succeeded')",
            name="ck_rezerwacje_idempotencja_status",
        ),
        sa.CheckConstraint(
            "(status = 'processing' AND http_status IS NULL AND response_enc IS NULL "
            "AND completed_at IS NULL) OR "
            "(status = 'succeeded' AND http_status BETWEEN 200 AND 299 "
            "AND response_enc IS NOT NULL AND completed_at IS NOT NULL)",
            name="ck_rezerwacje_idempotencja_result",
        ),
    )
    op.create_index(
        "ix_rezerwacje_idempotencja_expires_at",
        "rezerwacje_idempotencja", ["expires_at"],
    )

    op.create_table(
        "rezerwacje_dni_ledger",
        sa.Column("data", sa.Date(), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("revision >= 0", name="ck_rezerwacje_dni_ledger_revision"),
    )

    op.create_table(
        "rezerwacje_stoliki_claims",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "termin_id", sa.Integer(),
            sa.ForeignKey("terminy.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column(
            "waitlist_id", sa.Integer(),
            sa.ForeignKey("lista_oczekujacych.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column(
            "stolik_id", sa.Integer(),
            sa.ForeignKey("stoliki.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("minute", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "stolik_id", "data", "minute", name="uq_rezerwacje_stolik_claim_slot",
        ),
        sa.UniqueConstraint(
            "termin_id", "stolik_id", "data", "minute",
            name="uq_rezerwacje_stolik_claim_termin_owner",
        ),
        sa.UniqueConstraint(
            "waitlist_id", "stolik_id", "data", "minute",
            name="uq_rezerwacje_stolik_claim_waitlist_owner",
        ),
        sa.CheckConstraint(
            "minute >= 0 AND minute < 1440", name="ck_rezerwacje_stolik_claim_minute",
        ),
        sa.CheckConstraint(
            "(termin_id IS NOT NULL AND waitlist_id IS NULL AND expires_at IS NULL) OR "
            "(termin_id IS NULL AND waitlist_id IS NOT NULL AND expires_at IS NOT NULL)",
            name="ck_rezerwacje_stolik_claim_owner",
        ),
    )
    op.create_index(
        "ix_rezerwacje_stolik_claim_termin_id", "rezerwacje_stoliki_claims", ["termin_id"],
    )
    op.create_index(
        "ix_rezerwacje_stolik_claim_waitlist_id", "rezerwacje_stoliki_claims", ["waitlist_id"],
    )
    op.create_index(
        "ix_rezerwacje_stolik_claim_expires_at", "rezerwacje_stoliki_claims", ["expires_at"],
    )

    op.create_table(
        "rezerwacje_pacing_ledger",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "termin_id", sa.Integer(),
            sa.ForeignKey("terminy.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("start_minute", sa.Integer(), nullable=False),
        sa.Column("covers", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("override", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("termin_id", name="uq_rezerwacje_pacing_ledger_termin"),
        sa.CheckConstraint(
            "start_minute >= 0 AND start_minute < 1440",
            name="ck_rezerwacje_pacing_ledger_start_minute",
        ),
        sa.CheckConstraint("covers >= 0", name="ck_rezerwacje_pacing_ledger_covers"),
    )
    op.create_index(
        "ix_rezerwacje_pacing_ledger_data_start",
        "rezerwacje_pacing_ledger", ["data", "start_minute"],
    )

    _apply_backfill(bind, prepared)


def downgrade() -> None:
    op.drop_index(
        "ix_rezerwacje_pacing_ledger_data_start", table_name="rezerwacje_pacing_ledger",
    )
    op.drop_table("rezerwacje_pacing_ledger")

    op.drop_index(
        "ix_rezerwacje_stolik_claim_expires_at", table_name="rezerwacje_stoliki_claims",
    )
    op.drop_index(
        "ix_rezerwacje_stolik_claim_waitlist_id", table_name="rezerwacje_stoliki_claims",
    )
    op.drop_index(
        "ix_rezerwacje_stolik_claim_termin_id", table_name="rezerwacje_stoliki_claims",
    )
    op.drop_table("rezerwacje_stoliki_claims")

    op.drop_table("rezerwacje_dni_ledger")

    op.drop_index(
        "ix_rezerwacje_idempotencja_expires_at", table_name="rezerwacje_idempotencja",
    )
    op.drop_table("rezerwacje_idempotencja")
