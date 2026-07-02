"""antyfraud POS — storna/rabaty/anulacje z Gastro (ingest agenta + analiza per kelner)

Nowa tabela storna_gastro (upsert po GUID z POS). Brak zmian w istniejacych tabelach.

Revision ID: 0021_antyfraud_storna
Revises: 0020_portal_imprezy
Create Date: 2026-07-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0021_antyfraud_storna'
down_revision: Union[str, None] = '0020_portal_imprezy'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'storna_gastro',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('data', sa.Date(), nullable=False),
        sa.Column('imie_nazwisko', sa.String(length=128), nullable=True),
        sa.Column('pracownik_id', sa.Integer(), nullable=True),
        sa.Column('typ', sa.String(length=16), nullable=False, server_default='storno'),
        sa.Column('kwota', sa.Float(), nullable=False, server_default='0'),
        sa.Column('opis', sa.String(), nullable=True),
        sa.Column('godzina', sa.Time(), nullable=True),
        sa.Column('zaktualizowano_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['pracownik_id'], ['pracownicy.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_storna_gastro_data', 'storna_gastro', ['data'])
    op.create_index('ix_storna_gastro_pracownik_id', 'storna_gastro', ['pracownik_id'])


def downgrade() -> None:
    op.drop_index('ix_storna_gastro_pracownik_id', table_name='storna_gastro')
    op.drop_index('ix_storna_gastro_data', table_name='storna_gastro')
    op.drop_table('storna_gastro')
