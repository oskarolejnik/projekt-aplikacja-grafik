"""R5b: transactional reservation communication and delivery lifecycle."""

from datetime import date, datetime, time, timedelta
import hashlib

import pytest
from sqlalchemy import text

from delivery_result import DeliveryResult
import models
import reservation_communication as communication
from routers import rodo


NOW = datetime(2026, 7, 16, 10, 0)


def _reservation(
    db,
    *,
    preference="email",
    email="guest@example.test",
    phone="600100200",
    visit_days=3,
):
    cfg = db.get(models.LokalConfig, 1)
    if cfg is not None:
        cfg.rezerwacje_przypomnienie_h = 24
    reservation = models.Termin(
        data=date(2026, 7, 16) + timedelta(days=visit_days),
        godz_od=time(18, 0),
        nazwisko="Gość R5b",
        liczba_osob=4,
        telefon=phone,
        email=email,
        kanal_komunikacji=preference,
        status="potwierdzona",
        rodzaj="stolik",
        kanal="reczna",
        utworzono_at=NOW,
    )
    db.add(reservation)
    db.flush()
    return reservation


def _queue_due_message(db, *, channel="email", now=NOW):
    preference = "sms" if channel == "sms" else "email"
    reservation = _reservation(db, preference=preference)
    rows = communication.enqueue_reservation(
        db,
        reservation,
        "confirmation",
        dedupe_key=f"test:{channel}:{reservation.id}",
        available_at=now - timedelta(seconds=1),
        expires_at=now + timedelta(days=1),
    )
    db.flush()
    message_id = rows[0].id
    provider_key = rows[0].provider_idempotency_key
    db.commit()
    db.close()
    return message_id, provider_key


@pytest.mark.parametrize(
    ("preference", "expected"),
    [
        ("auto", [("email", "guest@example.test")]),
        ("email", [("email", "guest@example.test")]),
        ("sms", [("sms", "600100200")]),
        (
            "oba",
            [("email", "guest@example.test"), ("sms", "600100200")],
        ),
        ("brak", []),
    ],
)
def test_channel_preference_is_explicit(preference, expected):
    owner = models.Termin(
        email="guest@example.test",
        telefon="600100200",
        kanal_komunikacji=preference,
    )

    assert communication._channels(owner) == expected


def test_subject_refs_are_keyed_canonical_and_fail_closed(monkeypatch):
    email_ref = communication.subject_refs_for_key(
        "  ＧＵＥＳＴ@Example.TEST  ",
    )[1]
    canonical_ref = communication.subject_refs_for_key(
        "guest@example.test",
    )[1]

    assert email_ref == canonical_ref
    assert email_ref != hashlib.sha256(
        b"guest@example.test",
    ).hexdigest()

    monkeypatch.setattr(communication.app_settings, "IS_DEV", True)
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError, match="SUBJECT_REF_KEY_UNAVAILABLE"):
        communication.subject_refs_for_key("guest@example.test")


def test_operational_snapshot_is_encrypted_and_independent_of_marketing(db):
    reservation = _reservation(db, preference="email")
    declined = models.RezerwacjaZgodaPubliczna(
        termin_id=reservation.id,
        notice_version="privacy-r5b",
        notice_ack_at=NOW,
        marketing=False,
        marketing_version="marketing-r5b",
        marketing_at=NOW,
        sensitive=False,
        retention_until=NOW + timedelta(days=365),
        ip_hash="a" * 64,
        created_at=NOW,
    )
    db.add(declined)
    rows = communication.enqueue_reservation(
        db,
        reservation,
        "confirmation",
        dedupe_key="marketing-declined-operational-confirmation",
        available_at=NOW,
        expires_at=NOW + timedelta(days=1),
    )
    db.flush()
    message = rows[0]
    message_id = message.id
    original_recipient = message.odbiorca
    original_body = message.tresc

    raw_recipient, raw_subject, raw_body = db.execute(
        text(
            "SELECT odbiorca, temat, tresc "
            "FROM rezerwacje_wiadomosci_outbox WHERE id=:id"
        ),
        {"id": message_id},
    ).one()
    assert declined.marketing is False
    assert message.kanal == "email"
    assert original_recipient == "guest@example.test"
    assert "Gość R5b" not in original_body
    assert raw_recipient != original_recipient
    assert original_recipient not in str(raw_recipient)
    assert original_body not in str(raw_body)
    assert message.temat not in str(raw_subject)

    reservation.email = "changed@example.test"
    reservation.telefon = "699999999"
    db.commit()
    db.expire_all()
    snapshot = db.get(models.RezerwacjaWiadomoscOutbox, message_id)
    assert snapshot.odbiorca == original_recipient
    assert snapshot.tresc == original_body


