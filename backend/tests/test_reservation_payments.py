"""Focused R5c domain tests; provider I/O is intentionally absent."""
from datetime import date, datetime, time, timedelta

import pytest

import models
import reservation_payments as payments


NOW = datetime(2026, 7, 16, 10, 0)
TODAY = date(2026, 7, 16)


def _service(db):
    row = models.GodzinyOtwarcia(
        dzien_tygodnia=4,
        godz_od=time(17, 0),
        godz_do=time(23, 0),
        dlugosc_slotu_min=120,
        krok_slotu_min=30,
        domyslny_turn_time_min=120,
        aktywny=True,
        nazwa="Kolacja",
    )
    db.add(row)
    db.flush()
    return row


def _policy(db, **overrides):
    values = {
        "nazwa": "Zadatek globalny",
        "aktywna": True,
        "kanal": "oba",
        "min_osob": 1,
        "max_osob": 0,
        "rodzaj": "zadatek",
        "sposob_kwoty": "stala",
        "kwota_minor": 5_000,
        "waluta": "PLN",
        "waznosc_min": 30,
        "po_niepowodzeniu": "ponow",
        "zwrot_przy_anulowaniu": True,
        "priorytet": 100,
        "utworzono_at": NOW,
        "zaktualizowano_at": NOW,
    }
    values.update(overrides)
    row = models.PolitykaPlatnosciRezerwacji(**values)
    db.add(row)
    db.flush()
    return row


def _reservation(db, *, days=2, people=4):
    row = models.Termin(
        data=TODAY + timedelta(days=days),
        nazwisko="Gość R5c",
        liczba_osob=people,
        status="rezerwacja",
        zadatek=0,
        utworzono_at=NOW,
        godz_od=time(18, 0),
        godz_do=time(20, 0),
        kanal="online",
        rodzaj="stolik",
    )
    db.add(row)
    db.flush()
    return row


def test_resolve_policy_exact_date_service_group_precedence(db):
    service = _service(db)
    _policy(db, nazwa="Global", kwota_minor=1_000, priorytet=1)
    _policy(
        db,
        nazwa="Serwis",
        serwis_id=service.id,
        sposob_kwoty="od_osoby",
        kwota_minor=2_000,
        priorytet=1,
    )
    exact = _policy(
        db,
        nazwa="Dokładna data i serwis",
        data=TODAY,
        serwis_id=service.id,
        min_osob=4,
        max_osob=8,
        rodzaj="preautoryzacja",
        sposob_kwoty="od_osoby",
        kwota_minor=3_000,
        po_niepowodzeniu="zwolnij",
        zwrot_przy_anulowaniu=False,
        priorytet=50,
    )

    resolved = payments.resolve_policy(db, TODAY, service.id, 5, "online")

    assert resolved.policy_id == exact.id
    assert resolved.kind == "preautoryzacja"
    assert resolved.amount_minor == 15_000
    assert resolved.failure_policy == "zwolnij"
    assert resolved.refund_on_cancel is False


def test_typed_brak_suppresses_legacy_config(db):
    config = db.get(models.LokalConfig, 1)
    config.zadatek_wymagany = True
    config.zadatek_kwota_os = 25
    config.zadatek_prog_osob = 1
    disabled = _policy(db, rodzaj="brak", kwota_minor=0, nazwa="Bez zadatku")

    resolved = payments.resolve_policy(db, TODAY, None, 4, "online")

    assert resolved.policy_id == disabled.id
    assert resolved.required is False


def test_legacy_policy_uses_minor_units_without_float_drift(db):
    config = db.get(models.LokalConfig, 1)
    config.zadatek_wymagany = True
    config.zadatek_kwota_os = 19.99
    config.zadatek_prog_osob = 2

    resolved = payments.resolve_policy(db, TODAY, None, 3, "online")

    assert resolved.source == "legacy_lokal_config"
    assert resolved.amount_minor == 5_997


def test_create_payment_is_local_atomic_and_idempotent(db):
    reservation = _reservation(db)
    policy_row = _policy(db, sposob_kwoty="od_osoby", kwota_minor=2_000)
    policy = payments.resolve_policy(db, reservation.data, None, 4, "online")

    payment, command = payments.create_payment_for_reservation(
        db,
        reservation,
        policy,
        provider="stripe",
        now=NOW,
        business_today=TODAY,
        service_id=None,
        operation_key="public-create-001",
    )
    replay_payment, replay_command = payments.create_payment_for_reservation(
        db,
        reservation,
        policy,
        provider="stripe",
        now=NOW,
        business_today=TODAY,
        service_id=None,
        operation_key="public-create-001",
    )

    assert policy.policy_id == policy_row.id
    assert payment.id == replay_payment.id
    assert command.id == replay_command.id
    assert payment.kwota_minor == 8_000 and payment.kwota == 80
    assert payment.link is None
    assert payment.policy_snapshot["zwrot_przy_anulowaniu"] is True
    assert command.typ == "create_checkout" and len(command.provider_idempotency_key) == 64
    assert db.query(models.Platnosc).count() == 1
    assert db.query(models.RezerwacjaPlatnoscPolecenie).count() == 1


