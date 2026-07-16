"""HTTP contract for the public R5c payment flow.

The tests keep provider I/O outside the process: the reservation flow uses the
explicit sandbox mode, while the Stripe endpoint is exercised with a patched
signed-webhook ingestor.  Public success is always read from the canonical
payment projection, never inferred from a browser return URL.
"""

from datetime import date, timedelta
import json

from fastapi.testclient import TestClient

import main
import models
import reservation_payment_worker
import reservation_payments
import szyfrowanie


SESSION = "r5c-public-browser-session-0001"
HOLD_KEY = "r5c-public-hold-0001"
CREATE_KEY = "r5c-public-create-0001"


def _booking_date() -> date:
    return date.today() + timedelta(days=21)


def _prepare_paid_booking_policy(admin_client, booking_date: date) -> None:
    config = admin_client.put(
        "/api/lokal/config",
        json={
            "rezerwacje_online": True,
            "rezerwacje_widget_v2": True,
            "rezerwacje_auto_potwierdzenie": False,
            "rezerwacje_rodo_kontakt": "rodo@lokalo.test",
            "rezerwacje_rodo_adres": "ul. Testowa 1, 00-001 Warszawa",
        },
    )
    assert config.status_code == 200, config.text

    service = admin_client.post(
        "/api/godziny-otwarcia",
        json={
            "dzien_tygodnia": booking_date.weekday(),
            "godz_od": "12:00",
            "godz_do": "22:00",
            "krok_slotu_min": 60,
            "domyslny_turn_time_min": 120,
            "nazwa": "Kolacja R5c",
        },
    )
    assert service.status_code == 201, service.text

    table = admin_client.post(
        "/api/stoliki",
        json={"nazwa": "R5c-S1", "pojemnosc": 4},
    )
    assert table.status_code == 201, table.text

    policy = admin_client.post(
        "/api/polityki-platnosci-rezerwacji",
        json={
            "nazwa": "Zadatek kolacyjny R5c",
            "aktywna": True,
            "data": booking_date.isoformat(),
            "serwis_id": service.json()["id"],
            "kanal": "online",
            "min_osob": 2,
            "max_osob": 4,
            "rodzaj": "zadatek",
            "sposob_kwoty": "stala",
            "kwota_minor": 5_000,
            "waluta": "PLN",
            "waznosc_min": 30,
            "po_niepowodzeniu": "ponow",
            "zwrot_przy_anulowaniu": True,
            "priorytet": 10,
        },
    )
    assert policy.status_code == 201, policy.text


def _create_public_booking(public_client: TestClient, booking_date: date) -> dict:
    config = public_client.get("/api/online/widget-config")
    assert config.status_code == 200, config.text
    widget = config.json()

    hold = public_client.post(
        "/api/online/hold",
        json={
            "data": booking_date.isoformat(),
            "godz_od": "18:00",
            "liczba_osob": 2,
        },
        headers={
            "X-Reservation-Session": SESSION,
            "Idempotency-Key": HOLD_KEY,
        },
    )
    assert hold.status_code == 201, hold.text

    created = public_client.post(
        "/api/online/rezerwacja",
        json={
            "data": booking_date.isoformat(),
            "godz_od": "18:00",
            "liczba_osob": 2,
            "nazwisko": "Gość R5c",
            "email": "gosc-r5c@example.test",
            "privacy_notice_acknowledged": True,
            "privacy_notice_version": widget["privacy"]["notice_version"],
            "marketing_consent": False,
            "marketing_consent_version": widget["marketing"]["version"],
            "sensitive_data_consent": False,
        },
        headers={
            "X-Reservation-Session": SESSION,
            "X-Reservation-Hold": hold.json()["hold_token"],
            "Idempotency-Key": CREATE_KEY,
        },
    )
    assert created.status_code == 201, created.text
    return created.json()


def _assert_guest_safe_payment(response) -> dict:
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "private, no-store"
    body = response.json()
    payment = body["platnosc"]
    forbidden = {
        "provider",
        "external_id",
        "provider_checkout_session_id",
        "provider_payment_intent_id",
        "provider_charge_id",
        "provider_refund_id",
        "reservation_ref",
        "creation_key",
        "policy_snapshot",
        "last_error_code",
    }
    assert forbidden.isdisjoint(payment)
    raw = json.dumps(body, ensure_ascii=False)
    assert "gosc-r5c@example.test" not in raw
    assert "provider_idempotency_key" not in raw
    return body


