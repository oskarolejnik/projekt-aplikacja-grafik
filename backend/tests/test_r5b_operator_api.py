"""Focused R5b operator API contracts: idempotency, waitlist and owner auth."""

from datetime import date, datetime, timedelta

import factories
import main
import models
import schemas
from auth import create_access_token


DAY = "2026-08-20"


def _headers(user, **extra):
    return {
        "Authorization": f"Bearer {create_access_token(user)}",
        **extra,
    }


def _table(admin_client, name="R5B"):
    response = admin_client.post(
        "/api/stoliki", json={"nazwa": name, "pojemnosc": 6},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _reservation(admin_client, table_id, *, preference="email"):
    response = admin_client.post(
        "/api/rezerwacje-stolik",
        headers={"Idempotency-Key": f"create-r5b-{preference}-{table_id}"},
        json={
            "data": DAY,
            "godz_od": "18:00",
            "stolik_id": table_id,
            "liczba_osob": 2,
            "nazwisko": "Gość R5b",
            "email": "gosc@example.com",
            "telefon": "600100200",
            "kanal_komunikacji": preference,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _waitlist(admin_client, *, preference="email"):
    response = admin_client.post(
        "/api/lista-oczekujacych",
        json={
            "data": DAY,
            "godz_od": "19:00",
            "liczba_osob": 3,
            "nazwisko": "Lista R5b",
            "email": "lista@example.com",
            "telefon": "600300400",
            "kanal_komunikacji": preference,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _set_confirmation_state(db, reservation_id, state):
    now = datetime.utcnow()
    rows = db.query(models.RezerwacjaWiadomoscOutbox).filter_by(
        termin_id=reservation_id,
        typ_zdarzenia="confirmation",
    ).all()
    assert rows
    for row in rows:
        row.stan = state
        row.updated_at = now
        row.sent_at = now if state == "sent" else None
        row.uncertain_at = now if state == "uncertain" else None
        row.lease_token = None
        row.lease_expires_at = None
    db.commit()
    return rows


def test_manual_confirmation_idempotency_replays_exact_group_for_both_channels(
    admin_client, db,
):
    reservation_id = _reservation(
        admin_client, _table(admin_client, "IDEM"), preference="oba",
    )
    key = "manual-confirmation-retry-0001"
    path = f"/api/rezerwacje-stolik/{reservation_id}/wyslij-potwierdzenie"

    original = _set_confirmation_state(db, reservation_id, "sent")

    headers = {"Idempotency-Key": key, "X-Confirm-Resend": "true"}
    first = admin_client.post(path, headers=headers)
    second = admin_client.post(path, headers=headers)

    assert first.status_code == second.status_code == 200
    assert "no-store" in first.headers["cache-control"]
    assert second.json() == first.json()
    body = schemas.RezerwacjaKomunikacjaQueueOut.model_validate(first.json())
    assert body.queued == 2
    assert {message.channel for message in body.messages} == {"email", "sms"}

    rows = db.query(models.RezerwacjaWiadomoscOutbox).filter_by(
        termin_id=reservation_id,
        typ_zdarzenia="confirmation",
    ).all()
    # Two messages from transactional create + one two-channel manual resend.
    assert len(rows) == 4
    manual_group = [row for row in rows if row.id in {item.id for item in body.messages}]
    assert len(manual_group) == 2
    assert len({row.dedupe_key for row in manual_group}) == 1
    assert all(len(row.dedupe_key) == 64 and key not in row.dedupe_key for row in manual_group)
    assert all(row.template_key == "confirmation_manual_resend" for row in manual_group)
    assert all(row.actor_kind == "user" and row.actor_user_id for row in manual_group)
    assert {row.id for row in original}.isdisjoint({row.id for row in manual_group})


def test_manual_confirmation_requires_explicit_ack_after_sent(admin_client, db):
    reservation_id = _reservation(admin_client, _table(admin_client, "ACK"))
    _set_confirmation_state(db, reservation_id, "sent")
    path = f"/api/rezerwacje-stolik/{reservation_id}/wyslij-potwierdzenie"
    key = "manual-confirmation-ack-0001"

    missing_ack = admin_client.post(path, headers={"Idempotency-Key": key})
    assert missing_ack.status_code == 409
    assert missing_ack.json()["code"] == "COMMUNICATION_RESEND_CONFIRMATION_REQUIRED"

    accepted = admin_client.post(
        path,
        headers={"Idempotency-Key": key, "X-Confirm-Resend": "true"},
    )
    assert accepted.status_code == 200, accepted.text
    mismatched_replay = admin_client.post(path, headers={"Idempotency-Key": key})
    assert mismatched_replay.status_code == 409
    assert mismatched_replay.json()["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_manual_confirmation_blocks_parallel_distinct_request_keys(admin_client, db):
    reservation_id = _reservation(admin_client, _table(admin_client, "TABS"))
    _set_confirmation_state(db, reservation_id, "sent")
    path = f"/api/rezerwacje-stolik/{reservation_id}/wyslij-potwierdzenie"

    first = admin_client.post(
        path,
        headers={"Idempotency-Key": "manual-tab-a", "X-Confirm-Resend": "true"},
    )
    second = admin_client.post(
        path,
        headers={"Idempotency-Key": "manual-tab-b", "X-Confirm-Resend": "true"},
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 409
    assert second.json()["code"] == "COMMUNICATION_ALREADY_PENDING"


def test_manual_confirmation_routes_failed_and_uncertain_to_safe_actions(
    admin_client, db,
):
    reservation_id = _reservation(admin_client, _table(admin_client, "SAFE"))
    path = f"/api/rezerwacje-stolik/{reservation_id}/wyslij-potwierdzenie"

    _set_confirmation_state(db, reservation_id, "failed")
    failed = admin_client.post(path, headers={"Idempotency-Key": "manual-failed"})
    assert failed.status_code == 409
    assert failed.json()["code"] == "COMMUNICATION_RETRY_REQUIRED"

    _set_confirmation_state(db, reservation_id, "uncertain")
    uncertain = admin_client.post(
        path,
        headers={"Idempotency-Key": "manual-uncertain"},
    )
    assert uncertain.status_code == 409
    assert uncertain.json()["code"] == "COMMUNICATION_RECONCILIATION_REQUIRED"


def test_manual_confirmation_after_cancelled_generation_is_audited_as_initial(
    admin_client, db,
):
    reservation_id = _reservation(admin_client, _table(admin_client, "INITIAL"))
    _set_confirmation_state(db, reservation_id, "cancelled")
    response = admin_client.post(
        f"/api/rezerwacje-stolik/{reservation_id}/wyslij-potwierdzenie",
        headers={"Idempotency-Key": "manual-initial"},
    )
    assert response.status_code == 200, response.text
    message_id = response.json()["messages"][0]["id"]
    row = db.get(models.RezerwacjaWiadomoscOutbox, message_id)
    assert row.template_key == "confirmation_manual_initial"
    assert row.actor_kind == "user"
    assert row.actor_user_id is not None


def test_history_exposes_canonical_resend_contract_for_mixed_channel_group(
    admin_client, db,
):
    reservation_id = _reservation(
        admin_client,
        _table(admin_client, "MIXED"),
        preference="oba",
    )
    rows = _set_confirmation_state(db, reservation_id, "sent")
    rows[0].stan = "expired"
    rows[0].sent_at = None
    db.commit()

    response = admin_client.get(
        f"/api/rezerwacje-stolik/{reservation_id}/komunikacja",
    )
    assert response.status_code == 200, response.text
    body = schemas.RezerwacjaKomunikacjaHistoriaOut.model_validate(response.json())
    assert body.summary.state == "expired"
    assert body.manual_confirmation_state == "sent"
    assert body.manual_confirmation_resend_required is True


def test_superseded_failed_confirmation_does_not_block_fresh_manual_generation(
    admin_client, db,
):
    reservation_id = _reservation(admin_client, _table(admin_client, "STALE"))
    old = _set_confirmation_state(db, reservation_id, "sent")[0]
    reservation = db.get(models.Termin, reservation_id)
    main.reservation_communication.enqueue_reservation(
        db,
        reservation,
        "change",
        dedupe_key="test:reservation:changed-after-confirmation",
    )
    db.flush()
    old.stan = "failed"
    old.sent_at = None
    old.last_error_code = "RECONCILED_NOT_SENT"
    db.commit()

    history_response = admin_client.get(
        f"/api/rezerwacje-stolik/{reservation_id}/komunikacja",
    )
    assert history_response.status_code == 200, history_response.text
    history = schemas.RezerwacjaKomunikacjaHistoriaOut.model_validate(
        history_response.json(),
    )
    assert history.summary.state == "failed"
    assert history.manual_confirmation_state is None
    assert history.manual_confirmation_resend_required is False
    stale = next(message for message in history.messages if message.id == old.id)
    assert stale.retry_allowed is False

    queued = admin_client.post(
        f"/api/rezerwacje-stolik/{reservation_id}/wyslij-potwierdzenie",
        headers={"Idempotency-Key": "fresh-after-superseded"},
    )
    assert queued.status_code == 200, queued.text


def test_manual_confirmation_rejects_invalid_idempotency_key(admin_client):
    reservation_id = _reservation(admin_client, _table(admin_client, "BADKEY"))
    missing = admin_client.post(
        f"/api/rezerwacje-stolik/{reservation_id}/wyslij-potwierdzenie",
    )
    assert missing.status_code == 422
    response = admin_client.post(
        f"/api/rezerwacje-stolik/{reservation_id}/wyslij-potwierdzenie",
        headers={"Idempotency-Key": "x" * 129},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_IDEMPOTENCY_KEY"


def test_reservation_edit_cancels_reminder_only_inside_planner_scope(
    monkeypatch,
    admin_client,
):
    table_id = _table(admin_client, "LOCK-ORDER")
    reservation_id = _reservation(admin_client, table_id, preference="sms")
    real_cancel = main.reservation_communication.cancel_pending
    real_schedule = main.reservation_communication.schedule_reminder
    events = []

    def record_cancel(db, rid, *, event_types=None, now=None):
        events.append(("cancel", tuple(event_types or ())))
        return real_cancel(db, rid, event_types=event_types, now=now)

    def record_schedule(db, reservation, **kwargs):
        # schedule_reminder przejmuje planner przed własnym cancel_pending.
        events.append(("schedule", bool(kwargs.get("force_new"))))
        return real_schedule(db, reservation, **kwargs)

    monkeypatch.setattr(main.reservation_communication, "cancel_pending", record_cancel)
    monkeypatch.setattr(main.reservation_communication, "schedule_reminder", record_schedule)

    response = admin_client.put(
        f"/api/rezerwacje-stolik/{reservation_id}",
        json={
            "data": DAY,
            "godz_od": "18:00",
            "stolik_id": table_id,
            "liczba_osob": 3,
            "nazwisko": "Gość R5b",
            "email": "gosc@example.com",
            "telefon": "600100200",
            "kanal_komunikacji": "sms",
        },
    )

    assert response.status_code == 200, response.text
    assert events == [
        ("cancel", ("confirmation", "change")),
        ("schedule", True),
        ("cancel", ("reminder",)),
    ]


def test_waitlist_both_channels_have_one_group_summary_history_and_no_duplicates(
    admin_client, db,
):
    waitlist_id = _waitlist(admin_client, preference="oba")
    path = f"/api/lista-oczekujacych/{waitlist_id}/powiadom"

    first = admin_client.post(path)
    assert first.status_code == 200, first.text
    first_body = schemas.WaitlistPowiadomOut.model_validate(first.json())
    assert first_body.queued is True
    assert {message.channel for message in first_body.messages} == {"email", "sms"}
    assert first_body.wpis["communication_summary"]["channel"] == "oba"
    assert first_body.wpis["communication_summary"]["pending_count"] == 2

    second = admin_client.post(path)
    assert second.status_code == 200, second.text
    second_body = schemas.WaitlistPowiadomOut.model_validate(second.json())
    assert {message.id for message in second_body.messages} == {
        message.id for message in first_body.messages
    }
    rows = db.query(models.RezerwacjaWiadomoscOutbox).filter_by(
        waitlist_id=waitlist_id,
        typ_zdarzenia="table_ready",
    ).all()
    assert len(rows) == 2
    assert len({row.dedupe_key for row in rows}) == 1

    listed = admin_client.get(f"/api/lista-oczekujacych?data={DAY}")
    summary = listed.json()["lista"][0]["communication_summary"]
    assert summary["channel"] == "oba"
    assert summary["state"] == "queued"

    history = admin_client.get(
        f"/api/lista-oczekujacych/{waitlist_id}/komunikacja",
    )
    assert history.status_code == 200
    assert "no-store" in history.headers["cache-control"]
    history_body = schemas.WaitlistKomunikacjaHistoriaOut.model_validate(history.json())
    assert history_body.summary.channel == "oba"
    assert history_body.legacy_delivery is False
    assert len(history_body.messages) == 2


def test_legacy_waitlist_stamp_is_visible_but_never_requeued(admin_client, db):
    waitlist_id = _waitlist(admin_client)
    delivered_at = datetime(2026, 8, 20, 16, 45)
    row = db.get(models.ListaOczekujacych, waitlist_id)
    row.powiadomiono_at = delivered_at
    db.commit()

    listed = admin_client.get(f"/api/lista-oczekujacych?data={DAY}").json()["lista"][0]
    assert listed["communication_summary"] == {
        "message_id": None,
        "state": "sent",
        "attention_required": False,
        "attention_count": 0,
        "pending_count": 0,
        "channel": None,
        "event": "table_ready",
        "last_event_at": delivered_at.isoformat(),
        "next_attempt_at": None,
        "legacy_delivery": True,
    }

    history = admin_client.get(
        f"/api/lista-oczekujacych/{waitlist_id}/komunikacja",
    )
    history_body = schemas.WaitlistKomunikacjaHistoriaOut.model_validate(history.json())
    assert history_body.legacy_delivery is True
    assert history_body.messages == []
    assert history_body.summary.state == "sent"

    notify = admin_client.post(f"/api/lista-oczekujacych/{waitlist_id}/powiadom")
    notify_body = schemas.WaitlistPowiadomOut.model_validate(notify.json())
    assert notify_body.queued is False
    assert notify_body.juz_powiadomiony is True
    assert notify_body.legacy_delivery is True
    assert notify_body.messages == []
    assert db.query(models.RezerwacjaWiadomoscOutbox).filter_by(
        waitlist_id=waitlist_id,
    ).count() == 0


def test_generic_retry_and_reconcile_enforce_message_owner_type(client, admin_client, db):
    reservation_id = _reservation(admin_client, _table(admin_client, "AUTH"), preference="oba")
    waitlist_id = _waitlist(admin_client, preference="oba")
    queued = admin_client.post(f"/api/lista-oczekujacych/{waitlist_id}/powiadom")
    assert queued.status_code == 200, queued.text

    reservation_rows = db.query(models.RezerwacjaWiadomoscOutbox).filter_by(
        termin_id=reservation_id,
        typ_zdarzenia="confirmation",
    ).order_by(models.RezerwacjaWiadomoscOutbox.id).all()
    waitlist_rows = db.query(models.RezerwacjaWiadomoscOutbox).filter_by(
        waitlist_id=waitlist_id,
        typ_zdarzenia="table_ready",
    ).order_by(models.RezerwacjaWiadomoscOutbox.id).all()
    now = datetime.utcnow()
    for failed, uncertain in (reservation_rows, waitlist_rows):
        failed.stan = "failed"
        failed.last_error_code = "TEST_FAILED"
        failed.updated_at = now
        failed.expires_at = now + timedelta(hours=1)
        uncertain.stan = "uncertain"
        uncertain.last_error_code = "TEST_UNCERTAIN"
        uncertain.uncertain_at = now
        uncertain.updated_at = now
        uncertain.expires_at = now + timedelta(hours=1)
    db.commit()

    host = factories.UserFactory(
        login="host_only_r5b",
        rola="szef",
        pracownik=None,
        uprawnienia_override={
            "rezerwacje.host": True,
            "rezerwacje.operacje": False,
            "rezerwacje.dane_kontaktowe": True,
        },
    )
    headers = _headers(host)

    assert client.post(
        f"/api/rezerwacje/komunikacja/{reservation_rows[0].id}/retry",
        headers=headers,
    ).status_code == 403
    assert client.post(
        f"/api/rezerwacje/komunikacja/{reservation_rows[1].id}/reconcile",
        headers=headers,
        json={"wynik": "failed", "notatka": "Nie dostarczono"},
    ).status_code == 403

    retry = client.post(
        f"/api/rezerwacje/komunikacja/{waitlist_rows[0].id}/retry",
        headers=headers,
    )
    assert retry.status_code == 200, retry.text
    assert schemas.RezerwacjaWiadomoscOut.model_validate(retry.json()).state == "queued"
    reconcile = client.post(
        f"/api/rezerwacje/komunikacja/{waitlist_rows[1].id}/reconcile",
        headers=headers,
        json={"wynik": "failed", "notatka": "Nie dostarczono"},
    )
    assert reconcile.status_code == 200, reconcile.text
    assert schemas.RezerwacjaWiadomoscOut.model_validate(reconcile.json()).state == "failed"
