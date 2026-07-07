"""Rozszerzenie stołów (min/kształt/cechy/priorytet) + tabela kombinacji stołów.

Stolik dostaje pola pod silnik sadzania (wszystkie NULLable — legacy-safe). Nowa tabela
`kombinacje_stolow` trzyma predefiniowane zestawy stołów do łączenia pod większe grupy
(`stoliki` = lista id w JSON).

Revision ID: 0039_stoly_kombinacje
Revises: 0038_serwisy_turn_time_pacing
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0039_stoly_kombinacje"
down_revision: Union[str, None] = "0038_serwisy_turn_time_pacing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("stoliki") as batch:
        batch.add_column(sa.Column("pojemnosc_min", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("ksztalt", sa.String(length=16), nullable=True))
        batch.add_column(sa.Column("cechy", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("priorytet", sa.Integer(), nullable=True))

    op.create_table(
        "kombinacje_stolow",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nazwa", sa.String(length=64), nullable=False),
        sa.Column("stoliki", sa.JSON(), nullable=False),
        sa.Column("pojemnosc_min", sa.Integer(), nullable=True),
        sa.Column("pojemnosc_max", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("aktywna", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("priorytet", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_kombinacje_stolow_id", "kombinacje_stolow", ["id"])


def downgrade() -> None:
    op.drop_index("ix_kombinacje_stolow_id", table_name="kombinacje_stolow")
    op.drop_table("kombinacje_stolow")
    with op.batch_alter_table("stoliki") as batch:
        batch.drop_column("priorytet")
        batch.drop_column("cechy")
        batch.drop_column("ksztalt")
        batch.drop_column("pojemnosc_min")
