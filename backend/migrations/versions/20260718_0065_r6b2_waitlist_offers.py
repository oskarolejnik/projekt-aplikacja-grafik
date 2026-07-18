"""R6b.2 atomic waitlist offer lifecycle.

Revision ID: 0065_r6b2_waitlist_offers
Revises: 0064_r6a_reservation_workstations
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0065_r6b2_waitlist_offers"
down_revision: Union[str, None] = "0064_r6a_reservation_workstations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_CHECKS = {
    "ck_lista_oczekujacych_status": (
        "status IN ('oczekuje', 'zaoferowano', 'zaakceptowano', "
        "'wygasla', 'anulowano')"
    ),
    "ck_lista_oczekujacych_priorytet": "priorytet >= 0 AND priorytet <= 9",
    "ck_lista_oczekujacych_offer_version": "offer_version >= 0",
    "ck_lista_oczekujacych_offer_key_hash": (
        "offer_key_hash IS NULL OR length(offer_key_hash) = 64"
    ),
    "ck_lista_oczekujacych_offer_fingerprint": (
        "offer_request_fingerprint IS NULL OR "
        "length(offer_request_fingerprint) = 64"
    ),
    "ck_lista_oczekujacych_offer_kanal": (
        "offer_kanal IS NULL OR offer_kanal IN ('online', 'wewnetrzna')"
    ),
}
_INDEX_NAME = "ix_lista_oczekujacych_data_status_priorytet"
_INDEX_COLUMNS = ["data", "status", "priorytet", "utworzono_at", "id"]
_CONTEXT_TABLE = "waitlist_offer_override_context"
_CONTEXT_COLUMNS = (
    ("id", sa.Integer(), False),
    ("waitlist_id", sa.Integer(), False),
    ("offer_version", sa.Integer(), False),
    ("reason_code", sa.String(length=32), False),
    ("note", sa.String(length=2048), True),
    ("created_at", sa.DateTime(), False),
)
_CONTEXT_CHECKS = {
    "ck_waitlist_offer_override_context_version": "offer_version > 0",
    "ck_waitlist_offer_override_context_reason_code": (
        "reason_code IN ("
        "'guest_request', 'large_group_confirmed', 'event_exception', "
        "'operational_decision', 'walk_in', 'other', 'legacy_confirmation')"
    ),
}
_CONTEXT_UNIQUES = {
    "uq_waitlist_offer_override_context_generation": (
        "waitlist_id", "offer_version",
    ),
}
_CONTEXT_INDEXES = {
    "ix_waitlist_offer_override_context_waitlist_created": (
        ("waitlist_id", "created_at"), False,
    ),
}
_CONTEXT_FKS = {
    (("waitlist_id",), "lista_oczekujacych", ("id",), "CASCADE"),
}
_POSTGRES_MEMBERSHIP_CHECKS = {
    "ck_lista_oczekujacych_status",
    "ck_lista_oczekujacych_offer_kanal",
    "ck_waitlist_offer_override_context_reason_code",
}
_ADDITIONS = (
    ("priorytet", sa.Integer(), False, "0"),
    ("offer_version", sa.Integer(), False, "0"),
    ("offer_auto_przydzielony", sa.Boolean(), True, None),
    ("offer_override_authorized", sa.Boolean(), True, None),
    ("offer_override_note", sa.String(length=2048), True, None),
    ("offer_sala_id", sa.Integer(), True, None),
    ("offer_kanal", sa.String(length=16), True, None),
    ("offer_key_hash", sa.String(length=64), True, None),
    ("offer_request_fingerprint", sa.String(length=64), True, None),
    ("zaoferowano_at", sa.DateTime(), True, None),
    ("oferta_wygasa_at", sa.DateTime(), True, None),
    ("zaakceptowano_at", sa.DateTime(), True, None),
    ("wygasla_at", sa.DateTime(), True, None),
    ("anulowano_at", sa.DateTime(), True, None),
)


def _column_names(bind) -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(bind).get_columns("lista_oczekujacych")
    }


def _check_names(bind) -> set[str]:
    return {
        constraint.get("name")
        for constraint in sa.inspect(bind).get_check_constraints(
            "lista_oczekujacych"
        )
        if constraint.get("name")
    }


def _index_names(bind) -> set[str]:
    return {
        index.get("name")
        for index in sa.inspect(bind).get_indexes("lista_oczekujacych")
        if index.get("name")
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
        expected_prefix[:-len("in")] + "=anyarray" + expected_shape[first_literal:]
    )
    return actual_shape in {expected_shape, pg_any_shape}


def _postgres_pk_generator_is_valid(column) -> bool:
    """Accept the two PostgreSQL generators emitted by supported SQLAlchemy.

    ``SERIAL`` reflects as a ``nextval('…'::regclass)`` default, while modern
    identity columns expose an ``identity`` mapping.  A bare integer primary
    key is not self-generating on PostgreSQL and must fail closed during
    adoption, even though SQLite gives the equivalent declaration rowid
    semantics automatically.
    """
    if isinstance(column.get("identity"), dict):
        return True
    default = re.sub(r"\s+", "", str(column.get("default") or "")).casefold()
    return bool(re.fullmatch(
        r"nextval\('(?:[^']|'')+'::regclass\)",
        default,
    ))


def _validate_context_schema(inspector, dialect_name: str) -> None:
    columns = {item["name"]: item for item in inspector.get_columns(_CONTEXT_TABLE)}
    if set(columns) != {item[0] for item in _CONTEXT_COLUMNS}:
        raise RuntimeError("R6B2_PARTIAL_ADOPTION: incompatible override context columns")
    for name, expected_type, nullable in _CONTEXT_COLUMNS:
        actual = columns[name]
        type_ok = isinstance(actual["type"], type(expected_type))
        if isinstance(expected_type, sa.String):
            type_ok = type_ok and getattr(actual["type"], "length", None) == getattr(
                expected_type, "length", None,
            )
        if not type_ok or bool(actual.get("nullable")) != nullable:
            raise RuntimeError(
                f"R6B2_PARTIAL_ADOPTION: incompatible override context column {name}"
            )
    pk = tuple(
        inspector.get_pk_constraint(_CONTEXT_TABLE).get("constrained_columns") or ()
    )
    if pk != ("id",):
        raise RuntimeError("R6B2_PARTIAL_ADOPTION: incompatible override context PK")
    if (
        dialect_name == "postgresql"
        and not _postgres_pk_generator_is_valid(columns["id"])
    ):
        raise RuntimeError(
            "R6B2_PARTIAL_ADOPTION: override context PK has no generator"
        )

    raw_indexes = inspector.get_indexes(_CONTEXT_TABLE)
    indexes = {
        item.get("name"): (
            tuple(item.get("column_names") or ()), bool(item.get("unique")),
        )
        for item in raw_indexes if item.get("name")
    }
    for name, expected in _CONTEXT_INDEXES.items():
        if indexes.get(name) != expected:
            raise RuntimeError(
                f"R6B2_PARTIAL_ADOPTION: incompatible override context index {name}"
            )

    raw_uniques = inspector.get_unique_constraints(_CONTEXT_TABLE)
    uniques = {
        item.get("name"): tuple(item.get("column_names") or ())
        for item in raw_uniques if item.get("name")
    }
    for name, (columns_, unique) in indexes.items():
        if unique:
            uniques.setdefault(name, columns_)
    if uniques != _CONTEXT_UNIQUES:
        raise RuntimeError("R6B2_PARTIAL_ADOPTION: incompatible override context UNIQUE")

    fks = {
        (
            tuple(item.get("constrained_columns") or ()),
            item.get("referred_table"),
            tuple(item.get("referred_columns") or ()),
            str((item.get("options") or {}).get("ondelete") or "").upper(),
        )
        for item in inspector.get_foreign_keys(_CONTEXT_TABLE)
    }
    if fks != _CONTEXT_FKS:
        raise RuntimeError("R6B2_PARTIAL_ADOPTION: incompatible override context FK")

    raw_checks = inspector.get_check_constraints(_CONTEXT_TABLE)
    checks = {
        item.get("name"): item.get("sqltext")
        for item in raw_checks if item.get("name")
    }
    if set(checks) != set(_CONTEXT_CHECKS):
        raise RuntimeError("R6B2_PARTIAL_ADOPTION: incompatible override context CHECK")
    for name, expected in _CONTEXT_CHECKS.items():
        if not _check_matches(name, checks[name], expected, dialect_name):
            raise RuntimeError(
                f"R6B2_PARTIAL_ADOPTION: incompatible override context check {name}"
            )


def _validate_adopted_schema(bind) -> None:
    inspector = sa.inspect(bind)
    context_exists = _CONTEXT_TABLE in set(inspector.get_table_names())
    columns = {
        column["name"]: column
        for column in inspector.get_columns("lista_oczekujacych")
    }
    expected_names = {item[0] for item in _ADDITIONS}
    present_names = expected_names & set(columns)
    if not present_names:
        conflicting_checks = _check_names(bind) & set(_CHECKS)
        if conflicting_checks or _INDEX_NAME in _index_names(bind):
            raise RuntimeError(
                "R6B2_PARTIAL_ADOPTION: constraints exist without lifecycle columns"
            )
        if context_exists:
            raise RuntimeError(
                "R6B2_PARTIAL_ADOPTION: override context exists without lifecycle columns"
            )
        return
    if present_names != expected_names:
        raise RuntimeError(
            "R6B2_PARTIAL_ADOPTION: only some lifecycle columns are present"
        )
    if not context_exists:
        raise RuntimeError(
            "R6B2_PARTIAL_ADOPTION: lifecycle columns exist without override context"
        )
    _validate_context_schema(inspector, bind.dialect.name)

    for name, expected_type, nullable, default in _ADDITIONS:
        column = columns[name]
        actual_type = column["type"]
        type_ok = isinstance(actual_type, type(expected_type))
        if isinstance(expected_type, sa.String):
            type_ok = type_ok and getattr(actual_type, "length", None) == getattr(
                expected_type, "length", None,
            )
        reflected_default = _normalise_sql(column.get("default"))
        expected_default = _normalise_sql(default)
        if expected_default:
            reflected_default = reflected_default.strip("()'")
        if (
            not type_ok
            or bool(column.get("nullable")) != nullable
            or reflected_default != expected_default
        ):
            raise RuntimeError(
                f"R6B2_PARTIAL_ADOPTION: incompatible column {name}"
            )

    dialect_name = bind.dialect.name
    checks = {
        item.get("name"): item.get("sqltext")
        for item in inspector.get_check_constraints("lista_oczekujacych")
        if item.get("name")
    }
    for name, expected_sql in _CHECKS.items():
        if not _check_matches(
            name, checks.get(name), expected_sql, dialect_name,
        ):
            raise RuntimeError(
                f"R6B2_PARTIAL_ADOPTION: incompatible check {name}"
            )

    indexes = {
        item.get("name"): item
        for item in inspector.get_indexes("lista_oczekujacych")
        if item.get("name")
    }
    index = indexes.get(_INDEX_NAME)
    if (
        index is None
        or list(index.get("column_names") or ()) != _INDEX_COLUMNS
        or bool(index.get("unique"))
    ):
        raise RuntimeError(
            f"R6B2_PARTIAL_ADOPTION: incompatible index {_INDEX_NAME}"
        )


def upgrade() -> None:
    bind = op.get_bind()
    _validate_adopted_schema(bind)
    existing = _column_names(bind)
    missing = [item for item in _ADDITIONS if item[0] not in existing]
    existing_checks = _check_names(bind)
    missing_checks = [
        (name, sql) for name, sql in _CHECKS.items()
        if name not in existing_checks
    ]
    if missing:
        # Map legacy labels before the SQLite table copy installs the new status
        # check. Columns and checks must be created in one copy: adding columns
        # after an inline legacy CHECK confuses SQLite's constraint reflection.
        op.execute(sa.text(
            "UPDATE lista_oczekujacych SET status='zaakceptowano' "
            "WHERE status='zrealizowany'"
        ))
        op.execute(sa.text(
            "UPDATE lista_oczekujacych SET status='anulowano' "
            "WHERE status='odwolany'"
        ))
        recreate = "always" if bind.dialect.name == "sqlite" else "auto"
        with op.batch_alter_table(
            "lista_oczekujacych", recreate=recreate,
        ) as batch:
            for name, column_type, nullable, default in missing:
                batch.add_column(sa.Column(
                    name,
                    column_type,
                    nullable=nullable,
                    server_default=default,
                ))
            for name, sql in missing_checks:
                batch.create_check_constraint(name, sql)

    # Backfill lifecycle timestamps after the new nullable columns exist.
    op.execute(sa.text(
        "UPDATE lista_oczekujacych SET "
        "zaakceptowano_at=COALESCE(zrealizowano_at, utworzono_at) "
        "WHERE status='zaakceptowano' AND zaakceptowano_at IS NULL"
    ))
    migration_now = datetime.now(timezone.utc).replace(tzinfo=None)
    op.execute(sa.text(
        "UPDATE lista_oczekujacych SET "
        "anulowano_at=COALESCE(utworzono_at, :migration_now) "
        "WHERE status='anulowano' AND anulowano_at IS NULL"
    ).bindparams(migration_now=migration_now))

    if _INDEX_NAME not in _index_names(bind):
        op.create_index(
            _INDEX_NAME,
            "lista_oczekujacych",
            _INDEX_COLUMNS,
        )
    if _CONTEXT_TABLE not in set(sa.inspect(bind).get_table_names()):
        op.create_table(
            _CONTEXT_TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "waitlist_id",
                sa.Integer(),
                sa.ForeignKey("lista_oczekujacych.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("offer_version", sa.Integer(), nullable=False),
            sa.Column("reason_code", sa.String(length=32), nullable=False),
            sa.Column("note", sa.String(length=2048), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.CheckConstraint(
                "offer_version > 0",
                name="ck_waitlist_offer_override_context_version",
            ),
            sa.CheckConstraint(
                "reason_code IN ("
                "'guest_request', 'large_group_confirmed', 'event_exception', "
                "'operational_decision', 'walk_in', 'other', 'legacy_confirmation')",
                name="ck_waitlist_offer_override_context_reason_code",
            ),
            sa.UniqueConstraint(
                "waitlist_id", "offer_version",
                name="uq_waitlist_offer_override_context_generation",
            ),
        )
        op.create_index(
            "ix_waitlist_offer_override_context_waitlist_created",
            _CONTEXT_TABLE,
            ["waitlist_id", "created_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _CONTEXT_TABLE in set(sa.inspect(bind).get_table_names()):
        context_lossy = bind.execute(sa.text(
            f"SELECT 1 FROM {_CONTEXT_TABLE} LIMIT 1"
        )).first()
        if context_lossy is not None:
            raise RuntimeError(
                "R6B2_DOWNGRADE_DATA_LOSS: istnieje historia autoryzacji ofert."
            )
    lossy = bind.execute(sa.text(
        "SELECT 1 FROM lista_oczekujacych WHERE "
        "status IN ('zaoferowano', 'wygasla') OR "
        "priorytet <> 0 OR offer_version <> 0 OR "
        "offer_auto_przydzielony IS NOT NULL OR "
        "offer_override_authorized IS NOT NULL OR "
        "offer_override_note IS NOT NULL OR "
        "offer_sala_id IS NOT NULL OR "
        "offer_kanal IS NOT NULL OR "
        "offer_key_hash IS NOT NULL OR offer_request_fingerprint IS NOT NULL OR "
        "zaoferowano_at IS NOT NULL OR oferta_wygasa_at IS NOT NULL OR "
        "wygasla_at IS NOT NULL OR "
        "(zaakceptowano_at IS NOT NULL AND "
        " zaakceptowano_at <> COALESCE(zrealizowano_at, utworzono_at)) OR "
        "(anulowano_at IS NOT NULL AND anulowano_at <> utworzono_at) LIMIT 1"
    )).first()
    if lossy is not None:
        raise RuntimeError(
            "R6B2_DOWNGRADE_DATA_LOSS: waitlista zawiera oferty, priorytety albo "
            "historię generacji, których starszy schemat nie potrafi zachować."
        )
    if _CONTEXT_TABLE in set(sa.inspect(bind).get_table_names()):
        op.drop_table(_CONTEXT_TABLE)
    check_names = _check_names(bind)
    with op.batch_alter_table("lista_oczekujacych") as batch:
        if _INDEX_NAME in _index_names(bind):
            batch.drop_index(_INDEX_NAME)
        for name in _CHECKS:
            if name in check_names:
                batch.drop_constraint(name, type_="check")

    op.execute(sa.text(
        "UPDATE lista_oczekujacych SET status='zrealizowany' "
        "WHERE status='zaakceptowano'"
    ))
    op.execute(sa.text(
        "UPDATE lista_oczekujacych SET status='odwolany' "
        "WHERE status IN ('wygasla', 'anulowano')"
    ))
    op.execute(sa.text(
        "UPDATE lista_oczekujacych SET status='oczekuje' "
        "WHERE status='zaoferowano'"
    ))

    existing = _column_names(bind)
    with op.batch_alter_table("lista_oczekujacych") as batch:
        for name in (
            "anulowano_at",
            "wygasla_at",
            "zaakceptowano_at",
            "oferta_wygasa_at",
            "zaoferowano_at",
            "offer_request_fingerprint",
            "offer_key_hash",
            "offer_override_authorized",
            "offer_override_note",
            "offer_auto_przydzielony",
            "offer_sala_id",
            "offer_kanal",
            "offer_version",
            "priorytet",
        ):
            if name in existing:
                batch.drop_column(name)
