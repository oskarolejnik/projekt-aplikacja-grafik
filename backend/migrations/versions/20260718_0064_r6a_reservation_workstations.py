"""R6a registered reservation workstations and named PIN sessions.

Revision ID: 0064_r6a_reservation_workstations
Revises: 0063_r5c_reservation_payments
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0064_r6a_reservation_workstations"
down_revision: Union[str, None] = "0063_r5c_reservation_payments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reservation_operator_credentials",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("pin_hash", sa.String(length=255), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "failed_attempts >= 0",
            name="ck_reservation_operator_credential_attempts",
        ),
        sa.CheckConstraint(
            "version >= 1",
            name="ck_reservation_operator_credential_version",
        ),
    )

    op.create_table(
        "reservation_workstations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=96), nullable=False),
        sa.Column("secret_hash", sa.String(length=64), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "idle_timeout_seconds", sa.Integer(), nullable=False, server_default="300",
        ),
        sa.Column("session_epoch", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "secret_hash", name="uq_reservation_workstation_secret_hash",
        ),
        sa.CheckConstraint("length(id) = 36", name="ck_reservation_workstation_id"),
        sa.CheckConstraint(
            "length(secret_hash) = 64",
            name="ck_reservation_workstation_secret_hash",
        ),
        sa.CheckConstraint(
            "length(trim(name)) >= 1 AND length(name) <= 96",
            name="ck_reservation_workstation_name",
        ),
        sa.CheckConstraint(
            "idle_timeout_seconds >= 60 AND idle_timeout_seconds <= 3600",
            name="ck_reservation_workstation_idle_timeout",
        ),
        sa.CheckConstraint(
            "session_epoch >= 0",
            name="ck_reservation_workstation_epoch",
        ),
        sa.CheckConstraint(
            "failed_attempts >= 0",
            name="ck_reservation_workstation_attempts",
        ),
    )

    op.create_table(
        "reservation_operator_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "workstation_id",
            sa.String(length=36),
            sa.ForeignKey("reservation_workstations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor_login", sa.String(length=64), nullable=False),
        sa.Column("station_epoch", sa.Integer(), nullable=False),
        sa.Column("credential_version", sa.Integer(), nullable=False),
        sa.Column("authorization_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("reauth_grant_hash", sa.String(length=64), nullable=True),
        sa.Column("reauth_scope", sa.String(length=32), nullable=True),
        sa.Column("reauth_expires_at", sa.DateTime(), nullable=True),
        sa.Column("locked_at", sa.DateTime(), nullable=True),
        sa.Column("lock_reason", sa.String(length=32), nullable=True),
        sa.UniqueConstraint(
            "token_hash", name="uq_reservation_operator_session_token_hash",
        ),
        sa.CheckConstraint(
            "length(id) = 36", name="ck_reservation_operator_session_id",
        ),
        sa.CheckConstraint(
            "station_epoch >= 1", name="ck_reservation_operator_session_epoch",
        ),
        sa.CheckConstraint(
            "credential_version >= 1",
            name="ck_reservation_operator_session_credential_version",
        ),
        sa.CheckConstraint(
            "length(authorization_fingerprint) = 64",
            name="ck_reservation_operator_session_fingerprint",
        ),
        sa.CheckConstraint(
            "length(token_hash) = 64 AND length(csrf_hash) = 64",
            name="ck_reservation_operator_session_secret_hashes",
        ),
        sa.CheckConstraint(
            "(reauth_grant_hash IS NULL AND reauth_scope IS NULL "
            "AND reauth_expires_at IS NULL) OR "
            "(length(reauth_grant_hash) = 64 "
            "AND reauth_scope = 'reservation_override' "
            "AND reauth_expires_at IS NOT NULL)",
            name="ck_reservation_operator_session_reauth_grant",
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_reservation_operator_session_expiry",
        ),
    )
    op.create_index(
        "ix_reservation_operator_session_station_state",
        "reservation_operator_sessions",
        ["workstation_id", "locked_at", "expires_at"],
    )
    op.create_index(
        "ix_reservation_operator_session_user_created",
        "reservation_operator_sessions",
        ["user_id", "created_at"],
    )

    op.create_table(
        "reservation_workstation_audit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column(
            "workstation_id",
            sa.String(length=36),
            sa.ForeignKey("reservation_workstations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "session_id",
            sa.String(length=36),
            sa.ForeignKey("reservation_operator_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("actor_login", sa.String(length=64), nullable=True),
        sa.Column("event", sa.String(length=24), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.CheckConstraint(
            "event IN ('register', 'unlock', 'lock', 'switch', 'timeout', "
            "'revoke', 'pin_set', 'pin_revoke', 'authz_revoke', 'reauth', "
            "'reauth_use')",
            name="ck_reservation_workstation_audit_event",
        ),
        sa.CheckConstraint(
            "outcome IN ('success', 'failure', 'blocked')",
            name="ck_reservation_workstation_audit_outcome",
        ),
    )
    op.create_index(
        "ix_reservation_workstation_audit_station_ts",
        "reservation_workstation_audit",
        ["workstation_id", "ts"],
    )
    op.create_index(
        "ix_reservation_workstation_audit_user_ts",
        "reservation_workstation_audit",
        ["user_id", "ts"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    for table_name in (
        "reservation_workstation_audit",
        "reservation_operator_sessions",
        "reservation_workstations",
        "reservation_operator_credentials",
    ):
        if connection.execute(
            sa.text(f"SELECT 1 FROM {table_name} LIMIT 1")
        ).first() is not None:
            raise RuntimeError(
                "R6A_DOWNGRADE_REFUSED: usuń lub zarchiwizuj konfigurację i audyt "
                "stanowisk przed downgrade."
            )

    op.drop_index(
        "ix_reservation_workstation_audit_user_ts",
        table_name="reservation_workstation_audit",
    )
    op.drop_index(
        "ix_reservation_workstation_audit_station_ts",
        table_name="reservation_workstation_audit",
    )
    op.drop_table("reservation_workstation_audit")
    op.drop_index(
        "ix_reservation_operator_session_user_created",
        table_name="reservation_operator_sessions",
    )
    op.drop_index(
        "ix_reservation_operator_session_station_state",
        table_name="reservation_operator_sessions",
    )
    op.drop_table("reservation_operator_sessions")
    op.drop_table("reservation_workstations")
    op.drop_table("reservation_operator_credentials")
