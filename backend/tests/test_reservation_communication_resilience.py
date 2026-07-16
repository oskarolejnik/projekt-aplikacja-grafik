"""Additional R5b invariants for rollout, planning and provider snapshots."""

from datetime import date, datetime, time, timedelta

from delivery_result import DeliveryResult
import models
import reservation_communication as communication


NOW = datetime(2026, 7, 16, 10, 0)


def _reservation(db, *, preference="email", visit_days=30):
    reservation = models.Termin(
        data=date(2026, 7, 16) + timedelta(days=visit_days),
        godz_od=time(18, 0),
        nazwisko="Test R5b",
        liczba_osob=4,
        telefon="600100200",
        email="guest@example.test",
        kanal_komunikacji=preference,
        status="potwierdzona",
        rodzaj="stolik",
        kanal="reczna",
        utworzono_at=NOW,
    )
    db.add(reservation)
    db.flush()
    return reservation


def test_reminders_are_opt_in_for_a_safe_rollout(db):
    cfg = db.get(models.LokalConfig, 1)
    reservation = _reservation(db)

    assert cfg.rezerwacje_przypomnienie_h == 0
    assert communication.schedule_reminder(
        db, reservation, cfg=cfg, now=NOW,
    ) == []
    assert db.query(models.RezerwacjaWiadomoscOutbox).filter_by(
        termin_id=reservation.id,
        typ_zdarzenia="reminder",
    ).count() == 0


def test_reconfigure_reminders_replaces_the_entire_future_policy(db):
    cfg = db.get(models.LokalConfig, 1)
    cfg.rezerwacje_przypomnienie_h = 168
    reservation = _reservation(db, visit_days=30)
    old = communication.schedule_reminder(
        db, reservation, cfg=cfg, now=NOW,
    )[0]
    db.flush()
    old_id = old.id

    cfg.rezerwacje_przypomnienie_h = 0
    communication.reconfigure_reminders(db, cfg=cfg, now=NOW)
    db.flush()
    assert db.get(models.RezerwacjaWiadomoscOutbox, old_id).stan == "cancelled"
    assert db.query(models.RezerwacjaWiadomoscOutbox).filter_by(
        termin_id=reservation.id,
        typ_zdarzenia="reminder",
        stan="queued",
    ).count() == 0

    cfg.rezerwacje_przypomnienie_h = 24
    communication.reconfigure_reminders(db, cfg=cfg, now=NOW)
    db.flush()
    current = db.query(models.RezerwacjaWiadomoscOutbox).filter_by(
        termin_id=reservation.id,
        typ_zdarzenia="reminder",
        stan="queued",
    ).one()
    assert current.id != old_id
    assert current.available_at == communication._visit_utc(reservation) - timedelta(hours=24)


def test_config_endpoint_applies_reminder_policy_in_the_same_transaction(
    db,
    admin_client,
):
    cfg = db.get(models.LokalConfig, 1)
    cfg.rezerwacje_przypomnienie_h = 168
    reservation = _reservation(db, visit_days=30)
    old = communication.schedule_reminder(
        db, reservation, cfg=cfg, now=NOW,
    )[0]
    db.flush()
    old_id = old.id
    db.commit()

    response = admin_client.put(
        "/api/lokal/config",
        json={"rezerwacje_przypomnienie_h": 0},
    )

    assert response.status_code == 200, response.text
    db.expire_all()
    assert db.get(models.RezerwacjaWiadomoscOutbox, old_id).stan == "cancelled"
    assert db.get(models.LokalConfig, 1).rezerwacje_przypomnienie_h == 0


def test_planner_refreshes_config_after_waiting_for_a_rollout(db):
    cfg = db.get(models.LokalConfig, 1)
    cfg.rezerwacje_przypomnienie_h = 24
    db.commit()
    cfg = db.get(models.LokalConfig, 1)
    assert cfg.rezerwacje_przypomnienie_h == 24

    other = communication.SessionLocal()
    try:
        other_cfg = other.get(models.LokalConfig, 1)
        other_cfg.rezerwacje_przypomnienie_h = 0
        other.commit()
    finally:
        other.close()

    # This session still holds the old object in its identity map. A planner
    # call without an authoritative config must reload after its planner lock.
    assert cfg.rezerwacje_przypomnienie_h == 24
    reservation = _reservation(db)
    assert communication.schedule_reminder(db, reservation, now=NOW) == []
    assert cfg.rezerwacje_przypomnienie_h == 0


