"""R5c operator API: typed policies and durable payment commands."""

from datetime import date, datetime, time, timedelta
import json

import factories
import integracje
import models
import reservation_access
import settings
from auth import create_access_token
from deps import get_subskrypcja


def _headers(user):
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def _expire_subscription(db):
    subscription = get_subskrypcja(db)
    subscription.status = "wygasla"
    subscription.data_do = None
    db.commit()


def _service(db):
    service = models.GodzinyOtwarcia(
        dzien_tygodnia=4,
        godz_od=time(17, 0),
        godz_do=time(23, 0),
        dlugosc_slotu_min=30,
        krok_slotu_min=30,
        domyslny_turn_time_min=120,
        aktywny=True,
        nazwa="Kolacja",
    )
    db.add(service)
    db.commit()
    return service


def _reservation(db):
    reservation = models.Termin(
        data=date.today() + timedelta(days=2),
        nazwisko="Gość płatności",
        liczba_osob=4,
        status="rezerwacja",
        zadatek=0,
        utworzono_at=datetime.utcnow(),
        godz_od=time(18, 0),
        godz_do=time(20, 0),
        kanal="online",
        rodzaj="stolik",
    )
    db.add(reservation)
    db.commit()
    return reservation


def _payment(db, *, status="oczekuje", kind="zadatek", reservation=None, provider="stripe"):
    now = datetime.utcnow()
    captured = 5_000 if status == "oplacona" else 0
    payment = models.Platnosc(
        termin_id=reservation.id if reservation is not None else None,
        kwota=50,
        kwota_minor=5_000,
        przechwycono_minor=captured,
        zwrocono_minor=0,
        waluta="PLN",
        rodzaj=kind,
        status=status,
        refund_status="brak",
        tryb_przechwycenia="manual" if kind == "preautoryzacja" else "automatic",
        provider=provider,
        external_id=f"legacy-secret-{status}-{kind}",
        provider_checkout_session_id=f"cs_{status}_{kind}",
        provider_payment_intent_id=f"pi_{status}_{kind}",
        link="https://checkout.example.test/session" if status == "oczekuje" else None,
        reservation_ref="a" * 64 if reservation is not None else None,
        policy_snapshot={
            "version": 1,
            "policy_id": None,
            "source": "test_snapshot",
            "name": "Testowa polityka",
            "rodzaj": kind,
            "kwota_minor": 5_000,
            "waluta": "PLN",
            "sposob_kwoty": "stala",
            "waznosc_min": 30,
            "po_niepowodzeniu": "ponow",
            "zwrot_przy_anulowaniu": True,
            "reservation_date": reservation.data.isoformat() if reservation else None,
            "service_id": None,
            "people": 4,
            "channel": "online",
        },
        expires_at=now + timedelta(minutes=30),
        authorization_expires_at=(now + timedelta(days=5) if status == "autoryzowana" else None),
        utworzono_at=now,
        zaktualizowano_at=now,
        autoryzowano_at=now if status == "autoryzowana" else None,
        oplacono_at=now if status == "oplacona" else None,
        nieudana_at=now if status == "nieudana" else None,
        version=1,
    )
    db.add(payment)
    db.commit()
    return payment


def _policy_payload(service_id):
    return {
        "nazwa": "Kolacja 4+",
        "aktywna": True,
        "data": None,
        "serwis_id": service_id,
        "kanal": "online",
        "min_osob": 4,
        "max_osob": 8,
        "rodzaj": "zadatek",
        "sposob_kwoty": "od_osoby",
        "kwota_minor": 2_000,
        "waluta": "pln",
        "waznosc_min": 30,
        "po_niepowodzeniu": "ponow",
        "zwrot_przy_anulowaniu": True,
        "priorytet": 20,
    }


