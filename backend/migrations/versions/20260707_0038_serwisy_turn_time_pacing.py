"""Serwisy rezerwacyjne: turn-time zależny od grupy + pacing (limit coverów) na GodzinyOtwarcia.

Rozszerza tabelę `godziny_otwarcia` o etykietę serwisu (lunch/kolacja), progi turn-time wg
wielkości grupy oraz limity pacingu. Wszystkie kolumny NULLable — istniejące wiersze zachowują
zachowanie historyczne (jeden slot = dlugosc_slotu_min, brak pacingu), więc bez server_default.

Revision ID: 0038_serwisy_turn_time_pacing
Revises: 0037_dedup_karta_unique
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0038_serwisy_turn_time_pacing"
down_revision: Union[str, None] = "0037_dedup_karta_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("godziny_otwarcia") as batch:
        batch.add_column(sa.Column("nazwa", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("turn_time_progi", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("pacing_max_rez", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("pacing_max_osob", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("pacing_okno_min", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("godziny_otwarcia") as batch:
        batch.drop_column("pacing_okno_min")
        batch.drop_column("pacing_max_osob")
        batch.drop_column("pacing_max_rez")
        batch.drop_column("turn_time_progi")
        batch.drop_column("nazwa")
