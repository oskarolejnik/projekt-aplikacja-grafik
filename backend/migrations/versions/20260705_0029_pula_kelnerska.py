"""Wspólna pula kelnerska (de-Rajculizacja, krok 5).

rozliczenia_dnia: pula_gotowka/karta/fv/kw — jeden zbiorczy zestaw dla całej zmiany
w trybie rozliczenia_tryb_kelnera='pula'. server_default '0' → istniejące rekordy
(tryb 'indywidualnie') mają zera, więc zero zmian behawioralnych.

Revision ID: 0029_pula_kelnerska
Revises: 0028_struktura_lokalu
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0029_pula_kelnerska"
down_revision: Union[str, None] = "0028_struktura_lokalu"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

POLA = ("pula_gotowka", "pula_karta", "pula_fv", "pula_kw")


def upgrade() -> None:
    with op.batch_alter_table("rozliczenia_dnia") as batch:
        for nazwa in POLA:
            batch.add_column(sa.Column(nazwa, sa.Float(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("rozliczenia_dnia") as batch:
        for nazwa in reversed(POLA):
            batch.drop_column(nazwa)
