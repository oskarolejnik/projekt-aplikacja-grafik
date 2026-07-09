"""RejestracjaLokalu.sale — sale/strefy lokalu zebrane w kreatorze (wpinają się w sprzątanie + rezerwacje).

Kolumna JSON nullable (lista nazw sal). Legacy-safe: NULL = kreator ich nie zebrał → neutralny default.

Revision ID: 0047_rejestracja_sale
Revises: 0046_waitlist_hold
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0047_rejestracja_sale"
down_revision: Union[str, None] = "0046_waitlist_hold"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("rejestracje_lokalu") as batch:
        batch.add_column(sa.Column("sale", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("rejestracje_lokalu") as batch:
        batch.drop_column("sale")
