"""Tor A integracji POS: dzienny utarg (wspólny mianownik źródeł) + heartbeat agenta.

- utarg_dnia: upsert po (data, zrodlo); zasila prognozę ruchu (liczba_rachunkow →
  stoliki_historia) i panel „Utarg (POS)". Źródła: reczny|csv|<driver agenta>|<konektor>.
- agent_status: zdrowie lokalnego agenta (wersja, capabilities, ostatni sync, błędy).

Revision ID: 0026_utarg_pos
Revises: 0025_profil_rozliczen
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0026_utarg_pos"
down_revision: Union[str, None] = "0025_profil_rozliczen"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "utarg_dnia",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("zrodlo", sa.String(length=32), nullable=False, server_default="reczny"),
        sa.Column("netto", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("gotowka", sa.Float(), nullable=True),
        sa.Column("karta", sa.Float(), nullable=True),
        sa.Column("liczba_rachunkow", sa.Integer(), nullable=True),
        sa.Column("aktualizacja_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("data", "zrodlo"),
    )
    op.create_index("ix_utarg_dnia_data", "utarg_dnia", ["data"])

    op.create_table(
        "agent_status",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("driver", sa.String(length=48), nullable=False, unique=True),
        sa.Column("wersja", sa.String(length=32), nullable=True),
        sa.Column("capabilities", sa.JSON(), nullable=True),
        sa.Column("ostatni_sync", sa.DateTime(), nullable=True),
        sa.Column("bledy", sa.JSON(), nullable=True),
        sa.Column("aktualizacja_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("agent_status")
    op.drop_index("ix_utarg_dnia_data", table_name="utarg_dnia")
    op.drop_table("utarg_dnia")
