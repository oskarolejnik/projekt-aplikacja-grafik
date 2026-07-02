"""portal klienta imprezy — token publicznego linku na Terminie + watek wiadomosci

Dodaje terminy.portal_token (NULL = portal niewygenerowany) i tabele wiadomosci_imprez
(watek ustalen klient <-> lokal + notki systemowe). Bezpieczne dla dzialajacych instancji.

Revision ID: 0020_portal_imprezy
Revises: 0019_zgodnosc
Create Date: 2026-07-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0020_portal_imprezy'
down_revision: Union[str, None] = '0019_zgodnosc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('terminy', sa.Column('portal_token', sa.String(length=64), nullable=True))
    op.create_index('ix_terminy_portal_token', 'terminy', ['portal_token'], unique=True)

    op.create_table(
        'wiadomosci_imprez',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('termin_id', sa.Integer(), nullable=False),
        sa.Column('autor', sa.String(length=16), nullable=False, server_default='klient'),
        sa.Column('tresc', sa.String(), nullable=False),
        sa.Column('utworzono_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['termin_id'], ['terminy.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_wiadomosci_imprez_id', 'wiadomosci_imprez', ['id'])
    op.create_index('ix_wiadomosci_imprez_termin_id', 'wiadomosci_imprez', ['termin_id'])


def downgrade() -> None:
    op.drop_index('ix_wiadomosci_imprez_termin_id', table_name='wiadomosci_imprez')
    op.drop_index('ix_wiadomosci_imprez_id', table_name='wiadomosci_imprez')
    op.drop_table('wiadomosci_imprez')
    op.drop_index('ix_terminy_portal_token', table_name='terminy')
    op.drop_column('terminy', 'portal_token')
