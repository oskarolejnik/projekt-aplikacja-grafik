"""zgodnosc lokalu — dokumenty pracownikow (sanepid/medycyna/BHP) + terminy lokalu (koncesja/przeglady)

Nowa tabela dokumenty_zgodnosci (jedna na oba byty; pracownik_id NULL = termin lokalu).
Brak zmian w istniejacych tabelach — bezpieczne dla dzialajacych instancji.

Revision ID: 0019_zgodnosc
Revises: 0018_napiwki
Create Date: 2026-07-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0019_zgodnosc'
down_revision: Union[str, None] = '0018_napiwki'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'dokumenty_zgodnosci',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pracownik_id', sa.Integer(), nullable=True),
        sa.Column('typ', sa.String(length=32), nullable=False, server_default='inne'),
        sa.Column('nazwa', sa.String(length=160), nullable=False),
        sa.Column('data_waznosci', sa.Date(), nullable=False),
        sa.Column('notatka', sa.String(), nullable=True),
        sa.Column('blokuje_grafik', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('utworzono_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['pracownik_id'], ['pracownicy.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_dokumenty_zgodnosci_id', 'dokumenty_zgodnosci', ['id'])
    op.create_index('ix_dokumenty_zgodnosci_pracownik_id', 'dokumenty_zgodnosci', ['pracownik_id'])
    op.create_index('ix_dokumenty_zgodnosci_data_waznosci', 'dokumenty_zgodnosci', ['data_waznosci'])


def downgrade() -> None:
    op.drop_index('ix_dokumenty_zgodnosci_data_waznosci', table_name='dokumenty_zgodnosci')
    op.drop_index('ix_dokumenty_zgodnosci_pracownik_id', table_name='dokumenty_zgodnosci')
    op.drop_index('ix_dokumenty_zgodnosci_id', table_name='dokumenty_zgodnosci')
    op.drop_table('dokumenty_zgodnosci')
