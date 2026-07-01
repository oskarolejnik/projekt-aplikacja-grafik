"""napiwki dnia — pula napiwkow do podzialu miedzy obsluge sali (roadmapa v1.5)

Nowa tabela napiwki_dnia (jedna kwota + sposob podzialu na dzien; sam podzial liczony w locie
z grafiku/RCP). Brak zmian w istniejacych tabelach — bezpieczne dla dzialajacych instancji.

Revision ID: 0018_napiwki
Revises: 0017_ogloszenia
Create Date: 2026-07-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0018_napiwki'
down_revision: Union[str, None] = '0017_ogloszenia'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'napiwki_dnia',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('data', sa.Date(), nullable=False),
        sa.Column('kwota', sa.Float(), nullable=False, server_default='0'),
        sa.Column('sposob', sa.String(length=16), nullable=False, server_default='godziny'),
        sa.Column('utworzono_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('data', name='uq_napiwki_data'),
    )
    op.create_index('ix_napiwki_dnia_id', 'napiwki_dnia', ['id'])
    op.create_index('ix_napiwki_dnia_data', 'napiwki_dnia', ['data'])


def downgrade() -> None:
    op.drop_index('ix_napiwki_dnia_data', table_name='napiwki_dnia')
    op.drop_index('ix_napiwki_dnia_id', table_name='napiwki_dnia')
    op.drop_table('napiwki_dnia')
