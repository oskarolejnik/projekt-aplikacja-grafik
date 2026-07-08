"""Polityka rezerwacji (LokalConfig): okno wyprzedzenia, cutoff, min/max grupa online, bufor,
anulacja, auto-no-show + tabela wyjatki_kalendarza (blackout / godziny specjalne per dzień).

Wszystkie kolumny polityki NOT NULL z server_default (defaulty = polityka wyłączona = zachowanie
historyczne). Nowa tabela wyjatki_kalendarza dla nadpisań kalendarza.

Revision ID: 0044_polityka_rezerwacji
Revises: 0043_zgoda_rejestracja
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0044_polityka_rezerwacji"
down_revision: Union[str, None] = "0043_zgoda_rejestracja"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_POLA = [
    ("rez_okno_wyprzedzenia_dni", "0"),
    ("rez_cutoff_min", "0"),
    ("rez_min_grupa_online", "1"),
    ("rez_max_grupa_online", "0"),
    ("rez_bufor_min", "0"),
    ("rez_anulacja_do_h", "0"),
    ("rez_no_show_po_min", "0"),
]


def upgrade() -> None:
    with op.batch_alter_table("lokal_config") as batch:
        for nazwa, dom in _POLA:
            batch.add_column(sa.Column(nazwa, sa.Integer(), nullable=False, server_default=dom))
    op.create_table(
        "wyjatki_kalendarza",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("typ", sa.String(length=16), nullable=False),
        sa.Column("godz_od", sa.Time(), nullable=True),
        sa.Column("godz_do", sa.Time(), nullable=True),
        sa.Column("ostatni_zasiadek", sa.Time(), nullable=True),
        sa.Column("dlugosc_slotu_min", sa.Integer(), nullable=True),
        sa.Column("nazwa", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_wyjatki_kalendarza_id", "wyjatki_kalendarza", ["id"])
    op.create_index("ix_wyjatki_kalendarza_data", "wyjatki_kalendarza", ["data"])


def downgrade() -> None:
    op.drop_index("ix_wyjatki_kalendarza_data", table_name="wyjatki_kalendarza")
    op.drop_index("ix_wyjatki_kalendarza_id", table_name="wyjatki_kalendarza")
    op.drop_table("wyjatki_kalendarza")
    with op.batch_alter_table("lokal_config") as batch:
        for nazwa, _ in reversed(_POLA):
            batch.drop_column(nazwa)
