"""platnosci zadatkow online (Rec#7 audytu) — model + tryb sandbox

Nowa tabela `platnosci`: zadatek powiazany z rezerwacja (termin_id), kwota, status
(oczekuje/oplacona/anulowana), provider (sandbox lub docelowo Stripe/P24), external_id/link
z bramki. FK ondelete=SET NULL (platnosc przezywa usuniecie terminu — slad ksiegowy).

Revision ID: 0010_platnosci
Revises: 0009_subskrypcja
Create Date: 2026-07-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0010_platnosci'
down_revision: Union[str, None] = '0009_subskrypcja'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'platnosci',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('termin_id', sa.Integer(), nullable=True),
        sa.Column('kwota', sa.Float(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='oczekuje'),
        sa.Column('provider', sa.String(length=32), nullable=False, server_default='sandbox'),
        sa.Column('external_id', sa.String(), nullable=True),
        sa.Column('link', sa.String(), nullable=True),
        sa.Column('utworzono_at', sa.DateTime(), nullable=False),
        sa.Column('oplacono_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['termin_id'], ['terminy.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('platnosci', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_platnosci_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_platnosci_termin_id'), ['termin_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_platnosci_external_id'), ['external_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('platnosci', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_platnosci_external_id'))
        batch_op.drop_index(batch_op.f('ix_platnosci_termin_id'))
        batch_op.drop_index(batch_op.f('ix_platnosci_id'))
    op.drop_table('platnosci')
