"""subskrypcja/licencja instancji (Rec#2 audytu) — singleton + degradacja READ_ONLY

Nowa tabela `subskrypcja` (singleton id=1): tier, status, daty waznosci. Status nieaktywny
degraduje instancje do trybu tylko-odczyt (middleware zwraca 402 na zapisach). Bez realnej
bramki platnosci — status ustawia operator SaaS.

Revision ID: 0009_subskrypcja
Revises: 0008_parametry_imprez
Create Date: 2026-07-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0009_subskrypcja'
down_revision: Union[str, None] = '0008_parametry_imprez'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'subskrypcja',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tier', sa.String(length=16), nullable=False, server_default='free'),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='aktywna'),
        sa.Column('data_od', sa.Date(), nullable=True),
        sa.Column('data_do', sa.Date(), nullable=True),
        sa.Column('uwagi', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('subskrypcja')
