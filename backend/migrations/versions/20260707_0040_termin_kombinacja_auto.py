"""Termin: stoły dodatkowe (kombinacja) + znacznik auto-przydziału (silnik sadzania).

`stoliki_dodatkowe` (JSON) trzyma stoły złączki poza wiodącym `stolik_id`, gdy rezerwację posadzono
na kombinacji. `auto_przydzielony` = audyt, czy stół dobrał algorytm. Oba NULLable — legacy-safe.

Revision ID: 0040_termin_kombinacja_auto
Revises: 0039_stoly_kombinacje
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0040_termin_kombinacja_auto"
down_revision: Union[str, None] = "0039_stoly_kombinacje"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("terminy") as batch:
        batch.add_column(sa.Column("stoliki_dodatkowe", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("auto_przydzielony", sa.Boolean(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("terminy") as batch:
        batch.drop_column("auto_przydzielony")
        batch.drop_column("stoliki_dodatkowe")
