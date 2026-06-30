"""rezerwacje: stoliki, godziny_otwarcia, rozszerzenie Termin, modul_rezerwacje

Wprowadza moduł rezerwacji:
  • tabele `stoliki` i `godziny_otwarcia`,
  • rozszerzenie `terminy` (godz_od/godz_do/kanal/rodzaj/stolik_id/email/token + timestampy),
  • flagę `lokal_config.modul_rezerwacje`.

Backfill: istniejące `terminy` to wpisy kalendarza imprez → `rodzaj=impreza` (server_default);
`kanal=ical` dla rekordów z `ical_uid` (import .ics), w pozostałych `reczna`.

Revision ID: 0003_rezerwacje
Revises: 0002_lokal_config_rola
Create Date: 2026-06-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0003_rezerwacje'
down_revision: Union[str, None] = '0002_lokal_config_rola'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'godziny_otwarcia',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('dzien_tygodnia', sa.Integer(), nullable=False),
        sa.Column('godz_od', sa.Time(), nullable=False),
        sa.Column('godz_do', sa.Time(), nullable=False),
        sa.Column('ostatni_zasiadek', sa.Time(), nullable=True),
        sa.Column('dlugosc_slotu_min', sa.Integer(), nullable=False),
        sa.Column('aktywny', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('godziny_otwarcia', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_godziny_otwarcia_id'), ['id'], unique=False)

    op.create_table(
        'stoliki',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nazwa', sa.String(length=32), nullable=False),
        sa.Column('strefa', sa.String(length=32), nullable=True),
        sa.Column('pojemnosc', sa.Integer(), nullable=False),
        sa.Column('laczy_sie', sa.Boolean(), nullable=False),
        sa.Column('aktywny', sa.Boolean(), nullable=False),
        sa.Column('kolejnosc', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('stoliki', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_stoliki_id'), ['id'], unique=False)

    # Kolumna NOT NULL na istniejącej tabeli → server_default (istniejące lokale: moduł włączony).
    with op.batch_alter_table('lokal_config', schema=None) as batch_op:
        batch_op.add_column(sa.Column('modul_rezerwacje', sa.Boolean(), nullable=False,
                                      server_default=sa.true()))

    with op.batch_alter_table('terminy', schema=None) as batch_op:
        batch_op.add_column(sa.Column('godz_od', sa.Time(), nullable=True))
        batch_op.add_column(sa.Column('godz_do', sa.Time(), nullable=True))
        batch_op.add_column(sa.Column('kanal', sa.String(length=16), nullable=False,
                                      server_default='reczna'))
        batch_op.add_column(sa.Column('rodzaj', sa.String(length=16), nullable=False,
                                      server_default='impreza'))
        batch_op.add_column(sa.Column('stolik_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('email', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column('token_potwierdzenia', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('potwierdzono_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('odwolano_at', sa.DateTime(), nullable=True))
        batch_op.create_index(batch_op.f('ix_terminy_token_potwierdzenia'),
                              ['token_potwierdzenia'], unique=False)
        batch_op.create_foreign_key('fk_terminy_stolik_id', 'stoliki', ['stolik_id'], ['id'],
                                    ondelete='SET NULL')

    # Backfill: rekordy z importu .ics dostają kanal='ical' (reszta zostaje 'reczna').
    terminy = sa.table("terminy", sa.column("kanal", sa.String), sa.column("ical_uid", sa.String))
    op.execute(terminy.update().where(terminy.c.ical_uid.isnot(None)).values(kanal="ical"))


def downgrade() -> None:
    with op.batch_alter_table('terminy', schema=None) as batch_op:
        batch_op.drop_constraint('fk_terminy_stolik_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_terminy_token_potwierdzenia'))
        batch_op.drop_column('odwolano_at')
        batch_op.drop_column('potwierdzono_at')
        batch_op.drop_column('token_potwierdzenia')
        batch_op.drop_column('email')
        batch_op.drop_column('stolik_id')
        batch_op.drop_column('rodzaj')
        batch_op.drop_column('kanal')
        batch_op.drop_column('godz_do')
        batch_op.drop_column('godz_od')

    with op.batch_alter_table('lokal_config', schema=None) as batch_op:
        batch_op.drop_column('modul_rezerwacje')

    with op.batch_alter_table('stoliki', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_stoliki_id'))
    op.drop_table('stoliki')

    with op.batch_alter_table('godziny_otwarcia', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_godziny_otwarcia_id'))
    op.drop_table('godziny_otwarcia')
