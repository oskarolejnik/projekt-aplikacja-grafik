"""plan sali — pozycje stolikow (plan_x/plan_y) w tabeli stoliki (roadmapa v1.5)

Wizualne rozmieszczenie stolikow na planie sali: pozycja w % kontenera (0-100).
NULL = brak pozycji (front ustawia auto-siatke). Kolumny nullable — bez migracji danych.

Revision ID: 0015_plan_sali
Revises: 0014_typ_lokalu
Create Date: 2026-07-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0015_plan_sali'
down_revision: Union[str, None] = '0014_typ_lokalu'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('stoliki', schema=None) as batch_op:
        batch_op.add_column(sa.Column('plan_x', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('plan_y', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('stoliki', schema=None) as batch_op:
        batch_op.drop_column('plan_y')
        batch_op.drop_column('plan_x')
