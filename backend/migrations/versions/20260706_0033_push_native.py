"""Natywne tokeny push (aplikacja Capacitor — FCM/APNs) obok Web Push (monetyzacja Faza 5).

Revision ID: 0033_push_native
Revises: 0032_faktury_ksef
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0033_push_native"
down_revision: Union[str, None] = "0032_faktury_ksef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "push_device_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=True),
        sa.UniqueConstraint("token"),
    )
    op.create_index("ix_push_device_tokens_user_id", "push_device_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_push_device_tokens_user_id", table_name="push_device_tokens")
    op.drop_table("push_device_tokens")