"""Wielostolowe, czasowe holdy wspolnego allocatora R4.

Revision ID: 0060_r4_allocator_core
Revises: 0059_r3_reguly_dostepnosci
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0060_r4_allocator_core"
down_revision: Union[str, None] = "0059_r3_reguly_dostepnosci"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(bind) -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(bind).get_columns("lista_oczekujacych")
    }


def upgrade() -> None:
    bind = op.get_bind()
    existing = _columns(bind)
    additions = (
        sa.Column("hold_stoliki_dodatkowe", sa.JSON(), nullable=True),
        sa.Column("hold_godz_od", sa.Time(), nullable=True),
        sa.Column("hold_godz_do", sa.Time(), nullable=True),
        sa.Column("hold_bufor_min", sa.Integer(), nullable=True),
    )
    for column in additions:
        if column.name not in existing:
            op.add_column("lista_oczekujacych", column)


def downgrade() -> None:
    bind = op.get_bind()
    existing = _columns(bind)
    new_columns = {
        "hold_stoliki_dodatkowe", "hold_godz_od", "hold_godz_do", "hold_bufor_min",
    }
    if new_columns <= existing:
        configured = bind.execute(sa.text(
            "SELECT count(*) FROM lista_oczekujacych "
            "WHERE hold_stoliki_dodatkowe IS NOT NULL "
            "OR hold_godz_od IS NOT NULL OR hold_godz_do IS NOT NULL "
            "OR hold_bufor_min IS NOT NULL"
        )).scalar_one()
        if configured:
            raise RuntimeError("R4_DOWNGRADE_ACTIVE_MULTI_TABLE_HOLD_LOSS")
    for name in (
        "hold_bufor_min", "hold_godz_do", "hold_godz_od", "hold_stoliki_dodatkowe",
    ):
        if name in existing:
            op.drop_column("lista_oczekujacych", name)
