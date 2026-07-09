"""Polityka zadatku + no-show fee (LokalConfig) — za flagą; realne pobieranie czeka na bramkę.

Cztery kolumny NOT NULL z server_default (defaulty = polityka wyłączona = zachowanie historyczne).

Revision ID: 0048_polityka_zadatku
Revises: 0047_rejestracja_sale
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0048_polityka_zadatku"
down_revision: Union[str, None] = "0047_rejestracja_sale"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("lokal_config") as batch:
        batch.add_column(sa.Column("zadatek_wymagany", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("zadatek_kwota_os", sa.Float(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("zadatek_prog_osob", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("no_show_fee", sa.Float(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("lokal_config") as batch:
        batch.drop_column("no_show_fee")
        batch.drop_column("zadatek_prog_osob")
        batch.drop_column("zadatek_kwota_os")
        batch.drop_column("zadatek_wymagany")
