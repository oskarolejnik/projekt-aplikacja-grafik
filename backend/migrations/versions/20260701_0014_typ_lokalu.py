"""typ lokalu w lokal_config (kreator restauracji)

Zapamietuje wybrany w kreatorze typ lokalu (np. 'pizzeria', 'dom-weselny'),
zeby mozna go pokazac/edytowac pozniej i sterowac presetem modulow.
Kolumna nullable — istniejace instancje bez zmian.

Revision ID: 0014_typ_lokalu
Revises: 0013_prawo_pracy
Create Date: 2026-07-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0014_typ_lokalu'
down_revision: Union[str, None] = '0013_prawo_pracy'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('lokal_config', schema=None) as batch_op:
        batch_op.add_column(sa.Column('typ_lokalu', sa.String(length=48), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('lokal_config', schema=None) as batch_op:
        batch_op.drop_column('typ_lokalu')
