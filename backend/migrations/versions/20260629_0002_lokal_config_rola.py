"""lokal_config + rola/daje_dostep_zamowien na stanowisku

Wprowadza:
  • tabelę `lokal_config` (singleton konfiguracji lokalu: branding, początek tygodnia, moduły),
  • kolumny `stanowiska.rola` i `stanowiska.daje_dostep_zamowien` (zastępują rozpoznawanie po nazwie).

Backfill (adopcja istniejących danych pierwszego wdrożenia): mapuje dawną konwencję nazw na role,
żeby po wdrożeniu zachowanie było IDENTYCZNE, a logika runtime mogła oprzeć się na flagach.

Revision ID: 0002_lokal_config_rola
Revises: 0001_baseline
Create Date: 2026-06-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002_lokal_config_rola'
down_revision: Union[str, None] = '0001_baseline'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'lokal_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nazwa_lokalu', sa.String(length=128), nullable=False),
        sa.Column('logo_url', sa.String(), nullable=True),
        sa.Column('kolor_primary', sa.String(length=16), nullable=True),
        sa.Column('poczatek_tygodnia', sa.Integer(), nullable=False),
        sa.Column('modul_rozliczenia', sa.Boolean(), nullable=False),
        sa.Column('modul_imprezy', sa.Boolean(), nullable=False),
        sa.Column('modul_pos', sa.Boolean(), nullable=False),
        sa.Column('modul_sprzatanie', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    # Kolumna NOT NULL dodawana do ISTNIEJĄCEJ tabeli → server_default, by istniejące wiersze
    # dostały wartość (False). Po backfillu zostawiamy default (nieszkodliwy; runtime i tak
    # ustawia jawnie). `rola` jest nullable, więc bez server_default (NULL = zwykłe stanowisko).
    with op.batch_alter_table('stanowiska', schema=None) as batch_op:
        batch_op.add_column(sa.Column('rola', sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column('daje_dostep_zamowien', sa.Boolean(),
                                      nullable=False, server_default=sa.false()))
        batch_op.create_index(batch_op.f('ix_stanowiska_rola'), ['rola'], unique=False)

    # --- Backfill: dawna logika „po nazwie" → flagi (portowalne UPDATE-y: SQLite i PostgreSQL). ---
    stanowiska = sa.table(
        "stanowiska",
        sa.column("nazwa", sa.String),
        sa.column("rola", sa.String),
        sa.column("daje_dostep_zamowien", sa.Boolean),
    )
    op.execute(stanowiska.update()
               .where(sa.func.lower(stanowiska.c.nazwa).like("sala%"))
               .values(rola="sala"))
    op.execute(stanowiska.update()
               .where(stanowiska.c.nazwa == "Kuchnia")
               .values(rola="kuchnia"))
    op.execute(stanowiska.update()
               .where(stanowiska.c.nazwa == "Techniczny")
               .values(rola="techniczny"))
    op.execute(stanowiska.update()
               .where(sa.func.lower(stanowiska.c.nazwa).like("imprez%"))
               .values(rola="imprezy"))
    op.execute(stanowiska.update()
               .where(stanowiska.c.nazwa == "Sprzątaczka")
               .values(daje_dostep_zamowien=True))


def downgrade() -> None:
    with op.batch_alter_table('stanowiska', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_stanowiska_rola'))
        batch_op.drop_column('daje_dostep_zamowien')
        batch_op.drop_column('rola')

    op.drop_table('lokal_config')
