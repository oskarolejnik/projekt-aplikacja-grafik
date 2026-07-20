"""RCP mobilne (geofencing): pracownik odbija start/koniec zmiany telefonem.

lokal_config: włącznik + położenie lokalu + promień strefy. odbicia_rcp: współrzędne
odbić z telefonu (ślad audytowy; NULL dla odbić z agenta POS). Defensywnie: bazy
adoptowane przez create_all mogą już mieć kolumny — dodajemy tylko brakujące.

UWAGA: celowo BEZ batch_alter_table — batch przebudowuje tabelę na SQLite, a przy
przebudowie kolumnowe CHECK-i (np. ck_lokal_config_rezerwacje_przypomnienie_h z 0062)
stają się tabelowe i łamią downgrade starszych migracji (DROP COLUMN nie może usunąć
kolumny, do której odwołuje się CHECK tabelowy). Zwykłe ADD/DROP COLUMN wystarcza —
nowe kolumny nie mają constraintów ani indeksów.

Revision ID: 0067_rcp_geofencing
Revises: 0066_r72_reservation_demand
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0067_rcp_geofencing"
down_revision: Union[str, None] = "0066_r72_reservation_demand"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_LOKAL_CONFIG = (
    ("rcp_mobilne", sa.Boolean(), False, sa.text("false")),
    ("rcp_geo_lat", sa.Float(), True, None),
    ("rcp_geo_lng", sa.Float(), True, None),
    ("rcp_geo_promien_m", sa.Integer(), False, "150"),
)
_ODBICIA = (
    ("wejscie_lat", sa.Float(), True, None),
    ("wejscie_lng", sa.Float(), True, None),
    ("wejscie_dokladnosc_m", sa.Float(), True, None),
    ("wyjscie_lat", sa.Float(), True, None),
    ("wyjscie_lng", sa.Float(), True, None),
    ("wyjscie_dokladnosc_m", sa.Float(), True, None),
)


def _istniejace(bind, tabela: str) -> set:
    return {c["name"] for c in sa.inspect(bind).get_columns(tabela)}


def upgrade() -> None:
    bind = op.get_bind()
    for tabela, kolumny in (("lokal_config", _LOKAL_CONFIG), ("odbicia_rcp", _ODBICIA)):
        obecne = _istniejace(bind, tabela)
        for nazwa, typ, nullable, default in kolumny:
            if nazwa not in obecne:
                op.add_column(tabela, sa.Column(nazwa, typ, nullable=nullable, server_default=default))


def downgrade() -> None:
    bind = op.get_bind()
    for tabela, kolumny in (("odbicia_rcp", _ODBICIA), ("lokal_config", _LOKAL_CONFIG)):
        obecne = _istniejace(bind, tabela)
        for nazwa, _typ, _nullable, _default in reversed(kolumny):
            if nazwa in obecne:
                op.drop_column(tabela, nazwa)