def test_payment_routes_require_granular_finance_permission():
    for path in (
        "/api/platnosci",
        "/api/platnosci/7",
        "/api/platnosci/7/retry",
        "/api/platnosci/7/capture",
        "/api/platnosci/7/anuluj-autoryzacje",
        "/api/platnosci/7/zwrot",
        "/api/platnosci/7/reconcile",
        "/api/platnosci/7/oplacona",
    ):
        requirement = reservation_access.requirement_for("POST", path)
        assert requirement is not None
        assert requirement.admin_only is False
        assert requirement.all_of == ("rezerwacje.finanse",)


def test_payment_policy_mutations_require_rules_and_finance(client, db):
    assert reservation_access.requirement_for(
        "GET", "/api/polityki-platnosci-rezerwacji",
    ).all_of == ("rezerwacje.reguly",)
    for method, path in (
        ("POST", "/api/polityki-platnosci-rezerwacji"),
        ("PUT", "/api/polityki-platnosci-rezerwacji/7"),
        ("DELETE", "/api/polityki-platnosci-rezerwacji/7"),
    ):
        assert reservation_access.requirement_for(method, path).all_of == (
            "rezerwacje.reguly",
            "rezerwacje.finanse",
        )

    rules_only = factories.UserFactory(
        login="payment_policy_rules_only",
        rola="szef",
        pracownik=None,
        uprawnienia_override={
            "rezerwacje.reguly": True,
            "rezerwacje.finanse": False,
        },
    )
    headers = _headers(rules_only)
    assert client.get(
        "/api/polityki-platnosci-rezerwacji", headers=headers,
    ).status_code == 200
    assert client.post(
        "/api/polityki-platnosci-rezerwacji",
        headers=headers,
        json=_policy_payload(None),
    ).status_code == 403
    assert client.put(
        "/api/polityki-platnosci-rezerwacji/7",
        headers=headers,
        json=_policy_payload(None),
    ).status_code == 403
    assert client.delete(
        "/api/polityki-platnosci-rezerwacji/7", headers=headers,
    ).status_code == 403
    assert db.query(models.PolitykaPlatnosciRezerwacji).count() == 0


def test_read_only_allows_only_closing_public_and_payment_operations(client, db, admin):
    _expire_subscription(db)

    for path in (
        "/api/online/zarzadzanie/odwolaj",
        "/api/online/zarzadzanie/dane/usun",
    ):
        response = client.post(path, json={})
        assert response.status_code != 402, (path, response.text)

    for path in (
        "/api/online/zarzadzanie/edytuj",
        "/api/online/zarzadzanie/odwolaj/przyszla-akcja",
    ):
        assert client.post(path, json={}).status_code == 402

    operator_headers = {
        **_headers(admin),
        "Idempotency-Key": "read-only-closing-operation",
    }
    for path in (
        "/api/platnosci/999/anuluj-autoryzacje",
        "/api/platnosci/999/zwrot",
        "/api/platnosci/999/reconcile",
    ):
        response = client.post(path, headers=operator_headers, json={})
        assert response.status_code != 402, (path, response.text)

    for path in (
        "/api/platnosci",
        "/api/platnosci/999/capture",
        "/api/platnosci/999/retry",
        "/api/platnosci/0/zwrot",
    ):
        assert client.post(
            path, headers=operator_headers, json={},
        ).status_code == 402


def test_legacy_sandbox_creation_fails_closed_in_production(
    admin_client, monkeypatch,
):
    monkeypatch.setattr(settings, "IS_DEV", False)
    monkeypatch.setenv("PAYMENTS_PROVIDER", "sandbox")

    response = admin_client.post("/api/platnosci", json={"kwota": 50})

    assert response.status_code == 503, response.text
    assert response.json()["code"] == integracje.PaymentProviderConfigurationError.code