def test_confirmation_and_reminder_are_enqueued_once_in_same_transaction(db):
    reservation = _reservation(db, preference="oba")
    confirmation = communication.enqueue_reservation(
        db,
        reservation,
        "confirmation",
        dedupe_key=f"reservation:{reservation.id}:confirmation:create",
        available_at=NOW,
        expires_at=NOW + timedelta(days=1),
    )
    reminder = communication.schedule_reminder(db, reservation, now=NOW)
    repeated_confirmation = communication.enqueue_reservation(
        db,
        reservation,
        "confirmation",
        dedupe_key=f"reservation:{reservation.id}:confirmation:create",
        available_at=NOW,
        expires_at=NOW + timedelta(days=1),
    )
    repeated_reminder = communication.schedule_reminder(db, reservation, now=NOW)
    db.commit()

    assert len(confirmation) == len(reminder) == 2
    assert {row.id for row in repeated_confirmation} == {
        row.id for row in confirmation
    }
    assert {row.id for row in repeated_reminder} == {row.id for row in reminder}
    assert db.query(models.RezerwacjaWiadomoscOutbox).filter_by(
        termin_id=reservation.id,
    ).count() == 4
    assert {row.typ_zdarzenia for row in confirmation + reminder} == {
        "confirmation",
        "reminder",
    }


def test_scheduler_does_not_recreate_an_already_sent_reminder(db):
    reservation = _reservation(db, preference="email")
    first = communication.schedule_reminder(db, reservation, now=NOW)
    db.flush()
    first[0].stan = "sent"
    first[0].sent_at = NOW
    db.commit()

    repeated = communication.schedule_reminder(db, reservation, now=NOW)
    db.flush()

    assert [row.id for row in repeated] == [first[0].id]
    assert db.query(models.RezerwacjaWiadomoscOutbox).filter_by(
        termin_id=reservation.id,
        typ_zdarzenia="reminder",
    ).count() == 1


def test_explicit_edit_creates_a_new_reminder_generation_after_a_b_a(db):
    reservation = _reservation(db, preference="email")
    original = communication.schedule_reminder(db, reservation, now=NOW)[0]
    db.flush()
    original.stan = "sent"
    original.sent_at = NOW

    reservation.godz_od = time(19, 0)
    communication.enqueue_reservation(
        db, reservation, "change", dedupe_key="edit-generation-b",
    )
    middle = communication.schedule_reminder(
        db, reservation, now=NOW, force_new=True,
    )[0]
    db.flush()
    reservation.godz_od = time(18, 0)
    communication.enqueue_reservation(
        db, reservation, "change", dedupe_key="edit-generation-a2",
    )
    latest = communication.schedule_reminder(
        db, reservation, now=NOW, force_new=True,
    )[0]
    db.flush()
    repeated = communication.schedule_reminder(db, reservation, now=NOW)

    assert len({original.id, middle.id, latest.id}) == 3
    assert original.stan == "sent"
    assert middle.stan == "cancelled"
    assert latest.stan == "queued"
    assert [row.id for row in repeated] == [latest.id]


def test_channel_edit_does_not_make_planner_duplicate_new_reminder(db):
    reservation = _reservation(db, preference="email")
    original = communication.schedule_reminder(db, reservation, now=NOW)[0]
    db.flush()
    original.stan = "sent"
    original.sent_at = NOW

    reservation.kanal_komunikacji = "sms"
    communication.enqueue_reservation(
        db, reservation, "change", dedupe_key="edit-channel-sms",
    )
    current = communication.schedule_reminder(
        db, reservation, now=NOW, force_new=True,
    )[0]
    db.flush()
    repeated = communication.schedule_reminder(db, reservation, now=NOW)

    assert current.kanal == "sms"
    assert [row.id for row in repeated] == [current.id]
    assert db.query(models.RezerwacjaWiadomoscOutbox).filter_by(
        termin_id=reservation.id,
        typ_zdarzenia="reminder",
        stan="queued",
    ).count() == 1


