"""R7.2 rejected demand and waitlist effectiveness.

Revision ID: 0066_r72_reservation_demand
Revises: 0065_r6b2_waitlist_offers
"""
from __future__ import annotations

import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0066_r72_reservation_demand"
down_revision: Union[str, None] = "0065_r6b2_waitlist_offers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_WAITLIST_TABLE = "lista_oczekujacych"
_EVENT_TABLE = "reservation_demand_events"
_WAITLIST_ADDITIONS = (
    ("create_key_hash", sa.String(length=64), True, None),
    ("create_request_fingerprint", sa.String(length=64), True, None),
    ("demand_reason_code", sa.String(length=32), False, "legacy_unknown"),
    ("demand_resource_kind", sa.String(length=32), False, "unknown"),
    ("attended_at", sa.DateTime(), True, None),
)
_WAITLIST_CHECKS = {
    "ck_lista_oczekujacych_create_idempotency": (
        "(create_key_hash IS NULL AND create_request_fingerprint IS NULL) OR "
        "(length(create_key_hash) = 64 AND "
        "length(create_request_fingerprint) = 64)"
    ),
    "ck_lista_oczekujacych_demand_reason": (
        "demand_reason_code IN ("
        "'service_closed', 'channel_unavailable', 'booking_window', "
        "'party_policy', 'pacing_limit', 'concurrent_limit', "
        "'resource_occupied', 'no_capacity_match', "
        "'operator_decision', 'legacy_unknown', 'other')"
    ),
    "ck_lista_oczekujacych_demand_resource": (
        "demand_resource_kind IN ("
        "'policy', 'service_capacity', 'table_or_combination', "
        "'capacity', 'available', 'unknown')"
    ),
}
_WAITLIST_UNIQUES = {
    "uq_lista_oczekujacych_create_key_hash": ("create_key_hash",),
}

_EVENT_COLUMNS = (
    ("id", sa.Integer(), False),
    ("source_kind", sa.String(length=16), False),
    ("channel", sa.String(length=16), False),
    ("requested_date", sa.Date(), False),
    ("requested_time", sa.Time(), True),
    ("party_size", sa.Integer(), False),
    ("reason_code", sa.String(length=32), False),
    ("resource_kind", sa.String(length=32), False),
    ("event_key_hash", sa.String(length=64), False),
    ("request_fingerprint", sa.String(length=64), False),
    ("captured_at", sa.DateTime(), False),
)
_EVENT_CHECKS = {
    "ck_reservation_demand_events_source": (
        "source_kind IN ('availability', 'waitlist')"
    ),
    "ck_reservation_demand_events_channel": (
        "channel IN ('online', 'wewnetrzna')"
    ),
    "ck_reservation_demand_events_party_size": (
        "party_size >= 1 AND party_size <= 500"
    ),
    "ck_reservation_demand_events_reason": (
        "reason_code IN ("
        "'service_closed', 'channel_unavailable', 'booking_window', "
        "'party_policy', 'pacing_limit', 'concurrent_limit', "
        "'resource_occupied', 'no_capacity_match', "
        "'operator_decision', 'legacy_unknown', 'other')"
    ),
    "ck_reservation_demand_events_resource": (
        "resource_kind IN ("
        "'policy', 'service_capacity', 'table_or_combination', "
        "'capacity', 'available', 'unknown')"
    ),
    "ck_reservation_demand_events_key_hash": "length(event_key_hash) = 64",
    "ck_reservation_demand_events_fingerprint": (
        "length(request_fingerprint) = 64"
    ),
}
_EVENT_UNIQUES = {
    "uq_reservation_demand_events_source_key": (
        "source_kind", "event_key_hash",
    ),
}
_EVENT_INDEXES = {
    "ix_reservation_demand_events_date_source_reason": (
        ("requested_date", "source_kind", "reason_code"), False,
    ),
}
_POSTGRES_MEMBERSHIP_CHECKS = {
    "ck_lista_oczekujacych_demand_reason",
    "ck_lista_oczekujacych_demand_resource",
    "ck_reservation_demand_events_source",
    "ck_reservation_demand_events_channel",
    "ck_reservation_demand_events_reason",
    "ck_reservation_demand_events_resource",
}


