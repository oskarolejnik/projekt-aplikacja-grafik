"""Waitlist v2: powiadomienie „stolik gotowy" + tymczasowy HOLD stołu + kanał + token (magic-link).

Rozszerza lista_oczekujacych o pola operacyjne. Wszystko NULLable / z server_default — legacy-safe.

Revision ID: 0046_waitlist_hold
Revises: 0045_graf_sekcje
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0046_waitlist_hold"
down_revision: Union[str, None] = "0045_graf_sekcje"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("lista_oczekujacych") as batch:
        batch.add_column(sa.Column("powiadomiono_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("hold_stolik_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("hold_do", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("token", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("kanal", sa.String(length=16), nullable=False, server_default="reczna"))
    op.create_index("ix_lista_oczekujacych_token", "lista_oczekujacych", ["token"])


def downgrade() -> None:
    op.drop_index("ix_lista_oczekujacych_token", table_name="lista_oczekujacych")
    with op.batch_alter_table("lista_oczekujacych") as batch:
        batch.drop_column("kanal")
        batch.drop_column("token")
        batch.drop_column("hold_do")
        batch.drop_column("hold_stolik_id")
        batch.drop_column("powiadomiono_at")