def test_manual_create_commits_booking_and_outbox_without_provider_io(
    admin_client,
    db,
    monkeypatch,
):
    cfg = db.get(models.LokalConfig, 1)
    cfg.rezerwacje_przypomnienie_h = 24
    db.commit()
    calls = {"email": 0}

    def forbidden_provider_call(*args, **kwargs):
        calls["email"] += 1
        raise OSError("provider must not run in HTTP request")

    monkeypatch.setattr(
        communication.mailer,
        "dostarcz_email",
        forbidden_provider_call,
    )
    booking_date = date.today() + timedelta(days=30)
    response = admin_client.post(
        "/api/rezerwacje-stolik",
        json={
            "data": booking_date.isoformat(),
            "godz_od": "18:00",
            "liczba_osob": 2,
            "nazwisko": "HTTP R5b",
            "email": "http@example.test",
            "kanal_komunikacji": "email",
        },
    )

    assert response.status_code == 201, response.text
    reservation_id = response.json()["id"]
    assert db.get(models.Termin, reservation_id) is not None
    messages = db.query(models.RezerwacjaWiadomoscOutbox).filter_by(
        termin_id=reservation_id,
    ).order_by(models.RezerwacjaWiadomoscOutbox.typ_zdarzenia).all()
    assert [(row.typ_zdarzenia, row.kanal, row.stan) for row in messages] == [
        ("confirmation", "email", "queued"),
        ("reminder", "email", "queued"),
    ]
    assert calls["email"] == 0


def test_claim_started_sent_records_one_reproducible_attempt(db):
    message_id, provider_key = _queue_due_message(db)

    claim = communication.claim_next(now=NOW)
    assert claim is not None
    assert claim.id == message_id
    assert claim.provider_idempotency_key == provider_key
    row = db.get(models.RezerwacjaWiadomoscOutbox, message_id)
    attempt = db.query(models.RezerwacjaWiadomoscProba).filter_by(
        wiadomosc_id=message_id,
        numer=1,
    ).one()
    assert row.stan == "processing"
    assert attempt.wynik == "claimed"
    assert attempt.started_at is None
    db.close()

    started = communication.mark_claim_started(claim, now=NOW)
    assert started is not None
    attempt = db.query(models.RezerwacjaWiadomoscProba).filter_by(
        wiadomosc_id=message_id,
        numer=1,
    ).one()
    assert attempt.wynik == "processing"
    assert attempt.started_at == NOW
    db.close()

    assert communication.finalize_claim(
        started,
        DeliveryResult("sent", "accepted", provider_message_id="provider-1"),
        now=NOW + timedelta(seconds=1),
    )
    row = db.get(models.RezerwacjaWiadomoscOutbox, message_id)
    attempt = db.query(models.RezerwacjaWiadomoscProba).filter_by(
        wiadomosc_id=message_id,
        numer=1,
    ).one()
    assert row.stan == "sent"
    assert row.sent_at == NOW + timedelta(seconds=1)
    assert row.lease_token is None
    assert attempt.wynik == "sent"
    assert attempt.provider_idempotency_key == provider_key
    assert attempt.provider_message_id == "provider-1"


def test_retry_reuses_stable_provider_key(monkeypatch, db):
    monkeypatch.setenv("SMS_SUPPORTS_IDEMPOTENCY", "true")
    message_id, provider_key = _queue_due_message(db, channel="sms")
    first = communication.claim_next(now=NOW)
    started = communication.mark_claim_started(first, now=NOW)
    communication.finalize_claim(
        started,
        DeliveryResult("retry", "temporary_failure", status_code=503),
        now=NOW,
    )

    row = db.get(models.RezerwacjaWiadomoscOutbox, message_id)
    retry_at = row.available_at
    assert row.stan == "retry"
    assert row.provider_idempotency_key == provider_key
    db.close()

    second = communication.claim_next(now=retry_at)
    assert second is not None
    assert second.attempt_number == 2
    assert second.provider_idempotency_key == provider_key
    attempts = db.query(models.RezerwacjaWiadomoscProba).filter_by(
        wiadomosc_id=message_id,
    ).order_by(models.RezerwacjaWiadomoscProba.numer).all()
    assert [attempt.provider_idempotency_key for attempt in attempts] == [
        provider_key,
        provider_key,
    ]


def test_expired_lease_before_io_is_safe_to_retry(db):
    message_id, provider_key = _queue_due_message(db)
    first = communication.claim_next(now=NOW)

    recovered_at = NOW + timedelta(seconds=communication.LEASE_SECONDS + 1)
    second = communication.claim_next(now=recovered_at)

    assert second is not None
    assert second.id == message_id
    assert second.attempt_number == 2
    assert second.provider_idempotency_key == provider_key
    attempts = db.query(models.RezerwacjaWiadomoscProba).filter_by(
        wiadomosc_id=message_id,
    ).order_by(models.RezerwacjaWiadomoscProba.numer).all()
    assert attempts[0].wynik == "retry"
    assert attempts[0].error_code == "LEASE_EXPIRED_BEFORE_IO"
    assert attempts[1].wynik == "claimed"
    assert first.lease_token != second.lease_token