def _normalise_sql(value) -> str:
    text = re.sub(r'[\s"`\[\]]+', "", str(value or "")).lower()
    while text.startswith("(") and text.endswith(")"):
        text = text[1:-1]
    return text


def _postgres_check_signature(value) -> str:
    sql = str(value or "").casefold().replace('"', "").replace("`", "")
    sql = re.sub(
        r"::\s*(?:character\s+varying|timestamp(?:\s+(?:with|without)\s+"
        r"time\s+zone)?|time(?:\s+(?:with|without)\s+time\s+zone)?|"
        r"double\s+precision|[a-z_][a-z0-9_.]*)"
        r"(?:\s*\(\s*\d+(?:\s*,\s*\d+)?\s*\))?(?:\s*\[\s*\])?",
        "",
        sql,
    )
    return re.sub(r"[\s()\[\]]+", "", sql)


def _check_matches(name: str, actual, expected, dialect_name: str) -> bool:
    if dialect_name != "postgresql":
        return _normalise_sql(actual) == _normalise_sql(expected)
    actual_signature = _postgres_check_signature(actual)
    expected_signature = _postgres_check_signature(expected)
    if name not in _POSTGRES_MEMBERSHIP_CHECKS:
        return actual_signature == expected_signature

    expected_literals = re.findall(r"'([^']*)'", str(expected))
    actual_literals = re.findall(r"'([^']*)'", str(actual))
    if actual_literals != expected_literals:
        return False
    actual_shape = re.sub(r"'[^']*'", "?", actual_signature)
    expected_shape = re.sub(r"'[^']*'", "?", expected_signature)
    first_literal = expected_shape.find("?")
    expected_prefix = expected_shape[:first_literal]
    if first_literal < 0 or not expected_prefix.endswith("in"):
        return False
    pg_any_shape = (
        expected_prefix[:-len("in")] + "=anyarray"
        + expected_shape[first_literal:]
    )
    return actual_shape in {expected_shape, pg_any_shape}


def _type_matches(actual, expected) -> bool:
    if not isinstance(actual, type(expected)):
        return False
    if isinstance(expected, sa.String):
        return getattr(actual, "length", None) == getattr(expected, "length", None)
    return True


def _default_matches(actual, expected) -> bool:
    def signature(value):
        if value is None:
            return None
        value = getattr(value, "arg", value)
        raw = str(value).strip().casefold()
        while raw.startswith("(") and raw.endswith(")"):
            raw = raw[1:-1].strip()
        raw = re.sub(
            r"::\s*(?:character\s+varying|varchar|text)"
            r"(?:\s*\(\s*\d+\s*\))?$",
            "",
            raw,
        ).strip()
        while raw.startswith("(") and raw.endswith(")"):
            raw = raw[1:-1].strip()
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {"'", '"'}:
            raw = raw[1:-1].replace("''", "'")
        return raw

    return signature(actual) == signature(expected)


def _postgres_pk_generator_is_valid(column) -> bool:
    if isinstance(column.get("identity"), dict):
        return True
    default = re.sub(r"\s+", "", str(column.get("default") or "")).casefold()
    return bool(re.fullmatch(
        r"nextval\('(?:[^']|'')+'::regclass\)",
        default,
    ))


def _index_shapes(inspector, table_name: str) -> dict[str, tuple[tuple[str, ...], bool]]:
    return {
        item.get("name"): (
            tuple(item.get("column_names") or ()), bool(item.get("unique")),
        )
        for item in inspector.get_indexes(table_name)
        if item.get("name")
    }


def _unique_shapes(inspector, table_name: str) -> dict[str, tuple[str, ...]]:
    uniques = {
        item.get("name"): tuple(item.get("column_names") or ())
        for item in inspector.get_unique_constraints(table_name)
        if item.get("name")
    }
    for name, (columns, unique) in _index_shapes(inspector, table_name).items():
        if unique:
            uniques.setdefault(name, columns)
    return uniques


