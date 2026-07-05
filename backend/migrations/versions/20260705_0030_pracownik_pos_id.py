"""Mapowanie pracowników POS → Lokalo (POS faza 2, krok mapowań kreatora).

pracownik_pos_id: trwałe (zrodlo, pos_id) → pracownik_id, zastępuje kruche
dopasowanie po imieniu. Ingest odbić woli mapę jawną, fallback = imię.

Revision ID: 0030_pracownik_pos_id
Revises: 0029_pula_kelnerska
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0030_pracownik_pos_id"
down_revision: Union[str, None] = "0029_pula_kelnerska"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pracownik_pos_id",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("pracownik_id", sa.Integer(),
                  sa.ForeignKey("pracownicy.id", ondelete="CASCADE"), nullable=False),
        sa.Column("zrodlo", sa.String(length=32), nullable=False),
        sa.Column("pos_id", sa.String(length=64), nullable=False),
        sa.Column("pos_nazwa", sa.String(length=128), nullable=True),
        sa.UniqueConstraint("zrodlo", "pos_id"),
    )
    op.create_index("ix_pracownik_pos_id_pracownik_id", "pracownik_pos_id", ["pracownik_id"])
    # odbicia RCP: zapamiętujemy id pracownika z POS + źródło (do wykrycia nierozpoznanych
    # tożsamości w kreatorze mapowań)
    with op.batch_alter_table("odbicia_rcp") as batch:
        batch.add_column(sa.Column("pos_pracownik_id", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("zrodlo", sa.String(length=32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("odbicia_rcp") as batch:
        batch.drop_column("zrodlo")
        batch.drop_column("pos_pracownik_id")
    op.drop_index("ix_pracownik_pos_id_pracownik_id", table_name="pracownik_pos_id")
    op.drop_table("pracownik_pos_id")
