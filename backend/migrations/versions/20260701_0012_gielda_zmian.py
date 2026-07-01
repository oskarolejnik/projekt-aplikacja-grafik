"""gielda wymiany zmian — tabela oferty_zmian (roadmapa v1.5)

Pracownik wystawia swoj przydzial do przejecia; inny go przejmuje; manager akceptuje.
Nowa tabela, brak zmian w istniejacych — bezpieczne dla dzialajacych instancji.

Revision ID: 0012_gielda_zmian
Revises: 0011_prognoza_obsady
Create Date: 2026-07-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0012_gielda_zmian'
down_revision: Union[str, None] = '0011_prognoza_obsady'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'oferty_zmian',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('przydzial_id', sa.Integer(), nullable=False),
        sa.Column('wystawiajacy_id', sa.Integer(), nullable=False),
        sa.Column('przejmujacy_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='otwarta'),
        sa.Column('powod', sa.String(length=256), nullable=True),
        sa.Column('utworzono_at', sa.DateTime(), nullable=False),
        sa.Column('zajeto_at', sa.DateTime(), nullable=True),
        sa.Column('rozpatrzono_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['przydzial_id'], ['przydzialy_zmian.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['wystawiajacy_id'], ['pracownicy.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['przejmujacy_id'], ['pracownicy.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_oferty_zmian_id', 'oferty_zmian', ['id'])
    op.create_index('ix_oferty_zmian_przydzial_id', 'oferty_zmian', ['przydzial_id'])
    op.create_index('ix_oferty_zmian_wystawiajacy_id', 'oferty_zmian', ['wystawiajacy_id'])
    op.create_index('ix_oferty_zmian_przejmujacy_id', 'oferty_zmian', ['przejmujacy_id'])
    op.create_index('ix_oferty_zmian_status', 'oferty_zmian', ['status'])


def downgrade() -> None:
    op.drop_index('ix_oferty_zmian_status', table_name='oferty_zmian')
    op.drop_index('ix_oferty_zmian_przejmujacy_id', table_name='oferty_zmian')
    op.drop_index('ix_oferty_zmian_wystawiajacy_id', table_name='oferty_zmian')
    op.drop_index('ix_oferty_zmian_przydzial_id', table_name='oferty_zmian')
    op.drop_index('ix_oferty_zmian_id', table_name='oferty_zmian')
    op.drop_table('oferty_zmian')
