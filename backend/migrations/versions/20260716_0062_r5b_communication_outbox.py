"""R5b transactional reservation communication outbox.

Revision ID: 0062_r5b_communication_outbox
Revises: 0061_r5a_public_security
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0062_r5b_communication_outbox"
down_revision: Union[str, None] = "0061_r5a_public_security"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Inline CHECK pozwala SQLite wykonać bezpieczne ALTER TABLE ADD COLUMN bez
    # przebudowy rozległej tabeli ``terminy`` (jej historyczna kolejność kolumn
    # zawiera relacje partial_reordering, których Alembic nie potrafi sortować).
    op.add_column("terminy", sa.Column(
        "kanal_komunikacji",
        sa.String(length=8),
        sa.CheckConstraint(
            "kanal_komunikacji IN ('auto', 'email', 'sms', 'oba', 'brak')",
            name="ck_terminy_kanal_komunikacji",
        ),
        nullable=False,
        server_default="auto",
    ))
    op.add_column("lista_oczekujacych", sa.Column(
        "kanal_komunikacji",
        sa.String(length=8),
        sa.CheckConstraint(
            "kanal_komunikacji IN ('auto', 'email', 'sms', 'oba', 'brak')",
            name="ck_lista_oczekujacych_kanal_komunikacji",
        ),
        nullable=False,
        server_default="auto",
    ))
    op.add_column("lokal_config", sa.Column(
        "rezerwacje_przypomnienie_h",
        sa.Integer(),
        sa.CheckConstraint(
            "rezerwacje_przypomnienie_h >= 0 "
            "AND rezerwacje_przypomnienie_h <= 168",
            name="ck_lokal_config_rezerwacje_przypomnienie_h",
        ),
        nullable=False,
        server_default="0",
    ))

    op.create_table(
        "rezerwacje_wiadomosci_outbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "termin_id", sa.Integer(),
            sa.ForeignKey("terminy.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column(
            "waitlist_id", sa.Integer(),
            sa.ForeignKey("lista_oczekujacych.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("subject_phone_ref", sa.String(length=64), nullable=True),
        sa.Column("subject_email_ref", sa.String(length=64), nullable=True),
        sa.Column("dedupe_key", sa.String(length=64), nullable=False),
        sa.Column("typ_zdarzenia", sa.String(length=24), nullable=False),
        sa.Column("kanal", sa.String(length=8), nullable=False),
        # EncryptedString/EncryptedText are stored as portable String/Text DDL.
        sa.Column("odbiorca", sa.String(length=1024), nullable=False),
        sa.Column("temat", sa.Text(), nullable=True),
        sa.Column("tresc", sa.Text(), nullable=False),
        sa.Column("template_key", sa.String(length=32), nullable=False),
        sa.Column("template_version", sa.String(length=16), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column(
            "provider_idempotency_key", sa.String(length=64), nullable=False,
        ),
        sa.Column(
            "provider_supports_idempotency", sa.Boolean(), nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "provider_idempotency_header", sa.String(length=128), nullable=True,
        ),
        sa.Column(
            "stan", sa.String(length=16), nullable=False,
            server_default="queued",
        ),
        sa.Column(
            "liczba_prob", sa.Integer(), nullable=False, server_default="0",
        ),
        sa.Column(
            "maks_prob", sa.Integer(), nullable=False, server_default="5",
        ),
        sa.Column("available_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("lease_token", sa.String(length=64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "actor_kind", sa.String(length=16), nullable=False,
            server_default="system",
        ),
        sa.Column(
            "actor_user_id", sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("uncertain_at", sa.DateTime(), nullable=True),
        sa.Column("reconciled_at", sa.DateTime(), nullable=True),
        sa.Column(
            "reconciled_by_user_id", sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("reconciliation_note", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "dedupe_key", "kanal",
            name="uq_rezerwacje_wiadomosci_outbox_dedupe_kanal",
        ),
        sa.UniqueConstraint(
            "provider_idempotency_key",
            name="uq_rezerwacje_wiadomosci_outbox_provider_idempotency_key",
        ),
        sa.CheckConstraint(
            "(termin_id IS NOT NULL AND waitlist_id IS NULL) OR "
            "(termin_id IS NULL AND waitlist_id IS NOT NULL)",
            name="ck_rezerwacje_wiadomosci_outbox_owner",
        ),
        sa.CheckConstraint(
            "typ_zdarzenia IN ('confirmation', 'reminder', 'change', "
            "'cancellation', 'table_ready')",
            name="ck_rezerwacje_wiadomosci_outbox_typ",
        ),
        sa.CheckConstraint(
            "kanal IN ('email', 'sms')",
            name="ck_rezerwacje_wiadomosci_outbox_kanal",
        ),
        sa.CheckConstraint(
            "stan IN ('queued', 'processing', 'retry', 'sent', 'failed', "
            "'uncertain', 'cancelled', 'expired')",
            name="ck_rezerwacje_wiadomosci_outbox_stan",
        ),
        sa.CheckConstraint(
            "liczba_prob >= 0 AND maks_prob >= 1",
            name="ck_rezerwacje_wiadomosci_outbox_proby",
        ),
        sa.CheckConstraint(
            "length(provider_idempotency_key) = 64",
            name="ck_rezerwacje_wiadomosci_outbox_provider_key",
        ),
        sa.CheckConstraint(
            "length(dedupe_key) = 64",
            name="ck_rezerwacje_wiadomosci_outbox_dedupe_key",
        ),
        sa.CheckConstraint(
            "subject_phone_ref IS NOT NULL OR subject_email_ref IS NOT NULL",
            name="ck_rezerwacje_wiadomosci_outbox_subject_ref",
        ),
        sa.CheckConstraint(
            "subject_phone_ref IS NULL OR length(subject_phone_ref) = 64",
            name="ck_rezerwacje_wiadomosci_outbox_subject_phone_ref",
        ),
        sa.CheckConstraint(
            "subject_email_ref IS NULL OR length(subject_email_ref) = 64",
            name="ck_rezerwacje_wiadomosci_outbox_subject_email_ref",
        ),
        sa.CheckConstraint(
            "(provider_supports_idempotency = false AND "
            "provider_idempotency_header IS NULL) OR "
            "(provider_supports_idempotency = true AND "
            "provider_idempotency_header IS NOT NULL)",
            name="ck_rezerwacje_wiadomosci_outbox_provider_contract",
        ),
        sa.CheckConstraint(
            "actor_kind IN ('system', 'user', 'guest')",
            name="ck_rezerwacje_wiadomosci_outbox_actor",
        ),
        sa.CheckConstraint(
            "available_at < expires_at",
            name="ck_rezerwacje_wiadomosci_outbox_deadline",
        ),
        sa.CheckConstraint(
            "(stan = 'processing' AND lease_token IS NOT NULL "
            "AND lease_expires_at IS NOT NULL) OR "
            "(stan <> 'processing' AND lease_token IS NULL "
            "AND lease_expires_at IS NULL)",
            name="ck_rezerwacje_wiadomosci_outbox_lease_lifecycle",
        ),
        sa.CheckConstraint(
            "stan <> 'sent' OR sent_at IS NOT NULL",
            name="ck_rezerwacje_wiadomosci_outbox_sent_lifecycle",
        ),
        sa.CheckConstraint(
            "stan <> 'uncertain' OR uncertain_at IS NOT NULL",
            name="ck_rezerwacje_wiadomosci_outbox_uncertain_lifecycle",
        ),
        sa.CheckConstraint(
            "(reconciled_at IS NULL AND reconciled_by_user_id IS NULL "
            "AND reconciliation_note IS NULL) OR "
            "(reconciled_at IS NOT NULL AND reconciliation_note IS NOT NULL)",
            name="ck_rezerwacje_wiadomosci_outbox_reconciliation",
        ),
    )
    op.create_index(
        "ix_rezerwacje_wiadomosci_outbox_termin_id",
        "rezerwacje_wiadomosci_outbox", ["termin_id"],
    )
    op.create_index(
        "ix_rezerwacje_wiadomosci_outbox_waitlist_id",
        "rezerwacje_wiadomosci_outbox", ["waitlist_id"],
    )
    op.create_index(
        "ix_rezerwacje_wiadomosci_outbox_due",
        "rezerwacje_wiadomosci_outbox", ["stan", "available_at", "id"],
    )
    op.create_index(
        "ix_rezerwacje_wiadomosci_outbox_lease",
        "rezerwacje_wiadomosci_outbox", ["stan", "lease_expires_at"],
    )
    op.create_index(
        "ix_rezerwacje_wiadomosci_outbox_subject_phone_ref",
        "rezerwacje_wiadomosci_outbox", ["subject_phone_ref", "id"],
    )
    op.create_index(
        "ix_rezerwacje_wiadomosci_outbox_subject_email_ref",
        "rezerwacje_wiadomosci_outbox", ["subject_email_ref", "id"],
    )

    op.create_table(
        "rezerwacje_wiadomosci_proby",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "wiadomosc_id", sa.Integer(),
            sa.ForeignKey("rezerwacje_wiadomosci_outbox.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("numer", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column(
            "provider_idempotency_key", sa.String(length=64), nullable=False,
        ),
        sa.Column(
            "provider_supports_idempotency", sa.Boolean(), nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "provider_idempotency_header", sa.String(length=128), nullable=True,
        ),
        sa.Column("lease_token", sa.String(length=64), nullable=False),
        sa.Column("claimed_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column(
            "wynik", sa.String(length=24), nullable=False,
            server_default="claimed",
        ),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("provider_message_id", sa.String(length=512), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("retry_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint(
            "wiadomosc_id", "numer",
            name="uq_rezerwacje_wiadomosci_proby_numer",
        ),
        sa.CheckConstraint(
            "numer >= 1",
            name="ck_rezerwacje_wiadomosci_proby_numer",
        ),
        sa.CheckConstraint(
            "wynik IN ('claimed', 'processing', 'sent', 'retry', 'failed', "
            "'uncertain')",
            name="ck_rezerwacje_wiadomosci_proby_wynik",
        ),
        sa.CheckConstraint(
            "(wynik = 'claimed' AND started_at IS NULL AND finished_at IS NULL) OR "
            "(wynik = 'processing' AND started_at IS NOT NULL AND finished_at IS NULL) OR "
            "(wynik NOT IN ('claimed', 'processing') AND finished_at IS NOT NULL)",
            name="ck_rezerwacje_wiadomosci_proby_lifecycle",
        ),
        sa.CheckConstraint(
            "(wynik = 'retry' AND retry_at IS NOT NULL) OR "
            "(wynik <> 'retry' AND retry_at IS NULL)",
            name="ck_rezerwacje_wiadomosci_proby_retry",
        ),
        sa.CheckConstraint(
            "(provider_supports_idempotency = false AND "
            "provider_idempotency_header IS NULL) OR "
            "(provider_supports_idempotency = true AND "
            "provider_idempotency_header IS NOT NULL)",
            name="ck_rezerwacje_wiadomosci_proby_provider_contract",
        ),
    )
    op.create_index(
        "ix_rezerwacje_wiadomosci_proby_wiadomosc_started",
        "rezerwacje_wiadomosci_proby", ["wiadomosc_id", "started_at"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    # Downgrade jest dozwolony wyłącznie, dopóki R5b pozostaje przy bezpiecznych
    # defaultach. Utrata ``brak`` lub innej preferencji kanału mogłaby po ponownym
    # upgrade wznowić komunikację wbrew zapisanej decyzji gościa. Na PostgreSQL
    # blokada zamyka wyścig między sprawdzeniem a DROP; dla SQLite wdrożenie nadal
    # musi zatrzymać procesy aplikacji, bo Alembic wykonuje tam DDL nietransakcyjnie.
    if connection.dialect.name == "postgresql":
        connection.execute(sa.text(
            "LOCK TABLE rezerwacje_wiadomosci_proby, "
            "rezerwacje_wiadomosci_outbox, terminy, lista_oczekujacych, "
            "lokal_config IN ACCESS EXCLUSIVE MODE"
        ))
    has_r5b_data = connection.execute(sa.text(
        "SELECT 1 FROM rezerwacje_wiadomosci_outbox "
        "UNION ALL SELECT 1 FROM rezerwacje_wiadomosci_proby "
        "UNION ALL SELECT 1 FROM terminy "
        "WHERE kanal_komunikacji IS NULL OR kanal_komunikacji <> 'auto' "
        "UNION ALL SELECT 1 FROM lista_oczekujacych "
        "WHERE kanal_komunikacji IS NULL OR kanal_komunikacji <> 'auto' "
        "UNION ALL SELECT 1 FROM lokal_config "
        "WHERE rezerwacje_przypomnienie_h IS NULL "
        "OR rezerwacje_przypomnienie_h <> 0 "
        "LIMIT 1"
    )).first()
    if has_r5b_data is not None:
        raise RuntimeError(
            "R5B_DOWNGRADE_DATA_LOSS "
            "(R5B_DOWNGRADE_DELIVERY_HISTORY_LOSS): wyeksportuj lub jawnie "
            "wyzeruj historię i ustawienia komunikacji przed downgrade."
        )
    op.drop_index(
        "ix_rezerwacje_wiadomosci_proby_wiadomosc_started",
        table_name="rezerwacje_wiadomosci_proby",
    )
    op.drop_table("rezerwacje_wiadomosci_proby")

    op.drop_index(
        "ix_rezerwacje_wiadomosci_outbox_subject_email_ref",
        table_name="rezerwacje_wiadomosci_outbox",
    )
    op.drop_index(
        "ix_rezerwacje_wiadomosci_outbox_subject_phone_ref",
        table_name="rezerwacje_wiadomosci_outbox",
    )
    op.drop_index(
        "ix_rezerwacje_wiadomosci_outbox_lease",
        table_name="rezerwacje_wiadomosci_outbox",
    )
    op.drop_index(
        "ix_rezerwacje_wiadomosci_outbox_due",
        table_name="rezerwacje_wiadomosci_outbox",
    )
    op.drop_index(
        "ix_rezerwacje_wiadomosci_outbox_waitlist_id",
        table_name="rezerwacje_wiadomosci_outbox",
    )
    op.drop_index(
        "ix_rezerwacje_wiadomosci_outbox_termin_id",
        table_name="rezerwacje_wiadomosci_outbox",
    )
    op.drop_table("rezerwacje_wiadomosci_outbox")

    # Ograniczenia są inline i znikają razem z kolumnami.
    op.drop_column("lokal_config", "rezerwacje_przypomnienie_h")
    # ``lista_oczekujacych`` może zostać przebudowana przez późniejszą migrację
    # (np. R6b.2). SQLite zapisuje wtedy inline CHECK kanału jako ograniczenie
    # tabelowe, przez co natywny DROP COLUMN pozostawia odwołanie do usuniętej
    # kolumny i odrzuca DDL. Jawna przebudowa usuwa CHECK i kolumnę razem;
    # PostgreSQL nadal korzysta z natywnego DROP COLUMN.
    if connection.dialect.name == "sqlite":
        waitlist_checks = {
            item.get("name")
            for item in sa.inspect(connection).get_check_constraints(
                "lista_oczekujacych"
            )
            if item.get("name")
        }
        with op.batch_alter_table(
            "lista_oczekujacych", recreate="always",
        ) as batch:
            if "ck_lista_oczekujacych_kanal_komunikacji" in waitlist_checks:
                batch.drop_constraint(
                    "ck_lista_oczekujacych_kanal_komunikacji",
                    type_="check",
                )
            batch.drop_column("kanal_komunikacji")
    else:
        op.drop_column("lista_oczekujacych", "kanal_komunikacji")
    op.drop_column("terminy", "kanal_komunikacji")