def test_expired_smtp_lease_after_io_becomes_uncertain_without_blind_retry(db):
    message_id, _ = _queue_due_message(db)
    claim = communication.claim_next(now=NOW)
    communication.mark_claim_started(claim, now=NOW)

    assert communication.claim_next(
        now=NOW + timedelta(seconds=communication.LEASE_SECONDS + 1),
    ) is None

    row = db.get(models.RezerwacjaWiadomoscOutbox, message_id)
    attempt = db.query(models.RezerwacjaWiadomoscProba).filter_by(
        wiadomosc_id=message_id,
        numer=1,
    ).one()
    assert row.stan == "uncertain"
    assert row.last_error_code == "LEASE_EXPIRED_AMBIGUOUS"
    assert row.liczba_prob == 1
    assert attempt.wynik == "uncertain"


def test_expired_idempotent_lease_after_io_is_retried_with_same_key(
    monkeypatch,
    db,
):
    monkeypatch.setenv("SMS_SUPPORTS_IDEMPOTENCY", "true")
    message_id, provider_key = _queue_due_message(db, channel="sms")
    first = communication.claim_next(now=NOW)
    started = communication.mark_claim_started(first, now=NOW)
    assert started.provider_supports_idempotency is True

    recovered_at = NOW + timedelta(seconds=communication.LEASE_SECONDS + 1)
    second = communication.claim_next(now=recovered_at)

    assert second is not None
    assert second.id == message_id
    assert second.attempt_number == 2
    assert second.provider_idempotency_key == provider_key
    attempts = db.query(models.RezerwacjaWiadomoscProba).filter_by(
        wiadomosc_id=message_id,
    ).order_by(models.RezerwacjaWiadomoscProba.numer).all()
    assert attempts[0].wynik == "retry"
    assert attempts[0].error_code == "LEASE_EXPIRED_SAFE_RETRY"
    assert attempts[1].provider_idempotency_key == provider_key


def test_message_deadline_expires_without_provider_attempt(db):
    reservation = _reservation(db)
    rows = communication.enqueue_reservation(
        db,
        reservation,
        "confirmation",
        dedupe_key="deadline-expired",
        available_at=NOW - timedelta(minutes=1),
        expires_at=NOW,
    )
    db.flush()
    message_id = rows[0].id
    db.commit()
    db.close()

    assert communication.claim_next(now=NOW) is None
    row = db.get(models.RezerwacjaWiadomoscOutbox, message_id)
    assert row.stan == "expired"
    assert row.last_error_code == "MESSAGE_EXPIRED"
    assert row.liczba_prob == 0
    assert db.query(models.RezerwacjaWiadomoscProba).filter_by(
        wiadomosc_id=message_id,
    ).count() == 0


def test_uncertain_requires_explicit_reconciliation_before_retry(db, admin):
    message_id, provider_key = _queue_due_message(db)
    claim = communication.claim_next(now=NOW)
    started = communication.mark_claim_started(claim, now=NOW)
    communication.finalize_claim(
        started,
        DeliveryResult("uncertain", "smtp_delivery_uncertain"),
        now=NOW,
    )

    row = db.get(models.RezerwacjaWiadomoscOutbox, message_id)
    with pytest.raises(ValueError, match="UNCERTAIN_REQUIRES_RECONCILIATION"):
        communication.retry_failed(db, row, actor=admin, now=NOW)
    assert row.stan == "uncertain"

    communication.reconcile_uncertain(
        db,
        row,
        outcome="retry",
        note="Provider nie potwierdził przyjęcia; operator akceptuje ryzyko duplikatu.",
        actor=admin,
        now=NOW + timedelta(seconds=1),
    )
    db.commit()
    db.close()

    retried = communication.claim_next(now=NOW + timedelta(seconds=1))
    assert retried is not None
    assert retried.attempt_number == 2
    assert retried.provider_idempotency_key == provider_key