def _validate_event_schema(inspector, dialect_name: str) -> None:
    columns = {
        item["name"]: item for item in inspector.get_columns(_EVENT_TABLE)
    }
    if set(columns) != {item[0] for item in _EVENT_COLUMNS}:
        raise RuntimeError("R72_PARTIAL_ADOPTION: incompatible demand event columns")
    for name, expected_type, nullable in _EVENT_COLUMNS:
        actual = columns[name]
        if (
            not _type_matches(actual["type"], expected_type)
            or bool(actual.get("nullable")) != nullable
        ):
            raise RuntimeError(
                f"R72_PARTIAL_ADOPTION: incompatible demand event column {name}"
            )
        if name != "id" and not _default_matches(actual.get("default"), None):
            raise RuntimeError(
                f"R72_PARTIAL_ADOPTION: incompatible demand event default {name}"
            )

    pk = tuple(
        inspector.get_pk_constraint(_EVENT_TABLE).get("constrained_columns") or ()
    )
    if pk != ("id",):
        raise RuntimeError("R72_PARTIAL_ADOPTION: incompatible demand event PK")
    if (
        dialect_name == "postgresql"
        and not _postgres_pk_generator_is_valid(columns["id"])
    ):
        raise RuntimeError("R72_PARTIAL_ADOPTION: demand event PK has no generator")

    indexes = _index_shapes(inspector, _EVENT_TABLE)
    semantic_indexes = {
        name: shape for name, shape in indexes.items()
        if not (
            shape[1]
            and _EVENT_UNIQUES.get(name) == shape[0]
        )
    }
    if semantic_indexes != _EVENT_INDEXES:
        raise RuntimeError("R72_PARTIAL_ADOPTION: incompatible demand event indexes")
    if _unique_shapes(inspector, _EVENT_TABLE) != _EVENT_UNIQUES:
        raise RuntimeError("R72_PARTIAL_ADOPTION: incompatible demand event UNIQUE")
    if inspector.get_foreign_keys(_EVENT_TABLE):
        raise RuntimeError("R72_PARTIAL_ADOPTION: demand event table must not have FK")

    raw_checks = inspector.get_check_constraints(_EVENT_TABLE)
    checks = {
        item.get("name"): item.get("sqltext")
        for item in raw_checks if item.get("name")
    }
    if (
        len(raw_checks) != len(_EVENT_CHECKS)
        or any(not item.get("name") for item in raw_checks)
        or set(checks) != set(_EVENT_CHECKS)
    ):
        raise RuntimeError("R72_PARTIAL_ADOPTION: incompatible demand event CHECK")
    for name, expected in _EVENT_CHECKS.items():
        if not _check_matches(name, checks[name], expected, dialect_name):
            raise RuntimeError(
                f"R72_PARTIAL_ADOPTION: incompatible demand event check {name}"
            )


def _validate_adopted_schema(bind) -> None:
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    event_exists = _EVENT_TABLE in tables
    columns = {
        item["name"]: item
        for item in inspector.get_columns(_WAITLIST_TABLE)
    }
    expected_names = {item[0] for item in _WAITLIST_ADDITIONS}
    present_names = expected_names & set(columns)
    target_checks = {
        item.get("name")
        for item in inspector.get_check_constraints(_WAITLIST_TABLE)
        if item.get("name") in _WAITLIST_CHECKS
    }
    target_uniques = set(_unique_shapes(inspector, _WAITLIST_TABLE)) & set(
        _WAITLIST_UNIQUES
    )
    if not present_names:
        if event_exists or target_checks or target_uniques:
            raise RuntimeError(
                "R72_PARTIAL_ADOPTION: constraints or table exist without waitlist columns"
            )
        return
    if present_names != expected_names:
        raise RuntimeError("R72_PARTIAL_ADOPTION: only some waitlist columns are present")
    if not event_exists:
        raise RuntimeError("R72_PARTIAL_ADOPTION: waitlist columns exist without event table")

    for name, expected_type, nullable, default in _WAITLIST_ADDITIONS:
        actual = columns[name]
        if (
            not _type_matches(actual["type"], expected_type)
            or bool(actual.get("nullable")) != nullable
            or not _default_matches(actual.get("default"), default)
        ):
            raise RuntimeError(f"R72_PARTIAL_ADOPTION: incompatible column {name}")

    dialect_name = bind.dialect.name
    checks = {
        item.get("name"): item.get("sqltext")
        for item in inspector.get_check_constraints(_WAITLIST_TABLE)
        if item.get("name") in _WAITLIST_CHECKS
    }
    if set(checks) != set(_WAITLIST_CHECKS):
        raise RuntimeError("R72_PARTIAL_ADOPTION: incomplete waitlist CHECK")
    for name, expected in _WAITLIST_CHECKS.items():
        if not _check_matches(name, checks[name], expected, dialect_name):
            raise RuntimeError(f"R72_PARTIAL_ADOPTION: incompatible check {name}")
    if _unique_shapes(inspector, _WAITLIST_TABLE).get(
        "uq_lista_oczekujacych_create_key_hash"
    ) != ("create_key_hash",):
        raise RuntimeError("R72_PARTIAL_ADOPTION: incompatible waitlist UNIQUE")

    _validate_event_schema(inspector, dialect_name)


