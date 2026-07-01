"""ogloszenia zespolowe — tablica komunikatow manager->pracownicy + potwierdzenia przeczytania

Dwie nowe tabele (ogloszenia, ogloszenia_potwierdzenia), brak zmian w istniejacych —
bezpieczne dla dzialajacych instancji.

Revision ID: 0017_ogloszenia
Revises: 0016_stolik_rewir
Create Date: 2026-07-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0017_ogloszenia'
down_revision: Union[str, None] = '0016_stolik_rewir'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ogloszenia',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tytul', sa.String(length=160), nullable=False),
        sa.Column('tresc', sa.String(), nullable=False),
        sa.Column('autor_login', sa.String(), nullable=True),
        sa.Column('przypiete', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('wazne_do', sa.Date(), nullable=True),
        sa.Column('utworzono_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ogloszenia_id', 'ogloszenia', ['id'])

    op.create_table(
        'ogloszenia_potwierdzenia',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ogloszenie_id', sa.Integer(), nullable=False),
        sa.Column('pracownik_id', sa.Integer(), nullable=False),
        sa.Column('potwierdzono_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['ogloszenie_id'], ['ogloszenia.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['pracownik_id'], ['pracownicy.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ogloszenie_id', 'pracownik_id', name='uq_ogloszenie_pracownik'),
    )
    op.create_index('ix_ogloszenia_potwierdzenia_id', 'ogloszenia_potwierdzenia', ['id'])
    op.create_index('ix_ogloszenia_potwierdzenia_ogloszenie_id', 'ogloszenia_potwierdzenia', ['ogloszenie_id'])
    op.create_index('ix_ogloszenia_potwierdzenia_pracownik_id', 'ogloszenia_potwierdzenia', ['pracownik_id'])


def downgrade() -> None:
    op.drop_index('ix_ogloszenia_potwierdzenia_pracownik_id', table_name='ogloszenia_potwierdzenia')
    op.drop_index('ix_ogloszenia_potwierdzenia_ogloszenie_id', table_name='ogloszenia_potwierdzenia')
    op.drop_index('ix_ogloszenia_potwierdzenia_id', table_name='ogloszenia_potwierdzenia')
    op.drop_table('ogloszenia_potwierdzenia')
    op.drop_index('ix_ogloszenia_id', table_name='ogloszenia')
    op.drop_table('ogloszenia')
