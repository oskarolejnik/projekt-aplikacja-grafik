"""flagi rezerwacje_online + rezerwacje_auto_potwierdzenie

Dodaje do lokal_config flagi publicznego widgetu rezerwacji online (domyślnie wyłączone).

Revision ID: 0005_rezerwacje_online
Revises: 0004_lista_oczekujacych
Create Date: 2026-06-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0005_rezerwacje_online'
down_revision: Union[str, None] = '0004_lista_oczekujacych'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NOT NULL na istniejącej tabeli → server_default (istniejące lokale: online wyłączone).
    with op.batch_alter_table('lokal_config', schema=None) as batch_op:
        batch_op.add_column(sa.Column('rezerwacje_online', sa.Boolean(), nullable=False,
                                      server_default=sa.false()))
        batch_op.add_column(sa.Column('rezerwacje_auto_potwierdzenie', sa.Boolean(), nullable=False,
                                      server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table('lokal_config', schema=None) as batch_op:
        batch_op.drop_column('rezerwacje_auto_potwierdzenie')
        batch_op.drop_column('rezerwacje_online')