def test_sms_provider_contract_is_frozen_when_message_is_queued(
    db,
    monkeypatch,
):
    monkeypatch.setenv("SMS_SUPPORTS_IDEMPOTENCY", "true")
    monkeypatch.setenv("SMS_IDEMPOTENCY_HEADER", "X-Original-Request-ID")
    reservation = _reservation(db, preference="sms")
    row = communication.enqueue_reservation(
        db,
        reservation,
        "confirmation",
        dedupe_key="provider-contract-snapshot",
        available_at=NOW - timedelta(seconds=1),
        expires_at=NOW + timedelta(days=1),
    )[0]
    db.flush()
    message_id = row.id
    db.commit()
    db.close()

    # A deployment-time environment change cannot alter the retry semantics of
    # a message that was already persisted under a different provider contract.
    monkeypatch.setenv("SMS_SUPPORTS_IDEMPOTENCY", "false")
    monkeypatch.setenv("SMS_IDEMPOTENCY_HEADER", "X-New-Request-ID")
    claim = communication.claim_next(now=NOW)
    assert claim is not None and claim.id == message_id
    assert claim.provider_supports_idempotency is True
    assert claim.provider_idempotency_header == "X-Original-Request-ID"

    captured = {}

    def fake_delivery(*args, **kwargs):
        captured.update(kwargs)
        return DeliveryResult("sent", "accepted")

    monkeypatch.setattr(communication.sms, "dostarcz_sms", fake_delivery)
    started = communication.mark_claim_started(claim, now=NOW)
    result = communication.deliver_claim(started)

    assert result.outcome == "sent"
    assert captured["force_supports_idempotency"] is True
    assert captured["force_idempotency_header"] == "X-Original-Request-ID"


def test_unhandled_provider_error_never_logs_guest_pii(monkeypatch, caplog):
    secret = "guest-private@example.test"
    claim = communication.ClaimedMessage(
        id=123,
        attempt_number=1,
        lease_token="lease",
        channel="email",
        recipient=secret,
        subject="Private subject",
        body="Private body",
        provider_idempotency_key="a" * 64,
        provider_supports_idempotency=False,
        provider_idempotency_header=None,
    )

    def fail_provider(*args, **kwargs):
        raise RuntimeError(f"provider rejected {secret}")

    monkeypatch.setattr(communication.mailer, "dostarcz_email", fail_provider)
    result = communication.deliver_claim(claim)

    assert result == DeliveryResult("uncertain", "PROVIDER_UNHANDLED_EXCEPTION")
    assert secret not in caplog.text
    assert "Private body" not in caplog.text


def test_summary_prioritizes_attention_over_sent_and_pending(db):
    reservation = _reservation(db, preference="oba")
    rows = communication.enqueue_reservation(
        db,
        reservation,
        "confirmation",
        dedupe_key="summary-attention-priority",
        available_at=NOW,
        expires_at=NOW + timedelta(days=1),
    )
    db.flush()
    email, sms = rows
    email.stan = "sent"
    email.sent_at = NOW
    sms.stan = "failed"
    sms.last_error_code = "sms_request_rejected"
    db.flush()

    summary = communication.summaries_for_reservations(
        db, [reservation.id],
    )[reservation.id]

    assert summary["message_id"] == sms.id
    assert summary["state"] == "failed"
    assert summary["attention_required"] is True
    assert summary["attention_count"] == 1
    assert summary["pending_count"] == 0


