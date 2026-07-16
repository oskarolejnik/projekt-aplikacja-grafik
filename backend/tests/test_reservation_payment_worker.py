"""Durability and monotonic-projection tests for the R5c payment worker."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import models
import reservation_payment_worker as worker


NOW = datetime(2026, 7, 16, 10, 0, 0)


class FakeStripeDriver:
    def __init__(self):
        self.calls = []
        self.create_responses = []
        self.capture_response = None
        self.cancel_response = None
        self.expire_response = None
        self.refund_response = None
        self.intent_response = None
        self.session_response = None
        self.retrieve_refund_response = None
        self.webhook_event = None
        self.before_call = None

    def _call(self, method, args, kwargs, response):
        self.calls.append((method, args, kwargs))
        if self.before_call is not None:
            self.before_call(method)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, dict):
            response = dict(response)
            if method in {"create_checkout", "expire", "retrieve_session"}:
                response.setdefault("currency", "pln")
                response.setdefault("amount_total", 10_000)
                response.setdefault(
                    "metadata", {"lokalo_payment_ref": "pay_test_opaque"},
                )
                response.setdefault("client_reference_id", "pay_test_opaque")
                if isinstance(response.get("payment_intent"), dict):
                    intent = dict(response["payment_intent"])
                    intent.setdefault("currency", "pln")
                    intent.setdefault("amount", 10_000)
                    intent.setdefault(
                        "metadata", {"lokalo_payment_ref": "pay_test_opaque"},
                    )
                    response["payment_intent"] = intent
            elif method in {"capture", "cancel", "retrieve_intent"}:
                response.setdefault("currency", "pln")
                response.setdefault("amount", 10_000)
                response.setdefault(
                    "metadata", {"lokalo_payment_ref": "pay_test_opaque"},
                )
            elif method in {"refund", "retrieve_refund"}:
                response.setdefault("currency", "pln")
                response.setdefault(
                    "metadata", {"lokalo_payment_ref": "pay_test_opaque"},
                )
                if method == "refund" and args:
                    response.setdefault("payment_intent", args[0])
        return response

    def create_checkout_session(self, **kwargs):
        response = self.create_responses.pop(0)
        return self._call("create_checkout", (), kwargs, response)

    def capture_payment_intent(self, *args, **kwargs):
        return self._call("capture", args, kwargs, self.capture_response)

    def cancel_payment_intent(self, *args, **kwargs):
        return self._call("cancel", args, kwargs, self.cancel_response)

    def expire_checkout_session(self, *args, **kwargs):
        return self._call("expire", args, kwargs, self.expire_response)

    def create_full_refund(self, *args, **kwargs):
        return self._call("refund", args, kwargs, self.refund_response)

    def retrieve_payment_intent(self, *args, **kwargs):
        return self._call("retrieve_intent", args, kwargs, self.intent_response)

    def retrieve_checkout_session(self, *args, **kwargs):
        return self._call("retrieve_session", args, kwargs, self.session_response)

    def retrieve_refund(self, *args, **kwargs):
        return self._call(
            "retrieve_refund", args, kwargs, self.retrieve_refund_response
        )

    def construct_webhook_event(self, *args, **kwargs):
        return self._call("construct_event", args, kwargs, self.webhook_event)


def _payment_and_command(
    db,
    *,
    command_type="create_checkout",
    payment_status="oczekuje",
    amount_minor=10_000,
    captured_minor=0,
    refunded_minor=0,
    command_amount_minor=None,
    capture_mode="automatic",
    checkout_session_id=None,
    payment_intent_id=None,
    refund_status="brak",
    command_state="queued",
    attempts=0,
    available_at=NOW,
    expires_at=None,
    lease_token=None,
    lease_expires_at=None,
    termin_id=None,
    failure_policy="ponow",
    refund_on_cancel=True,
):
    expires_at = expires_at or (NOW + timedelta(hours=4))
    external_id = "pay_test_opaque"
    if db.query(models.Platnosc.id).filter_by(
        provider="stripe", external_id=external_id,
    ).first() is not None:
        external_id = f"{external_id}_{db.query(models.Platnosc).count() + 1}"
    payment = models.Platnosc(
        termin_id=termin_id,
        polityka_id=None,
        kwota=amount_minor / 100,
        kwota_minor=amount_minor,
        przechwycono_minor=captured_minor,
        zwrocono_minor=refunded_minor,
        waluta="PLN",
        rodzaj=("preautoryzacja" if capture_mode == "manual" else "zadatek"),
        status=payment_status,
        refund_status=refund_status,
        tryb_przechwycenia=capture_mode,
        provider="stripe",
        external_id=external_id,
        provider_checkout_session_id=checkout_session_id,
        provider_payment_intent_id=payment_intent_id,
        reservation_ref="b" * 64,
        creation_key=None,
        policy_snapshot={
            "version": 1,
            "po_niepowodzeniu": failure_policy,
            "zwrot_przy_anulowaniu": refund_on_cancel,
        },
        expires_at=expires_at,
        utworzono_at=NOW,
        zaktualizowano_at=NOW,
        autoryzowano_at=(NOW if payment_status == "autoryzowana" else None),
        oplacono_at=(
            NOW if payment_status in {"oplacona", "zwrocona"} else None
        ),
        zwrocono_at=(NOW if payment_status == "zwrocona" else None),
        version=0,
    )
    db.add(payment)
    db.flush()
    command = models.RezerwacjaPlatnoscPolecenie(
        platnosc_id=payment.id,
        typ=command_type,
        operation_key=f"test:{command_type}",
        provider_idempotency_key=hashlib_sha(payment.id, command_type),
        kwota_minor=command_amount_minor,
        stan=command_state,
        liczba_prob=attempts,
        maks_prob=5,
        available_at=available_at,
        expires_at=expires_at,
        lease_token=lease_token,
        lease_expires_at=lease_expires_at,
        actor_kind="system",
        created_at=NOW,
        updated_at=NOW,
    )
    db.add(command)
    db.commit()
    return payment.id, command.id


def hashlib_sha(payment_id, command_type):
    import hashlib

    return hashlib.sha256(f"{payment_id}:{command_type}".encode()).hexdigest()


def _row(db, model, row_id):
    db.expire_all()
    return db.get(model, row_id)


def _enable(monkeypatch):
    monkeypatch.setattr(worker.integracje, "skonfigurowane", lambda key: key == "platnosci")


def _reservation(db, *, deposit=0.0):
    reservation = models.Termin(
        data=date(2026, 7, 20),
        nazwisko="Test",
        liczba_osob=4,
        status="rezerwacja",
        zadatek=deposit,
        utworzono_at=NOW,
        godz_od=time(18, 0),
        godz_do=time(20, 0),
        kanal="online",
        rodzaj="stolik",
    )
    db.add(reservation)
    db.commit()
    return reservation.id


def _webhook_row(
    db,
    *,
    payment_id,
    event_type,
    object_type,
    object_id,
):
    row = models.RezerwacjaPlatnoscWebhook(
        platnosc_id=payment_id,
        provider="stripe",
        event_id=f"evt_{event_type.replace('.', '_')}_{object_id}",
        event_type=event_type,
        api_version="2026-06-24.dahlia",
        livemode=False,
        object_id=object_id,
        object_type=object_type,
        payload_sha256="d" * 64,
        stan="queued",
        liczba_prob=0,
        maks_prob=8,
        available_at=NOW,
        received_at=NOW,
    )
    db.add(row)
    db.commit()
    return row.id


def test_disabled_integration_never_claims_or_builds_driver(db, monkeypatch):
    _, command_id = _payment_and_command(db)
    monkeypatch.setattr(worker.integracje, "skonfigurowane", lambda _key: False)

    def forbidden():
        raise AssertionError("driver must not be constructed")

    monkeypatch.setattr(worker.StripePaymentDriver, "from_environment", forbidden)
    result = worker.run_payment_commands_once(limit=1, now=NOW)

    assert result == {
        "enabled": False,
        "processed": 0,
        "succeeded": 0,
        "retry": 0,
        "failed": 0,
        "uncertain": 0,
    }
    assert _row(db, models.RezerwacjaPlatnoscPolecenie, command_id).stan == "queued"


def test_checkout_claim_is_committed_before_io_and_finalized(db, monkeypatch):
    _enable(monkeypatch)
    payment_id, command_id = _payment_and_command(db)
    driver = FakeStripeDriver()
    expires_epoch = int((NOW + timedelta(hours=4)).replace(tzinfo=timezone.utc).timestamp())
    driver.create_responses = [{
        "id": "cs_test_checkout",
        "status": "open",
        "payment_status": "unpaid",
        "url": "https://checkout.stripe.com/c/pay_test",
        "expires_at": expires_epoch,
        "payment_intent": "pi_test_checkout",
    }]

    def assert_committed(_method):
        session = worker.SessionLocal()
        try:
            command = session.get(models.RezerwacjaPlatnoscPolecenie, command_id)
            assert command.stan == "processing"
            assert command.lease_token
        finally:
            session.close()

    driver.before_call = assert_committed
    result = worker.run_payment_commands_once(limit=1, driver=driver, now=NOW)

    assert result["succeeded"] == 1
    command = _row(db, models.RezerwacjaPlatnoscPolecenie, command_id)
    payment = _row(db, models.Platnosc, payment_id)
    assert command.stan == "succeeded"
    assert command.lease_token is None
    assert command.provider_object_id == "cs_test_checkout"
    assert payment.provider_checkout_session_id == "cs_test_checkout"
    assert payment.provider_payment_intent_id == "pi_test_checkout"
    assert payment.link == "https://checkout.stripe.com/c/pay_test"
    assert payment.status == "oczekuje"
    _, _, kwargs = driver.calls[0]
    assert kwargs["attempt_ref"] == command.provider_idempotency_key
    assert kwargs["kind"] == "deposit"


def test_checkout_deadline_keeps_stripe_minimum_after_worker_delay(db, monkeypatch):
    _enable(monkeypatch)
    requested_expiry = NOW + timedelta(minutes=30)
    _payment_and_command(db, expires_at=requested_expiry)
    driver = FakeStripeDriver()
    provider_expiry = NOW + timedelta(minutes=31, seconds=10)
    driver.create_responses = [{
        "id": "cs_test_minimum_expiry",
        "status": "open",
        "payment_status": "unpaid",
        "url": "https://checkout.stripe.com/c/minimum-expiry",
        "expires_at": int(provider_expiry.replace(tzinfo=timezone.utc).timestamp()),
        "payment_intent": "pi_test_minimum_expiry",
    }]

    worker.run_payment_commands_once(
        limit=1,
        driver=driver,
        now=NOW + timedelta(seconds=10),
    )

    _, _, kwargs = driver.calls[0]
    assert kwargs["expires_at"] == int(
        provider_expiry.replace(tzinfo=timezone.utc).timestamp()
    )


def test_transient_retry_reuses_stable_command_reference(db, monkeypatch):
    _enable(monkeypatch)
    _, command_id = _payment_and_command(db)
    driver = FakeStripeDriver()
    driver.create_responses = [
        RuntimeError("ambiguous network failure"),
        {
            "id": "cs_test_retry",
            "status": "open",
            "payment_status": "unpaid",
            "url": "https://checkout.stripe.com/c/retry",
            "expires_at": int(
                (NOW + timedelta(hours=4)).replace(tzinfo=timezone.utc).timestamp()
            ),
            "payment_intent": "pi_test_retry",
        },
    ]

    first = worker.run_payment_commands_once(limit=1, driver=driver, now=NOW)
    command = _row(db, models.RezerwacjaPlatnoscPolecenie, command_id)
    assert first["retry"] == 1
    assert command.stan == "retry"
    retry_at = command.available_at

    second = worker.run_payment_commands_once(
        limit=1, driver=driver, now=retry_at
    )
    command = _row(db, models.RezerwacjaPlatnoscPolecenie, command_id)
    assert second["succeeded"] == 1
    assert command.liczba_prob == 2
    assert driver.calls[0][2]["attempt_ref"] == driver.calls[1][2]["attempt_ref"]


def test_checkout_expired_before_claim_projects_expired_and_releases_reservation(db):
    reservation_id = _reservation(db)
    payment_id, command_id = _payment_and_command(
        db,
        termin_id=reservation_id,
        failure_policy="zwolnij",
        available_at=NOW - timedelta(minutes=1),
        expires_at=NOW,
    )

    assert worker.claim_next(now=NOW) is None

    payment = _row(db, models.Platnosc, payment_id)
    command = _row(db, models.RezerwacjaPlatnoscPolecenie, command_id)
    reservation = _row(db, models.Termin, reservation_id)
    assert payment.status == "wygasla"
    assert payment.wygasla_at == NOW
    assert payment.last_error_code == "COMMAND_EXPIRED_BEFORE_CLAIM"
    assert command.stan == "failed"
    assert command.last_error_code == "COMMAND_EXPIRED_BEFORE_CLAIM"
    assert reservation.status == "odwolana"
    assert reservation.odwolano_at == NOW
    assert db.query(models.ReservationAudit).filter_by(
        termin_id=reservation_id,
        action="cancel",
        actor_kind="system",
    ).count() == 1
    assert db.query(models.RezerwacjaDzienLedger).filter_by(
        data=reservation.data,
    ).one().revision == 1


def test_checkout_expired_before_claim_keeps_reservation_for_retry_policy(db):
    reservation_id = _reservation(db)
    payment_id, command_id = _payment_and_command(
        db,
        termin_id=reservation_id,
        failure_policy="ponow",
        available_at=NOW - timedelta(minutes=1),
        expires_at=NOW,
    )

    assert worker.claim_next(now=NOW) is None

    assert _row(db, models.Platnosc, payment_id).status == "wygasla"
    assert _row(db, models.RezerwacjaPlatnoscPolecenie, command_id).stan == "failed"
    assert _row(db, models.Termin, reservation_id).status == "rezerwacja"
    assert db.query(models.ReservationAudit).filter_by(
        termin_id=reservation_id,
        action="cancel",
        actor_kind="system",
    ).count() == 0


def test_capture_projects_paid_amount_monotonically(db, monkeypatch):
    _enable(monkeypatch)
    reservation_id = _reservation(db)
    payment_id, command_id = _payment_and_command(
        db,
        command_type="capture",
        payment_status="autoryzowana",
        capture_mode="manual",
        command_amount_minor=7_500,
        payment_intent_id="pi_test_capture",
        termin_id=reservation_id,
    )
    driver = FakeStripeDriver()
    driver.capture_response = {
        "id": "pi_test_capture",
        "status": "succeeded",
        "amount": 10_000,
        "amount_received": 7_500,
        "latest_charge": {"id": "ch_test_capture"},
    }

    worker.run_payment_commands_once(limit=1, driver=driver, now=NOW)

    payment = _row(db, models.Platnosc, payment_id)
    command = _row(db, models.RezerwacjaPlatnoscPolecenie, command_id)
    assert payment.status == "oplacona"
    assert payment.przechwycono_minor == 7_500
    assert payment.provider_charge_id == "ch_test_capture"
    assert _row(db, models.Termin, reservation_id).zadatek == 75.0
    assert command.stan == "succeeded"
    assert driver.calls[0][2]["operation_ref"] == command.provider_idempotency_key


def test_capture_finishing_after_soft_cancel_queues_one_full_refund(
    db, monkeypatch
):
    _enable(monkeypatch)
    reservation_id = _reservation(db)
    payment_id, _ = _payment_and_command(
        db,
        command_type="capture",
        payment_status="autoryzowana",
        capture_mode="manual",
        command_amount_minor=10_000,
        payment_intent_id="pi_test_cancel_race",
        termin_id=reservation_id,
    )
    claim = worker.claim_next(now=NOW)
    assert claim is not None

    reservation = _row(db, models.Termin, reservation_id)
    reservation.status = "odwolana"
    reservation.odwolano_at = NOW
    worker.reservation_payments.request_reservation_cancellation_settlement(
        db,
        reservation,
        now=NOW,
        actor_kind="guest",
    )
    db.commit()

    driver = FakeStripeDriver()
    driver.capture_response = {
        "id": "pi_test_cancel_race",
        "status": "succeeded",
        "amount": 10_000,
        "amount_received": 10_000,
        "latest_charge": {"id": "ch_test_cancel_race"},
    }
    projection = worker.execute_claim(claim, driver, now=NOW)
    assert worker.finalize_claim(claim, projection, now=NOW) == "succeeded"

    payment = _row(db, models.Platnosc, payment_id)
    refunds = db.query(models.RezerwacjaPlatnoscPolecenie).filter_by(
        platnosc_id=payment_id,
        typ="refund",
        reason_code="reservation_cancelled",
    ).all()
    assert payment.status == "oplacona"
    assert payment.refund_status == "oczekuje"
    assert len(refunds) == 1 and refunds[0].kwota_minor == 10_000

    # A duplicate/later canonical paid projection must reuse the same settlement.
    webhook_id = _webhook_row(
        db,
        payment_id=payment_id,
        event_type="payment_intent.succeeded",
        object_type="payment_intent",
        object_id="pi_test_cancel_race",
    )
    driver.intent_response = driver.capture_response
    assert worker.run_payment_webhooks_once(
        limit=1, driver=driver, now=NOW + timedelta(seconds=1),
    )["processed"] == 1
    assert _row(db, models.RezerwacjaPlatnoscWebhook, webhook_id).stan == "processed"
    assert db.query(models.RezerwacjaPlatnoscPolecenie).filter_by(
        platnosc_id=payment_id,
        typ="refund",
        reason_code="reservation_cancelled",
    ).count() == 1


def test_capture_finishing_after_hard_delete_keeps_refund_intent(
    db, monkeypatch
):
    _enable(monkeypatch)
    reservation_id = _reservation(db)
    payment_id, _ = _payment_and_command(
        db,
        command_type="capture",
        payment_status="autoryzowana",
        capture_mode="manual",
        command_amount_minor=10_000,
        payment_intent_id="pi_test_delete_race",
        termin_id=reservation_id,
    )
    claim = worker.claim_next(now=NOW)
    assert claim is not None

    reservation = _row(db, models.Termin, reservation_id)
    worker.reservation_payments.request_reservation_cancellation_settlement(
        db,
        reservation,
        now=NOW,
        actor_kind="user",
        operation_key=f"reservation-delete:{reservation_id}",
    )
    db.delete(reservation)
    db.commit()
    assert _row(db, models.Termin, reservation_id) is None

    driver = FakeStripeDriver()
    driver.capture_response = {
        "id": "pi_test_delete_race",
        "status": "succeeded",
        "amount": 10_000,
        "amount_received": 10_000,
        "latest_charge": {"id": "ch_test_delete_race"},
    }
    projection = worker.execute_claim(claim, driver, now=NOW)
    assert worker.finalize_claim(claim, projection, now=NOW) == "succeeded"

    payment = _row(db, models.Platnosc, payment_id)
    refunds = db.query(models.RezerwacjaPlatnoscPolecenie).filter_by(
        platnosc_id=payment_id,
        typ="refund",
        reason_code="reservation_cancelled",
    ).all()
    assert payment.status == "oplacona"
    assert payment.refund_status == "oczekuje"
    assert len(refunds) == 1 and refunds[0].kwota_minor == 10_000


def test_hard_delete_marks_every_attempt_for_late_capture_settlement(
    db, monkeypatch
):
    _enable(monkeypatch)
    reservation_id = _reservation(db)
    old_payment_id, _ = _payment_and_command(
        db,
        command_state="failed",
        payment_status="nieudana",
        payment_intent_id="pi_test_old_attempt",
        termin_id=reservation_id,
    )
    new_payment_id, _ = _payment_and_command(
        db,
        payment_intent_id="pi_test_new_attempt",
        termin_id=reservation_id,
    )
    reservation = _row(db, models.Termin, reservation_id)

    worker.reservation_payments.request_reservation_cancellation_settlement(
        db,
        reservation,
        now=NOW,
        actor_kind="user",
        operation_key=f"reservation-delete:{reservation_id}",
    )
    assert db.query(models.RezerwacjaPlatnoscPolecenie).filter_by(
        platnosc_id=old_payment_id,
        typ="reconcile",
        reason_code="reservation_cancelled",
    ).count() == 1
    assert db.query(models.RezerwacjaPlatnoscPolecenie).filter_by(
        platnosc_id=new_payment_id,
        typ="cancel_authorization",
        reason_code="reservation_cancelled",
    ).count() == 1
    db.delete(reservation)
    db.commit()

    _webhook_row(
        db,
        payment_id=old_payment_id,
        event_type="payment_intent.succeeded",
        object_type="payment_intent",
        object_id="pi_test_old_attempt",
    )
    driver = FakeStripeDriver()
    driver.intent_response = {
        "id": "pi_test_old_attempt",
        "status": "succeeded",
        "amount": 10_000,
        "amount_received": 10_000,
        "latest_charge": {"id": "ch_test_old_attempt"},
    }

    assert worker.run_payment_webhooks_once(
        limit=1, driver=driver, now=NOW,
    )["processed"] == 1
    old_payment = _row(db, models.Platnosc, old_payment_id)
    assert old_payment.status == "oplacona"
    assert old_payment.refund_status == "oczekuje"
    assert db.query(models.RezerwacjaPlatnoscPolecenie).filter_by(
        platnosc_id=old_payment_id,
        typ="refund",
        reason_code="reservation_cancelled",
    ).count() == 1


def test_late_canonical_capture_overrides_local_cancel_and_queues_refund(
    db, monkeypatch
):
    _enable(monkeypatch)
    reservation_id = _reservation(db)
    reservation = _row(db, models.Termin, reservation_id)
    reservation.status = "odwolana"
    reservation.odwolano_at = NOW
    payment_id, command_id = _payment_and_command(
        db,
        command_type="cancel_authorization",
        command_state="succeeded",
        payment_status="anulowana",
        payment_intent_id="pi_test_late_capture",
        termin_id=reservation_id,
    )
    command = _row(db, models.RezerwacjaPlatnoscPolecenie, command_id)
    command.reason_code = "reservation_cancelled"
    db.commit()
    _webhook_row(
        db,
        payment_id=payment_id,
        event_type="payment_intent.succeeded",
        object_type="payment_intent",
        object_id="pi_test_late_capture",
    )
    driver = FakeStripeDriver()
    driver.intent_response = {
        "id": "pi_test_late_capture",
        "status": "succeeded",
        "amount": 10_000,
        "amount_received": 10_000,
        "latest_charge": {"id": "ch_test_late_capture"},
    }

    result = worker.run_payment_webhooks_once(limit=1, driver=driver, now=NOW)

    payment = _row(db, models.Platnosc, payment_id)
    assert result["processed"] == 1
    assert payment.status == "oplacona"
    assert payment.przechwycono_minor == 10_000
    assert payment.refund_status == "oczekuje"
    assert db.query(models.RezerwacjaPlatnoscPolecenie).filter_by(
        platnosc_id=payment_id,
        typ="refund",
        reason_code="reservation_cancelled",
    ).count() == 1


def test_cancel_without_intent_expires_checkout_and_marks_cancelled(db, monkeypatch):
    _enable(monkeypatch)
    payment_id, _ = _payment_and_command(
        db,
        command_type="cancel_authorization",
        checkout_session_id="cs_test_cancel",
    )
    driver = FakeStripeDriver()
    driver.expire_response = {
        "id": "cs_test_cancel",
        "status": "expired",
        "payment_status": "unpaid",
        "url": None,
        "payment_intent": None,
    }

    worker.run_payment_commands_once(limit=1, driver=driver, now=NOW)

    assert _row(db, models.Platnosc, payment_id).status == "anulowana"
    assert driver.calls[0][0] == "expire"


def test_full_refund_projects_terminal_refund(db, monkeypatch):
    _enable(monkeypatch)
    reservation_id = _reservation(db, deposit=100.0)
    payment_id, command_id = _payment_and_command(
        db,
        command_type="refund",
        payment_status="oplacona",
        captured_minor=10_000,
        command_amount_minor=10_000,
        payment_intent_id="pi_test_refund",
        refund_status="oczekuje",
        termin_id=reservation_id,
    )
    driver = FakeStripeDriver()
    driver.refund_response = {
        "id": "re_test_refund",
        "status": "succeeded",
        "amount": 10_000,
    }

    worker.run_payment_commands_once(limit=1, driver=driver, now=NOW)

    payment = _row(db, models.Platnosc, payment_id)
    command = _row(db, models.RezerwacjaPlatnoscPolecenie, command_id)
    assert payment.status == "zwrocona"
    assert payment.refund_status == "zwrocona"
    assert payment.zwrocono_minor == 10_000
    assert _row(db, models.Termin, reservation_id).zadatek == 0.0
    assert command.provider_object_id == "re_test_refund"


def test_partial_refund_fails_closed_without_provider_io(db, monkeypatch):
    _enable(monkeypatch)
    payment_id, command_id = _payment_and_command(
        db,
        command_type="refund",
        payment_status="oplacona",
        captured_minor=10_000,
        command_amount_minor=5_000,
        payment_intent_id="pi_test_refund",
        refund_status="oczekuje",
    )
    driver = FakeStripeDriver()

    result = worker.run_payment_commands_once(limit=1, driver=driver, now=NOW)

    assert result["failed"] == 1
    assert driver.calls == []
    assert _row(db, models.Platnosc, payment_id).status == "oplacona"
    assert _row(db, models.Platnosc, payment_id).refund_status == "nieudana"
    command = _row(db, models.RezerwacjaPlatnoscPolecenie, command_id)
    assert command.last_error_code == "PARTIAL_REFUND_UNSUPPORTED"


def test_reconcile_does_not_regress_paid_payment_to_authorized(db, monkeypatch):
    _enable(monkeypatch)
    payment_id, _ = _payment_and_command(
        db,
        command_type="reconcile",
        payment_status="oplacona",
        captured_minor=10_000,
        capture_mode="manual",
        payment_intent_id="pi_test_reconcile",
    )
    driver = FakeStripeDriver()
    driver.intent_response = {
        "id": "pi_test_reconcile",
        "status": "requires_capture",
        "amount": 10_000,
        "latest_charge": {
            "id": "ch_test_reconcile",
            "payment_method_details": {
                "card": {"capture_before": 1_800_000_000}
            },
        },
    }

    worker.run_payment_commands_once(limit=1, driver=driver, now=NOW)

    payment = _row(db, models.Platnosc, payment_id)
    assert payment.status == "oplacona"
    assert payment.przechwycono_minor == 10_000


def test_expired_processing_lease_becomes_uncertain_without_io(db):
    _, command_id = _payment_and_command(
        db,
        command_state="processing",
        attempts=5,
        available_at=NOW - timedelta(minutes=1),
        expires_at=NOW,
        lease_token="c" * 64,
        lease_expires_at=NOW - timedelta(seconds=1),
    )

    assert worker.claim_next(now=NOW) is None

    command = _row(db, models.RezerwacjaPlatnoscPolecenie, command_id)
    assert command.stan == "uncertain"
    assert command.uncertain_at == NOW
    assert command.lease_token is None


def test_signed_webhook_ingest_is_deduplicated_without_storing_payload(
    db, monkeypatch
):
    _enable(monkeypatch)
    payment_id, _ = _payment_and_command(db)
    driver = FakeStripeDriver()
    driver.webhook_event = {
        "id": "evt_test_duplicate",
        "type": "checkout.session.completed",
        "api_version": "2026-06-24.dahlia",
        "livemode": False,
        "created": 1_800_000_000,
        "data": {
            "object": {
                "id": "cs_test_duplicate",
                "object": "checkout.session",
                "metadata": {"lokalo_payment_ref": "pay_test_opaque"},
            }
        },
    }
    raw = b'{"id":"evt_test_duplicate"}'

    first = worker.ingest_payment_webhook(raw, "sig", driver=driver, received_at=NOW)
    second = worker.ingest_payment_webhook(raw, "sig", driver=driver, received_at=NOW)

    assert first.id == second.id
    assert first.duplicate is False
    assert second.duplicate is True
    rows = db.query(models.RezerwacjaPlatnoscWebhook).all()
    assert len(rows) == 1
    assert rows[0].platnosc_id == payment_id
    assert rows[0].payload_sha256 != raw.decode()
    assert not hasattr(rows[0], "raw_payload")


def test_webhook_canonical_success_is_projected_after_committed_claim(
    db, monkeypatch
):
    _enable(monkeypatch)
    reservation_id = _reservation(db)
    payment_id, _ = _payment_and_command(
        db,
        checkout_session_id="cs_test_webhook_success",
        payment_intent_id="pi_test_webhook_success",
        termin_id=reservation_id,
    )
    webhook_id = _webhook_row(
        db,
        payment_id=payment_id,
        event_type="payment_intent.succeeded",
        object_type="payment_intent",
        object_id="pi_test_webhook_success",
    )
    driver = FakeStripeDriver()
    driver.intent_response = {
        "id": "pi_test_webhook_success",
        "status": "succeeded",
        "amount": 10_000,
        "amount_received": 10_000,
        "latest_charge": {"id": "ch_test_webhook_success"},
    }

    def assert_committed(method):
        if method != "retrieve_intent":
            return
        session = worker.SessionLocal()
        try:
            row = session.get(models.RezerwacjaPlatnoscWebhook, webhook_id)
            assert row.stan == "processing"
            assert row.lease_token
        finally:
            session.close()

    driver.before_call = assert_committed
    result = worker.run_payment_webhooks_once(limit=1, driver=driver, now=NOW)

    assert result["processed"] == 1
    assert _row(db, models.RezerwacjaPlatnoscWebhook, webhook_id).stan == "processed"
    assert _row(db, models.Platnosc, payment_id).status == "oplacona"
    assert _row(db, models.Termin, reservation_id).zadatek == 100.0


def test_unordered_webhook_cannot_regress_paid_to_authorized(db, monkeypatch):
    _enable(monkeypatch)
    payment_id, _ = _payment_and_command(
        db,
        payment_status="oplacona",
        captured_minor=10_000,
        capture_mode="manual",
        payment_intent_id="pi_test_old_event",
    )
    _webhook_row(
        db,
        payment_id=payment_id,
        event_type="payment_intent.amount_capturable_updated",
        object_type="payment_intent",
        object_id="pi_test_old_event",
    )
    driver = FakeStripeDriver()
    driver.intent_response = {
        "id": "pi_test_old_event",
        "status": "requires_capture",
        "amount": 10_000,
        "latest_charge": {"id": "ch_test_old_event"},
    }

    worker.run_payment_webhooks_once(limit=1, driver=driver, now=NOW)

    assert _row(db, models.Platnosc, payment_id).status == "oplacona"


def test_refund_webhook_can_arrive_before_payment_success_event(db, monkeypatch):
    _enable(monkeypatch)
    reservation_id = _reservation(db)
    payment_id, _ = _payment_and_command(
        db,
        payment_status="anulowana",
        payment_intent_id="pi_test_refund_unordered",
        termin_id=reservation_id,
        refund_status="oczekuje",
    )
    _webhook_row(
        db,
        payment_id=payment_id,
        event_type="refund.updated",
        object_type="refund",
        object_id="re_test_unordered",
    )
    driver = FakeStripeDriver()
    driver.retrieve_refund_response = {
        "id": "re_test_unordered",
        "status": "succeeded",
        "amount": 10_000,
        "payment_intent": "pi_test_refund_unordered",
    }

    worker.run_payment_webhooks_once(limit=1, driver=driver, now=NOW)

    payment = _row(db, models.Platnosc, payment_id)
    assert payment.status == "zwrocona"
    assert payment.przechwycono_minor == 10_000
    assert payment.zwrocono_minor == 10_000
    assert _row(db, models.Termin, reservation_id).zadatek == 0.0


def test_terminal_async_failure_releases_reservation_under_day_guard(
    db, monkeypatch
):
    _enable(monkeypatch)
    reservation_id = _reservation(db)
    payment_id, _ = _payment_and_command(
        db,
        checkout_session_id="cs_test_async_failed",
        termin_id=reservation_id,
        failure_policy="zwolnij",
    )
    webhook_id = _webhook_row(
        db,
        payment_id=payment_id,
        event_type="checkout.session.async_payment_failed",
        object_type="checkout.session",
        object_id="cs_test_async_failed",
    )
    driver = FakeStripeDriver()
    driver.session_response = {
        "id": "cs_test_async_failed",
        "status": "complete",
        "payment_status": "unpaid",
        "url": None,
        "payment_intent": "pi_test_async_failed",
    }

    worker.run_payment_webhooks_once(limit=1, driver=driver, now=NOW)

    assert _row(db, models.Platnosc, payment_id).status == "nieudana"
    reservation = _row(db, models.Termin, reservation_id)
    assert reservation.status == "odwolana"
    assert reservation.odwolano_at == NOW
    assert _row(db, models.RezerwacjaPlatnoscWebhook, webhook_id).stan == "processed"
    assert db.query(models.RezerwacjaDzienLedger).filter_by(
        data=reservation.data
    ).one().revision == 1
    assert db.query(models.ReservationAudit).filter_by(
        termin_id=reservation_id, action="cancel", actor_kind="system"
    ).count() == 1


def test_unknown_signed_event_is_ignored_without_provider_io(db, monkeypatch):
    _enable(monkeypatch)
    payment_id, _ = _payment_and_command(db)
    webhook_id = _webhook_row(
        db,
        payment_id=payment_id,
        event_type="customer.updated",
        object_type="customer",
        object_id="cus_test_ignored",
    )
    driver = FakeStripeDriver()

    result = worker.run_payment_webhooks_once(limit=1, driver=driver, now=NOW)

    assert result["ignored"] == 1
    assert driver.calls == []
    assert _row(db, models.RezerwacjaPlatnoscWebhook, webhook_id).stan == "ignored"


def test_expired_checkout_never_overrides_canonical_capture():
    result = worker._checkout_result(
        {
            "id": "cs_test_paid_then_expired",
            "status": "expired",
            "payment_status": "paid",
            "currency": "pln",
            "amount_total": 10_000,
            "metadata": {"lokalo_payment_ref": "pay_test_opaque"},
            "client_reference_id": "pay_test_opaque",
            "payment_intent": {
                "id": "pi_test_paid_then_expired",
                "status": "succeeded",
                "currency": "pln",
                "amount": 10_000,
                "amount_received": 10_000,
                "metadata": {"lokalo_payment_ref": "pay_test_opaque"},
                "latest_charge": {"id": "ch_test_paid_then_expired"},
            },
        },
        payment_amount_minor=10_000,
        explicit_cancel=True,
    )

    assert result.payment_target == "oplacona"
    assert result.captured_minor == 10_000


def test_cancel_waits_for_checkout_reference_instead_of_failing(db, monkeypatch):
    _enable(monkeypatch)
    _, command_id = _payment_and_command(
        db,
        command_type="cancel_authorization",
        checkout_session_id=None,
        payment_intent_id=None,
    )

    result = worker.run_payment_commands_once(
        limit=1, driver=FakeStripeDriver(), now=NOW,
    )

    command = _row(db, models.RezerwacjaPlatnoscPolecenie, command_id)
    assert result["retry"] == 1
    assert command.stan == "retry"
    assert command.last_error_code == "PROVIDER_REFERENCE_NOT_READY"


def test_pending_refund_remains_durable_retry(db, monkeypatch):
    _enable(monkeypatch)
    payment_id, command_id = _payment_and_command(
        db,
        command_type="refund",
        payment_status="oplacona",
        captured_minor=10_000,
        command_amount_minor=10_000,
        payment_intent_id="pi_test_pending_refund",
        refund_status="oczekuje",
    )
    driver = FakeStripeDriver()
    driver.refund_response = {
        "id": "re_test_pending_refund",
        "status": "pending",
        "amount": 10_000,
    }

    result = worker.run_payment_commands_once(limit=1, driver=driver, now=NOW)

    command = _row(db, models.RezerwacjaPlatnoscPolecenie, command_id)
    payment = _row(db, models.Platnosc, payment_id)
    assert result["retry"] == 1
    assert command.stan == "retry"
    assert command.provider_object_id == "re_test_pending_refund"
    assert payment.refund_status == "oczekuje"

    command.expires_at = command.available_at + timedelta(seconds=1)
    db.commit()
    assert worker.claim_next(now=command.expires_at) is None
    command = _row(db, models.RezerwacjaPlatnoscPolecenie, command_id)
    assert command.stan == "uncertain"
    assert command.last_error_code == "PROVIDER_RECONCILIATION_REQUIRED"
    assert _row(db, models.Platnosc, payment_id).refund_status == "oczekuje"


def test_refund_expired_before_first_claim_exposes_safe_retry(db):
    payment_id, command_id = _payment_and_command(
        db,
        command_type="refund",
        payment_status="oplacona",
        captured_minor=10_000,
        command_amount_minor=10_000,
        payment_intent_id="pi_test_unstarted_refund",
        refund_status="oczekuje",
        available_at=NOW - timedelta(minutes=1),
        expires_at=NOW,
    )

    assert worker.claim_next(now=NOW) is None

    command = _row(db, models.RezerwacjaPlatnoscPolecenie, command_id)
    payment = _row(db, models.Platnosc, payment_id)
    assert command.stan == "failed"
    assert command.liczba_prob == 0
    assert command.last_error_code == "COMMAND_EXPIRED_BEFORE_CLAIM"
    assert payment.refund_status == "nieudana"

    retry = worker.reservation_payments.request_refund(
        db,
        payment,
        amount_minor=None,
        operation_key="retry-after-local-expiry",
        now=NOW + timedelta(seconds=1),
        actor_user_id=None,
        actor_kind="system",
        reason_code="retry_after_local_expiry",
    )
    db.commit()

    assert retry.stan == "queued"
    assert retry.kwota_minor == 10_000
    assert _row(db, models.Platnosc, payment_id).refund_status == "oczekuje"


def test_late_pending_refund_cannot_regress_failed_projection(db):
    payment_id, _ = _payment_and_command(
        db,
        command_type="refund",
        command_state="failed",
        payment_status="oplacona",
        captured_minor=10_000,
        command_amount_minor=10_000,
        payment_intent_id="pi_test_failed_refund",
        refund_status="nieudana",
    )
    payment = _row(db, models.Platnosc, payment_id)
    worker._apply_provider_projection(
        db,
        payment,
        worker.ProviderCommandResult(
            outcome="retry",
            provider_object_id="re_test_failed_refund",
            payment_intent_id="pi_test_failed_refund",
            refund_status="oczekuje",
            provider_object_type="refund",
            provider_currency="pln",
            provider_amount_minor=10_000,
        ),
        now=NOW,
    )
    db.commit()

    assert _row(db, models.Platnosc, payment_id).refund_status == "nieudana"


def test_dashboard_refund_correlates_by_canonical_payment_intent(db, monkeypatch):
    _enable(monkeypatch)
    payment_id, _ = _payment_and_command(
        db,
        command_state="succeeded",
        payment_status="oplacona",
        captured_minor=10_000,
        payment_intent_id="pi_test_dashboard_refund",
    )
    webhook_id = _webhook_row(
        db,
        payment_id=None,
        event_type="refund.updated",
        object_type="refund",
        object_id="re_test_dashboard_refund",
    )
    driver = FakeStripeDriver()
    driver.retrieve_refund_response = {
        "id": "re_test_dashboard_refund",
        "status": "succeeded",
        "amount": 10_000,
        "currency": "pln",
        "payment_intent": "pi_test_dashboard_refund",
        "metadata": {},
    }

    result = worker.run_payment_webhooks_once(limit=1, driver=driver, now=NOW)

    assert result["processed"] == 1
    assert _row(db, models.RezerwacjaPlatnoscWebhook, webhook_id).platnosc_id == payment_id
    assert _row(db, models.Platnosc, payment_id).status == "zwrocona"


def test_webhook_rejects_wrong_currency_or_amount(db, monkeypatch):
    _enable(monkeypatch)
    payment_id, _ = _payment_and_command(
        db,
        command_state="succeeded",
        payment_intent_id="pi_test_contract_mismatch",
    )
    webhook_id = _webhook_row(
        db,
        payment_id=payment_id,
        event_type="payment_intent.succeeded",
        object_type="payment_intent",
        object_id="pi_test_contract_mismatch",
    )
    driver = FakeStripeDriver()
    driver.intent_response = {
        "id": "pi_test_contract_mismatch",
        "status": "succeeded",
        "currency": "eur",
        "amount": 200,
        "amount_received": 200,
        "metadata": {"lokalo_payment_ref": "pay_test_opaque"},
        "latest_charge": {"id": "ch_test_contract_mismatch"},
    }

    result = worker.run_payment_webhooks_once(limit=1, driver=driver, now=NOW)

    assert result["failed"] == 1
    assert _row(db, models.RezerwacjaPlatnoscWebhook, webhook_id).last_error_code == (
        "PAYMENT_PROJECTION_CONFLICT"
    )
    assert _row(db, models.Platnosc, payment_id).status == "oczekuje"


def test_superseded_attempt_late_capture_queues_exactly_one_refund(db, monkeypatch):
    _enable(monkeypatch)
    payment_id, _ = _payment_and_command(
        db,
        command_state="failed",
        payment_status="nieudana",
        payment_intent_id="pi_test_superseded_capture",
    )
    payment = _row(db, models.Platnosc, payment_id)
    worker.reservation_payments.mark_payment_superseded(
        db, payment, now=NOW, actor_kind="guest",
    )
    db.commit()
    _webhook_row(
        db,
        payment_id=payment_id,
        event_type="payment_intent.succeeded",
        object_type="payment_intent",
        object_id="pi_test_superseded_capture",
    )
    driver = FakeStripeDriver()
    driver.intent_response = {
        "id": "pi_test_superseded_capture",
        "status": "succeeded",
        "amount": 10_000,
        "amount_received": 10_000,
        "latest_charge": {"id": "ch_test_superseded_capture"},
    }

    assert worker.run_payment_webhooks_once(
        limit=1, driver=driver, now=NOW,
    )["processed"] == 1

    payment = _row(db, models.Platnosc, payment_id)
    assert payment.status == "oplacona"
    assert payment.refund_status == "oczekuje"
    assert db.query(models.RezerwacjaPlatnoscPolecenie).filter_by(
        platnosc_id=payment_id,
        typ="refund",
        reason_code="payment_superseded",
    ).count() == 1


def test_reconcile_replays_uncertain_operation_with_original_provider_key(
    db, monkeypatch,
):
    _enable(monkeypatch)
    payment_id, uncertain_id = _payment_and_command(
        db,
        command_state="uncertain",
        attempts=5,
    )
    payment = _row(db, models.Platnosc, payment_id)
    reconcile = worker.reservation_payments.queue_command(
        db,
        payment,
        "reconcile",
        operation_key="operator-reconcile:test",
        now=NOW,
        actor_kind="user",
        reason_code="operator_reconcile",
    )
    db.commit()
    driver = FakeStripeDriver()
    driver.create_responses = [{
        "id": "cs_test_reconciled_checkout",
        "status": "open",
        "payment_status": "unpaid",
        "url": "https://checkout.stripe.com/c/reconciled",
        "expires_at": int((NOW + timedelta(hours=4)).replace(tzinfo=timezone.utc).timestamp()),
        "payment_intent": "pi_test_reconciled_checkout",
    }]

    result = worker.run_payment_commands_once(limit=1, driver=driver, now=NOW)

    assert result["succeeded"] == 1
    assert driver.calls[0][2]["attempt_ref"] == _row(
        db, models.RezerwacjaPlatnoscPolecenie, uncertain_id,
    ).provider_idempotency_key
    assert _row(db, models.RezerwacjaPlatnoscPolecenie, reconcile.id).stan == "succeeded"
    assert _row(db, models.RezerwacjaPlatnoscPolecenie, uncertain_id).stan == "succeeded"
    assert _row(db, models.Platnosc, payment_id).provider_checkout_session_id == (
        "cs_test_reconciled_checkout"
    )


def test_reconcile_capture_processing_stays_unresolved_then_retrieves_terminal_pi(
    db, monkeypatch,
):
    _enable(monkeypatch)
    payment_id, capture_id = _payment_and_command(
        db,
        command_type="capture",
        command_state="uncertain",
        attempts=5,
        payment_status="autoryzowana",
        capture_mode="manual",
        command_amount_minor=10_000,
        payment_intent_id="pi_test_processing_capture",
    )
    payment = _row(db, models.Platnosc, payment_id)
    reconcile = worker.reservation_payments.queue_command(
        db,
        payment,
        "reconcile",
        operation_key="operator-reconcile:processing-capture",
        now=NOW,
        actor_kind="user",
        reason_code="operator_reconcile",
    )
    db.commit()
    driver = FakeStripeDriver()
    driver.capture_response = {
        "id": "pi_test_processing_capture",
        "status": "processing",
        "amount": 10_000,
    }

    first = worker.run_payment_commands_once(limit=1, driver=driver, now=NOW)

    source = _row(db, models.RezerwacjaPlatnoscPolecenie, capture_id)
    reconcile_row = _row(db, models.RezerwacjaPlatnoscPolecenie, reconcile.id)
    assert first["retry"] == 1
    assert source.stan == "uncertain"
    assert source.provider_object_id == "pi_test_processing_capture"
    assert reconcile_row.stan == "retry"
    assert reconcile_row.last_error_code == "CAPTURE_CANONICAL_PENDING"
    assert [call[0] for call in driver.calls] == ["capture"]

    driver.intent_response = {
        "id": "pi_test_processing_capture",
        "status": "succeeded",
        "amount": 10_000,
        "amount_received": 10_000,
        "latest_charge": {"id": "ch_test_processing_capture"},
    }
    second = worker.run_payment_commands_once(
        limit=1,
        driver=driver,
        now=reconcile_row.available_at,
    )

    assert second["succeeded"] == 1
    assert [call[0] for call in driver.calls] == ["capture", "retrieve_intent"]
    assert _row(db, models.RezerwacjaPlatnoscPolecenie, capture_id).stan == "succeeded"
    assert _row(db, models.RezerwacjaPlatnoscPolecenie, reconcile.id).stan == "succeeded"
    assert _row(db, models.Platnosc, payment_id).status == "oplacona"


def test_reconcile_resolves_create_before_dependent_cancel_and_finishes_both(
    db, monkeypatch,
):
    _enable(monkeypatch)
    payment_id, create_id = _payment_and_command(
        db,
        command_state="uncertain",
        attempts=5,
    )
    payment = _row(db, models.Platnosc, payment_id)
    cancel = models.RezerwacjaPlatnoscPolecenie(
        platnosc_id=payment_id,
        typ="cancel_authorization",
        operation_key="cancel-after-ambiguous-create",
        provider_idempotency_key=hashlib_sha(payment_id, "dependent-cancel"),
        kwota_minor=None,
        stan="uncertain",
        liczba_prob=5,
        maks_prob=5,
        available_at=NOW,
        expires_at=NOW + timedelta(hours=4),
        actor_kind="system",
        created_at=NOW,
        updated_at=NOW,
        uncertain_at=NOW,
    )
    db.add(cancel)
    reconcile = worker.reservation_payments.queue_command(
        db,
        payment,
        "reconcile",
        operation_key="operator-reconcile:dependent-chain",
        now=NOW,
        actor_kind="user",
        reason_code="operator_reconcile",
    )
    db.commit()

    driver = FakeStripeDriver()
    driver.create_responses = [{
        "id": "cs_test_dependency_reconcile",
        "status": "open",
        "payment_status": "unpaid",
        "url": "https://checkout.stripe.com/c/dependency",
        "expires_at": int(
            (NOW + timedelta(hours=4)).replace(tzinfo=timezone.utc).timestamp()
        ),
        "payment_intent": "pi_test_dependency_reconcile",
    }]
    driver.cancel_response = {
        "id": "pi_test_dependency_reconcile",
        "status": "canceled",
        "amount": 10_000,
    }

    first = worker.run_payment_commands_once(limit=1, driver=driver, now=NOW)

    assert first["processed"] == 1
    assert first["succeeded"] == 0
    assert [call[0] for call in driver.calls] == ["create_checkout"]
    assert driver.calls[0][2]["attempt_ref"] == _row(
        db, models.RezerwacjaPlatnoscPolecenie, create_id,
    ).provider_idempotency_key
    assert _row(db, models.RezerwacjaPlatnoscPolecenie, create_id).stan == "succeeded"
    assert _row(db, models.RezerwacjaPlatnoscPolecenie, cancel.id).stan == "uncertain"
    assert _row(db, models.RezerwacjaPlatnoscPolecenie, reconcile.id).stan == "queued"

    second = worker.run_payment_commands_once(limit=1, driver=driver, now=NOW)

    assert second["processed"] == 1
    assert second["succeeded"] == 1
    assert [call[0] for call in driver.calls] == ["create_checkout", "cancel"]
    assert driver.calls[1][2]["operation_ref"] == _row(
        db, models.RezerwacjaPlatnoscPolecenie, cancel.id,
    ).provider_idempotency_key
    assert _row(db, models.RezerwacjaPlatnoscPolecenie, cancel.id).stan == "succeeded"
    assert _row(db, models.RezerwacjaPlatnoscPolecenie, reconcile.id).stan == "succeeded"
    assert _row(db, models.Platnosc, payment_id).status == "anulowana"


def test_optional_daemon_is_disabled_for_ephemeral_sqlite(monkeypatch):
    _enable(monkeypatch)
    assert worker._ephemeral_sqlite() is True
    assert worker.start_worker() is False
