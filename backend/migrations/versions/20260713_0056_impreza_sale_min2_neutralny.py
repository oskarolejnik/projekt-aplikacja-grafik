"""Neutralizacja server_default lokal_config.impreza_sale_min2: 'R2Piw,R2G' → '' (de-Rajculizacja).

'R2Piw,R2G' to kody sal jednego konkretnego lokalu (matka) wpisywane jako DB-default do
konfiguracji KAŻDEJ nowej instancji — relikt. Zmieniamy sam server_default; istniejące wiersze
(w tym matka) ZACHOWUJĄ swoją wartość. Nowe instancje dostają '' (brak sal specjalnych; ustawiane
per lokal w Ustawieniach). Zmiana nie dotyka nazwy kolumny → drift model↔migracja bez zmian.

Revision ID: 0056_impreza_sale_min2_neutralny
Revises: 0055_usun_imprezy_excel_mapa
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0056_impreza_sale_min2_neutralny"
down_revision: Union[str, None] = "0055_usun_imprezy_excel_mapa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("lokal_config") as batch:
        batch.alter_column("impreza_sale_min2", server_default="")


def downgrade() -> None:
    with op.batch_alter_table("lokal_config") as batch:
        batch.alter_column("impreza_sale_min2", server_default="R2Piw,R2G")
