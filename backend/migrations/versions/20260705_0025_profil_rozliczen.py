"""Profil rozliczeń i imprez per lokal (de-Rajculizacja, krok 1).

Nowe kolumny lokal_config — defaulty odtwarzają dokładnie dotychczasowe
zachowanie (Rajcula), więc migracja nie zmienia niczego behawioralnie:

- impreza_osobne_rozliczenie ('1'): imprezy rozliczane osobno (IMP z kas,
  wiersze w zeszycie, kafelek na pulpicie); '0' = imprezy w ogólnym obrocie.
- rozliczenia_tryb_kelnera ('indywidualnie'): każdy kelner deklaruje G/T;
  'pula' = wspólna pula sali (silnik w przygotowaniu).
- rozliczenia_nazwy_kas / rozliczenia_nazwy_terminali (NULL = wolny wpis):
  predefiniowane etykiety (listy JSON) → dropdowny w Rozliczeniu dnia.
- grafik_cykl ('tydzien'): cykl układania grafiku; 'miesiac' w przygotowaniu.

Revision ID: 0025_profil_rozliczen
Revises: 0024_zaproszenia
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0025_profil_rozliczen"
down_revision: Union[str, None] = "0024_zaproszenia"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("lokal_config") as batch:
        batch.add_column(sa.Column("impreza_osobne_rozliczenie", sa.Boolean(),
                                   nullable=False, server_default=sa.text("1")))
        batch.add_column(sa.Column("rozliczenia_tryb_kelnera", sa.String(length=16),
                                   nullable=False, server_default="indywidualnie"))
        batch.add_column(sa.Column("rozliczenia_nazwy_kas", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("rozliczenia_nazwy_terminali", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("grafik_cykl", sa.String(length=16),
                                   nullable=False, server_default="tydzien"))


def downgrade() -> None:
    with op.batch_alter_table("lokal_config") as batch:
        batch.drop_column("grafik_cykl")
        batch.drop_column("rozliczenia_nazwy_terminali")
        batch.drop_column("rozliczenia_nazwy_kas")
        batch.drop_column("rozliczenia_tryb_kelnera")
        batch.drop_column("impreza_osobne_rozliczenie")
