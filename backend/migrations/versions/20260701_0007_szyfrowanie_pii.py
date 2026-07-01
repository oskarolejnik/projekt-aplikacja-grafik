"""szyfrowanie PII gosci at-rest — poszerzenie kolumn kontaktowych na szyfrogram

Pola telefon/email w `terminy` i `lista_oczekujacych` sa teraz szyfrowane (Fernet).
Szyfrogram jest dluzszy niz jawny tekst, wiec kolumny trzeba poszerzyc. Dotyczy tylko
PostgreSQL (egzekwuje dlugosc VARCHAR); SQLite ignoruje dlugosc, wiec tam no-op —
dzieki temu unikamy ryzykownego batch-recreate tabeli `terminy` (ma przychodzace FK).

Revision ID: 0007_szyfrowanie_pii
Revises: 0006_audit_log
Create Date: 2026-07-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0007_szyfrowanie_pii'
down_revision: Union[str, None] = '0006_audit_log'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_KOLUMNY = [
    ('terminy', 'telefon', 32),
    ('terminy', 'email', 128),
    ('lista_oczekujacych', 'telefon', 32),
    ('lista_oczekujacych', 'email', 128),
]


def upgrade() -> None:
    if op.get_bind().dialect.name != 'postgresql':
        return   # SQLite/inne: dlugosc nieegzekwowana — nic nie trzeba zmieniac
    for tabela, kol, stara in _KOLUMNY:
        op.alter_column(tabela, kol, existing_type=sa.String(length=stara),
                        type_=sa.String(length=512), existing_nullable=True)


def downgrade() -> None:
    if op.get_bind().dialect.name != 'postgresql':
        return
    for tabela, kol, stara in _KOLUMNY:
        op.alter_column(tabela, kol, existing_type=sa.String(length=512),
                        type_=sa.String(length=stara), existing_nullable=True)
