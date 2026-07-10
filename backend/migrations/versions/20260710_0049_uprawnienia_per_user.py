"""Wyjątki uprawnień per konto użytkownika.

Revision ID: 0049_uprawnienia_per_user
Revises: 0048_polityka_zadatku
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0049_uprawnienia_per_user"
down_revision: Union[str, None] = "0048_polityka_zadatku"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("uprawnienia_override", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("uprawnienia_override")
