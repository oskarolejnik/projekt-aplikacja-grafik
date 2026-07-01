"""audit_log — dziennik audytu dostepu do danych wrazliwych (RODO)

Nowa tabela `audit_log`: kto (user_id + zdenormalizowany login), kiedy (ts UTC),
akcja/zasob, opcjonalnie kogo dotyczy (pracownik_id) i IP. Zapisywana przy dostepie
do danych placowych/finansowych. FK z ondelete=SET NULL, by wpis przetrwal usuniecie konta.

Revision ID: 0006_audit_log
Revises: 0005_rezerwacje_online
Create Date: 2026-07-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0006_audit_log'
down_revision: Union[str, None] = '0005_rezerwacje_online'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'audit_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ts', sa.DateTime(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('login', sa.String(length=64), nullable=True),
        sa.Column('akcja', sa.String(length=64), nullable=False),
        sa.Column('zasob', sa.String(length=128), nullable=True),
        sa.Column('pracownik_id', sa.Integer(), nullable=True),
        sa.Column('ip', sa.String(length=64), nullable=True),
        sa.Column('szczegoly', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['pracownik_id'], ['pracownicy.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('audit_log', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_audit_log_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_log_ts'), ['ts'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('audit_log', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_audit_log_ts'))
        batch_op.drop_index(batch_op.f('ix_audit_log_id'))
    op.drop_table('audit_log')
