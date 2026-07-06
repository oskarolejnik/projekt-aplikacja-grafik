"""Rejestracje lokalu oczekujące na płatność (instancja-matka): kreator → checkout → provision.

Tabela żyje na matce; instancje-dzieci dostają ją pustą (nieszkodliwe). external_id spina
rejestrację z płatnością i gwarantuje idempotencję realizacji.

Revision ID: 0035_rejestracje_lokalu
Revises: 0034_user_email
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0035_rejestracje_lokalu"
down_revision: Union[str, None] = "0034_user_email"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rejestracje_lokalu",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("haslo_hash", sa.String(length=255), nullable=False),
        sa.Column("nazwa", sa.String(length=120), nullable=False),
        sa.Column("typ_lokalu", sa.String(length=32), nullable=True),
        sa.Column("moduly", sa.JSON(), nullable=True),
        sa.Column("tier", sa.String(length=16), nullable=False, server_default="free"),
        sa.Column("netto", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="oczekuje"),
        sa.Column("external_id", sa.String(), nullable=False),
        sa.Column("slug", sa.String(length=40), nullable=True),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("utworzono_at", sa.DateTime(), nullable=True),
        sa.Column("zrealizowano_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_rejestracje_lokalu_email", "rejestracje_lokalu", ["email"])
    op.create_index("ix_rejestracje_lokalu_status", "rejestracje_lokalu", ["status"])
    op.create_index("ix_rejestracje_lokalu_external_id", "rejestracje_lokalu", ["external_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_rejestracje_lokalu_external_id", table_name="rejestracje_lokalu")
    op.drop_index("ix_rejestracje_lokalu_status", table_name="rejestracje_lokalu")
    op.drop_index("ix_rejestracje_lokalu_email", table_name="rejestracje_lokalu")
    op.drop_table("rejestracje_lokalu")
