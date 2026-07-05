"""Token agenta POS per lokal (kreator „Podłącz POS" w panelu).

lokal_config.pos_token_hash (SHA-256) + pos_token_od: token generowany w panelu,
plaintext pokazywany JEDEN raz, unieważnialny. Env RCP_INGEST_TOKEN zostaje jako
fallback (wdrożone agenty przeżywają deploy).

Revision ID: 0027_token_agenta
Revises: 0026_utarg_pos
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0027_token_agenta"
down_revision: Union[str, None] = "0026_utarg_pos"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("lokal_config") as batch:
        batch.add_column(sa.Column("pos_token_hash", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("pos_token_od", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("lokal_config") as batch:
        batch.drop_column("pos_token_od")
        batch.drop_column("pos_token_hash")