def test_public_sandbox_payment_retry_rotation_and_cancel_refund(
    admin_client, db, monkeypatch,
):
    booking_date = _booking_date()
    _prepare_paid_booking_policy(admin_client, booking_date)
    monkeypatch.setattr(
        main.integracje,
        "skonfigurowane",
        lambda _integration: False,
    )

    # A separate client proves that the public flow does not borrow the admin JWT.
    with TestClient(main.app) as public_client:
        assert "authorization" not in public_client.headers
        created = _create_public_booking(public_client, booking_date)
        original_token = created["management_token"]
        first_public_payment = created["platnosc"]
        assert first_public_payment["status"] == "oczekuje"
        assert first_public_payment["wymagana"] is True
        assert first_public_payment["rodzaj"] == "zadatek"
        assert first_public_payment["kwota_minor"] == 5_000
        assert first_public_payment["waluta"] == "PLN"
        assert first_public_payment["link"] == "/?platnosc=sandbox&rezerwuj"
        assert first_public_payment["mozna_ponowic"] is False

        # Nowy klient ma już HttpOnly cookie. Dopiero obca sesja bez cookie i
        # bez kompatybilnego nagłówka nie ma capability.
        with TestClient(main.app) as stranger:
            missing_capability = stranger.get(
                "/api/online/zarzadzanie/platnosc",
            )
            assert missing_capability.status_code == 400

        initial_status = _assert_guest_safe_payment(public_client.get(
            "/api/online/zarzadzanie/platnosc",
            headers={"X-Reservation-Token": original_token},
        ))
        first_payment_id = initial_status["platnosc"]["id"]

        blocked_edit = public_client.post(
            "/api/online/zarzadzanie/edytuj",
            json={"liczba_osob": 3},
            headers={
                "X-Reservation-Token": original_token,
                "Idempotency-Key": "r5c-public-edit-pending-payment-0001",
            },
        )
        assert blocked_edit.status_code == 409, blocked_edit.text
        assert blocked_edit.json()["code"] == "PAYMENT_SETTLEMENT_REQUIRED_BEFORE_EDIT"
        db.rollback()
        assert db.query(models.Termin).filter_by(kanal="online").one().liczba_osob == 2

        db.rollback()
        first_payment = db.get(models.Platnosc, first_payment_id)
        reservation_payments.apply_payment_status(
            first_payment,
            "nieudana",
            now=main.utcnow_naive(),
            error_code="sandbox_declined",
            strict=True,
        )
        db.commit()

        failed_status = _assert_guest_safe_payment(public_client.get(
            "/api/online/zarzadzanie/platnosc",
            headers={"X-Reservation-Token": original_token},
        ))
        assert failed_status["platnosc"]["status"] == "nieudana"
        assert failed_status["platnosc"]["mozna_ponowic"] is True
        assert failed_status["platnosc"]["link"] is None

        retry_headers = {
            "X-Reservation-Token": original_token,
            "Idempotency-Key": "r5c-public-payment-retry-0001",
        }
        retried = public_client.post(
            "/api/online/zarzadzanie/platnosc/ponow",
            headers=retry_headers,
        )
        replayed = public_client.post(
            "/api/online/zarzadzanie/platnosc/ponow",
            headers=retry_headers,
        )
        assert retried.status_code == replayed.status_code == 200, retried.text
        assert retried.json() == replayed.json()
        successor_token = retried.json()["management_token"]
        retried_payment = retried.json()["platnosc"]
        assert successor_token != original_token
        assert retried_payment["id"] != first_payment_id
        assert retried_payment["status"] == "oczekuje"
        assert retried_payment["link"] == "/?platnosc=sandbox&rezerwuj"

        consumed_status = public_client.get(
            "/api/online/zarzadzanie/platnosc",
            headers={"X-Reservation-Token": original_token},
        )
        assert consumed_status.status_code == 409
        assert consumed_status.json()["code"] == "MANAGEMENT_TOKEN_USED"

        db.rollback()
        assert db.query(models.Platnosc).count() == 2
        assert db.query(models.RezerwacjaPlatnoscPolecenie).count() == 2

        # Managed R5c payments remain manually confirmable only in explicit sandbox.
        marked_paid = admin_client.post(
            f"/api/platnosci/{retried_payment['id']}/oplacona",
        )
        assert marked_paid.status_code == 200, marked_paid.text
        assert marked_paid.json()["provider"] == "sandbox"
        assert marked_paid.json()["status"] == "oplacona"

        cancel_headers = {
            "X-Reservation-Token": successor_token,
            "Idempotency-Key": "r5c-public-cancel-paid-0001",
        }
        cancelled = public_client.post(
            "/api/online/zarzadzanie/odwolaj",
            headers=cancel_headers,
        )
        cancel_replay = public_client.post(
            "/api/online/zarzadzanie/odwolaj",
            headers=cancel_headers,
        )
        assert cancelled.status_code == cancel_replay.status_code == 200, cancelled.text
        assert cancelled.json() == cancel_replay.json()
        assert cancelled.json()["platnosc"]["status"] == "zwrocona"
        assert cancelled.json()["platnosc"]["refund_status"] == "zwrocona"
        final_token = cancelled.json()["management_token"]

        final_status = _assert_guest_safe_payment(public_client.get(
            "/api/online/zarzadzanie/platnosc",
            headers={"X-Reservation-Token": final_token},
        ))
        assert final_status["rezerwacja"]["status"] == "odwolana"
        assert final_status["platnosc"]["status"] == "zwrocona"
        assert final_status["platnosc"]["zwrocono_minor"] == 5_000
        assert final_status["platnosc"]["link"] is None

    db.rollback()
    db.expire_all()
    reservation = db.query(models.Termin).filter_by(kanal="online").one()
    paid_attempt = db.get(models.Platnosc, retried_payment["id"])
    assert reservation.status == "odwolana"
    assert reservation.zadatek == 0
    assert paid_attempt.status == "zwrocona"
    assert paid_attempt.przechwycono_minor == paid_attempt.zwrocono_minor == 5_000
    assert db.query(models.RezerwacjaStolikClaim).filter_by(
        termin_id=reservation.id,
    ).count() == 0