def test_preauthorisation_cannot_start_more_than_six_days_before_visit(db):
    reservation = _reservation(db, days=7)
    _policy(db, rodzaj="preautoryzacja", kwota_minor=10_000)
    policy = payments.resolve_policy(db, reservation.data, None, 4, "online")

    with pytest.raises(payments.PaymentDomainError) as exc:
        payments.create_payment_for_reservation(
            db,
            reservation,
            policy,
            provider="stripe",
            now=NOW,
            business_today=TODAY,
        )

    assert exc.value.code == "PREAUTH_TOO_EARLY"
    assert db.query(models.Platnosc).count() == 0


def test_payment_creation_rejects_non_pln_even_for_corrupted_snapshot(db):
    reservation = _reservation(db)
    policy = payments.ResolvedPaymentPolicy(
        policy_id=None,
        source="corrupted_snapshot",
        name="Unsupported currency",
        kind="zadatek",
        amount_minor=5_000,
        currency="EUR",
        validity_minutes=30,
        failure_policy="ponow",
        refund_on_cancel=True,
        amount_mode="stala",
    )

    with pytest.raises(payments.PaymentDomainError) as exc:
        payments.create_payment_for_reservation(
            db,
            reservation,
            policy,
            provider="stripe",
            now=NOW,
            business_today=TODAY,
        )

    assert exc.value.code == "UNSUPPORTED_PAYMENT_CURRENCY"
    assert db.query(models.Platnosc).count() == 0


def test_signed_event_duplicate_requires_identical_payload(db):
    event, replayed = payments.record_signed_event(
        db,
        provider="stripe",
        event_id="evt_123",
        event_type="payment_intent.succeeded",
        api_version="2026-06-24.dahlia",
        livemode=False,
        object_id="pi_123",
        object_type="payment_intent",
        raw_payload=b'{"id":"evt_123"}',
        received_at=NOW,
    )
    replay, replayed = payments.record_signed_event(
        db,
        provider="stripe",
        event_id="evt_123",
        event_type="payment_intent.succeeded",
        api_version="2026-06-24.dahlia",
        livemode=False,
        object_id="pi_123",
        object_type="payment_intent",
        raw_payload=b'{"id":"evt_123"}',
        received_at=NOW,
    )

    assert replay.id == event.id and replayed is True
    with pytest.raises(payments.PaymentDomainError) as exc:
        payments.record_signed_event(
            db,
            provider="stripe",
            event_id="evt_123",
            event_type="payment_intent.succeeded",
            api_version="2026-06-24.dahlia",
            livemode=False,
            object_id="pi_123",
            object_type="payment_intent",
            raw_payload=b'{"id":"evt_123","changed":true}',
            received_at=NOW,
        )
    assert exc.value.code == "WEBHOOK_EVENT_PAYLOAD_MISMATCH"


def test_refund_command_is_full_only_and_public_projection_hides_provider_ids(db):
    reservation = _reservation(db)
    _policy(db, kwota_minor=10_000)
    policy = payments.resolve_policy(db, reservation.data, None, 4, "online")
    payment, _ = payments.create_payment_for_reservation(
        db, reservation, policy, provider="stripe", now=NOW, business_today=TODAY,
    )
    payments.apply_payment_status(payment, "oplacona", now=NOW, captured_minor=10_000)
    payment.provider_payment_intent_id = "pi_secret_opaque"

    with pytest.raises(payments.PaymentDomainError) as exc:
        payments.request_refund(
            db,
            payment,
            amount_minor=5_000,
            operation_key="refund-partial",
            now=NOW,
            actor_user_id=None,
            reason_code="guest_request",
        )
    assert exc.value.code == "PARTIAL_REFUND_UNSUPPORTED"

    command = payments.request_refund(
        db,
        payment,
        amount_minor=None,
        operation_key="refund-full",
        now=NOW,
        actor_user_id=None,
        reason_code="guest_request",
    )
    public = payments.payment_public_dict(payment)

    assert command.kwota_minor == 10_000
    assert public["id"] == payment.id
    assert public["amount_minor"] == 10_000 and public["currency"] == "PLN"
    assert public["po_niepowodzeniu"] == "ponow"
    assert "provider_payment_intent_id" not in public and "provider" not in public


