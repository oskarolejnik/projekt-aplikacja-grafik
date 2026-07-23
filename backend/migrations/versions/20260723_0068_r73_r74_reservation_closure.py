"""R7.3/R7.4: CRM governance and explicit reservation recommendations.

The migration is deliberately non-destructive.  CRM merges are logical edges,
consent events are append-only, and recommendation reviews contain aggregates
only.  Existing installations created with ``Base.metadata.create_all`` may
already contain the complete tables, so a complete matching table is adopted;
partial tables fail closed.

Revision ID: 0068_reservation_closure
Revises: 0067_rcp_geofencing
"""
from __future__ import annotations

import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0068_reservation_closure"
down_revision: Union[str, None] = "0067_rcp_geofencing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_PUBLIC_CONSENT_TABLE = "rezerwacje_zgody_publiczne"
_PUBLIC_SUBJECT_COLUMN = (
    "subject_hash", sa.String(length=64), True, None,
)
_PUBLIC_SUBJECT_INDEX = "ix_rezerwacje_zgody_publiczne_subject_hash"

_TABLE_COLUMNS = {
    "crm_consent_events": (
        ("id", sa.Integer(), False, None),
        ("subject_hash", sa.String(64), False, None),
        ("purpose", sa.String(32), False, "marketing"),
        ("decision", sa.String(16), False, None),
        ("document_version", sa.String(64), False, None),
        ("source", sa.String(32), False, None),
        ("captured_at", sa.DateTime(), False, None),
        ("termin_id", sa.Integer(), True, None),
        ("waitlist_id", sa.Integer(), True, None),
        ("actor_user_id", sa.Integer(), True, None),
        ("actor_login", sa.String(64), True, None),
        ("event_key_hash", sa.String(64), True, None),
        ("request_fingerprint", sa.String(64), False, None),
        ("created_at", sa.DateTime(), False, None),
    ),
    "crm_guest_merges": (
        ("id", sa.Integer(), False, None),
        ("source_hash", sa.String(64), False, None),
        ("target_hash", sa.String(64), False, None),
        ("source_reservation_id", sa.Integer(), True, None),
        ("target_reservation_id", sa.Integer(), True, None),
        ("evidence", sa.JSON(), False, None),
        ("reason_code", sa.String(32), False, None),
        ("status", sa.String(16), False, "active"),
        ("version", sa.Integer(), False, "1"),
        ("create_key_hash", sa.String(64), False, None),
        ("revert_key_hash", sa.String(64), True, None),
        ("created_by_user_id", sa.Integer(), True, None),
        ("created_by_login", sa.String(64), True, None),
        ("created_at", sa.DateTime(), False, None),
        ("reverted_by_user_id", sa.Integer(), True, None),
        ("reverted_by_login", sa.String(64), True, None),
        ("reverted_at", sa.DateTime(), True, None),
    ),
    "reservation_recommendation_reviews": (
        ("id", sa.Integer(), False, None),
        ("recommendation_hash", sa.String(64), False, None),
        ("simulation_hash", sa.String(64), False, None),
        ("kind", sa.String(32), False, "turn_time"),
        ("service_id", sa.Integer(), False, None),
        ("segment", sa.String(8), False, None),
        ("period_start", sa.Date(), False, None),
        ("period_end", sa.Date(), False, None),
        ("recommendation", sa.JSON(), False, None),
        ("simulation", sa.JSON(), False, None),
        ("status", sa.String(16), False, "simulated"),
        ("simulated_by_user_id", sa.Integer(), True, None),
        ("simulated_by_login", sa.String(64), True, None),
        ("created_at", sa.DateTime(), False, None),
        ("decision_reason", sa.String(64), True, None),
        ("decision_key_hash", sa.String(64), True, None),
        ("decision_fingerprint", sa.String(64), True, None),
        ("decided_by_user_id", sa.Integer(), True, None),
        ("decided_by_login", sa.String(64), True, None),
        ("decided_at", sa.DateTime(), True, None),
    ),
}
_TABLES = {
    table: {column[0] for column in columns}
    for table, columns in _TABLE_COLUMNS.items()
}
_TABLE_CHECKS = {
    "crm_consent_events": {
        "ck_crm_consent_events_subject_hash": "length(subject_hash) = 64",
        "ck_crm_consent_events_purpose": "purpose = 'marketing'",
        "ck_crm_consent_events_decision": (
            "decision IN ('grant', 'decline', 'withdraw')"
        ),
        "ck_crm_consent_events_source": (
            "source IN ('operator_phone', 'operator_in_person', "
            "'operator_email', 'import')"
        ),
        "ck_crm_consent_events_document_version": (
            "length(trim(document_version)) > 0"
        ),
        "ck_crm_consent_events_event_key_hash": (
            "event_key_hash IS NULL OR length(event_key_hash) = 64"
        ),
        "ck_crm_consent_events_request_fingerprint": (
            "length(request_fingerprint) = 64"
        ),
    },
    "crm_guest_merges": {
        "ck_crm_guest_merges_hashes": (
            "length(source_hash) = 64 AND length(target_hash) = 64"
        ),
        "ck_crm_guest_merges_distinct": "source_hash <> target_hash",
        "ck_crm_guest_merges_status": "status IN ('active', 'reverted')",
        "ck_crm_guest_merges_reason_code": (
            "reason_code IN ('duplicate_confirmed', 'operator_correction')"
        ),
        "ck_crm_guest_merges_version": "version >= 1",
        "ck_crm_guest_merges_create_key_hash": (
            "length(create_key_hash) = 64"
        ),
        "ck_crm_guest_merges_revert_key_hash": (
            "revert_key_hash IS NULL OR length(revert_key_hash) = 64"
        ),
    },
    "reservation_recommendation_reviews": {
        "ck_reservation_recommendation_reviews_hashes": (
            "length(recommendation_hash) = 64 AND "
            "length(simulation_hash) = 64"
        ),
        "ck_reservation_recommendation_reviews_kind": "kind = 'turn_time'",
        "ck_reservation_recommendation_reviews_segment": (
            "segment IN ('1-2', '3-4', '5+')"
        ),
        "ck_reservation_recommendation_reviews_status": (
            "status IN ('simulated', 'accepted', 'rejected')"
        ),
        "ck_reservation_recommendation_reviews_period": (
            "period_end >= period_start"
        ),
        "ck_reservation_recommendation_reviews_decision_key": (
            "decision_key_hash IS NULL OR length(decision_key_hash) = 64"
        ),
        "ck_reservation_recommendation_reviews_decision_fingerprint": (
            "decision_fingerprint IS NULL OR "
            "length(decision_fingerprint) = 64"
        ),
    },
}
_TABLE_UNIQUES = {
    "crm_consent_events": {
        "uq_crm_consent_events_event_key_hash": ("event_key_hash",),
    },
    "crm_guest_merges": {
        "uq_crm_guest_merges_create_key_hash": ("create_key_hash",),
        "uq_crm_guest_merges_revert_key_hash": ("revert_key_hash",),
    },
    "reservation_recommendation_reviews": {
        "uq_reservation_recommendation_reviews_recommendation_hash": (
            "recommendation_hash",
        ),
        "uq_reservation_recommendation_reviews_simulation_hash": (
            "simulation_hash",
        ),
        "uq_reservation_recommendation_reviews_decision_key_hash": (
            "decision_key_hash",
        ),
    },
}
_TABLE_INDEXES = {
    "crm_consent_events": {
        "ix_crm_consent_events_subject_captured": (
            ("subject_hash", "captured_at"), False, None,
        ),
    },
    "crm_guest_merges": {
        "uq_crm_guest_merges_active_source": (
            ("source_hash",), True, "status = 'active'",
        ),
        "ix_crm_guest_merges_target_status": (
            ("target_hash", "status"), False, None,
        ),
    },
    "reservation_recommendation_reviews": {
        "ix_reservation_recommendation_reviews_service_created": (
            ("service_id", "created_at"), False, None,
        ),
    },
}
_TABLE_FOREIGN_KEYS = {
    "crm_consent_events": {
        (("termin_id",), "terminy", ("id",), "SET NULL"),
        (("waitlist_id",), "lista_oczekujacych", ("id",), "SET NULL"),
        (("actor_user_id",), "users", ("id",), "SET NULL"),
    },
    "crm_guest_merges": {
        (("source_reservation_id",), "terminy", ("id",), "SET NULL"),
        (("target_reservation_id",), "terminy", ("id",), "SET NULL"),
        (("created_by_user_id",), "users", ("id",), "SET NULL"),
        (("reverted_by_user_id",), "users", ("id",), "SET NULL"),
    },
    "reservation_recommendation_reviews": {
        (("service_id",), "godziny_otwarcia", ("id",), "RESTRICT"),
        (("simulated_by_user_id",), "users", ("id",), "SET NULL"),
        (("decided_by_user_id",), "users", ("id",), "SET NULL"),
    },
}
_POSTGRES_MEMBERSHIP_CHECKS = {
    "ck_crm_consent_events_decision",
    "ck_crm_consent_events_source",
    "ck_crm_guest_merges_status",
    "ck_crm_guest_merges_reason_code",
    "ck_reservation_recommendation_reviews_segment",
    "ck_reservation_recommendation_reviews_status",
}


