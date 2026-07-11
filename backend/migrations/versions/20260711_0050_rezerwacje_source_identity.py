"""Proweniencja źródła rezerwacji dla kontrolowanego cutoveru.

Revision ID: 0050_rezerwacje_source_identity
Revises: 0049_uprawnienia_per_user
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0050_rezerwacje_source_identity"
down_revision: Union[str, None] = "0049_uprawnienia_per_user"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("terminy") as batch:
        batch.add_column(sa.Column("source_type", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("source_external_id", sa.String(length=512), nullable=True))
        batch.create_index(
            "uq_terminy_source_identity",
            ["source_type", "source_external_id"],
            unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("terminy") as batch:
        batch.drop_index("uq_terminy_source_identity")
        batch.drop_column("source_external_id")
        batch.drop_column("source_type")
