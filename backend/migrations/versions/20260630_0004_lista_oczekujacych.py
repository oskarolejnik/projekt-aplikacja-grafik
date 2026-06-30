"""lista oczekujacych (waitlist)

Nowa tabela `lista_oczekujacych` — goście bez wolnego stolika; po zwolnieniu miejsca
admin realizuje wpis → tworzy rezerwację (Termin rodzaj=stolik).

Revision ID: 0004_lista_oczekujacych
Revises: 0003_rezerwacje
Create Date: 2026-06-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0004_lista_oczekujacych'
down_revision: Union[str, None] = '0003_rezerwacje'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'lista_oczekujacych',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('data', sa.Date(), nullable=False),
        sa.Column('godz_od', sa.Time(), nullable=True),
        sa.Column('liczba_osob', sa.Integer(), nullable=True),
        sa.Column('nazwisko', sa.String(length=128), nullable=False),
        sa.Column('telefon', sa.String(length=32), nullable=True),
        sa.Column('email', sa.String(length=128), nullable=True),
        sa.Column('notatka', sa.String(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('utworzono_at', sa.DateTime(), nullable=False),
        sa.Column('zrealizowano_at', sa.DateTime(), nullable=True),
        sa.Column('termin_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['termin_id'], ['terminy.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('lista_oczekujacych', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_lista_oczekujacych_data'), ['data'], unique=False)
        batch_op.create_index(batch_op.f('ix_lista_oczekujacych_id'), ['id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('lista_oczekujacych', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_lista_oczekujacych_id'))
        batch_op.drop_index(batch_op.f('ix_lista_oczekujacych_data'))
    op.drop_table('lista_oczekujacych')