def _normalise_sql(value) -> str:
    normalized = re.sub(r'[\s"`\[\]]+', "", str(value or "")).lower()
    while normalized.startswith("(") and normalized.endswith(")"):
        normalized = normalized[1:-1]
    return normalized


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
    if first_literal < 0:
        return False
    expected_prefix = expected_shape[:first_literal]
    if not expected_prefix.endswith("in"):
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
            r"::\s*(?:character\s+varying|varchar|text|integer)"
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


def _predicate(index: dict) -> str | None:
    options = index.get("dialect_options") or {}
    where = " ".join(
        str(value)
        for key, value in options.items()
        if key.endswith("_where") and value is not None
    )
    return _normalise_sql(where) or None


def _index_shapes(inspector, table: str):
    return {
        item.get("name"): (
            tuple(item.get("column_names") or ()),
            bool(item.get("unique")),
            _predicate(item),
        )
        for item in inspector.get_indexes(table)
        if item.get("name")
    }


def _unique_shapes(inspector, table: str):
    expected = _TABLE_UNIQUES[table]
    uniques = {
        item.get("name"): tuple(item.get("column_names") or ())
        for item in inspector.get_unique_constraints(table)
        if item.get("name")
    }
    for name, (columns, unique, _where) in _index_shapes(
        inspector, table,
    ).items():
        if unique and name in expected:
            uniques.setdefault(name, columns)
    return uniques


