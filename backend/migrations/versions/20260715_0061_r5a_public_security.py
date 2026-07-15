"""R5a public holds, hash-only management tokens, consent proofs and quotas.

Revision ID: 0061_r5a_public_security
Revises: 0060_r4_allocator_core
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0061_r5a_public_security"
down_revision: Union[str, None] = "0060_r4_allocator_core"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_CLAIM_OWNER_R5A = (
    "(termin_id IS NOT NULL AND waitlist_id IS NULL "
    "AND public_hold_id IS NULL AND expires_at IS NULL) OR "
    "(termin_id IS NULL AND waitlist_id IS NOT NULL "
    "AND public_hold_id IS NULL AND expires_at IS NOT NULL) OR "
    "(termin_id IS NULL AND waitlist_id IS NULL "
    "AND public_hold_id IS NOT NULL AND expires_at IS NOT NULL)"
)

_CLAIM_OWNER_R4 = (
    "(termin_id IS NOT NULL AND waitlist_id IS NULL AND expires_at IS NULL) OR "
    "(termin_id IS NULL AND waitlist_id IS NOT NULL AND expires_at IS NOT NULL)"
)


def upgrade() -> None:
    # Starsze waitlist holdy zapisywały expires_at jako lokalny czas naiwny. R5a
    # standaryzuje lifecycle na naive UTC; krótki, chwilowy hold bezpieczniej
    # zwolnić podczas wdrożenia niż zgadywać CET/CEST i ryzykować blokadę stołu.
    op.execute(sa.text(
        "DELETE FROM rezerwacje_stoliki_claims WHERE waitlist_id IS NOT NULL"
    ))
    op.execute(sa.text(
        "UPDATE lista_oczekujacych SET "
        "hold_stolik_id=NULL, hold_stoliki_dodatkowe=NULL, "
        "hold_godz_od=NULL, hold_godz_do=NULL, hold_bufor_min=NULL, hold_do=NULL "
        "WHERE hold_stolik_id IS NOT NULL OR hold_do IS NOT NULL"
    ))

    with op.batch_alter_table("lokal_config") as batch:
        batch.add_column(sa.Column(
            "rezerwacje_widget_v2", sa.Boolean(), nullable=False,
            server_default=sa.false(),
        ))
        batch.add_column(sa.Column(
            "rezerwacje_retencja_dni", sa.Integer(), nullable=False,
            server_default="365",
        ))
        batch.add_column(sa.Column(
            "rezerwacje_rodo_kontakt", sa.String(length=254), nullable=True,
        ))
        batch.add_column(sa.Column(
            "rezerwacje_rodo_adres", sa.String(length=256), nullable=True,
        ))
        batch.create_check_constraint(
            "ck_lokal_config_rezerwacje_retencja_dni",
            "rezerwacje_retencja_dni >= 30 AND rezerwacje_retencja_dni <= 3650",
        )

    op.create_table(
        "rezerwacje_publiczne_holdy",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("session_hash", sa.String(length=64), nullable=False),
        sa.Column("ip_hash", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("godz_od", sa.Time(), nullable=False),
        sa.Column("godz_do", sa.Time(), nullable=False),
        sa.Column("liczba_osob", sa.Integer(), nullable=False),
        sa.Column(
            "stolik_id", sa.Integer(),
            sa.ForeignKey("stoliki.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column("stoliki_dodatkowe", sa.JSON(), nullable=True),
        sa.Column("allocation_snapshot", sa.JSON(), nullable=False),
        sa.Column("bufor_min", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("released_at", sa.DateTime(), nullable=True),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "termin_id", sa.Integer(),
            sa.ForeignKey("terminy.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.UniqueConstraint(
            "token_hash", name="uq_rezerwacje_publiczne_holdy_token_hash",
        ),
        sa.CheckConstraint(
            "length(token_hash) = 64",
            name="ck_rezerwacje_publiczne_holdy_token_hash",
        ),
        sa.CheckConstraint(
            "length(session_hash) = 64",
            name="ck_rezerwacje_publiczne_holdy_session_hash",
        ),
        sa.CheckConstraint(
            "length(ip_hash) = 64",
            name="ck_rezerwacje_publiczne_holdy_ip_hash",
        ),
        sa.CheckConstraint(
            "state IN ('active', 'consumed', 'released', 'expired')",
            name="ck_rezerwacje_publiczne_holdy_state",
        ),
        sa.CheckConstraint(
            "liczba_osob > 0",
            name="ck_rezerwacje_publiczne_holdy_liczba_osob",
        ),
        sa.CheckConstraint(
            "bufor_min >= 0",
            name="ck_rezerwacje_publiczne_holdy_bufor_min",
        ),
        sa.CheckConstraint(
            "godz_do > godz_od",
            name="ck_rezerwacje_publiczne_holdy_interval",
        ),
        sa.CheckConstraint(
            "(state = 'active' AND released_at IS NULL AND consumed_at IS NULL "
            "AND termin_id IS NULL) OR "
            "(state IN ('released', 'expired') AND released_at IS NOT NULL "
            "AND consumed_at IS NULL AND termin_id IS NULL) OR "
            "(state = 'consumed' AND released_at IS NULL AND consumed_at IS NOT NULL)",
            name="ck_rezerwacje_publiczne_holdy_lifecycle",
        ),
    )
    op.create_index(
        "ix_rezerwacje_publiczne_holdy_session_state",
        "rezerwacje_publiczne_holdy", ["session_hash", "state", "expires_at"],
    )
    op.create_index(
        "ix_rezerwacje_publiczne_holdy_ip_state",
        "rezerwacje_publiczne_holdy", ["ip_hash", "state", "expires_at"],
    )
    op.create_index(
        "ix_rezerwacje_publiczne_holdy_data_interval",
        "rezerwacje_publiczne_holdy", ["data", "godz_od", "godz_do"],
    )
    op.create_index(
        "ix_rezerwacje_publiczne_holdy_expires_at",
        "rezerwacje_publiczne_holdy", ["expires_at"],
    )
    op.create_index(
        "ix_rezerwacje_publiczne_holdy_termin_id",
        "rezerwacje_publiczne_holdy", ["termin_id"],
    )

    op.create_table(
        "rezerwacje_tokeny_zarzadzania",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "termin_id", sa.Integer(),
            sa.ForeignKey("terminy.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("rotated_to_id", sa.Integer(), nullable=True),
        sa.Column("used_operation", sa.String(length=64), nullable=True),
        sa.Column("used_request_fingerprint", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["rotated_to_id"], ["rezerwacje_tokeny_zarzadzania.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "token_hash", name="uq_rezerwacje_tokeny_zarzadzania_token_hash",
        ),
        sa.CheckConstraint(
            "length(token_hash) = 64",
            name="ck_rezerwacje_tokeny_zarzadzania_token_hash",
        ),
        sa.CheckConstraint(
            "used_request_fingerprint IS NULL OR length(used_request_fingerprint) = 64",
            name="ck_rezerwacje_tokeny_zarzadzania_fingerprint",
        ),
        sa.CheckConstraint(
            "(used_at IS NULL AND used_operation IS NULL "
            "AND used_request_fingerprint IS NULL AND rotated_to_id IS NULL) OR "
            "(used_at IS NOT NULL AND used_operation IS NOT NULL "
            "AND used_request_fingerprint IS NOT NULL AND rotated_to_id IS NOT NULL)",
            name="ck_rezerwacje_tokeny_zarzadzania_usage",
        ),
    )
    op.create_index(
        "ix_rezerwacje_tokeny_zarzadzania_termin_id",
        "rezerwacje_tokeny_zarzadzania", ["termin_id"],
    )
    op.create_index(
        "ix_rezerwacje_tokeny_zarzadzania_expires_at",
        "rezerwacje_tokeny_zarzadzania", ["expires_at"],
    )
    op.create_index(
        "ix_rezerwacje_tokeny_zarzadzania_rotated_to_id",
        "rezerwacje_tokeny_zarzadzania", ["rotated_to_id"],
    )

    op.create_table(
        "rezerwacje_zgody_publiczne",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "termin_id", sa.Integer(),
            sa.ForeignKey("terminy.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column(
            "waitlist_id", sa.Integer(),
            sa.ForeignKey("lista_oczekujacych.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column("notice_version", sa.String(length=64), nullable=False),
        sa.Column("notice_ack_at", sa.DateTime(), nullable=False),
        sa.Column("marketing", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("marketing_version", sa.String(length=64), nullable=False),
        sa.Column("marketing_at", sa.DateTime(), nullable=False),
        sa.Column("sensitive", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sensitive_version", sa.String(length=64), nullable=True),
        sa.Column("sensitive_at", sa.DateTime(), nullable=True),
        # Fernet + UTF-8 + base64 może wielokrotnie powiększyć tekst wejściowy.
        sa.Column("sensitive_data", sa.Text(), nullable=True),
        sa.Column("retention_until", sa.DateTime(), nullable=False),
        sa.Column("ip_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "(termin_id IS NOT NULL AND waitlist_id IS NULL) OR "
            "(termin_id IS NULL AND waitlist_id IS NOT NULL)",
            name="ck_rezerwacje_zgody_publiczne_owner",
        ),
        sa.CheckConstraint(
            "length(trim(notice_version)) > 0",
            name="ck_rezerwacje_zgody_publiczne_notice_version",
        ),
        sa.CheckConstraint(
            "length(trim(marketing_version)) > 0",
            name="ck_rezerwacje_zgody_publiczne_marketing_version",
        ),
        sa.CheckConstraint(
            "(NOT sensitive AND sensitive_version IS NULL AND sensitive_at IS NULL "
            "AND sensitive_data IS NULL) OR "
            "(sensitive AND sensitive_version IS NOT NULL AND sensitive_at IS NOT NULL "
            "AND sensitive_data IS NOT NULL)",
            name="ck_rezerwacje_zgody_publiczne_sensitive",
        ),
        sa.CheckConstraint(
            "length(ip_hash) = 64",
            name="ck_rezerwacje_zgody_publiczne_ip_hash",
        ),
    )
    op.create_index(
        "ix_rezerwacje_zgody_publiczne_termin_id",
        "rezerwacje_zgody_publiczne", ["termin_id"],
    )
    op.create_index(
        "ix_rezerwacje_zgody_publiczne_waitlist_id",
        "rezerwacje_zgody_publiczne", ["waitlist_id"],
    )
    op.create_index(
        "ix_rezerwacje_zgody_publiczne_retention_until",
        "rezerwacje_zgody_publiczne", ["retention_until"],
    )

    op.create_table(
        "rezerwacje_publiczne_kwoty",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("client_hash", sa.String(length=64), nullable=False),
        sa.Column("window_start", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "scope", "client_hash", "window_start",
            name="uq_rezerwacje_publiczne_kwoty_scope_client_window",
        ),
        sa.CheckConstraint(
            "length(trim(scope)) > 0",
            name="ck_rezerwacje_publiczne_kwoty_scope",
        ),
        sa.CheckConstraint(
            "length(client_hash) = 64",
            name="ck_rezerwacje_publiczne_kwoty_client_hash",
        ),
        sa.CheckConstraint(
            "count >= 0",
            name="ck_rezerwacje_publiczne_kwoty_count",
        ),
        sa.CheckConstraint(
            "expires_at > window_start",
            name="ck_rezerwacje_publiczne_kwoty_window",
        ),
    )
    op.create_index(
        "ix_rezerwacje_publiczne_kwoty_expires_at",
        "rezerwacje_publiczne_kwoty", ["expires_at"],
    )

    with op.batch_alter_table("rezerwacje_stoliki_claims") as batch:
        batch.add_column(sa.Column("public_hold_id", sa.Integer(), nullable=True))
        batch.drop_constraint("ck_rezerwacje_stolik_claim_owner", type_="check")
        batch.create_foreign_key(
            "fk_rezerwacje_stolik_claim_public_hold_id",
            "rezerwacje_publiczne_holdy", ["public_hold_id"], ["id"],
            ondelete="CASCADE",
        )
        batch.create_unique_constraint(
            "uq_rezerwacje_stolik_claim_public_hold_owner",
            ["public_hold_id", "stolik_id", "data", "minute"],
        )
        batch.create_check_constraint(
            "ck_rezerwacje_stolik_claim_owner", _CLAIM_OWNER_R5A,
        )
        batch.create_index(
            "ix_rezerwacje_stolik_claim_public_hold_id", ["public_hold_id"],
        )

    # Legacy magic links are intentionally invalidated. They are never copied into
    # the hash-only token model and a downgrade must not resurrect them.
    op.execute(sa.text(
        "UPDATE terminy SET token_potwierdzenia = NULL "
        "WHERE token_potwierdzenia IS NOT NULL"
    ))
    op.execute(sa.text(
        "UPDATE lista_oczekujacych SET token = NULL WHERE token IS NOT NULL"
    ))


def downgrade() -> None:
    with op.batch_alter_table("rezerwacje_stoliki_claims") as batch:
        batch.drop_index("ix_rezerwacje_stolik_claim_public_hold_id")
        batch.drop_constraint(
            "uq_rezerwacje_stolik_claim_public_hold_owner", type_="unique",
        )
        batch.drop_constraint(
            "fk_rezerwacje_stolik_claim_public_hold_id", type_="foreignkey",
        )
        batch.drop_constraint("ck_rezerwacje_stolik_claim_owner", type_="check")
        batch.create_check_constraint(
            "ck_rezerwacje_stolik_claim_owner", _CLAIM_OWNER_R4,
        )
        batch.drop_column("public_hold_id")

    op.drop_index(
        "ix_rezerwacje_publiczne_kwoty_expires_at",
        table_name="rezerwacje_publiczne_kwoty",
    )
    op.drop_table("rezerwacje_publiczne_kwoty")

    op.drop_index(
        "ix_rezerwacje_zgody_publiczne_retention_until",
        table_name="rezerwacje_zgody_publiczne",
    )
    op.drop_index(
        "ix_rezerwacje_zgody_publiczne_waitlist_id",
        table_name="rezerwacje_zgody_publiczne",
    )
    op.drop_index(
        "ix_rezerwacje_zgody_publiczne_termin_id",
        table_name="rezerwacje_zgody_publiczne",
    )
    op.drop_table("rezerwacje_zgody_publiczne")

    op.drop_index(
        "ix_rezerwacje_tokeny_zarzadzania_rotated_to_id",
        table_name="rezerwacje_tokeny_zarzadzania",
    )
    op.drop_index(
        "ix_rezerwacje_tokeny_zarzadzania_expires_at",
        table_name="rezerwacje_tokeny_zarzadzania",
    )
    op.drop_index(
        "ix_rezerwacje_tokeny_zarzadzania_termin_id",
        table_name="rezerwacje_tokeny_zarzadzania",
    )
    op.drop_table("rezerwacje_tokeny_zarzadzania")

    op.drop_index(
        "ix_rezerwacje_publiczne_holdy_termin_id",
        table_name="rezerwacje_publiczne_holdy",
    )
    op.drop_index(
        "ix_rezerwacje_publiczne_holdy_expires_at",
        table_name="rezerwacje_publiczne_holdy",
    )
    op.drop_index(
        "ix_rezerwacje_publiczne_holdy_data_interval",
        table_name="rezerwacje_publiczne_holdy",
    )
    op.drop_index(
        "ix_rezerwacje_publiczne_holdy_ip_state",
        table_name="rezerwacje_publiczne_holdy",
    )
    op.drop_index(
        "ix_rezerwacje_publiczne_holdy_session_state",
        table_name="rezerwacje_publiczne_holdy",
    )
    op.drop_table("rezerwacje_publiczne_holdy")

    with op.batch_alter_table("lokal_config") as batch:
        batch.drop_constraint(
            "ck_lokal_config_rezerwacje_retencja_dni", type_="check",
        )
        batch.drop_column("rezerwacje_rodo_adres")
        batch.drop_column("rezerwacje_rodo_kontakt")
        batch.drop_column("rezerwacje_retencja_dni")
        batch.drop_column("rezerwacje_widget_v2")
