"""Zaproszenia pracowników + wyłączenie otwartej rejestracji.

- lokal_config.rejestracja_otwarta (Boolean, server_default '0'): publiczna
  samodzielna rejestracja pracownika jest od teraz DOMYŚLNIE wyłączona —
  konta zakłada się z linku-zaproszenia od managera. Instancje, które chcą
  zachować stare zachowanie, włączają flagę w konfiguracji lokalu.
- nowa tabela `zaproszenia`: jednorazowy token rejestracyjny przypięty do
  KONKRETNEGO pracownika z docelową rolą konta i terminem ważności.

Revision ID: 0024_zaproszenia
Revises: 0023_zaliczki
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0024_zaproszenia"
down_revision: Union[str, None] = "0023_zaliczki"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("lokal_config") as batch:
        batch.add_column(sa.Column("rejestracja_otwarta", sa.Boolean(),
                                   nullable=False, server_default=sa.text("0")))

    op.create_table(
        "zaproszenia",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("pracownik_id", sa.Integer(),
                  sa.ForeignKey("pracownicy.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rola", sa.String(length=16), nullable=False, server_default="employee"),
        sa.Column("utworzono_at", sa.DateTime(), nullable=False),
        sa.Column("wygasa_at", sa.DateTime(), nullable=False),
        sa.Column("uzyte_at", sa.DateTime(), nullable=True),
        sa.Column("utworzyl_login", sa.String(), nullable=True),
    )
    op.create_index("ix_zaproszenia_token", "zaproszenia", ["token"], unique=True)
    op.create_index("ix_zaproszenia_pracownik_id", "zaproszenia", ["pracownik_id"])


def downgrade() -> None:
    op.drop_index("ix_zaproszenia_pracownik_id", table_name="zaproszenia")
    op.drop_index("ix_zaproszenia_token", table_name="zaproszenia")
    op.drop_table("zaproszenia")
    with op.batch_alter_table("lokal_config") as batch:
        batch.drop_column("rejestracja_otwarta")