def test_encrypted_httponly_cookie_status_csrf_rotation_and_quota_isolation(
    admin_client, db, monkeypatch,
):
    booking_date = _booking_date()
    _prepare_paid_booking_policy(admin_client, booking_date)
    monkeypatch.setattr(main.integracje, "skonfigurowane", lambda _key: False)
    monkeypatch.setattr(main.app_settings, "IS_DEV", False)
    # Ten test izoluje atrybuty produkcyjnego cookie. Sam fail-closed providera
    # ma osobne testy i jest tu jawnie zastąpiony hermetycznym sandboxem.
    monkeypatch.setattr(
        main.integracje,
        "provider_platnosci_wymaganej",
        lambda: "sandbox",
    )

    with TestClient(main.app, base_url="https://testserver") as public_client:
        created = _create_public_booking(public_client, booking_date)
        raw_token = created["management_token"]
        stored = next(
            cookie for cookie in public_client.cookies.jar
            if cookie.name == main.PUBLIC_MANAGEMENT_COOKIE
        )
        assert stored.path == main.PUBLIC_MANAGEMENT_COOKIE_PATH
        assert stored.secure is True
        assert stored.value.startswith("enc:v1:")
        assert raw_token not in stored.value
        assert szyfrowanie.odszyfruj(stored.value) == raw_token
        assert "HttpOnly" in stored._rest
        assert str(stored._rest.get("SameSite", "")).lower() == "lax"

        # Powrót z Checkout zna wyłącznie cookie; provider ID nie jest potrzebny.
        status = public_client.get("/api/online/zarzadzanie/platnosc")
        assert status.status_code == 200, status.text
        payment_id = status.json()["platnosc"]["id"]

        payment = db.get(models.Platnosc, payment_id)
        reservation_payments.apply_payment_status(
            payment,
            "nieudana",
            now=main.utcnow_naive(),
            error_code="sandbox_declined",
            strict=True,
        )
        db.commit()

        retry_path = "/api/online/zarzadzanie/platnosc/ponow"
        retry_headers = {"Idempotency-Key": "r5c-cookie-payment-retry-0001"}
        no_session = public_client.post(retry_path, headers=retry_headers)
        assert no_session.status_code == 400
        wrong_origin = public_client.post(
            retry_path,
            headers={
                **retry_headers,
                "X-Reservation-Session": SESSION,
                "Origin": "https://attacker.example",
                "Sec-Fetch-Site": "cross-site",
            },
        )
        assert wrong_origin.status_code == 403

        previous_ciphertext = stored.value
        retried = public_client.post(
            retry_path,
            headers={
                **retry_headers,
                "X-Reservation-Session": SESSION,
                # Browser-controlled metadata stays trustworthy behind TLS proxy.
                "Origin": "https://public.lokalo.test",
                "Sec-Fetch-Site": "same-origin",
            },
        )
        assert retried.status_code == 200, retried.text
        successor = retried.json()["management_token"]
        rotated = next(
            cookie for cookie in public_client.cookies.jar
            if cookie.name == main.PUBLIC_MANAGEMENT_COOKIE
        )
        assert rotated.value != previous_ciphertext
        assert successor not in rotated.value
        assert szyfrowanie.odszyfruj(rotated.value) == successor

        # Polling i retry mają osobne współdzielone kwoty. Nie zużywają
        # budżetu cancel/edit/RODO (`reservation-management`).
        db.rollback()
        quota_counts = {
            row.scope: row.count
            for row in db.query(models.RezerwacjaPublicznaKwota).all()
        }
        assert quota_counts["payment-status"] == 1
        assert quota_counts["payment-action"] == 3
        assert "reservation-management" not in quota_counts

        cancelled = public_client.post(
            "/api/online/zarzadzanie/odwolaj",
            headers={
                "X-Reservation-Session": SESSION,
                "Idempotency-Key": "r5c-cookie-cancel-0001",
                # Jawnie skonfigurowany cross-origin API_BASE przechodzi CORS i
                # ten sam allowlistowy guard mutacji cookie.
                "Origin": "http://localhost",
            },
        )
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "odwolana"


