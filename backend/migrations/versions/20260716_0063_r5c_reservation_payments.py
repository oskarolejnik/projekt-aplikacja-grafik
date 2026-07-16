"""R5c reservation deposits, preauthorisation and durable provider commands.

Revision ID: 0063_r5c_reservation_payments
Revises: 0062_r5b_communication_outbox
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0063_r5c_reservation_payments"
down_revision: Union[str, None] = "0062_r5b_communication_outbox"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ``platnosci.kwota`` is a legacy Float (DOUBLE PRECISION on PostgreSQL).
# PostgreSQL has no ``round(double precision, integer)`` overload, while both
# supported databases accept the value after an explicit NUMERIC cast.
_LEGACY_MINOR_SQL = (
    "CAST(ROUND(CAST(kwota AS NUMERIC) * 100, 0) AS BIGINT)"
)


def upgrade() -> None:
    connection = op.get_bind()
    invalid_legacy = connection.execute(sa.text(
        "SELECT id FROM platnosci WHERE kwota < 0 OR kwota > 999999.99 OR status NOT IN "
        "('oczekuje', 'oplacona', 'anulowana') LIMIT 1"
    )).first()
    if invalid_legacy is not None:
        raise RuntimeError(
            "R5C_LEGACY_PAYMENT_INVALID: popraw ujemna kwote lub nieznany status przed migracja."
        )
    duplicate_reference = connection.execute(sa.text(
        "SELECT provider, external_id FROM platnosci "
        "WHERE external_id IS NOT NULL "
        "GROUP BY provider, external_id HAVING COUNT(*) > 1 LIMIT 1"
    )).first()
    if duplicate_reference is not None:
        raise RuntimeError(
            "R5C_LEGACY_PAYMENT_REFERENCE_DUPLICATE: uzgodnij zduplikowane "
            "(provider, external_id) przed migracja."
        )

    op.create_table(
        "polityki_platnosci_rezerwacji",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nazwa", sa.String(length=96), nullable=False),
        sa.Column("aktywna", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("data", sa.Date(), nullable=True),
        sa.Column(
            "serwis_id", sa.Integer(),
            sa.ForeignKey("godziny_otwarcia.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column("kanal", sa.String(length=16), nullable=False, server_default="oba"),
        sa.Column("min_osob", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_osob", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rodzaj", sa.String(length=20), nullable=False, server_default="brak"),
        sa.Column(
            "sposob_kwoty", sa.String(length=16), nullable=False, server_default="stala",
        ),
        sa.Column("kwota_minor", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("waluta", sa.String(length=3), nullable=False, server_default="PLN"),
        sa.Column("waznosc_min", sa.Integer(), nullable=False, server_default="30"),
        sa.Column(
            "po_niepowodzeniu", sa.String(length=16), nullable=False, server_default="ponow",
        ),
        sa.Column(
            "zwrot_przy_anulowaniu", sa.Boolean(), nullable=False, server_default=sa.true(),
        ),
        sa.Column("priorytet", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("utworzono_at", sa.DateTime(), nullable=False),
        sa.Column("zaktualizowano_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "kanal IN ('oba', 'online', 'wewnetrzna')",
            name="ck_polityki_platnosci_kanal",
        ),
        sa.CheckConstraint(
            "min_osob >= 1 AND (max_osob = 0 OR max_osob >= min_osob)",
            name="ck_polityki_platnosci_grupa",
        ),
        sa.CheckConstraint(
            "rodzaj IN ('brak', 'zadatek', 'preautoryzacja')",
            name="ck_polityki_platnosci_rodzaj",
        ),
        sa.CheckConstraint(
            "sposob_kwoty IN ('stala', 'od_osoby')",
            name="ck_polityki_platnosci_sposob_kwoty",
        ),
        sa.CheckConstraint(
            "(rodzaj = 'brak' AND kwota_minor = 0) OR "
            "(rodzaj <> 'brak' AND kwota_minor >= 200 AND kwota_minor <= 99999999)",
            name="ck_polityki_platnosci_kwota",
        ),
        sa.CheckConstraint(
            "waluta = 'PLN'",
            name="ck_polityki_platnosci_waluta",
        ),
        sa.CheckConstraint(
            "waznosc_min >= 30 AND waznosc_min <= 1440",
            name="ck_polityki_platnosci_waznosc",
        ),
        sa.CheckConstraint(
            "po_niepowodzeniu IN ('ponow', 'zwolnij')",
            name="ck_polityki_platnosci_niepowodzenie",
        ),
        sa.CheckConstraint("priorytet >= 0", name="ck_polityki_platnosci_priorytet"),
    )
    op.create_index(
        "ix_polityki_platnosci_dopasowanie",
        "polityki_platnosci_rezerwacji",
        ["aktywna", "data", "serwis_id", "kanal", "min_osob", "max_osob"],
    )

    with op.batch_alter_table("platnosci") as batch:
        batch.add_column(sa.Column("polityka_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("kwota_minor", sa.BigInteger(), nullable=False, server_default="0"))
        batch.add_column(sa.Column(
            "przechwycono_minor", sa.BigInteger(), nullable=False, server_default="0",
        ))
        batch.add_column(sa.Column(
            "zwrocono_minor", sa.BigInteger(), nullable=False, server_default="0",
        ))
        batch.add_column(sa.Column(
            "waluta", sa.String(length=3), nullable=False, server_default="PLN",
        ))
        batch.add_column(sa.Column(
            "rodzaj", sa.String(length=20), nullable=False, server_default="zadatek",
        ))
        batch.add_column(sa.Column(
            "refund_status", sa.String(length=16), nullable=False, server_default="brak",
        ))
        batch.add_column(sa.Column(
            "tryb_przechwycenia", sa.String(length=16), nullable=False,
            server_default="automatic",
        ))
        batch.add_column(sa.Column("provider_checkout_session_id", sa.String(length=255)))
        batch.add_column(sa.Column("provider_payment_intent_id", sa.String(length=255)))
        batch.add_column(sa.Column("provider_charge_id", sa.String(length=255)))
        batch.add_column(sa.Column("reservation_ref", sa.String(length=64)))
        batch.add_column(sa.Column("creation_key", sa.String(length=64)))
        batch.add_column(sa.Column("policy_snapshot", sa.JSON()))
        batch.add_column(sa.Column("expires_at", sa.DateTime()))
        batch.add_column(sa.Column("authorization_expires_at", sa.DateTime()))
        batch.add_column(sa.Column("zaktualizowano_at", sa.DateTime()))
        batch.add_column(sa.Column("autoryzowano_at", sa.DateTime()))
        batch.add_column(sa.Column("nieudana_at", sa.DateTime()))
        batch.add_column(sa.Column("wygasla_at", sa.DateTime()))
        batch.add_column(sa.Column("anulowano_at", sa.DateTime()))
        batch.add_column(sa.Column("zwrocono_at", sa.DateTime()))
        batch.add_column(sa.Column("last_error_code", sa.String(length=64)))
        batch.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="0"))

    connection.execute(sa.text(
        "UPDATE platnosci SET "
        f"kwota_minor = {_LEGACY_MINOR_SQL}, "
        "przechwycono_minor = CASE WHEN status = 'oplacona' "
        f"THEN {_LEGACY_MINOR_SQL} ELSE 0 END, "
        "zaktualizowano_at = utworzono_at"
    ))

    with op.batch_alter_table("platnosci") as batch:
        batch.create_foreign_key(
            "fk_platnosci_polityka_id", "polityki_platnosci_rezerwacji",
            ["polityka_id"], ["id"], ondelete="SET NULL",
        )
        batch.create_check_constraint(
            "ck_platnosci_rodzaj",
            "rodzaj IN ('zadatek', 'preautoryzacja', 'no_show', 'reczna')",
        )
        batch.create_check_constraint(
            "ck_platnosci_status_r5c",
            "status IN ('oczekuje', 'autoryzowana', 'oplacona', 'nieudana', "
            "'wygasla', 'anulowana', 'zwrocona')",
        )
        batch.create_check_constraint(
            "ck_platnosci_tryb_przechwycenia",
            "tryb_przechwycenia IN ('automatic', 'manual')",
        )
        batch.create_check_constraint(
            "ck_platnosci_refund_status",
            "refund_status IN ('brak', 'oczekuje', 'czesciowy', 'zwrocona', 'nieudana')",
        )
        batch.create_check_constraint(
            "ck_platnosci_kwoty_minor",
            "kwota_minor >= 0 AND kwota_minor <= 99999999 AND przechwycono_minor >= 0 "
            "AND zwrocono_minor >= 0 AND przechwycono_minor <= kwota_minor "
            "AND zwrocono_minor <= przechwycono_minor",
        )
        batch.create_check_constraint(
            "ck_platnosci_waluta",
            "waluta = 'PLN'",
        )
        batch.create_check_constraint(
            "ck_platnosci_reservation_ref",
            "reservation_ref IS NULL OR length(reservation_ref) = 64",
        )
        batch.create_check_constraint(
            "ck_platnosci_creation_key",
            "creation_key IS NULL OR length(creation_key) = 64",
        )
        batch.create_check_constraint("ck_platnosci_version", "version >= 0")
        batch.create_check_constraint(
            "ck_platnosci_autoryzacja_lifecycle",
            "status <> 'autoryzowana' OR autoryzowano_at IS NOT NULL",
        )
        batch.create_check_constraint(
            "ck_platnosci_capture_lifecycle",
            "status <> 'oplacona' OR (oplacono_at IS NOT NULL AND "
            "(przechwycono_minor > 0 OR kwota_minor = 0))",
        )
        batch.create_check_constraint(
            "ck_platnosci_refund_lifecycle",
            "status <> 'zwrocona' OR "
            "(refund_status = 'zwrocona' AND zwrocono_minor = przechwycono_minor)",
        )

    op.create_index(
        "uq_platnosci_provider_payment_intent", "platnosci",
        ["provider", "provider_payment_intent_id"], unique=True,
    )
    op.create_index(
        "uq_platnosci_provider_checkout_session", "platnosci",
        ["provider", "provider_checkout_session_id"], unique=True,
    )
    op.create_index(
        "uq_platnosci_provider_external_id", "platnosci",
        ["provider", "external_id"], unique=True,
    )
    op.create_index(
        "ix_platnosci_status_expires", "platnosci", ["status", "expires_at"],
    )
    op.create_index("ix_platnosci_reservation_ref", "platnosci", ["reservation_ref"])
    op.create_index("uq_platnosci_creation_key", "platnosci", ["creation_key"], unique=True)

    op.create_table(
        "rezerwacje_platnosci_polecenia",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "platnosc_id", sa.Integer(),
            sa.ForeignKey("platnosci.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("typ", sa.String(length=24), nullable=False),
        sa.Column("operation_key", sa.String(length=96), nullable=False),
        sa.Column("provider_idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("kwota_minor", sa.BigInteger(), nullable=True),
        sa.Column("stan", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("liczba_prob", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("maks_prob", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("available_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("lease_token", sa.String(length=64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("provider_object_id", sa.String(length=255), nullable=True),
        sa.Column("actor_kind", sa.String(length=16), nullable=False, server_default="system"),
        sa.Column(
            "actor_user_id", sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("reason_code", sa.String(length=64), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("uncertain_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint(
            "platnosc_id", "operation_key",
            name="uq_rezerwacje_platnosci_polecenie_operacja",
        ),
        sa.UniqueConstraint(
            "provider_idempotency_key",
            name="uq_rezerwacje_platnosci_polecenie_provider_key",
        ),
        sa.CheckConstraint(
            "typ IN ('create_checkout', 'capture', 'cancel_authorization', 'refund', 'reconcile')",
            name="ck_rezerwacje_platnosci_polecenie_typ",
        ),
        sa.CheckConstraint(
            "stan IN ('queued', 'processing', 'retry', 'succeeded', 'failed', 'uncertain', 'cancelled')",
            name="ck_rezerwacje_platnosci_polecenie_stan",
        ),
        sa.CheckConstraint(
            "kwota_minor IS NULL OR (kwota_minor > 0 AND kwota_minor <= 99999999)",
            name="ck_rezerwacje_platnosci_polecenie_kwota",
        ),
        sa.CheckConstraint(
            "liczba_prob >= 0 AND maks_prob >= 1",
            name="ck_rezerwacje_platnosci_polecenie_proby",
        ),
        sa.CheckConstraint(
            "length(provider_idempotency_key) = 64",
            name="ck_rezerwacje_platnosci_polecenie_provider_key",
        ),
        sa.CheckConstraint(
            "available_at < expires_at",
            name="ck_rezerwacje_platnosci_polecenie_deadline",
        ),
        sa.CheckConstraint(
            "(stan = 'processing' AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL) OR "
            "(stan <> 'processing' AND lease_token IS NULL AND lease_expires_at IS NULL)",
            name="ck_rezerwacje_platnosci_polecenie_lease",
        ),
        sa.CheckConstraint(
            "actor_kind IN ('system', 'user', 'guest')",
            name="ck_rezerwacje_platnosci_polecenie_actor",
        ),
    )
    op.create_index(
        "ix_rezerwacje_platnosci_polecenia_due", "rezerwacje_platnosci_polecenia",
        ["stan", "available_at", "id"],
    )
    op.create_index(
        "ix_rezerwacje_platnosci_polecenia_lease", "rezerwacje_platnosci_polecenia",
        ["stan", "lease_expires_at"],
    )

    op.create_table(
        "rezerwacje_platnosci_webhooki",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "platnosc_id", sa.Integer(),
            sa.ForeignKey("platnosci.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=96), nullable=False),
        sa.Column("api_version", sa.String(length=32), nullable=True),
        sa.Column("livemode", sa.Boolean(), nullable=False),
        sa.Column("object_id", sa.String(length=255), nullable=False),
        sa.Column("object_type", sa.String(length=32), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("provider_created_at", sa.DateTime(), nullable=True),
        sa.Column("stan", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("liczba_prob", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("maks_prob", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("available_at", sa.DateTime(), nullable=False),
        sa.Column("lease_token", sa.String(length=64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint(
            "provider", "event_id",
            name="uq_rezerwacje_platnosci_webhook_provider_event",
        ),
        sa.CheckConstraint(
            "stan IN ('queued', 'processing', 'processed', 'ignored', 'failed')",
            name="ck_rezerwacje_platnosci_webhook_stan",
        ),
        sa.CheckConstraint(
            "length(payload_sha256) = 64",
            name="ck_rezerwacje_platnosci_webhook_payload_hash",
        ),
        sa.CheckConstraint(
            "liczba_prob >= 0 AND maks_prob >= 1",
            name="ck_rezerwacje_platnosci_webhook_proby",
        ),
        sa.CheckConstraint(
            "(stan = 'processing' AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL) OR "
            "(stan <> 'processing' AND lease_token IS NULL AND lease_expires_at IS NULL)",
            name="ck_rezerwacje_platnosci_webhook_lease",
        ),
    )
    op.create_index(
        "ix_rezerwacje_platnosci_webhooki_due", "rezerwacje_platnosci_webhooki",
        ["stan", "available_at", "id"],
    )
    op.create_index(
        "ix_rezerwacje_platnosci_webhooki_object", "rezerwacje_platnosci_webhooki",
        ["provider", "object_id"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        connection.execute(sa.text(
            "LOCK TABLE rezerwacje_platnosci_webhooki, "
            "rezerwacje_platnosci_polecenia, platnosci, "
            "polityki_platnosci_rezerwacji IN ACCESS EXCLUSIVE MODE"
        ))
    has_r5c_data = connection.execute(sa.text(
        "SELECT 1 FROM polityki_platnosci_rezerwacji "
        "UNION ALL SELECT 1 FROM rezerwacje_platnosci_polecenia "
        "UNION ALL SELECT 1 FROM rezerwacje_platnosci_webhooki "
        "UNION ALL SELECT 1 FROM platnosci WHERE "
        "polityka_id IS NOT NULL OR rodzaj <> 'zadatek' "
        "OR refund_status <> 'brak' OR status NOT IN ('oczekuje', 'oplacona', 'anulowana') "
        "OR provider_checkout_session_id IS NOT NULL "
        "OR provider_payment_intent_id IS NOT NULL OR provider_charge_id IS NOT NULL "
        "OR reservation_ref IS NOT NULL OR policy_snapshot IS NOT NULL "
        "OR creation_key IS NOT NULL "
        "OR expires_at IS NOT NULL OR authorization_expires_at IS NOT NULL "
        "OR autoryzowano_at IS NOT NULL OR nieudana_at IS NOT NULL "
        "OR wygasla_at IS NOT NULL OR anulowano_at IS NOT NULL OR zwrocono_at IS NOT NULL "
        "OR last_error_code IS NOT NULL OR zwrocono_minor <> 0 "
        f"OR kwota_minor <> {_LEGACY_MINOR_SQL} "
        "OR przechwycono_minor <> CASE WHEN status = 'oplacona' "
        "THEN kwota_minor ELSE 0 END LIMIT 1"
    )).first()
    if has_r5c_data is not None:
        raise RuntimeError(
            "R5C_DOWNGRADE_PAYMENT_HISTORY_LOSS: wyeksportuj i uzgodnij platnosci R5c "
            "przed downgrade."
        )

    op.drop_index(
        "ix_rezerwacje_platnosci_webhooki_object",
        table_name="rezerwacje_platnosci_webhooki",
    )
    op.drop_index(
        "ix_rezerwacje_platnosci_webhooki_due",
        table_name="rezerwacje_platnosci_webhooki",
    )
    op.drop_table("rezerwacje_platnosci_webhooki")
    op.drop_index(
        "ix_rezerwacje_platnosci_polecenia_lease",
        table_name="rezerwacje_platnosci_polecenia",
    )
    op.drop_index(
        "ix_rezerwacje_platnosci_polecenia_due",
        table_name="rezerwacje_platnosci_polecenia",
    )
    op.drop_table("rezerwacje_platnosci_polecenia")

    op.drop_index("uq_platnosci_creation_key", table_name="platnosci")
    op.drop_index("ix_platnosci_reservation_ref", table_name="platnosci")
    op.drop_index("ix_platnosci_status_expires", table_name="platnosci")
    op.drop_index("uq_platnosci_provider_external_id", table_name="platnosci")
    op.drop_index("uq_platnosci_provider_checkout_session", table_name="platnosci")
    op.drop_index("uq_platnosci_provider_payment_intent", table_name="platnosci")
    with op.batch_alter_table("platnosci") as batch:
        batch.drop_constraint("ck_platnosci_refund_lifecycle", type_="check")
        batch.drop_constraint("ck_platnosci_capture_lifecycle", type_="check")
        batch.drop_constraint("ck_platnosci_autoryzacja_lifecycle", type_="check")
        batch.drop_constraint("ck_platnosci_version", type_="check")
        batch.drop_constraint("ck_platnosci_creation_key", type_="check")
        batch.drop_constraint("ck_platnosci_reservation_ref", type_="check")
        batch.drop_constraint("ck_platnosci_waluta", type_="check")
        batch.drop_constraint("ck_platnosci_kwoty_minor", type_="check")
        batch.drop_constraint("ck_platnosci_refund_status", type_="check")
        batch.drop_constraint("ck_platnosci_tryb_przechwycenia", type_="check")
        batch.drop_constraint("ck_platnosci_status_r5c", type_="check")
        batch.drop_constraint("ck_platnosci_rodzaj", type_="check")
        batch.drop_constraint("fk_platnosci_polityka_id", type_="foreignkey")
        for column in (
            "version", "last_error_code", "zwrocono_at", "anulowano_at", "wygasla_at",
            "nieudana_at", "autoryzowano_at", "zaktualizowano_at",
            "authorization_expires_at", "expires_at", "policy_snapshot", "creation_key",
            "reservation_ref",
            "provider_charge_id", "provider_payment_intent_id", "provider_checkout_session_id",
            "tryb_przechwycenia", "refund_status", "rodzaj", "waluta", "zwrocono_minor",
            "przechwycono_minor", "kwota_minor", "polityka_id",
        ):
            batch.drop_column(column)

    op.drop_index(
        "ix_polityki_platnosci_dopasowanie",
        table_name="polityki_platnosci_rezerwacji",
    )
    op.drop_table("polityki_platnosci_rezerwacji")
