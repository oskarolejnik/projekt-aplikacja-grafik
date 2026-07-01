"""stolik.rewir_nr — powiazanie stolika z rewirem POS (live oblozenie na planie sali)

Nullable — istniejace stoliki bez podpiecia. Pozwala pokazac na Planie sali live
oblozenie z Gastro (StanStolow.rewir_nr) obok statusu rezerwacji.

Revision ID: 0016_stolik_rewir
Revises: 0015_plan_sali
Create Date: 2026-07-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0016_stolik_rewir'
down_revision: Union[str, None] = '0015_plan_sali'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('stoliki', schema=None) as batch_op:
        batch_op.add_column(sa.Column('rewir_nr', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('stoliki', schema=None) as batch_op:
        batch_op.drop_column('rewir_nr')
