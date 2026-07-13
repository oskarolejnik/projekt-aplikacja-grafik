"""Usunięcie kolumny lokal_config.imprezy_excel_mapa (relikt importu xlsx imprez).

Import imprez z plików .xlsx (skan NAS + ingest z laptopa) został wycofany —
mapowanie komórek Excela (J1/H8/J2) nie ma już konsumenta. Kolumna imprezy_mapa_sal
ZOSTAJE (używa jej moduł sprzątania). Kolumna była nullable (NULL = domyślne komórki),
więc usunięcie nie zmienia zachowania żadnego istniejącego wdrożenia.

Revision ID: 0055_usun_imprezy_excel_mapa
Revises: 0054_room_name_key
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0055_usun_imprezy_excel_mapa"
down_revision: Union[str, None] = "0054_room_name_key"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _ma_kolumne() -> bool:
    kolumny = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("lokal_config")}
    return "imprezy_excel_mapa" in kolumny


def upgrade() -> None:
    # Idempotentnie: bazy zaadoptowane z create_all (aktualny models.py) już nie mają tej
    # kolumny — wtedy drop byłby KeyError. Dropujemy tylko, gdy kolumna faktycznie istnieje.
    if _ma_kolumne():
        with op.batch_alter_table("lokal_config") as batch:
            batch.drop_column("imprezy_excel_mapa")


def downgrade() -> None:
    if not _ma_kolumne():
        with op.batch_alter_table("lokal_config") as batch:
            batch.add_column(sa.Column("imprezy_excel_mapa", sa.JSON(), nullable=True))