def test_table_ready_is_stamped_only_after_confirmed_or_reconciled_delivery(
    db,
    admin,
):
    waitlist = models.ListaOczekujacych(
        data=NOW.date(),
        godz_od=time(18, 0),
        liczba_osob=2,
        nazwisko="Gość listy",
        email="wait@example.test",
        kanal_komunikacji="email",
        status="oczekuje",
        kanal="reczna",
        hold_do=NOW + timedelta(minutes=30),
        utworzono_at=NOW,
    )
    db.add(waitlist)
    db.flush()
    rows = communication.enqueue_table_ready(
        db,
        waitlist,
        dedupe_key="table-ready-once",
        actor=admin,
    )
    db.flush()
    waitlist_id = waitlist.id
    message_id = rows[0].id
    assert waitlist.powiadomiono_at is None
    db.commit()
    db.close()

    claim = communication.claim_next(now=NOW)
    started = communication.mark_claim_started(claim, now=NOW)
    communication.finalize_claim(
        started,
        DeliveryResult("uncertain", "smtp_delivery_uncertain"),
        now=NOW + timedelta(seconds=1),
    )
    waitlist = db.get(models.ListaOczekujacych, waitlist_id)
    message = db.get(models.RezerwacjaWiadomoscOutbox, message_id)
    assert waitlist.powiadomiono_at is None

    communication.reconcile_uncertain(
        db,
        message,
        outcome="sent",
        note="Potwierdzone ręcznie w panelu dostawcy.",
        actor=admin,
        now=NOW + timedelta(seconds=2),
    )
    db.commit()
    db.expire_all()
    assert db.get(models.ListaOczekujacych, waitlist_id).powiadomiono_at == (
        NOW + timedelta(seconds=2)
    )
    assert db.get(models.RezerwacjaWiadomoscOutbox, message_id).stan == "sent"


def test_rodo_purge_removes_encrypted_snapshot_and_delivery_attempt(db):
    message_id, _ = _queue_due_message(db)
    claim = communication.claim_next(now=NOW)
    started = communication.mark_claim_started(claim, now=NOW)
    communication.finalize_claim(
        started,
        DeliveryResult("sent", "accepted"),
        now=NOW + timedelta(seconds=1),
    )

    message = db.get(models.RezerwacjaWiadomoscOutbox, message_id)
    reservation = db.get(models.Termin, message.termin_id)
    assert db.query(models.RezerwacjaWiadomoscProba).filter_by(
        wiadomosc_id=message_id,
    ).count() == 1

    rodo.usun_powiazane_pii_rezerwacji(db, [reservation])
    db.commit()

    assert db.get(models.RezerwacjaWiadomoscOutbox, message_id) is None
    assert db.query(models.RezerwacjaWiadomoscProba).filter_by(
        wiadomosc_id=message_id,
    ).count() == 0


def test_rodo_erasure_cancels_claimed_message_before_provider_io(db):
    message_id, _ = _queue_due_message(db)
    claim = communication.claim_next(now=NOW)
    message = db.get(models.RezerwacjaWiadomoscOutbox, message_id)
    reservation = db.get(models.Termin, message.termin_id)

    blocked = rodo.usun_powiazane_pii_rezerwacji(db, [reservation])
    db.commit()

    assert blocked == set()
    assert communication.mark_claim_started(claim, now=NOW) is None
    assert db.query(models.RezerwacjaWiadomoscOutbox).filter_by(
        id=message_id,
    ).count() == 0
    assert db.query(models.RezerwacjaWiadomoscProba).filter_by(
        wiadomosc_id=message_id,
    ).count() == 0


def test_rodo_erasure_rejects_attempt_after_provider_io_started(db):
    message_id, _ = _queue_due_message(db)
    claim = communication.claim_next(now=NOW)
    started = communication.mark_claim_started(claim, now=NOW)
    message = db.get(models.RezerwacjaWiadomoscOutbox, message_id)
    reservation = db.get(models.Termin, message.termin_id)

    with pytest.raises(
        communication.CommunicationDeliveryInProgress,
        match="COMMUNICATION_DELIVERY_IN_PROGRESS",
    ):
        rodo.usun_powiazane_pii_rezerwacji(db, [reservation])
    db.rollback()

    assert db.query(models.RezerwacjaWiadomoscOutbox).filter_by(
        id=message_id,
        stan="processing",
    ).count() == 1
    assert db.query(models.RezerwacjaWiadomoscProba).filter_by(
        wiadomosc_id=message_id,
        wynik="processing",
    ).count() == 1
    assert communication.finalize_claim(
        started,
        DeliveryResult("sent", "accepted"),
        now=NOW + timedelta(seconds=1),
    )
