"""parametry obsady imprez w lokal_config (Rec#4 audytu)

Przenosi zaszyte w algorithm.py parametry obsady imprez do konfiguracji lokalu:
liczba gosci na pracownika, wyprzedzenie startu, najwczesniejsza godzina, sale z min. 2.
server_default = wartosci historyczne, wiec zachowanie istniejacych instancji sie nie zmienia.

Revision ID: 0008_parametry_imprez
Revises: 0007_szyfrowanie_pii
Create Date: 2026-07-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0008_parametry_imprez'
down_revision: Union[str, None] = '0007_szyfrowanie_pii'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('lokal_config', schema=None) as batch_op:
        batch_op.add_column(sa.Column('impreza_osoby_na_obsluge', sa.Integer(),
                                      nullable=False, server_default='15'))
        batch_op.add_column(sa.Column('impreza_wyprzedzenie_min', sa.Integer(),
                                      nullable=False, server_default='120'))
        batch_op.add_column(sa.Column('impreza_najwczesniej', sa.String(length=5),
                                      nullable=False, server_default='10:00'))
        batch_op.add_column(sa.Column('impreza_sale_min2', sa.String(length=128),
                                      nullable=False, server_default='R2Piw,R2G'))


def downgrade() -> None:
    with op.batch_alter_table('lokal_config', schema=None) as batch_op:
        batch_op.drop_column('impreza_sale_min2')
        batch_op.drop_column('impreza_najwczesniej')
        batch_op.drop_column('impreza_wyprzedzenie_min')
        batch_op.drop_column('impreza_osoby_na_obsluge')