def _validate_table_schema(inspector, table: str, dialect_name: str) -> None:
    columns = {
        item["name"]: item for item in inspector.get_columns(table)
    }
    expected_columns = _TABLE_COLUMNS[table]
    if set(columns) != _TABLES[table]:
        missing = sorted(_TABLES[table] - set(columns))
        extra = sorted(set(columns) - _TABLES[table])
        raise RuntimeError(
            f"Cannot adopt partial {table} schema; missing={missing}, extra={extra}"
        )
    for name, expected_type, nullable, default in expected_columns:
        actual = columns[name]
        if (
            not _type_matches(actual["type"], expected_type)
            or bool(actual.get("nullable")) != nullable
            or (
                name != "id"
                and not _default_matches(actual.get("default"), default)
            )
        ):
            raise RuntimeError(
                f"Cannot adopt incompatible {table}.{name} column contract"
            )
    pk = tuple(
        inspector.get_pk_constraint(table).get("constrained_columns") or ()
    )
    if pk != ("id",):
        raise RuntimeError(f"Cannot adopt incompatible {table} primary key")
    indexes = _index_shapes(inspector, table)
    semantic_indexes = {
        name: shape for name, shape in indexes.items()
        if not (
            name in _TABLE_UNIQUES[table]
            and shape[1]
            and shape[0] == _TABLE_UNIQUES[table][name]
        )
    }
    expected_indexes = {
        name: (columns, unique, _normalise_sql(where) or None)
        for name, (columns, unique, where) in _TABLE_INDEXES[table].items()
    }
    if semantic_indexes != expected_indexes:
        raise RuntimeError(f"Cannot adopt incompatible {table} indexes")
    if _unique_shapes(inspector, table) != _TABLE_UNIQUES[table]:
        raise RuntimeError(f"Cannot adopt incompatible {table} unique constraints")
    foreign_keys = {
        (
            tuple(item.get("constrained_columns") or ()),
            item.get("referred_table"),
            tuple(item.get("referred_columns") or ()),
            str((item.get("options") or {}).get("ondelete") or "").upper(),
        )
        for item in inspector.get_foreign_keys(table)
    }
    if foreign_keys != _TABLE_FOREIGN_KEYS[table]:
        raise RuntimeError(f"Cannot adopt incompatible {table} foreign keys")
    raw_checks = inspector.get_check_constraints(table)
    checks = {
        item.get("name"): item.get("sqltext")
        for item in raw_checks if item.get("name")
    }
    if (
        len(raw_checks) != len(_TABLE_CHECKS[table])
        or any(not item.get("name") for item in raw_checks)
        or set(checks) != set(_TABLE_CHECKS[table])
    ):
        raise RuntimeError(f"Cannot adopt incompatible {table} check constraints")
    for name, expected in _TABLE_CHECKS[table].items():
        if not _check_matches(name, checks[name], expected, dialect_name):
            raise RuntimeError(f"Cannot adopt incompatible {table} check {name}")


