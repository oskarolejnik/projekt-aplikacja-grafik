"""portfel pracownika — wnioski o zaliczki z potraceniem w raporcie wyplat

Nowa tabela zaliczki. Brak zmian w istniejacych tabelach.

Revision ID: 0023_zaliczki
Revises: 0022_menu_raty_portalu
Create Date: 2026-07-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0023_zaliczki'
down_revision: Union[str, None] = '0022_menu_raty_portalu'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'zaliczki',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pracownik_id', sa.Integer(), nullable=False),
        sa.Column('miesiac', sa.String(length=7), nullable=False),
        sa.Column('kwota', sa.Float(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='oczekuje'),
        sa.Column('wniosek_at', sa.DateTime(), nullable=False),
        sa.Column('decyzja_at', sa.DateTime(), nullable=True),
        sa.Column('decyzja_login', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['pracownik_id'], ['pracownicy.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_zaliczki_id', 'zaliczki', ['id'])
    op.create_index('ix_zaliczki_pracownik_id', 'zaliczki', ['pracownik_id'])
    op.create_index('ix_zaliczki_miesiac', 'zaliczki', ['miesiac'])


def downgrade() -> None:
    op.drop_index('ix_zaliczki_miesiac', table_name='zaliczki')
    op.drop_index('ix_zaliczki_pracownik_id', table_name='zaliczki')
    op.drop_index('ix_zaliczki_id', table_name='zaliczki')
    op.drop_table('zaliczki')
