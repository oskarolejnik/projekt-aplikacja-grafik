"""Karta zapięta na trial planu płatnego: auto-obciążenie po 14 dniach + dedup po odcisku karty.

Subskrypcja (instancja): karta_token + karta_ostatnie4 (metoda do obciążenia po trialu).
RejestracjaLokalu (matka): karta_token + karta_ostatnie4 + karta_fingerprint (indeks; dedup —
jedna karta = jeden trial). PAN nigdy nie jest przechowywany.

Revision ID: 0036_karta_trial
Revises: 0035_rejestracje_lokalu
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0036_karta_trial"
down_revision: Union[str, None] = "0035_rejestracje_lokalu"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("subskrypcja") as b:
        b.add_column(sa.Column("karta_token", sa.String(length=64), nullable=True))
        b.add_column(sa.Column("karta_ostatnie4", sa.String(length=4), nullable=True))
    with op.batch_alter_table("rejestracje_lokalu") as b:
        b.add_column(sa.Column("karta_token", sa.String(length=64), nullable=True))
        b.add_column(sa.Column("karta_ostatnie4", sa.String(length=4), nullable=True))
        b.add_column(sa.Column("karta_fingerprint", sa.String(length=64), nullable=True))
    op.create_index("ix_rejestracje_lokalu_karta_fingerprint", "rejestracje_lokalu", ["karta_fingerprint"])


def downgrade() -> None:
    op.drop_index("ix_rejestracje_lokalu_karta_fingerprint", table_name="rejestracje_lokalu")
    with op.batch_alter_table("rejestracje_lokalu") as b:
        b.drop_column("karta_fingerprint")
        b.drop_column("karta_ostatnie4")
        b.drop_column("karta_token")
    with op.batch_alter_table("subskrypcja") as b:
        b.drop_column("karta_ostatnie4")
        b.drop_column("karta_token")