def _validate_adopted_schema(bind) -> bool:
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    present = set(_TABLES) & tables
    public_columns = {
        item["name"]: item
        for item in inspector.get_columns(_PUBLIC_CONSENT_TABLE)
    }
    subject_present = _PUBLIC_SUBJECT_COLUMN[0] in public_columns
    public_indexes = {
        item.get("name"): item
        for item in inspector.get_indexes(_PUBLIC_CONSENT_TABLE)
        if item.get("name")
    }
    subject_index_present = _PUBLIC_SUBJECT_INDEX in public_indexes

    if not present and not subject_present and not subject_index_present:
        return False
    if present != set(_TABLES) or not subject_present or not subject_index_present:
        raise RuntimeError(
            "R68_PARTIAL_ADOPTION: tables, frozen consent identity and index "
            "must be adopted together"
        )

    name, expected_type, nullable, default = _PUBLIC_SUBJECT_COLUMN
    actual = public_columns[name]
    if (
        not _type_matches(actual["type"], expected_type)
        or bool(actual.get("nullable")) != nullable
        or not _default_matches(actual.get("default"), default)
    ):
        raise RuntimeError(
            "R68_PARTIAL_ADOPTION: incompatible frozen consent identity column"
        )
    subject_index = public_indexes[_PUBLIC_SUBJECT_INDEX]
    if (
        tuple(subject_index.get("column_names") or ()) != (name,)
        or bool(subject_index.get("unique"))
        or _predicate(subject_index) is not None
    ):
        raise RuntimeError(
            "R68_PARTIAL_ADOPTION: incompatible frozen consent identity index"
        )

    for table in _TABLES:
        _validate_table_schema(inspector, table, bind.dialect.name)
    return True


