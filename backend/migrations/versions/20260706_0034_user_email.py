"""Kolumna users.email — logowanie e-mailem (nowy kanał); login zostaje wewnętrzny.

Nowe konta (właściciel z kreatora, pracownicy z zaproszenia) mają e-mail i logują się nim.
Stare konta bez e-maila (NULL) logują się dalej po login (fallback w /api/auth/login).
Na SQLite wiele NULL nie łamie UNIQUE, więc kolumnę dodajemy nullable + unikalny indeks.

Revision ID: 0034_user_email
Revises: 0033_push_native
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0034_user_email"
down_revision: Union[str, None] = "0033_push_native"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ADD COLUMN nullable jest natywnie wspierany przez SQLite — bez rekreacji tabeli (unikamy
    # ruszania FK wskazujących na users). Unikalny indeks osobno (NULL-e współistnieją).
    op.add_column("users", sa.Column("email", sa.String(length=255), nullable=True))
    op.create_index("ix_users_email", "users", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("email")
