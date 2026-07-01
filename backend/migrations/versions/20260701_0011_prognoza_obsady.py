"""prognoza obsady — parametry w lokal_config (roadmapa v1.5)

Parametry przeliczania prognozowanego ruchu na sugerowana obsade zmiany:
obsada_rachunki_na_osobe (ilu rachunkow obsluguje 1 osoba) + obsada_min (minimalna obsada).
server_default = wartosci domyslne, wiec istniejace instancje bez zmian.

Revision ID: 0011_prognoza_obsady
Revises: 0010_platnosci
Create Date: 2026-07-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0011_prognoza_obsady'
down_revision: Union[str, None] = '0010_platnosci'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('lokal_config', schema=None) as batch_op:
        batch_op.add_column(sa.Column('obsada_rachunki_na_osobe', sa.Integer(),
                                      nullable=False, server_default='20'))
        batch_op.add_column(sa.Column('obsada_min', sa.Integer(),
                                      nullable=False, server_default='1'))


def downgrade() -> None:
    with op.batch_alter_table('lokal_config', schema=None) as batch_op:
        batch_op.drop_column('obsada_min')
        batch_op.drop_column('obsada_rachunki_na_osobe')
