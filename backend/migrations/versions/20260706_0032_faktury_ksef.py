"""Fakturowanie subskrypcji + KSeF FA(3) (monetyzacja Faza 3).

- lokal_config: dane firmowe lokalu jako nabywcy faktur (faktura_nip/nazwa/adres_l1/l2).
- faktury: faktura VAT za subskrypcję (numer, nabywca snapshot, kwoty, XML FA(3),
  numer KSeF + UPO, status).

Revision ID: 0032_faktury_ksef
Revises: 0031_billing_subskrypcji
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0032_faktury_ksef"
down_revision: Union[str, None] = "0031_billing_subskrypcji"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("lokal_config") as batch:
        batch.add_column(sa.Column("faktura_nip", sa.String(length=16), nullable=True))
        batch.add_column(sa.Column("faktura_nazwa", sa.String(length=256), nullable=True))
        batch.add_column(sa.Column("faktura_adres_l1", sa.String(length=256), nullable=True))
        batch.add_column(sa.Column("faktura_adres_l2", sa.String(length=256), nullable=True))

    op.create_table(
        "faktury",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("numer", sa.String(length=32), nullable=False),
        sa.Column("platnosc_id", sa.Integer(),
                  sa.ForeignKey("platnosci_subskrypcji.id", ondelete="SET NULL"), nullable=True),
        sa.Column("rodzaj", sa.String(length=8), nullable=False, server_default="VAT"),
        sa.Column("nabywca_nip", sa.String(length=16), nullable=True),
        sa.Column("nabywca_nazwa", sa.String(length=256), nullable=True),
        sa.Column("netto", sa.Float(), nullable=False, server_default="0"),
        sa.Column("vat", sa.Float(), nullable=False, server_default="0"),
        sa.Column("brutto", sa.Float(), nullable=False, server_default="0"),
        sa.Column("okres_od", sa.Date(), nullable=True),
        sa.Column("okres_do", sa.Date(), nullable=True),
        sa.Column("opis", sa.String(length=512), nullable=True),
        sa.Column("xml", sa.String(), nullable=True),
        sa.Column("ksef_number", sa.String(length=64), nullable=True),
        sa.Column("upo", sa.String(), nullable=True),
        sa.Column("status_ksef", sa.String(length=16), nullable=False, server_default="roboczy"),
        sa.Column("data_wystawienia", sa.Date(), nullable=True),
        sa.Column("utworzono_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("numer"),
    )


def downgrade() -> None:
    op.drop_table("faktury")
    with op.batch_alter_table("lokal_config") as batch:
        batch.drop_column("faktura_adres_l2")
        batch.drop_column("faktura_adres_l1")
        batch.drop_column("faktura_nazwa")
        batch.drop_column("faktura_nip")