def test_retry_creates_new_monotonic_attempt_and_is_idempotent(db):
    reservation = _reservation(db)
    _policy(db, kwota_minor=7_500, po_niepowodzeniu="ponow")
    policy = payments.resolve_policy(db, reservation.data, None, 4, "online")
    failed, _ = payments.create_payment_for_reservation(
        db, reservation, policy, provider="stripe", now=NOW, business_today=TODAY,
    )
    payments.apply_payment_status(failed, "nieudana", now=NOW)

    retried, command = payments.retry_payment_for_reservation(
        db,
        failed,
        reservation,
        operation_key="retry-001",
        now=NOW + timedelta(minutes=1),
        business_today=TODAY,
        actor_kind="guest",
    )
    replay, replay_command = payments.retry_payment_for_reservation(
        db,
        failed,
        reservation,
        operation_key="retry-001",
        now=NOW + timedelta(minutes=1),
        business_today=TODAY,
        actor_kind="guest",
    )

    assert failed.status == "nieudana"
    assert retried.id != failed.id and retried.status == "oczekuje"
    assert replay.id == retried.id and replay_command.id == command.id
    assert db.query(models.Platnosc).count() == 2
    assert db.query(models.RezerwacjaPlatnoscPolecenie).filter_by(
        platnosc_id=failed.id,
        typ="reconcile",
        reason_code="payment_superseded",
    ).count() == 1


def test_public_projection_hides_checkout_link_after_reservation_ends(db):
    reservation = _reservation(db)
    _policy(db, kwota_minor=5_000)
    policy = payments.resolve_policy(db, reservation.data, None, 4, "online")
    payment, _ = payments.create_payment_for_reservation(
        db, reservation, policy, provider="stripe", now=NOW, business_today=TODAY,
    )
    payment.link = "https://checkout.stripe.com/c/private-capability"

    active = payments.payment_public_dict(payment, reservation_active=True)
    inactive = payments.payment_public_dict(payment, reservation_active=False)

    assert active["link"] == payment.link
    assert inactive["link"] is None
    assert inactive["can_retry"] is False


def test_cancellation_refunds_paid_sandbox_without_fake_provider_io(db):
    reservation = _reservation(db)
    _policy(db, kwota_minor=5_000, zwrot_przy_anulowaniu=True)
    policy = payments.resolve_policy(db, reservation.data, None, 4, "online")
    payment, _ = payments.create_payment_for_reservation(
        db, reservation, policy, provider="sandbox", now=NOW, business_today=TODAY,
    )
    payments.apply_payment_status(payment, "oplacona", now=NOW, captured_minor=5_000)
    reservation.zadatek = 50

    command = payments.request_reservation_cancellation_settlement(
        db, reservation, now=NOW, actor_kind="guest",
    )

    assert command is None
    assert payment.status == "zwrocona" and payment.zwrocono_minor == 5_000
    assert reservation.zadatek == 0


def test_cancellation_queues_provider_release_in_same_transaction(db):
    reservation = _reservation(db)
    _policy(db, rodzaj="preautoryzacja", kwota_minor=8_000)
    policy = payments.resolve_policy(db, reservation.data, None, 4, "online")
    payment, _ = payments.create_payment_for_reservation(
        db, reservation, policy, provider="stripe", now=NOW, business_today=TODAY,
    )

    command = payments.request_reservation_cancellation_settlement(
        db, reservation, now=NOW, actor_kind="guest",
    )

    assert command.typ == "cancel_authorization"
    assert command.reason_code == "reservation_cancelled"
    assert payment.status == "oczekuje"


def test_paid_cancellation_queues_exactly_one_full_refund(db):
    reservation = _reservation(db)
    _policy(db, kwota_minor=9_000, zwrot_przy_anulowaniu=True)
    policy = payments.resolve_policy(db, reservation.data, None, 4, "online")
    payment, _ = payments.create_payment_for_reservation(
        db, reservation, policy, provider="stripe", now=NOW, business_today=TODAY,
    )
    payments.apply_payment_status(payment, "oplacona", now=NOW, captured_minor=9_000)
    reservation.status = "odwolana"

    first = payments.request_reservation_cancellation_settlement(
        db,
        reservation,
        now=NOW,
        actor_kind="guest",
        operation_key="first-cancel-request",
    )
    version_after_first = payment.version
    replay = payments.request_reservation_cancellation_settlement(
        db,
        reservation,
        now=NOW + timedelta(seconds=1),
        actor_kind="guest",
        operation_key="replayed-cancel-request",
    )

    refunds = db.query(models.RezerwacjaPlatnoscPolecenie).filter_by(
        platnosc_id=payment.id,
        typ="refund",
    ).all()
    assert replay.id == first.id
    assert len(refunds) == 1
    assert refunds[0].kwota_minor == 9_000
    assert refunds[0].reason_code == "reservation_cancelled"
    assert payment.refund_status == "oczekuje"
    assert payment.version == version_after_first
