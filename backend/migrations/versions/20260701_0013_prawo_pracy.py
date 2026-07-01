"""strażnik prawa pracy — limity w lokal_config (roadmapa v1.5)

Parametry walidacji recznego przydzialu zmian: min. odpoczynek miedzy zmianami +
maks. dni pracy w tygodniu/miesiacu. server_default = domyslne, wiec istniejace
instancje bez zmian (limity wlaczone z rozsadnymi wartosciami; 0 = limit wylaczony).

Revision ID: 0013_prawo_pracy
Revises: 0012_gielda_zmian
Create Date: 2026-07-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0013_prawo_pracy'
down_revision: Union[str, None] = '0012_gielda_zmian'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('lokal_config', schema=None) as batch_op:
        batch_op.add_column(sa.Column('praca_min_odpoczynek_h', sa.Integer(),
                                      nullable=False, server_default='11'))
        batch_op.add_column(sa.Column('praca_max_dni_tydzien', sa.Integer(),
                                      nullable=False, server_default='6'))
        batch_op.add_column(sa.Column('praca_max_dni_miesiac', sa.Integer(),
                                      nullable=False, server_default='22'))


def downgrade() -> None:
    with op.batch_alter_table('lokal_config', schema=None) as batch_op:
        batch_op.drop_column('praca_max_dni_miesiac')
        batch_op.drop_column('praca_max_dni_tydzien')
        batch_op.drop_column('praca_min_odpoczynek_h')
