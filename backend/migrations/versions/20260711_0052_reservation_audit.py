"""Transakcyjny, pozbawiony PII audyt operacji na rezerwacjach.

Revision ID: 0052_reservation_audit
Revises: 0051_rezerwacje_atomic_ledger
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0052_reservation_audit"
down_revision: Union[str, None] = "0051_rezerwacje_atomic_ledger"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reservation_audit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reservation_ref", sa.String(length=64), nullable=False),
        sa.Column(
            "termin_id",
            sa.Integer(),
            sa.ForeignKey("terminy.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("actor_kind", sa.String(length=16), nullable=False),
        sa.Column(
            "actor_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("actor_login", sa.String(length=64), nullable=True),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=True),
        sa.Column("diff", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "length(reservation_ref) = 64",
            name="ck_reservation_audit_ref",
        ),
        sa.CheckConstraint(
            "actor_kind IN ('user', 'guest', 'system', 'migration')",
            name="ck_reservation_audit_actor_kind",
        ),
        sa.CheckConstraint(
            "action IN ('create', 'edit', 'cancel', 'delete', 'status', "
            "'host', 'assign', 'override')",
            name="ck_reservation_audit_action",
        ),
        sa.CheckConstraint(
            "reason IS NULL OR reason IN ("
            "'guest_request', 'operator_correction', 'capacity_override', "
            "'pacing_override', 'table_override', 'system_automation', "
            "'import_reconciliation', 'other')",
            name="ck_reservation_audit_reason",
        ),
        sa.CheckConstraint(
            "actor_kind != 'user' OR "
            "(actor_login IS NOT NULL AND length(trim(actor_login)) > 0)",
            name="ck_reservation_audit_user_actor",
        ),
        sa.CheckConstraint(
            "action != 'override' OR reason IS NOT NULL",
            name="ck_reservation_audit_override_reason",
        ),
    )
    op.create_index(
        "ix_reservation_audit_ref_created",
        "reservation_audit",
        ["reservation_ref", "created_at"],
    )
    op.create_index(
        "ix_reservation_audit_termin_created",
        "reservation_audit",
        ["termin_id", "created_at"],
    )
    op.create_index(
        "ix_reservation_audit_actor_created",
        "reservation_audit",
        ["actor_user_id", "created_at"],
    )
    # Starsze operacje RODO zapisywały telefon/e-mail/nazwisko w ``audit_log.zasob``.
    # Nie da się bezpiecznie zachować ich korelacji bez sekretu aplikacji, więc usuwamy
    # historyczny identyfikator. Nowy kod zapisuje stabilny HMAC ``guest_ref:*``.
    op.execute(
        sa.text(
            "UPDATE audit_log SET zasob = '[redacted]' "
            "WHERE akcja IN ('rodo_eksport_gosc', 'rodo_anonimizuj_gosc') "
            "AND zasob IS NOT NULL AND zasob <> '[redacted]' "
            "AND zasob NOT LIKE 'guest_ref:%'"
        )
    )


def downgrade() -> None:
    op.drop_index(
        "ix_reservation_audit_actor_created", table_name="reservation_audit",
    )
    op.drop_index(
        "ix_reservation_audit_termin_created", table_name="reservation_audit",
    )
    op.drop_index(
        "ix_reservation_audit_ref_created", table_name="reservation_audit",
    )
    op.drop_table("reservation_audit")