def test_public_payment_cookie_cors_allows_only_configured_credentialed_origin(client):
    preflight = client.options(
        "/api/online/zarzadzanie/platnosc",
        headers={
            "Origin": "http://localhost",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-Reservation-Session",
        },
    )
    assert preflight.status_code == 200, preflight.text
    assert preflight.headers["access-control-allow-origin"] == "http://localhost"
    assert preflight.headers["access-control-allow-credentials"] == "true"


def test_stripe_webhook_is_exact_public_raw_signed_and_read_only_safe(
    client, db, monkeypatch,
):
    assert "authorization" not in client.headers
    calls = []

    def fake_ingest(raw_body, signature, *, received_at):
        calls.append((raw_body, signature, received_at))
        return reservation_payment_worker.IngestedPaymentWebhook(
            id=77,
            duplicate=len(calls) > 1,
            state="queued",
        )

    monkeypatch.setattr(
        main.reservation_payment_worker,
        "ingest_payment_webhook",
        fake_ingest,
    )
    subscription = db.get(models.Subskrypcja, 1)
    subscription.status = "wygasla"
    db.commit()

    raw = b'{"id":"evt_r5c_http","type":"payment_intent.succeeded"}'
    signature = "t=1784210400,v1=test-signature"
    first = client.post(
        "/api/online/platnosci/stripe/webhook",
        content=raw,
        headers={"Stripe-Signature": signature},
    )
    duplicate = client.post(
        "/api/online/platnosci/stripe/webhook",
        content=raw,
        headers={"Stripe-Signature": signature},
    )
    assert first.status_code == duplicate.status_code == 200, first.text
    assert first.json() == {"received": True, "duplicate": False, "state": "queued"}
    assert duplicate.json() == {"received": True, "duplicate": True, "state": "queued"}
    assert [call[:2] for call in calls] == [(raw, signature), (raw, signature)]
    assert all(call[2].tzinfo is None for call in calls)

    missing_signature = client.post(
        "/api/online/platnosci/stripe/webhook",
        content=raw,
    )
    assert missing_signature.status_code == 400
    assert len(calls) == 2

    # Restore writes so nearby, non-allowlisted paths reach the JWT guard instead
    # of the read-only subscription guard. Matching is exact in method and path.
    subscription = db.get(models.Subskrypcja, 1)
    subscription.status = "aktywna"
    db.commit()
    assert client.get(
        "/api/online/platnosci/stripe/webhook",
    ).status_code == 401
    assert client.post(
        "/api/online/platnosci/stripe/webhook/extra",
        content=raw,
        headers={"Stripe-Signature": signature},
    ).status_code == 401
