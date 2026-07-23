"""Focused contract tests for the PII-free reservation readiness endpoint."""

from datetime import timedelta
import json

import factories
import main
import models
from conftest import auth_header
from deps import get_lokal_config, utcnow_naive
from routers import reservation_ops


PATH = "/api/ops/rezerwacje/health"


def _checks(payload):
    return {item["code"]: item for item in payload["checks"]}


def _disable_optional_integrations(monkeypatch):
    monkeypatch.setattr(
        reservation_ops.integracje,
        "skonfigurowane",
        lambda _key: False,
    )
    monkeypatch.setattr(
        reservation_ops.reservation_communication,
        "worker_running",
        lambda: False,
    )
    monkeypatch.setattr(
        reservation_ops.reservation_payment_worker,
        "worker_running",
        lambda: False,
    )


def test_health_requires_admin(client):
    assert client.get(PATH).status_code == 401

    employee = factories.UserFactory(rola="employee")
    response = client.get(PATH, headers=auth_header(employee))
    assert response.status_code == 403


def test_health_reports_ready_core_without_requiring_optional_providers(
    admin_client,
    db,
    monkeypatch,
):
    _disable_optional_integrations(monkeypatch)
    cfg = get_lokal_config(db)
    cfg.modul_rezerwacje = True
    cfg.rezerwacje_online = False
    cfg.rezerwacje_przypomnienie_h = 0
    cfg.zadatek_wymagany = False
    db.commit()

    response = admin_client.get(PATH)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["privacy_notice_version"] == main.PUBLIC_PRIVACY_NOTICE_VERSION
    assert _checks(payload)["DB_CONNECTIVITY"]["status"] == "ok"
    assert _checks(payload)["SCHEMA_0068"]["status"] == "ok"
    assert _checks(payload)["RESERVATIONS_MODULE"]["status"] == "ok"
    assert payload["queues"]["communication"]["by_state"]["queued"] == 0
    assert payload["queues"]["payment_commands"]["by_state"]["queued"] == 0
    assert payload["queues"]["payment_webhooks"]["by_state"]["queued"] == 0
    assert {gate["code"]: gate for gate in payload["gates"]}[
        "PAYMENT_PROVIDER"
    ]["status"] == "deferred"


def test_health_fail_closed_gdy_pelny_kontrakt_0068_jest_oslabiony(
    admin_client,
    monkeypatch,
):
    def reject_weakened_schema(_inspector):
        raise RuntimeError("weakened schema")

    monkeypatch.setattr(
        reservation_ops.database,
        "_validate_r68_adoption_schema",
        reject_weakened_schema,
    )

    response = admin_client.get(PATH)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "blocked"
    schema = _checks(payload)["SCHEMA_0068"]
    assert schema["status"] == "blocked"
    assert schema["contract_compatible"] is False
    assert payload["queues"] is None


def test_enabled_widget_without_v2_privacy_is_blocked(
    admin_client,
    db,
    monkeypatch,
):
    _disable_optional_integrations(monkeypatch)
    cfg = get_lokal_config(db)
    cfg.rezerwacje_online = True
    cfg.rezerwacje_widget_v2 = False
    cfg.rezerwacje_rodo_kontakt = None
    cfg.rezerwacje_rodo_adres = None
    db.commit()

    response = admin_client.get(PATH)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "blocked"
    widget = _checks(payload)["PUBLIC_WIDGET_V2"]
    assert widget == {
        "code": "PUBLIC_WIDGET_V2",
        "status": "blocked",
        "online": True,
        "v2": False,
        "privacy_ready": False,
    }


def test_missing_providers_are_attention_when_dependent_features_are_enabled(
    admin_client,
    db,
    monkeypatch,
):
    _disable_optional_integrations(monkeypatch)
    cfg = get_lokal_config(db)
    cfg.rezerwacje_online = True
    cfg.rezerwacje_widget_v2 = True
    cfg.rezerwacje_rodo_kontakt = "privacy@example.test"
    cfg.rezerwacje_rodo_adres = "Adres administratora danych"
    db.commit()

    response = admin_client.get(PATH)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "attention"
    assert _checks(payload)["PUBLIC_WIDGET_V2"]["status"] == "ok"
    assert _checks(payload)["COMMUNICATION_PROVIDERS"]["status"] == "attention"
    gates = {gate["code"]: gate for gate in payload["gates"]}
    assert gates["EMAIL_PROVIDER"]["status"] == "open"
    assert gates["SMS_PROVIDER"]["status"] == "open"


def test_queue_report_contains_only_aggregate_state(
    admin_client,
    db,
    monkeypatch,
):
    _disable_optional_integrations(monkeypatch)
    now = utcnow_naive()
    secret_recipient = "private-recipient@example.test"
    db.add(
        models.RezerwacjaWiadomoscOutbox(
            termin_id=999,
            subject_email_ref="a" * 64,
            dedupe_key="b" * 64,
            typ_zdarzenia="confirmation",
            kanal="email",
            odbiorca=secret_recipient,
            temat="Private subject",
            tresc="Private body",
            template_key="reservation_confirmation",
            template_version="r5b-v1",
            provider="smtp",
            provider_idempotency_key="c" * 64,
            provider_supports_idempotency=False,
            stan="failed",
            liczba_prob=5,
            maks_prob=5,
            available_at=now - timedelta(minutes=10),
            expires_at=now + timedelta(days=1),
            last_error_code="PRIVATE_PROVIDER_DETAIL",
            actor_kind="system",
            created_at=now - timedelta(minutes=10),
            updated_at=now,
        )
    )
    db.commit()

    response = admin_client.get(PATH)

    assert response.status_code == 200
    payload = response.json()
    assert payload["queues"]["communication"]["by_state"]["failed"] == 1
    assert payload["queues"]["communication"]["pending_by_channel"]["email"] == 1
    assert _checks(payload)["COMMUNICATION_QUEUE_TERMINAL"]["status"] == "attention"
    serialized = json.dumps(payload)
    assert secret_recipient not in serialized
    assert "Private subject" not in serialized
    assert "Private body" not in serialized
    assert "PRIVATE_PROVIDER_DETAIL" not in serialized