def test_worker_cancels_a_due_message_that_no_longer_matches_owner(db):
    reservation = _reservation(db)
    row = communication.enqueue_reservation(
        db,
        reservation,
        "confirmation",
        dedupe_key="stale-before-claim",
        available_at=NOW - timedelta(seconds=1),
        expires_at=NOW + timedelta(days=1),
    )[0]
    db.flush()
    message_id = row.id
    reservation.status = "odwolana"
    db.commit()
    db.close()

    assert communication.claim_next(now=NOW) is None
    stale = db.get(models.RezerwacjaWiadomoscOutbox, message_id)
    assert stale.stan == "cancelled"
    assert stale.last_error_code == "MESSAGE_OWNER_NOT_CURRENT"
    assert db.query(models.RezerwacjaWiadomoscProba).filter_by(
        wiadomosc_id=message_id,
    ).count() == 0


def test_transient_result_cannot_revive_message_after_cancellation(db):
    reservation = _reservation(db)
    row = communication.enqueue_reservation(
        db,
        reservation,
        "confirmation",
        dedupe_key="stale-after-io-start",
        available_at=NOW - timedelta(seconds=1),
        expires_at=NOW + timedelta(days=1),
    )[0]
    db.flush()
    message_id = row.id
    reservation_id = reservation.id
    db.commit()
    db.close()
    claim = communication.claim_next(now=NOW)
    started = communication.mark_claim_started(claim, now=NOW)

    reservation = db.get(models.Termin, reservation_id)
    reservation.status = "odwolana"
    communication.cancel_pending(db, reservation.id, now=NOW)
    db.commit()
    db.close()

    assert communication.finalize_claim(
        started,
        DeliveryResult("retry", "smtp_connection_error"),
        now=NOW + timedelta(seconds=1),
    )
    stale = db.get(models.RezerwacjaWiadomoscOutbox, message_id)
    attempt = db.query(models.RezerwacjaWiadomoscProba).filter_by(
        wiadomosc_id=message_id,
    ).one()
    assert stale.stan == "cancelled"
    assert stale.last_error_code == "MESSAGE_OWNER_NOT_CURRENT"
    assert attempt.wynik == "failed"
    assert attempt.error_code == "MESSAGE_OWNER_NOT_CURRENT"


def test_planner_race_cannot_send_reminder_queued_from_stale_owner(db):
    cfg = db.get(models.LokalConfig, 1)
    cfg.rezerwacje_przypomnienie_h = 24
    db.commit()
    reservation = _reservation(db)
    reservation_id = reservation.id
    assert reservation.status == "potwierdzona"

    other = communication.SessionLocal()
    try:
        current = other.get(models.Termin, reservation_id)
        current.status = "odwolana"
        other.commit()
    finally:
        other.close()

    # Simulate the planner object loaded just before the cancellation committed.
    assert reservation.status == "potwierdzona"
    stale_rows = communication.schedule_reminder(
        db, reservation, cfg=cfg, now=NOW,
    )
    assert stale_rows
    db.flush()
    message_id = stale_rows[0].id
    due_at = communication._visit_utc(reservation) - timedelta(hours=24)
    db.commit()
    db.close()

    assert communication.claim_next(
        now=due_at,
    ) is None
    stale = db.get(models.RezerwacjaWiadomoscOutbox, message_id)
    assert stale.stan == "cancelled"
    assert stale.last_error_code == "MESSAGE_OWNER_NOT_CURRENT"


def test_reused_waitlist_id_gets_a_new_provider_idempotency_key(db):
    def make_waitlist():
        row = models.ListaOczekujacych(
            data=NOW.date(),
            godz_od=time(18, 0),
            liczba_osob=2,
            nazwisko="ID reuse",
            telefon="600100200",
            kanal_komunikacji="sms",
            status="oczekuje",
            kanal="reczna",
            hold_do=NOW + timedelta(minutes=30),
            utworzono_at=NOW,
        )
        db.add(row)
        db.flush()
        return row

    first_owner = make_waitlist()
    first = communication.enqueue_table_ready(db, first_owner)[0]
    db.flush()
    first_owner_id = first_owner.id
    first_provider_key = first.provider_idempotency_key
    db.delete(first)
    db.delete(first_owner)
    db.commit()

    second_owner = make_waitlist()
    second = communication.enqueue_table_ready(db, second_owner)[0]
    db.flush()

    assert second_owner.id == first_owner_id
    assert second.provider_idempotency_key != first_provider_key
