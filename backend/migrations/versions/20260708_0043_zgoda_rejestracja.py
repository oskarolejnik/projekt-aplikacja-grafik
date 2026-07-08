"""Rejestracja lokalu: zapis zgody na Regulamin/Politykę/DPA (dowodliwość RODO — wersja + moment).

Zgoda jest warunkiem założenia konta w torze samoobsługowym; przechowujemy WERSJĘ zaakceptowanych
dokumentów oraz znacznik czasu, żeby móc wykazać zgodę. Oba pola NULLable — legacy-safe.

Revision ID: 0043_zgoda_rejestracja
Revises: 0042_profil_goscia
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0043_zgoda_rejestracja"
down_revision: Union[str, None] = "0042_profil_goscia"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("rejestracje_lokalu") as batch:
        batch.add_column(sa.Column("zgoda_wersja", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("zgoda_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("rejestracje_lokalu") as batch:
        batch.drop_column("zgoda_at")
        batch.drop_column("zgoda_wersja")