def upgrade() -> None:
    bind = op.get_bind()
    _validate_adopted_schema(bind)
    existing_columns = {
        item["name"] for item in sa.inspect(bind).get_columns(_WAITLIST_TABLE)
    }
    missing = [
        item for item in _WAITLIST_ADDITIONS if item[0] not in existing_columns
    ]
    if missing:
        recreate = "always" if bind.dialect.name == "sqlite" else "auto"
        with op.batch_alter_table(_WAITLIST_TABLE, recreate=recreate) as batch:
            for name, column_type, nullable, default in missing:
                batch.add_column(sa.Column(
                    name,
                    column_type,
                    nullable=nullable,
                    server_default=default,
                ))
            for name, sql in _WAITLIST_CHECKS.items():
                batch.create_check_constraint(name, sql)
            batch.create_unique_constraint(
                "uq_lista_oczekujacych_create_key_hash",
                ["create_key_hash"],
            )

    if _EVENT_TABLE not in set(sa.inspect(bind).get_table_names()):
        op.create_table(
            _EVENT_TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source_kind", sa.String(length=16), nullable=False),
            sa.Column("channel", sa.String(length=16), nullable=False),
            sa.Column("requested_date", sa.Date(), nullable=False),
            sa.Column("requested_time", sa.Time(), nullable=True),
            sa.Column("party_size", sa.Integer(), nullable=False),
            sa.Column("reason_code", sa.String(length=32), nullable=False),
            sa.Column("resource_kind", sa.String(length=32), nullable=False),
            sa.Column("event_key_hash", sa.String(length=64), nullable=False),
            sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
            sa.Column("captured_at", sa.DateTime(), nullable=False),
            *[
                sa.CheckConstraint(sql, name=name)
                for name, sql in _EVENT_CHECKS.items()
            ],
            sa.UniqueConstraint(
                "source_kind", "event_key_hash",
                name="uq_reservation_demand_events_source_key",
            ),
        )
        op.create_index(
            "ix_reservation_demand_events_date_source_reason",
            _EVENT_TABLE,
            ["requested_date", "source_kind", "reason_code"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if _EVENT_TABLE in tables:
        event_data = bind.execute(sa.text(
            f"SELECT 1 FROM {_EVENT_TABLE} LIMIT 1"
        )).first()
        if event_data is not None:
            raise RuntimeError(
                "R72_DOWNGRADE_DATA_LOSS: istnieja zdarzenia odrzuconego popytu."
            )

    waitlist_data = bind.execute(sa.text(
        "SELECT 1 FROM lista_oczekujacych WHERE "
        "create_key_hash IS NOT NULL OR "
        "create_request_fingerprint IS NOT NULL OR "
        "demand_reason_code <> 'legacy_unknown' OR "
        "demand_resource_kind <> 'unknown' OR "
        "attended_at IS NOT NULL LIMIT 1"
    )).first()
    if waitlist_data is not None:
        raise RuntimeError(
            "R72_DOWNGRADE_DATA_LOSS: waitlista zawiera dane R7.2, ktorych "
            "starszy schemat nie potrafi zachowac."
        )

    if _EVENT_TABLE in tables:
        op.drop_table(_EVENT_TABLE)
    existing_columns = {
        item["name"] for item in sa.inspect(bind).get_columns(_WAITLIST_TABLE)
    }
    with op.batch_alter_table(_WAITLIST_TABLE) as batch:
        batch.drop_constraint(
            "uq_lista_oczekujacych_create_key_hash", type_="unique",
        )
        for name in _WAITLIST_CHECKS:
            batch.drop_constraint(name, type_="check")
        for name in (
            "attended_at",
            "demand_resource_kind",
            "demand_reason_code",
            "create_request_fingerprint",
            "create_key_hash",
        ):
            if name in existing_columns:
                batch.drop_column(name)
