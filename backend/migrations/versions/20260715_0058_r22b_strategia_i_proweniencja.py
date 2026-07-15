"""Strategia sal i trwała proweniencja przydziału R2.2b.

Revision ID: 0058_r22b_strategia_proweniencja
Revises: 0057_r22_topologia_planu
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0058_r22b_strategia_proweniencja"
down_revision: Union[str, None] = "0057_r22_topologia_planu"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # SQLite nie może bezpiecznie przebudować tej tabeli przy aktywnych FK z
    # ``stoliki``, ``plany_sali`` i historycznych ``terminy``. Oba CHECK-i są
    # dlatego częścią natywnego, addytywnego ADD COLUMN. PostgreSQL dostaje
    # równoważne nazwane ograniczenia bez kopiowania tabeli.
    if bind.dialect.name == "sqlite":
        op.execute(
            "ALTER TABLE sale_rezerwacyjne ADD COLUMN "
            "strategia_zapelniania VARCHAR(24) NOT NULL DEFAULT 'preferuj' "
            "CONSTRAINT ck_sale_rezerwacyjne_strategia_zapelniania "
            "CHECK (strategia_zapelniania IN ('preferuj', 'wypelniaj_kolejno'))"
        )
        op.execute(
            "ALTER TABLE sale_rezerwacyjne ADD COLUMN "
            "priorytet INTEGER NOT NULL DEFAULT 0 "
            "CONSTRAINT ck_sale_rezerwacyjne_priorytet CHECK (priorytet >= 0)"
        )
    else:
        op.add_column("sale_rezerwacyjne", sa.Column(
            "strategia_zapelniania",
            sa.String(length=24),
            nullable=False,
            server_default="preferuj",
        ))
        op.add_column("sale_rezerwacyjne", sa.Column(
            "priorytet", sa.Integer(), nullable=False, server_default="0",
        ))
        op.create_check_constraint(
            "ck_sale_rezerwacyjne_strategia_zapelniania",
            "sale_rezerwacyjne",
            "strategia_zapelniania IN ('preferuj', 'wypelniaj_kolejno')",
        )
        op.create_check_constraint(
            "ck_sale_rezerwacyjne_priorytet",
            "sale_rezerwacyjne",
            "priorytet >= 0",
        )

    # Dotychczasowa kolejność jest jedyną bezpieczną wskazówką priorytetu. Tryb
    # pozostaje miękki, więc migracja nie wprowadza nagle ścisłego filtrowania.
    op.execute(sa.text(
        "UPDATE sale_rezerwacyjne SET priorytet = kolejnosc"
    ))

    # ``terminy`` ma wiele tabel potomnych, więc jego rebuild przy włączonych FK
    # jest tak samo niebezpieczny. SQLite dostaje dwa natywne FK oraz triggery
    # pilnujące pary (kombinacja, wersja); PostgreSQL używa kompozytowego FK.
    if bind.dialect.name == "sqlite":
        op.execute(
            "ALTER TABLE terminy ADD COLUMN przydzial_wersja_planu_id INTEGER "
            "CONSTRAINT fk_terminy_przydzial_wersja_planu "
            "REFERENCES wersje_planu_sali(id) ON DELETE RESTRICT"
        )
        op.execute(
            "ALTER TABLE terminy ADD COLUMN przydzial_kombinacja_planu_id INTEGER "
            "CONSTRAINT fk_terminy_przydzial_kombinacja_planu "
            "REFERENCES kombinacje_stolow_planu(id) ON DELETE RESTRICT "
            "CONSTRAINT ck_terminy_przydzial_kombinacja_wymaga_wersji "
            "CHECK (przydzial_kombinacja_planu_id IS NULL "
            "OR przydzial_wersja_planu_id IS NOT NULL)"
        )
        op.execute(sa.text(
            "CREATE TRIGGER fk_terminy_przydzial_kombinacja_wersja_insert "
            "BEFORE INSERT ON terminy "
            "WHEN NEW.przydzial_kombinacja_planu_id IS NOT NULL "
            "AND NOT EXISTS ("
            "SELECT 1 FROM kombinacje_stolow_planu k "
            "WHERE k.id = NEW.przydzial_kombinacja_planu_id "
            "AND k.wersja_id = NEW.przydzial_wersja_planu_id"
            ") BEGIN SELECT RAISE(ABORT, "
            "'przydzial combination/version mismatch'); END"
        ))
        op.execute(sa.text(
            "CREATE TRIGGER fk_terminy_przydzial_kombinacja_wersja_update "
            "BEFORE UPDATE OF przydzial_kombinacja_planu_id, "
            "przydzial_wersja_planu_id ON terminy "
            "WHEN NEW.przydzial_kombinacja_planu_id IS NOT NULL "
            "AND NOT EXISTS ("
            "SELECT 1 FROM kombinacje_stolow_planu k "
            "WHERE k.id = NEW.przydzial_kombinacja_planu_id "
            "AND k.wersja_id = NEW.przydzial_wersja_planu_id"
            ") BEGIN SELECT RAISE(ABORT, "
            "'przydzial combination/version mismatch'); END"
        ))
    else:
        op.add_column("terminy", sa.Column(
            "przydzial_wersja_planu_id", sa.Integer(), nullable=True,
        ))
        op.add_column("terminy", sa.Column(
            "przydzial_kombinacja_planu_id", sa.Integer(), nullable=True,
        ))
        op.create_foreign_key(
            "fk_terminy_przydzial_wersja_planu",
            "terminy",
            "wersje_planu_sali",
            ["przydzial_wersja_planu_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_foreign_key(
            "fk_terminy_przydzial_kombinacja_wersja",
            "terminy",
            "kombinacje_stolow_planu",
            ["przydzial_kombinacja_planu_id", "przydzial_wersja_planu_id"],
            ["id", "wersja_id"],
            ondelete="RESTRICT",
        )
        op.create_check_constraint(
            "ck_terminy_przydzial_kombinacja_wymaga_wersji",
            "terminy",
            "przydzial_kombinacja_planu_id IS NULL "
            "OR przydzial_wersja_planu_id IS NOT NULL",
        )

    op.create_index(
        "ix_terminy_przydzial_wersja_planu_id",
        "terminy",
        ["przydzial_wersja_planu_id"],
    )
    op.create_index(
        "ix_terminy_przydzial_kombinacja_planu_id",
        "terminy",
        ["przydzial_kombinacja_planu_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_index(
        "ix_terminy_przydzial_kombinacja_planu_id", table_name="terminy",
    )
    op.drop_index(
        "ix_terminy_przydzial_wersja_planu_id", table_name="terminy",
    )
    if bind.dialect.name == "sqlite":
        op.execute(
            "DROP TRIGGER IF EXISTS fk_terminy_przydzial_kombinacja_wersja_update"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS fk_terminy_przydzial_kombinacja_wersja_insert"
        )
        op.execute(
            "ALTER TABLE terminy DROP COLUMN przydzial_kombinacja_planu_id"
        )
        op.execute("ALTER TABLE terminy DROP COLUMN przydzial_wersja_planu_id")
    else:
        op.drop_constraint(
            "ck_terminy_przydzial_kombinacja_wymaga_wersji", type_="check",
            table_name="terminy",
        )
        op.drop_constraint(
            "fk_terminy_przydzial_kombinacja_wersja", type_="foreignkey",
            table_name="terminy",
        )
        op.drop_constraint(
            "fk_terminy_przydzial_wersja_planu", type_="foreignkey",
            table_name="terminy",
        )
        op.drop_column("terminy", "przydzial_kombinacja_planu_id")
        op.drop_column("terminy", "przydzial_wersja_planu_id")

    if bind.dialect.name == "sqlite":
        op.execute("ALTER TABLE sale_rezerwacyjne DROP COLUMN priorytet")
        op.execute(
            "ALTER TABLE sale_rezerwacyjne DROP COLUMN strategia_zapelniania"
        )
    else:
        op.drop_constraint(
            "ck_sale_rezerwacyjne_priorytet", type_="check",
            table_name="sale_rezerwacyjne",
        )
        op.drop_constraint(
            "ck_sale_rezerwacyjne_strategia_zapelniania", type_="check",
            table_name="sale_rezerwacyjne",
        )
        op.drop_column("sale_rezerwacyjne", "priorytet")
        op.drop_column("sale_rezerwacyjne", "strategia_zapelniania")
