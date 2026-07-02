"""portal Pary Mlodej etap 2 — katalog ofert menu + harmonogram rat + wybor menu na Terminie

Nowe tabele oferty_menu i raty_imprez oraz kolumna terminy.menu_oferta_id (wybor klienta
z portalu). Kolumna bez twardego FK na SQLite (jak pozostale dodawane kolumny) — relacje
pilnuje ORM; swieze bazy z init_db/create_all maja pelny constraint.

Revision ID: 0022_menu_raty_portalu
Revises: 0021_antyfraud_storna
Create Date: 2026-07-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0022_menu_raty_portalu'
down_revision: Union[str, None] = '0021_antyfraud_storna'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'oferty_menu',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nazwa', sa.String(length=120), nullable=False),
        sa.Column('opis', sa.String(), nullable=True),
        sa.Column('cena_od_osoby', sa.Float(), nullable=False, server_default='0'),
        sa.Column('aktywna', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('kolejnosc', sa.Integer(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_oferty_menu_id', 'oferty_menu', ['id'])

    op.create_table(
        'raty_imprez',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('termin_id', sa.Integer(), nullable=False),
        sa.Column('nazwa', sa.String(length=120), nullable=False),
        sa.Column('kwota', sa.Float(), nullable=False, server_default='0'),
        sa.Column('termin_platnosci', sa.Date(), nullable=True),
        sa.Column('zaplacona', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('zaplacona_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['termin_id'], ['terminy.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_raty_imprez_id', 'raty_imprez', ['id'])
    op.create_index('ix_raty_imprez_termin_id', 'raty_imprez', ['termin_id'])

    op.add_column('terminy', sa.Column('menu_oferta_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('terminy', 'menu_oferta_id')
    op.drop_index('ix_raty_imprez_termin_id', table_name='raty_imprez')
    op.drop_index('ix_raty_imprez_id', table_name='raty_imprez')
    op.drop_table('raty_imprez')
    op.drop_index('ix_oferty_menu_id', table_name='oferty_menu')
    op.drop_table('oferty_menu')
