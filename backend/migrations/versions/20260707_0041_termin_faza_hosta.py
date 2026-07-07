"""Termin: faza operacyjna hosta (przybył→posadzony→rachunek→opłacony→wyszedł) + timestampy.

Obok status księgowego (rezerwacja/odbyła/no-show) host prowadzi stan sesji przy stole.
`host_seated_at` zasila timer obrotu na mapie sali. Wszystkie kolumny NULLable — legacy-safe.

Revision ID: 0041_termin_faza_hosta
Revises: 0040_termin_kombinacja_auto
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0041_termin_faza_hosta"
down_revision: Union[str, None] = "0040_termin_kombinacja_auto"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("terminy") as batch:
        batch.add_column(sa.Column("faza_hosta", sa.String(length=16), nullable=True))
        batch.add_column(sa.Column("host_arrived_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("host_seated_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("host_left_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("terminy") as batch:
        batch.drop_column("host_left_at")
        batch.drop_column("host_seated_at")
        batch.drop_column("host_arrived_at")
        batch.drop_column("faza_hosta")
