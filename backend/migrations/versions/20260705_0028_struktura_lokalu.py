"""Struktura lokalu per konfiguracja (de-Rajculizacja, kroki 3–4).

Nowe kolumny lokal_config (wszystkie NULLable — NULL = dokładnie dotychczasowe
wartości zaszyte w kodzie, więc migracja niczego nie zmienia behawioralnie):
sale, sprzatanie_sale_codziennie, sprzatanie_sala_niedziela (pusty string =
reguła wyłączona), imprezy_mapa_sal, imprezy_excel_mapa (komórki J1/H8/J2),
zeszyt_kolumny, pos_mapa_rewirow (mapowanie rewirów NGastro na widok stołów).

Revision ID: 0028_struktura_lokalu
Revises: 0027_token_agenta
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0028_struktura_lokalu"
down_revision: Union[str, None] = "0027_token_agenta"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

KOLUMNY = (
    ("sale", sa.JSON()),
    ("sprzatanie_sale_codziennie", sa.JSON()),
    ("sprzatanie_sala_niedziela", sa.String(length=32)),
    ("imprezy_mapa_sal", sa.JSON()),
    ("imprezy_excel_mapa", sa.JSON()),
    ("zeszyt_kolumny", sa.JSON()),
    ("pos_mapa_rewirow", sa.JSON()),
)


def upgrade() -> None:
    with op.batch_alter_table("lokal_config") as batch:
        for nazwa, typ in KOLUMNY:
            batch.add_column(sa.Column(nazwa, typ, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("lokal_config") as batch:
        for nazwa, _ in reversed(KOLUMNY):
            batch.drop_column(nazwa)