def test_payment_policy_crud_feeds_rules_aggregate_and_audit(admin_client, db):
    service = _service(db)
    created = admin_client.post(
        "/api/polityki-platnosci-rezerwacji",
        json=_policy_payload(service.id),
    )
    assert created.status_code == 201, created.text
    policy = created.json()
    assert policy["waluta"] == "PLN"
    assert policy["kwota_minor"] == 2_000

    listed = admin_client.get("/api/polityki-platnosci-rezerwacji")
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [policy["id"]]

    aggregate = admin_client.get("/api/rezerwacje/reguly")
    assert aggregate.status_code == 200
    assert aggregate.json()["polityki_platnosci"] == listed.json()
    assert aggregate.json()["legacy_zadatek_fallback"] == {
        "aktywna": False,
        "kwota_minor": 0,
        "min_osob": 1,
        "sposob_kwoty": "od_osoby",
        "waluta": "PLN",
    }

    changed_payload = _policy_payload(service.id)
    changed_payload.update({
        "nazwa": "Kolacja — preautoryzacja",
        "rodzaj": "preautoryzacja",
        "data": (date.today() + timedelta(days=2)).isoformat(),
    })
    changed = admin_client.put(
        f"/api/polityki-platnosci-rezerwacji/{policy['id']}",
        json=changed_payload,
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["rodzaj"] == "preautoryzacja"

    deleted = admin_client.delete(f"/api/polityki-platnosci-rezerwacji/{policy['id']}")
    assert deleted.status_code == 204
    assert admin_client.get("/api/polityki-platnosci-rezerwacji").json() == []

    db.expire_all()
    audit_rows = db.query(models.AuditLog).filter(
        models.AuditLog.zasob == f"payment_policy:{policy['id']}"
    ).order_by(models.AuditLog.id).all()
    assert [row.akcja for row in audit_rows] == [
        "platnosc_policy_create",
        "platnosc_policy_update",
        "platnosc_policy_delete",
    ]
    audit_details = [json.loads(row.szczegoly) for row in audit_rows]
    assert audit_details[0] == {"before": None, "after": policy}
    assert audit_details[1] == {"before": policy, "after": changed.json()}
    assert audit_details[2] == {"before": changed.json(), "after": None}


def test_operator_without_finance_cannot_bypass_policy_on_create_or_edit(
    admin_client, client, db,
):
    booking_date = date.today() + timedelta(days=14)
    table_response = admin_client.post(
        "/api/stoliki", json={"nazwa": "R5c policy guard", "pojemnosc": 6},
    )
    assert table_response.status_code == 201, table_response.text
    table_id = table_response.json()["id"]

    existing = admin_client.post("/api/rezerwacje-stolik", json={
        "data": booking_date.isoformat(),
        "godz_od": "18:00",
        "stolik_id": table_id,
        "liczba_osob": 4,
        "nazwisko": "Edycja bez finansów",
        "zadatek": 0,
    })
    assert existing.status_code == 201, existing.text
    assert db.query(models.Platnosc).filter_by(
        termin_id=existing.json()["id"],
    ).count() == 0

    policy_payload = _policy_payload(None)
    policy_payload["kanal"] = "wewnetrzna"
    policy_response = admin_client.post(
        "/api/polityki-platnosci-rezerwacji", json=policy_payload,
    )
    assert policy_response.status_code == 201, policy_response.text

    operator = factories.UserFactory(
        login="payment_policy_no_finance",
        rola="szef",
        pracownik=None,
        uprawnienia_override={
            "rezerwacje.operacje": True,
            "rezerwacje.dane_kontaktowe": True,
            "rezerwacje.finanse": False,
        },
    )
    headers = _headers(operator)
    created = client.post(
        "/api/rezerwacje-stolik",
        headers=headers,
        json={
            "data": (booking_date + timedelta(days=1)).isoformat(),
            "godz_od": "18:00",
            "stolik_id": table_id,
            "liczba_osob": 4,
            "nazwisko": "Utworzenie bez finansów",
            "zadatek": 999,
        },
    )
    assert created.status_code == 201, created.text

    edited = client.put(
        f"/api/rezerwacje-stolik/{existing.json()['id']}",
        headers=headers,
        json={
            "data": (booking_date + timedelta(days=2)).isoformat(),
            "godz_od": "18:00",
            "stolik_id": table_id,
            "liczba_osob": 4,
            "nazwisko": "Edycja bez finansów",
            "zadatek": 999,
        },
    )
    assert edited.status_code == 200, edited.text

    db.expire_all()
    for reservation_id in (created.json()["id"], existing.json()["id"]):
        reservation = db.get(models.Termin, reservation_id)
        assert reservation.zadatek == 0
        payment = db.query(models.Platnosc).filter_by(termin_id=reservation_id).one()
        assert payment.kwota_minor == 8_000


def test_rules_aggregate_exposes_normalized_legacy_deposit_fallback(admin_client, db):
    config = db.get(models.LokalConfig, 1)
    config.zadatek_wymagany = True
    config.zadatek_kwota_os = 19.99
    config.zadatek_prog_osob = 6
    db.commit()

    response = admin_client.get("/api/rezerwacje/reguly")

    assert response.status_code == 200
    assert response.json()["legacy_zadatek_fallback"] == {
        "aktywna": True,
        "kwota_minor": 1_999,
        "min_osob": 6,
        "sposob_kwoty": "od_osoby",
        "waluta": "PLN",
    }
    assert "zadatek_kwota_os" not in response.text
    assert "zadatek_wymagany" not in response.text


def test_payment_policy_rejects_unknown_service(admin_client, db):
    response = admin_client.post(
        "/api/polityki-platnosci-rezerwacji",
        json=_policy_payload(999_999),
    )
    assert response.status_code == 400
    assert db.query(models.PolitykaPlatnosciRezerwacji).count() == 0

    service = _service(db)
    too_small = _policy_payload(service.id)
    too_small["kwota_minor"] = 199
    response = admin_client.post(
        "/api/polityki-platnosci-rezerwacji",
        json=too_small,
    )
    assert response.status_code == 422
    assert db.query(models.PolitykaPlatnosciRezerwacji).count() == 0

    unsupported_currency = _policy_payload(service.id)
    unsupported_currency["waluta"] = "EUR"
    response = admin_client.post(
        "/api/polityki-platnosci-rezerwacji",
        json=unsupported_currency,
    )
    assert response.status_code == 422
    assert db.query(models.PolitykaPlatnosciRezerwacji).count() == 0


def test_active_preauthorization_requires_exact_near_date(admin_client, db):
    service = _service(db)
    payload = _policy_payload(service.id)
    payload["rodzaj"] = "preautoryzacja"

    no_date = admin_client.post(
        "/api/polityki-platnosci-rezerwacji",
        json=payload,
    )
    assert no_date.status_code == 400
    assert "wymaga konkretnego dnia" in no_date.json()["detail"]

    payload["data"] = (date.today() + timedelta(days=7)).isoformat()
    too_early = admin_client.post(
        "/api/polityki-platnosci-rezerwacji",
        json=payload,
    )
    assert too_early.status_code == 400
    assert "6 dni" in too_early.json()["detail"]

    payload["data"] = (date.today() + timedelta(days=6)).isoformat()
    accepted = admin_client.post(
        "/api/polityki-platnosci-rezerwacji",
        json=payload,
    )
    assert accepted.status_code == 201, accepted.text


def test_operator_projection_and_capture_are_idempotent(admin_client, db):
    payment = _payment(db, status="autoryzowana", kind="preautoryzacja")

    detail = admin_client.get(f"/api/platnosci/{payment.id}")
    assert detail.status_code == 200
    assert detail.headers["cache-control"] == "private, no-store"
    body = detail.json()
    assert body["provider_payment_intent_id"].startswith("pi_")
    assert "external_id" not in body

    path = f"/api/platnosci/{payment.id}/capture"
    assert admin_client.post(path, json={"powod": "no_show"}).status_code == 422
    headers = {"Idempotency-Key": "capture-payment-tab-1"}
    first = admin_client.post(
        path,
        headers=headers,
        json={"kwota_minor": 2_000, "powod": "no_show", "notatka": "Gość nie przyjechał"},
    )
    replay = admin_client.post(
        path,
        headers=headers,
        json={"kwota_minor": 2_000, "powod": "no_show", "notatka": "Gość nie przyjechał"},
    )
    assert first.status_code == replay.status_code == 202, first.text
    assert first.headers["cache-control"] == "private, no-store"
    assert first.json()["command"]["id"] == replay.json()["command"]["id"]
    assert first.json()["command"]["typ"] == "capture"

    db.expire_all()
    command = db.query(models.RezerwacjaPlatnoscPolecenie).one()
    assert command.operation_key != headers["Idempotency-Key"]
    assert headers["Idempotency-Key"] not in command.operation_key
    assert len(command.provider_idempotency_key) == 64
    assert db.query(models.AuditLog).filter_by(
        akcja="platnosc_capture_request",
        zasob=f"payment:{payment.id}",
    ).count() == 1

    detail_after_command = admin_client.get(f"/api/platnosci/{payment.id}")
    assert detail_after_command.status_code == 200
    assert detail_after_command.json()["latest_command"]["id"] == command.id
    assert detail_after_command.json()["latest_command"]["stan"] == "queued"

    mismatch = admin_client.post(
        path,
        headers=headers,
        json={"kwota_minor": 2_000, "powod": "damaged_table"},
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["code"] == "PAYMENT_OPERATION_KEY_REUSED"

    omitted_amount_changes_meaning = admin_client.post(
        path,
        headers=headers,
        json={"powod": "no_show", "notatka": "Gość nie przyjechał"},
    )
    assert omitted_amount_changes_meaning.status_code == 409
    assert omitted_amount_changes_meaning.json()["code"] == (
        "PAYMENT_OPERATION_KEY_REUSED"
    )


def test_operator_can_queue_cancel_and_only_full_refund(admin_client, db):
    authorized = _payment(db, status="autoryzowana", kind="preautoryzacja")
    cancel = admin_client.post(
        f"/api/platnosci/{authorized.id}/anuluj-autoryzacje",
        headers={"Idempotency-Key": "cancel-authorization-1"},
        json={"powod": "guest_cancelled", "notatka": "Telefon od gościa"},
    )
    assert cancel.status_code == 202, cancel.text
    assert cancel.json()["command"]["typ"] == "cancel_authorization"

    paid = _payment(db, status="oplacona", kind="zadatek")
    refund_path = f"/api/platnosci/{paid.id}/zwrot"
    partial = admin_client.post(
        refund_path,
        headers={"Idempotency-Key": "refund-partial-1"},
        json={"kwota_minor": 2_000, "powod": "requested_by_customer"},
    )
    assert partial.status_code == 409
    assert partial.json()["code"] == "PARTIAL_REFUND_UNSUPPORTED"

    full_headers = {"Idempotency-Key": "refund-full-1"}
    full = admin_client.post(
        refund_path,
        headers=full_headers,
        json={"powod": "requested_by_customer", "notatka": "Odwołana wizyta"},
    )
    replay = admin_client.post(
        refund_path,
        headers=full_headers,
        json={"powod": "requested_by_customer", "notatka": "Odwołana wizyta"},
    )
    assert full.status_code == replay.status_code == 202, full.text
    assert full.json()["command"]["kwota_minor"] == 5_000
    assert replay.json()["command"]["id"] == full.json()["command"]["id"]
    assert full.json()["payment"]["refund_status"] == "oczekuje"

    duplicate = admin_client.post(
        refund_path,
        headers={"Idempotency-Key": "refund-full-another-tab"},
        json={"powod": "requested_by_customer", "notatka": "Odwołana wizyta"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "PAYMENT_OPERATION_ALREADY_PENDING"


def test_sandbox_operations_finish_locally_without_dead_worker_queue(admin_client, db):
    reservation = _reservation(db)
    reservation.zadatek = 50
    authorized = _payment(
        db,
        status="autoryzowana",
        kind="preautoryzacja",
        reservation=reservation,
        provider="sandbox",
    )
    capture = admin_client.post(
        f"/api/platnosci/{authorized.id}/capture",
        headers={"Idempotency-Key": "sandbox-capture-1"},
        json={"powod": "operator_capture"},
    )
    assert capture.status_code == 202, capture.text
    assert capture.json()["payment"]["status"] == "oplacona"
    assert capture.json()["command"]["stan"] == "succeeded"

    paid = _payment(
        db,
        status="oplacona",
        reservation=reservation,
        provider="sandbox",
    )
    refund = admin_client.post(
        f"/api/platnosci/{paid.id}/zwrot",
        headers={"Idempotency-Key": "sandbox-refund-1"},
        json={"powod": "requested_by_customer"},
    )
    assert refund.status_code == 202, refund.text
    assert refund.json()["payment"]["status"] == "zwrocona"
    assert refund.json()["payment"]["refund_status"] == "zwrocona"
    assert refund.json()["command"]["stan"] == "succeeded"
    db.expire_all()
    assert db.get(models.Termin, reservation.id).zadatek == 0


def test_retry_creates_new_payment_aggregate_and_replays_same_one(admin_client, db):
    reservation = _reservation(db)
    failed = _payment(db, status="nieudana", reservation=reservation)
    headers = {"Idempotency-Key": "retry-failed-payment-tab-1"}

    first = admin_client.post(f"/api/platnosci/{failed.id}/retry", headers=headers)
    replay = admin_client.post(f"/api/platnosci/{failed.id}/retry", headers=headers)

    assert first.status_code == replay.status_code == 201, first.text
    assert first.json()["payment"]["id"] != failed.id
    assert first.json()["payment"]["status"] == "oczekuje"
    assert first.json()["command"]["typ"] == "create_checkout"
    assert replay.json()["payment"]["id"] == first.json()["payment"]["id"]
    assert replay.json()["command"]["id"] == first.json()["command"]["id"]
    assert db.query(models.Platnosc).count() == 2
    assert db.query(models.RezerwacjaPlatnoscPolecenie).count() == 2
    assert db.query(models.RezerwacjaPlatnoscPolecenie).filter_by(
        platnosc_id=failed.id,
        typ="reconcile",
        reason_code="payment_superseded",
    ).count() == 1
    assert db.query(models.AuditLog).filter_by(
        akcja="platnosc_checkout_retry",
        zasob=f"payment:{failed.id}",
    ).count() == 1


def test_operator_can_idempotently_reconcile_uncertain_stripe_operation(
    admin_client, db,
):
    payment = _payment(db, status="oczekuje", provider="stripe")
    now = datetime.utcnow()
    uncertain = models.RezerwacjaPlatnoscPolecenie(
        platnosc_id=payment.id,
        typ="create_checkout",
        operation_key="initial-checkout",
        provider_idempotency_key="f" * 64,
        stan="uncertain",
        liczba_prob=5,
        maks_prob=5,
        available_at=now,
        expires_at=now + timedelta(hours=1),
        actor_kind="system",
        created_at=now,
        updated_at=now,
        finished_at=now,
        uncertain_at=now,
    )
    db.add(uncertain)
    db.commit()
    headers = {"Idempotency-Key": "reconcile-payment-tab-1"}
    body = {"powod": "operator_reconcile", "notatka": "Kontrola po timeout"}

    first = admin_client.post(
        f"/api/platnosci/{payment.id}/reconcile",
        headers=headers,
        json=body,
    )
    replay = admin_client.post(
        f"/api/platnosci/{payment.id}/reconcile",
        headers=headers,
        json=body,
    )

    assert first.status_code == replay.status_code == 202, first.text
    assert first.json()["command"]["typ"] == "reconcile"
    assert first.json()["command"]["id"] == replay.json()["command"]["id"]
    assert db.query(models.AuditLog).filter_by(
        akcja="platnosc_reconcile_request",
        zasob=f"payment:{payment.id}",
    ).count() == 1


def test_real_provider_cannot_be_marked_paid_manually(admin_client, db):
    real = _payment(db, status="oczekuje", provider="stripe")
    response = admin_client.post(f"/api/platnosci/{real.id}/oplacona")
    assert response.status_code == 409
    assert response.json()["code"] == "MANUAL_PAYMENT_CONFIRMATION_FORBIDDEN"
    db.expire_all()
    assert db.get(models.Platnosc, real.id).status == "oczekuje"