def _create_consent_events() -> None:
    op.create_table(
        "crm_consent_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subject_hash", sa.String(64), nullable=False),
        sa.Column(
            "purpose", sa.String(32), nullable=False,
            server_default=sa.text("'marketing'"),
        ),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("document_version", sa.String(64), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("captured_at", sa.DateTime(), nullable=False),
        sa.Column(
            "termin_id", sa.Integer(),
            sa.ForeignKey("terminy.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "waitlist_id", sa.Integer(),
            sa.ForeignKey("lista_oczekujacych.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "actor_user_id", sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("actor_login", sa.String(64), nullable=True),
        sa.Column("event_key_hash", sa.String(64), nullable=True),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "length(subject_hash) = 64",
            name="ck_crm_consent_events_subject_hash",
        ),
        sa.CheckConstraint(
            "purpose = 'marketing'",
            name="ck_crm_consent_events_purpose",
        ),
        sa.CheckConstraint(
            "decision IN ('grant', 'decline', 'withdraw')",
            name="ck_crm_consent_events_decision",
        ),
        sa.CheckConstraint(
            "source IN ('operator_phone', 'operator_in_person', "
            "'operator_email', 'import')",
            name="ck_crm_consent_events_source",
        ),
        sa.CheckConstraint(
            "length(trim(document_version)) > 0",
            name="ck_crm_consent_events_document_version",
        ),
        sa.CheckConstraint(
            "event_key_hash IS NULL OR length(event_key_hash) = 64",
            name="ck_crm_consent_events_event_key_hash",
        ),
        sa.CheckConstraint(
            "length(request_fingerprint) = 64",
            name="ck_crm_consent_events_request_fingerprint",
        ),
        sa.UniqueConstraint(
            "event_key_hash", name="uq_crm_consent_events_event_key_hash",
        ),
    )
    op.create_index(
        "ix_crm_consent_events_subject_captured",
        "crm_consent_events",
        ["subject_hash", "captured_at"],
    )


def _create_guest_merges() -> None:
    op.create_table(
        "crm_guest_merges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("target_hash", sa.String(64), nullable=False),
        sa.Column(
            "source_reservation_id", sa.Integer(),
            sa.ForeignKey("terminy.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "target_reservation_id", sa.Integer(),
            sa.ForeignKey("terminy.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("reason_code", sa.String(32), nullable=False),
        sa.Column(
            "status", sa.String(16), nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("create_key_hash", sa.String(64), nullable=False),
        sa.Column("revert_key_hash", sa.String(64), nullable=True),
        sa.Column(
            "created_by_user_id", sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("created_by_login", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column(
            "reverted_by_user_id", sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("reverted_by_login", sa.String(64), nullable=True),
        sa.Column("reverted_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "length(source_hash) = 64 AND length(target_hash) = 64",
            name="ck_crm_guest_merges_hashes",
        ),
        sa.CheckConstraint(
            "source_hash <> target_hash",
            name="ck_crm_guest_merges_distinct",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'reverted')",
            name="ck_crm_guest_merges_status",
        ),
        sa.CheckConstraint(
            "reason_code IN ('duplicate_confirmed', 'operator_correction')",
            name="ck_crm_guest_merges_reason_code",
        ),
        sa.CheckConstraint(
            "version >= 1",
            name="ck_crm_guest_merges_version",
        ),
        sa.CheckConstraint(
            "length(create_key_hash) = 64",
            name="ck_crm_guest_merges_create_key_hash",
        ),
        sa.CheckConstraint(
            "revert_key_hash IS NULL OR length(revert_key_hash) = 64",
            name="ck_crm_guest_merges_revert_key_hash",
        ),
        sa.UniqueConstraint(
            "create_key_hash", name="uq_crm_guest_merges_create_key_hash",
        ),
        sa.UniqueConstraint(
            "revert_key_hash", name="uq_crm_guest_merges_revert_key_hash",
        ),
    )
    op.create_index(
        "uq_crm_guest_merges_active_source",
        "crm_guest_merges",
        ["source_hash"],
        unique=True,
        sqlite_where=sa.text("status = 'active'"),
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ix_crm_guest_merges_target_status",
        "crm_guest_merges",
        ["target_hash", "status"],
    )


def _create_recommendation_reviews() -> None:
    op.create_table(
        "reservation_recommendation_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("recommendation_hash", sa.String(64), nullable=False),
        sa.Column("simulation_hash", sa.String(64), nullable=False),
        sa.Column(
            "kind", sa.String(32), nullable=False,
            server_default=sa.text("'turn_time'"),
        ),
        sa.Column(
            "service_id", sa.Integer(),
            sa.ForeignKey("godziny_otwarcia.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("segment", sa.String(8), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("recommendation", sa.JSON(), nullable=False),
        sa.Column("simulation", sa.JSON(), nullable=False),
        sa.Column(
            "status", sa.String(16), nullable=False,
            server_default=sa.text("'simulated'"),
        ),
        sa.Column(
            "simulated_by_user_id", sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("simulated_by_login", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("decision_reason", sa.String(64), nullable=True),
        sa.Column("decision_key_hash", sa.String(64), nullable=True),
        sa.Column("decision_fingerprint", sa.String(64), nullable=True),
        sa.Column(
            "decided_by_user_id", sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("decided_by_login", sa.String(64), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "length(recommendation_hash) = 64 AND length(simulation_hash) = 64",
            name="ck_reservation_recommendation_reviews_hashes",
        ),
        sa.CheckConstraint(
            "kind = 'turn_time'",
            name="ck_reservation_recommendation_reviews_kind",
        ),
        sa.CheckConstraint(
            "segment IN ('1-2', '3-4', '5+')",
            name="ck_reservation_recommendation_reviews_segment",
        ),
        sa.CheckConstraint(
            "status IN ('simulated', 'accepted', 'rejected')",
            name="ck_reservation_recommendation_reviews_status",
        ),
        sa.CheckConstraint(
            "period_end >= period_start",
            name="ck_reservation_recommendation_reviews_period",
        ),
        sa.CheckConstraint(
            "decision_key_hash IS NULL OR length(decision_key_hash) = 64",
            name="ck_reservation_recommendation_reviews_decision_key",
        ),
        sa.CheckConstraint(
            "decision_fingerprint IS NULL OR length(decision_fingerprint) = 64",
            name="ck_reservation_recommendation_reviews_decision_fingerprint",
        ),
        sa.UniqueConstraint(
            "recommendation_hash",
            name="uq_reservation_recommendation_reviews_recommendation_hash",
        ),
        sa.UniqueConstraint(
            "simulation_hash",
            name="uq_reservation_recommendation_reviews_simulation_hash",
        ),
        sa.UniqueConstraint(
            "decision_key_hash",
            name="uq_reservation_recommendation_reviews_decision_key_hash",
        ),
    )
    op.create_index(
        "ix_reservation_recommendation_reviews_service_created",
        "reservation_recommendation_reviews",
        ["service_id", "created_at"],
    )


def upgrade() -> None:
    bind = op.get_bind()
    adopted = _validate_adopted_schema(bind)
    if adopted:
        return

    op.add_column(
        _PUBLIC_CONSENT_TABLE,
        sa.Column(
            _PUBLIC_SUBJECT_COLUMN[0],
            _PUBLIC_SUBJECT_COLUMN[1],
            nullable=_PUBLIC_SUBJECT_COLUMN[2],
        ),
    )
    op.create_index(
        _PUBLIC_SUBJECT_INDEX,
        _PUBLIC_CONSENT_TABLE,
        [_PUBLIC_SUBJECT_COLUMN[0]],
    )
    _create_consent_events()
    _create_guest_merges()
    _create_recommendation_reviews()
    _validate_adopted_schema(bind)


def downgrade() -> None:
    bind = op.get_bind()
    _validate_adopted_schema(bind)
    inspector = sa.inspect(bind)
    present = [
        table for table in reversed(tuple(_TABLES))
        if table in inspector.get_table_names()
    ]
    # Validate every table before the first DDL statement.  SQLite does not
    # reliably roll back all schema changes, so a late refusal could otherwise
    # leave a partially downgraded database while Alembic still reports 0068.
    for table in present:
        count = bind.execute(
            sa.text(f'SELECT COUNT(*) FROM "{table}"')
        ).scalar_one()
        if count:
            raise RuntimeError(
                f"Refusing to drop non-empty R7 governance table {table}"
            )
    frozen_subjects = bind.execute(sa.text(
        f'SELECT COUNT(*) FROM "{_PUBLIC_CONSENT_TABLE}" '
        f'WHERE "{_PUBLIC_SUBJECT_COLUMN[0]}" IS NOT NULL'
    )).scalar_one()
    if frozen_subjects:
        raise RuntimeError(
            "Refusing to drop non-empty frozen public consent identities"
        )
    for table in present:
        op.drop_table(table)
    op.drop_index(_PUBLIC_SUBJECT_INDEX, table_name=_PUBLIC_CONSENT_TABLE)
    with op.batch_alter_table(
        _PUBLIC_CONSENT_TABLE,
        recreate="always" if bind.dialect.name == "sqlite" else "auto",
    ) as batch:
        batch.drop_column(_PUBLIC_SUBJECT_COLUMN[0])
