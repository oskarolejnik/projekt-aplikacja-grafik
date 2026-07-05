"""Fundament billingu subskrypcji (monetyzacja Faza 0).

- subskrypcja: cena_netto (override, NULL=cennik) + saldo_kredytu (kredyt z downgrade).
- platnosci_subskrypcji: płatności abonamentowe/dopłaty (osobno od zadatków imprez).
- historia_subskrypcji: audyt zmian tieru (podstawa faktur + rozliczalność).

Revision ID: 0031_billing_subskrypcji
Revises: 0030_pracownik_pos_id
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0031_billing_subskrypcji"
down_revision: Union[str, None] = "0030_pracownik_pos_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("subskrypcja") as batch:
        batch.add_column(sa.Column("cena_netto", sa.Float(), nullable=True))
        batch.add_column(sa.Column("saldo_kredytu", sa.Float(), nullable=False, server_default="0"))

    op.create_table(
        "platnosci_subskrypcji",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("rodzaj", sa.String(length=16), nullable=False, server_default="abonament"),
        sa.Column("tier", sa.String(length=16), nullable=True),
        sa.Column("netto", sa.Float(), nullable=False, server_default="0"),
        sa.Column("vat", sa.Float(), nullable=False, server_default="0"),
        sa.Column("brutto", sa.Float(), nullable=False, server_default="0"),
        sa.Column("okres_od", sa.Date(), nullable=True),
        sa.Column("okres_do", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="oczekuje"),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="sandbox"),
        sa.Column("external_id", sa.String(), nullable=True),
        sa.Column("link", sa.String(), nullable=True),
        sa.Column("utworzono_at", sa.DateTime(), nullable=True),
        sa.Column("oplacono_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_platnosci_subskrypcji_external_id", "platnosci_subskrypcji", ["external_id"])

    op.create_table(
        "historia_subskrypcji",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("akcja", sa.String(length=24), nullable=False),
        sa.Column("tier_z", sa.String(length=16), nullable=True),
        sa.Column("tier_na", sa.String(length=16), nullable=True),
        sa.Column("kwota_netto", sa.Float(), nullable=True),
        sa.Column("login", sa.String(length=64), nullable=True),
        sa.Column("szczegoly", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("historia_subskrypcji")
    op.drop_index("ix_platnosci_subskrypcji_external_id", table_name="platnosci_subskrypcji")
    op.drop_table("platnosci_subskrypcji")
    with op.batch_alter_table("subskrypcja") as batch:
        batch.drop_column("saldo_kredytu")
        batch.drop_column("cena_netto")