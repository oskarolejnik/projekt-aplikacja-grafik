"""Profil gościa 360 (tabela profile_gosci): tagi/VIP, alergie (szyfrowane, RODO art. 9),
preferencje, okazje. Klucz = sha256 znormalizowanego telefonu (bez plaintextu PII w indeksie).

Revision ID: 0042_profil_goscia
Revises: 0041_termin_faza_hosta
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0042_profil_goscia"
down_revision: Union[str, None] = "0041_termin_faza_hosta"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "profile_gosci",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("klucz_hash", sa.String(length=64), nullable=False),
        sa.Column("nazwisko", sa.String(length=128), nullable=True),
        sa.Column("telefon", sa.String(length=512), nullable=True),
        sa.Column("email", sa.String(length=512), nullable=True),
        sa.Column("tagi", sa.JSON(), nullable=True),
        sa.Column("vip", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("alergie", sa.String(length=512), nullable=True),
        sa.Column("dieta", sa.String(length=128), nullable=True),
        sa.Column("preferowana_strefa", sa.String(length=64), nullable=True),
        sa.Column("notatka", sa.String(length=1024), nullable=True),
        sa.Column("okazja_typ", sa.String(length=32), nullable=True),
        sa.Column("okazja_data", sa.String(length=5), nullable=True),
        sa.Column("marketing_zgoda", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("utworzono_at", sa.DateTime(), nullable=True),
        sa.Column("zaktualizowano_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_profile_gosci_id", "profile_gosci", ["id"])
    op.create_index("ix_profile_gosci_klucz_hash", "profile_gosci", ["klucz_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_profile_gosci_klucz_hash", table_name="profile_gosci")
    op.drop_index("ix_profile_gosci_id", table_name="profile_gosci")
    op.drop_table("profile_gosci")
