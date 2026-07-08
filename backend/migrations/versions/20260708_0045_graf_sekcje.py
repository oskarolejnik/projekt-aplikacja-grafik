"""Graf sąsiedztwa stołów (auto-kombinacje) + sekcja kelnerska na Stoliku.

sasiedztwo_stolow = krawędzie grafu (które stoły da się złączyć); Stolik.sekcja = sekcja kelnerska
do balansu obłożenia w silniku sadzania. Wszystko NULLable/nowe — legacy-safe.

Revision ID: 0045_graf_sekcje
Revises: 0044_polityka_rezerwacji
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0045_graf_sekcje"
down_revision: Union[str, None] = "0044_polityka_rezerwacji"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("stoliki") as batch:
        batch.add_column(sa.Column("sekcja", sa.String(length=32), nullable=True))
    op.create_table(
        "sasiedztwo_stolow",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stolik_a", sa.Integer(), sa.ForeignKey("stoliki.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stolik_b", sa.Integer(), sa.ForeignKey("stoliki.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("stolik_a", "stolik_b", name="uq_sasiedztwo_para"),
    )
    op.create_index("ix_sasiedztwo_stolow_id", "sasiedztwo_stolow", ["id"])


def downgrade() -> None:
    op.drop_index("ix_sasiedztwo_stolow_id", table_name="sasiedztwo_stolow")
    op.drop_table("sasiedztwo_stolow")
    with op.batch_alter_table("stoliki") as batch:
        batch.drop_column("sekcja")
