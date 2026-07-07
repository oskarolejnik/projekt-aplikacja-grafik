"""Dedup karty na poziomie bazy: częściowy UNIQUE index na karta_fingerprint dla aktywnych
statusów — domyka wyścig TOCTOU (dwa równoległe trialy z tej samej karty).

Revision ID: 0037_dedup_karta_unique
Revises: 0036_karta_trial
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0037_dedup_karta_unique"
down_revision: Union[str, None] = "0036_karta_trial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_WHERE = "karta_fingerprint IS NOT NULL AND status IN ('przetwarzanie','zrealizowana')"


def upgrade() -> None:
    op.create_index(
        "uq_rejestracje_karta_aktywne", "rejestracje_lokalu", ["karta_fingerprint"], unique=True,
        sqlite_where=sa.text(_WHERE), postgresql_where=sa.text(_WHERE),
    )


def downgrade() -> None:
    op.drop_index("uq_rejestracje_karta_aktywne", table_name="rejestracje_lokalu")
