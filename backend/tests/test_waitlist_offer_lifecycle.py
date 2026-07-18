"""Focused R6b.2 contract: atomic, versioned waitlist offers."""

from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient

import factories
import main
import models
import reservation_communication as communication
from auth import create_access_token
from delivery_result import DeliveryResult


DAY = (date.today() + timedelta(days=37)).isoformat()


def _table(client, name, capacity=4):
    response = client.post(
        "/api/stoliki",
        json={"nazwa": name, "pojemnosc": capacity},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _waitlist(client, *, party=2, email="wait-r6b2@example.test"):
    response = client.post(
        "/api/lista-oczekujacych",
        json={
            "data": DAY,
            "godz_od": "18:00",
            "liczba_osob": party,
            "nazwisko": "Gość R6b.2",
            "email": email,
            "kanal_komunikacji": "email",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _offer(client, waitlist_id, table_ids, *, version=0, key="offer-r6b2", minutes=30):
    body = {
        "stoliki": list(table_ids),
        "minuty": minutes,
        "expected_offer_version": version,
    }
    return client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/oferta",
        json=body,
        headers={"Idempotency-Key": key},
    )


def _operator_client(*, contact):
    user = factories.UserFactory(
        login=f"r6b2_host_{'contact' if contact else 'oral'}",
        rola="szef",
        pracownik=None,
        uprawnienia_override={
            "rezerwacje.host": True,
            "rezerwacje.operacje": False,
            "rezerwacje.dane_kontaktowe": bool(contact),
        },
    )
    client = TestClient(main.app)
    client.headers.update({
        "Authorization": f"Bearer {create_access_token(user)}",
    })
    return client


def test_offer_is_atomic_hash_only_idempotent_and_uses_exact_combination(
    admin_client, db,
):
    tables = [
        _table(admin_client, "R6B2-4", 4),
        _table(admin_client, "R6B2-2", 2),
    ]
    combination = admin_client.post(
        "/api/kombinacje",
        json={
            "nazwa": "R6b.2 4+2",
            "stoliki": tables,
            "pojemnosc_min": 6,
            "pojemnosc_max": 6,
        },
    )
    assert combination.status_code == 201, combination.text
    waitlist_id = _waitlist(admin_client, party=6)

    missing_key = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/oferta",
        json={"stoliki": tables, "minuty": 30, "expected_offer_version": 0},
    )
    assert missing_key.status_code == 400
    assert missing_key.json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"

    first = _offer(admin_client, waitlist_id, tables, key="r6b2-combo-offer")
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["queued"] is True
    assert len(body["messages"]) == 1
    assert body["wpis"]["status"] == "zaoferowano"
    assert body["wpis"]["offer_version"] == 1
    assert {
        body["wpis"]["hold_stolik_id"],
        *body["wpis"]["hold_stoliki_dodatkowe"],
    } == set(tables)

    db.expire_all()
    owner = db.get(models.ListaOczekujacych, waitlist_id)
    assert owner.offer_key_hash and len(owner.offer_key_hash) == 64
    assert owner.offer_request_fingerprint and len(owner.offer_request_fingerprint) == 64
    assert owner.offer_key_hash != "r6b2-combo-offer"
    claim_count = db.query(models.RezerwacjaStolikClaim).filter_by(
        waitlist_id=waitlist_id,
    ).count()
    outbox_count = db.query(models.RezerwacjaWiadomoscOutbox).filter_by(
        waitlist_id=waitlist_id,
    ).count()
    audit_count = db.query(models.AuditLog).filter_by(
        zasob=f"waitlist:{waitlist_id}",
        akcja="waitlist_offered",
    ).count()
    assert claim_count == 2 * 120
    assert outbox_count == 1
    assert audit_count == 1

    replay = _offer(admin_client, waitlist_id, tables, key="r6b2-combo-offer")
    assert replay.status_code == 200, replay.text
    assert replay.json()["messages"][0]["id"] == body["messages"][0]["id"]
    assert replay.json()["wpis"]["offer_version"] == 1
    db.expire_all()
    assert db.query(models.RezerwacjaStolikClaim).filter_by(
        waitlist_id=waitlist_id,
    ).count() == claim_count
    assert db.query(models.RezerwacjaWiadomoscOutbox).filter_by(
        waitlist_id=waitlist_id,
    ).count() == outbox_count
    assert db.query(models.AuditLog).filter_by(
        zasob=f"waitlist:{waitlist_id}",
        akcja="waitlist_offered",
    ).count() == audit_count

    oral_client = _operator_client(contact=False)
    try:
        redacted_list = oral_client.get(
            f"/api/lista-oczekujacych?data={DAY}",
        ).json()["lista"][0]
        redacted_replay = _offer(
            oral_client,
            waitlist_id,
            tables,
            key="r6b2-combo-offer",
        )
    finally:
        oral_client.close()
    assert redacted_list["communication_summary"]["channel"] is None
    assert redacted_replay.status_code == 200, redacted_replay.text
    assert redacted_replay.json()["messages"] == []
    assert redacted_replay.json()["wpis"]["communication_summary"]["channel"] is None

    changed_payload = _offer(
        admin_client,
        waitlist_id,
        tables,
        key="r6b2-combo-offer",
        minutes=31,
    )
    assert changed_payload.status_code == 409
    assert changed_payload.json()["code"] == "IDEMPOTENCY_KEY_REUSED"

    summary = admin_client.get(
        f"/api/lista-oczekujacych?data={DAY}",
    ).json()["lista"][0]["communication_summary"]
    assert summary["state"] == "queued"
    notify = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/powiadom",
    )
    assert notify.status_code == 200, notify.text
    assert notify.json()["messages"][0]["id"] == body["messages"][0]["id"]
    assert db.query(models.RezerwacjaWiadomoscOutbox).filter_by(
        waitlist_id=waitlist_id,
    ).count() == outbox_count


def test_accept_requires_current_version_and_key_creates_unseated_reservation(
    admin_client, db,
):
    table_id = _table(admin_client, "R6B2-ACCEPT", 4)
    waitlist_id = _waitlist(admin_client)
    offered = _offer(
        admin_client, waitlist_id, [table_id], key="r6b2-accept-offer",
    )
    assert offered.status_code == 200, offered.text

    no_key = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/zaakceptuj",
        json={"offer_version": 1},
    )
    assert no_key.status_code == 400
    assert no_key.json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"
    stale = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/zaakceptuj",
        headers={"Idempotency-Key": "r6b2-accept"},
        json={"offer_version": 2},
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "WAITLIST_OFFER_VERSION_CONFLICT"

    accepted = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/zaakceptuj",
        headers={"Idempotency-Key": "r6b2-accept"},
        json={"offer_version": 1},
    )
    assert accepted.status_code == 200, accepted.text
    reservation = accepted.json()["rezerwacja"]
    assert reservation["kanal"] == "reczna"
    assert reservation["faza_hosta"] is None
    assert accepted.json()["wpis"]["status"] == "zaakceptowano"
    assert accepted.json()["wpis"]["offer_version"] == 2
    assert accepted.json()["wpis"]["hold_stolik_id"] is None

    oral_client = _operator_client(contact=False)
    try:
        replay = oral_client.post(
            f"/api/lista-oczekujacych/{waitlist_id}/zaakceptuj",
            headers={"Idempotency-Key": "r6b2-accept"},
            json={"offer_version": 1},
        )
    finally:
        oral_client.close()
    assert replay.status_code == 200, replay.text
    assert replay.json()["rezerwacja"]["nazwisko"] == "Gość"
    assert replay.json()["wpis"]["nazwisko"] == "Gość"
    assert db.query(models.Termin).count() == 1


def test_default_offer_freezes_and_transfers_auto_assignment(admin_client, db):
    _table(admin_client, "R6B2-AUTO-1", 4)
    _table(admin_client, "R6B2-AUTO-2", 4)
    waitlist_id = _waitlist(admin_client)

    offered = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/oferta",
        headers={"Idempotency-Key": "r6b2-auto-default-offer"},
        json={"minuty": 30, "expected_offer_version": 0},
    )
    assert offered.status_code == 200, offered.text
    assert offered.json()["wpis"]["offer_auto_przydzielony"] is True

    accepted = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/zaakceptuj",
        headers={"Idempotency-Key": "r6b2-auto-default-accept"},
        json={"offer_version": 1},
    )
    assert accepted.status_code == 200, accepted.text
    db.expire_all()
    reservation = db.get(models.Termin, accepted.json()["rezerwacja"]["id"])
    assert reservation.auto_przydzielony is True


def test_manual_alternative_keeps_frozen_manual_provenance_on_accept(
    admin_client, db,
):
    table_ids = [
        _table(admin_client, "R6B2-MANUAL-1", 4),
        _table(admin_client, "R6B2-MANUAL-2", 4),
    ]
    waitlist_id = _waitlist(admin_client)
    recommended = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/oferta",
        headers={"Idempotency-Key": "r6b2-manual-probe"},
        json={"minuty": 30, "expected_offer_version": 0},
    )
    assert recommended.status_code == 200, recommended.text
    recommended_body = recommended.json()["wpis"]
    assert recommended_body["offer_auto_przydzielony"] is True
    recommended_ids = {
        recommended_body["hold_stolik_id"],
        *recommended_body["hold_stoliki_dodatkowe"],
    }
    assert len(recommended_ids) == 1

    withdrawn = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/wycofaj-oferte",
        json={"offer_version": 1},
    )
    assert withdrawn.status_code == 200, withdrawn.text
    alternative_id = next(
        table_id for table_id in table_ids if table_id not in recommended_ids
    )
    manual = _offer(
        admin_client,
        waitlist_id,
        [alternative_id],
        version=2,
        key="r6b2-manual-alternative",
    )
    assert manual.status_code == 200, manual.text
    assert manual.json()["wpis"]["offer_auto_przydzielony"] is False

    accepted = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/zaakceptuj",
        headers={"Idempotency-Key": "r6b2-manual-accept"},
        json={"offer_version": 3},
    )
    assert accepted.status_code == 200, accepted.text
    db.expire_all()
    reservation = db.get(models.Termin, accepted.json()["rezerwacja"]["id"])
    assert reservation.auto_przydzielony is False


def test_host_waitlist_exposes_only_pii_safe_communication_capability(admin_client):
    email_id = _waitlist(
        admin_client, email="host-capability@example.test",
    )
    disabled = admin_client.post(
        "/api/lista-oczekujacych",
        json={
            "data": DAY,
            "godz_od": "18:15",
            "liczba_osob": 2,
        "nazwisko": "Kanał wyłączony",
            "email": "disabled@example.test",
            "kanal_komunikacji": "brak",
        },
    )
    assert disabled.status_code == 201, disabled.text
    missing = admin_client.post(
        "/api/lista-oczekujacych",
        json={
            "data": DAY,
            "godz_od": "18:30",
            "liczba_osob": 2,
            "nazwisko": "Brak kontaktu",
            "kanal_komunikacji": "auto",
        },
    )
    assert missing.status_code == 201, missing.text

    rows = {
        row["id"]: row
        for row in admin_client.get(f"/api/host/kolejka?data={DAY}").json()[
            "waitlista"
        ]
    }
    assert rows[email_id]["can_queue_communication"] is True
    assert rows[disabled.json()["id"]]["can_queue_communication"] is False
    assert rows[missing.json()["id"]]["can_queue_communication"] is False

    oral_client = _operator_client(contact=False)
    try:
        redacted = oral_client.get(f"/api/host/kolejka?data={DAY}")
    finally:
        oral_client.close()
    assert redacted.status_code == 200, redacted.text
    assert all(
        row["can_queue_communication"] is False
        for row in redacted.json()["waitlista"]
    )


def test_online_waitlist_offer_uses_online_channel_rules_and_leaves_no_hold(
    admin_client, db,
):
    _table(admin_client, "R6B2-ONLINE-RULE", 4)
    waitlist_id = _waitlist(admin_client, party=2)
    owner = db.get(models.ListaOczekujacych, waitlist_id)
    owner.kanal = "online"
    db.add(models.RegulaDostepnosciRezerwacji(
        kanal="online",
        max_grupa=1,
    ))
    db.commit()

    generic_preview = admin_client.get(
        f"/api/host/sugestia-stolika?data={DAY}&godz_od=18:00&osoby=2",
    )
    assert generic_preview.status_code == 200, generic_preview.text
    assert generic_preview.json()["decision"] == "allow"
    waitlist_preview = admin_client.get(
        f"/api/host/sugestia-stolika?data={DAY}&godz_od=18:00&osoby=2"
        f"&waitlist_id={waitlist_id}",
    )
    assert waitlist_preview.status_code == 200, waitlist_preview.text
    assert waitlist_preview.json()["decision"] == "override_required"
    assert any(
        item["code"] == "PARTY_SIZE_ABOVE_MAX"
        for item in waitlist_preview.json()["violations"]
    )

    offered = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/oferta",
        headers={"Idempotency-Key": "r6b2-online-rule-offer"},
        json={"minuty": 30, "expected_offer_version": 0},
    )
    assert offered.status_code == 409, offered.text
    db.expire_all()
    owner = db.get(models.ListaOczekujacych, waitlist_id)
    assert owner.status == "oczekuje"
    assert owner.offer_version == 0
    assert owner.hold_stolik_id is None and owner.hold_do is None
    assert db.query(models.RezerwacjaStolikClaim).filter_by(
        waitlist_id=waitlist_id,
    ).count() == 0


def test_offer_revalidates_exact_candidate_after_table_lock(
    admin_client, db, monkeypatch,
):
    table_id = _table(admin_client, "R6B2-PLAN-RACE", 4)
    waitlist_id = _waitlist(admin_client)
    original = main._ocen_przydzial_rezerwacji
    calls = 0

    def evaluate_with_plan_change(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            db.get(models.Stolik, table_id).aktywny = False
            db.flush()
        return original(*args, **kwargs)

    monkeypatch.setattr(
        main, "_ocen_przydzial_rezerwacji", evaluate_with_plan_change,
    )
    offered = _offer(
        admin_client,
        waitlist_id,
        [table_id],
        key="r6b2-plan-race-offer",
    )
    assert offered.status_code == 409, offered.text
    assert offered.json()["code"] == "WAITLIST_OFFER_PLAN_CHANGED"
    db.rollback()
    db.expire_all()
    owner = db.get(models.ListaOczekujacych, waitlist_id)
    assert owner.status == "oczekuje"
    assert owner.offer_version == 0
    assert owner.hold_stolik_id is None
    assert db.get(models.Stolik, table_id).aktywny is True
    assert db.query(models.RezerwacjaStolikClaim).filter_by(
        waitlist_id=waitlist_id,
    ).count() == 0


def test_offer_override_is_authorized_once_frozen_and_transferred_on_accept(
    admin_client, db,
):
    occupied_id = _table(admin_client, "R6B2-OVERRIDE-OCCUPIED", 4)
    offered_id = _table(admin_client, "R6B2-OVERRIDE-OFFER", 4)
    first = admin_client.post(
        "/api/rezerwacje-stolik",
        json={
            "data": DAY,
            "godz_od": "18:00",
            "stolik_id": occupied_id,
            "liczba_osob": 2,
            "nazwisko": "Pierwsza",
        },
    )
    assert first.status_code == 201, first.text
    db.add(models.RegulaDostepnosciRezerwacji(
        kanal="wewnetrzna",
        max_jednoczesnych_rez=1,
    ))
    db.commit()
    waitlist_id = _waitlist(admin_client, party=2)
    base = {
        "stolik_id": offered_id,
        "minuty": 30,
        "expected_offer_version": 0,
    }

    warning = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/oferta",
        headers={"Idempotency-Key": "r6b2-override-warning"},
        json=base,
    )
    assert warning.status_code == 409, warning.text
    assert warning.json()["availability"]["decision"] == "override_required"
    db.expire_all()
    owner = db.get(models.ListaOczekujacych, waitlist_id)
    assert owner.status == "oczekuje" and owner.hold_stolik_id is None

    forbidden_user = factories.UserFactory(
        login="r6b2_override_forbidden",
        rola="szef",
        pracownik=None,
        uprawnienia_override={
            "rezerwacje.host": True,
            "rezerwacje.dane_kontaktowe": True,
            "rezerwacje.nadpisuj_limity": False,
        },
    )
    forbidden_client = TestClient(main.app)
    forbidden_client.headers.update({
        "Authorization": f"Bearer {create_access_token(forbidden_user)}",
    })
    override_payload = {
        **base,
        "nadpisanie_limitow": {
            "powod": "operational_decision",
        "notatka": "Recepcja potwierdziła wyjątek waitlisty",
            "potwierdzone": True,
        },
    }
    try:
        forbidden = forbidden_client.post(
            f"/api/lista-oczekujacych/{waitlist_id}/oferta",
            headers={"Idempotency-Key": "r6b2-override-forbidden"},
            json=override_payload,
        )
    finally:
        forbidden_client.close()
    assert forbidden.status_code == 403, forbidden.text

    offered = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/oferta",
        headers={"Idempotency-Key": "r6b2-override-authorized"},
        json=override_payload,
    )
    assert offered.status_code == 200, offered.text
    assert offered.json()["wpis"]["offer_override_authorized"] is True
    db.expire_all()
    owner = db.get(models.ListaOczekujacych, waitlist_id)
    assert owner.offer_override_authorized is True
    generation_context = db.query(
        models.WaitlistOfferOverrideContext,
    ).filter_by(
        waitlist_id=waitlist_id,
        offer_version=1,
    ).one()
    assert generation_context.reason_code == "operational_decision"
    assert generation_context.note == "Recepcja potwierdziła wyjątek waitlisty"
    offered_audit = db.query(models.AuditLog).filter_by(
        zasob=f"waitlist:{waitlist_id}", akcja="waitlist_offered",
    ).one()
    assert "Recepcja potwierdzi" not in offered_audit.szczegoly
    assert "enc:v1:" not in offered_audit.szczegoly

    accepted = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/zaakceptuj",
        headers={"Idempotency-Key": "r6b2-override-accept"},
        json={"offer_version": 1},
    )
    assert accepted.status_code == 200, accepted.text
    reservation_id = accepted.json()["rezerwacja"]["id"]
    db.expire_all()
    assert db.get(models.ListaOczekujacych, waitlist_id).offer_override_authorized is None
    assert db.query(models.RezerwacjaPacingLedger).filter_by(
        termin_id=reservation_id,
    ).one().override is True
    occupancy = db.query(models.RezerwacjaOblozenieLedger).filter_by(
        termin_id=reservation_id,
    ).all()
    assert occupancy and all(row.override is True for row in occupancy)
    audit = db.query(models.ReservationAudit).filter_by(
        termin_id=reservation_id, action="override",
    ).one()
    context = db.query(models.ReservationOverrideContext).filter_by(
        audit_id=audit.id,
    ).one()
    assert context.reason_code == "operational_decision"
    assert context.note == "Recepcja potwierdziła wyjątek waitlisty"


def test_override_context_survives_withdraw_cancel_and_is_rodo_erased(
    admin_client, db,
):
    table_id = _table(admin_client, "R6B2-OVERRIDE-HISTORY", 4)
    db.add(models.RegulaDostepnosciRezerwacji(
        kanal="wewnetrzna",
        max_grupa=1,
    ))
    db.commit()
    email = "override-history@example.test"
    waitlist_id = _waitlist(admin_client, party=2, email=email)
    note = "Poufny wyjątek zachowany dla generacji"
    offered = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/oferta",
        headers={"Idempotency-Key": "r6b2-override-history-offer"},
        json={
            "stolik_id": table_id,
            "minuty": 30,
            "expected_offer_version": 0,
            "nadpisanie_limitow": {
                "powod": "other",
                "notatka": note,
                "potwierdzone": True,
            },
        },
    )
    assert offered.status_code == 200, offered.text
    audit = db.query(models.AuditLog).filter_by(
        zasob=f"waitlist:{waitlist_id}", akcja="waitlist_offered",
    ).one()
    assert note not in audit.szczegoly
    assert "enc:v1:" not in audit.szczegoly

    withdrawn = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/wycofaj-oferte",
        json={"offer_version": 1},
    )
    assert withdrawn.status_code == 200, withdrawn.text
    cancelled = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/anuluj",
        json={"expected_offer_version": 2},
    )
    assert cancelled.status_code == 200, cancelled.text
    db.expire_all()
    owner = db.get(models.ListaOczekujacych, waitlist_id)
    assert owner.offer_override_note is None
    context = db.query(models.WaitlistOfferOverrideContext).filter_by(
        waitlist_id=waitlist_id, offer_version=1,
    ).one()
    assert context.note == note

    exported = admin_client.post(
        "/api/rodo/eksport-gosc", json={"klucz": email},
    )
    assert exported.status_code == 200, exported.text
    history = exported.json()["prywatnosc"][
        "historia_nadpisan_ofert_waitlisty"
    ]
    assert history == [{
        "wpis_waitlisty_id": waitlist_id,
        "offer_version": 1,
        "kod_powodu": "other",
        "notatka": note,
        "utworzono_at": history[0]["utworzono_at"],
    }]

    erased = admin_client.post(
        "/api/rodo/anonimizuj-gosc", json={"klucz": email},
    )
    assert erased.status_code == 200, erased.text
    db.expire_all()
    context = db.get(models.WaitlistOfferOverrideContext, context.id)
    assert context.note is None
    assert context.reason_code == "other"


def test_active_offer_reserves_r3_capacity_but_its_own_accept_is_grandfathered(
    admin_client, db,
):
    first_table = _table(admin_client, "R6B2-PROMISE-1", 4)
    second_table = _table(admin_client, "R6B2-PROMISE-2", 4)
    db.add(models.RegulaDostepnosciRezerwacji(
        kanal="wewnetrzna",
        max_jednoczesnych_rez=1,
        pacing_okno_min=30,
        pacing_max_rez=1,
    ))
    db.commit()
    first_waitlist = _waitlist(
        admin_client, party=2, email="promise-a@example.test",
    )
    second_waitlist = _waitlist(
        admin_client, party=2, email="promise-b@example.test",
    )

    promised = _offer(
        admin_client,
        first_waitlist,
        [first_table],
        key="r6b2-promise-a",
    )
    assert promised.status_code == 200, promised.text
    assert promised.json()["wpis"]["offer_override_authorized"] is False

    blocked = _offer(
        admin_client,
        second_waitlist,
        [second_table],
        key="r6b2-promise-b",
    )
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["availability"]["decision"] == "override_required"
    assert blocked.json()["code"] in {
        "PACING_RESERVATION_LIMIT", "CONCURRENT_RESERVATION_LIMIT",
    }
    db.expire_all()
    second_owner = db.get(models.ListaOczekujacych, second_waitlist)
    assert second_owner.status == "oczekuje" and second_owner.hold_stolik_id is None

    later_booking = admin_client.post(
        "/api/rezerwacje-stolik",
        json={
            "data": DAY,
            "godz_od": "18:00",
            "stolik_id": second_table,
            "liczba_osob": 2,
            "nazwisko": "Późniejsza świadoma rezerwacja",
            "nadpisanie_limitow": {
                "powod": "operational_decision",
                "notatka": "Świadomie zajmujemy dodatkową pojemność.",
                "potwierdzone": True,
            },
        },
    )
    assert later_booking.status_code == 201, later_booking.text
    later_booking_id = later_booking.json()["id"]

    accepted = admin_client.post(
        f"/api/lista-oczekujacych/{first_waitlist}/zaakceptuj",
        headers={"Idempotency-Key": "r6b2-promise-a-accept"},
        json={"offer_version": 1},
    )
    assert accepted.status_code == 200, accepted.text
    reservation_id = accepted.json()["rezerwacja"]["id"]
    db.expire_all()
    assert db.query(models.RezerwacjaPacingLedger).filter_by(
        termin_id=reservation_id,
    ).one().override is False
    assert db.query(models.RezerwacjaPacingLedger).filter_by(
        termin_id=later_booking_id,
    ).one().override is True
    accepted_audit = db.query(models.AuditLog).filter_by(
        zasob=f"waitlist:{first_waitlist}",
        akcja="waitlist_accepted",
    ).one()
    assert "pacing_reservations" in accepted_audit.szczegoly
    assert "concurrent_reservations" in accepted_audit.szczegoly


def test_accept_preserves_frozen_interval_buffer_room_channel_and_claims(
    admin_client, db,
):
    booking_day = date.fromisoformat(DAY)
    table_id = _table(admin_client, "R6B2-FROZEN-CONTRACT", 4)
    service = models.GodzinyOtwarcia(
        dzien_tygodnia=booking_day.weekday(),
        godz_od=datetime.strptime("17:00", "%H:%M").time(),
        godz_do=datetime.strptime("23:00", "%H:%M").time(),
        ostatni_zasiadek=datetime.strptime("22:00", "%H:%M").time(),
        dlugosc_slotu_min=90,
        krok_slotu_min=30,
        domyslny_turn_time_min=90,
        aktywny=True,
        nazwa="Kolacja R6b.2",
    )
    rule = models.RegulaDostepnosciRezerwacji(
        kanal="wewnetrzna",
        bufor_min=15,
    )
    db.add_all([service, rule])
    db.commit()
    waitlist_id = _waitlist(admin_client)

    offered = _offer(
        admin_client,
        waitlist_id,
        [table_id],
        key="r6b2-frozen-contract-offer",
    )
    assert offered.status_code == 200, offered.text
    db.expire_all()
    owner = db.get(models.ListaOczekujacych, waitlist_id)
    frozen_end = owner.hold_godz_do
    frozen_buffer = owner.hold_bufor_min
    frozen_room = owner.offer_sala_id
    frozen_channel = owner.offer_kanal
    frozen_claims = {
        (row.stolik_id, row.minute)
        for row in db.query(models.RezerwacjaStolikClaim).filter_by(
            waitlist_id=waitlist_id,
        ).all()
    }
    assert frozen_buffer == 15
    assert frozen_channel == "wewnetrzna"

    service.domyslny_turn_time_min = 180
    service.dlugosc_slotu_min = 180
    rule.bufor_min = 45
    owner.kanal = "online"
    db.commit()

    adjacent = admin_client.post(
        "/api/rezerwacje-stolik",
        json={
            "data": DAY,
            "godz_od": "19:45",
            "stolik_id": table_id,
            "liczba_osob": 2,
            "nazwisko": "Po zamrożonym buforze",
        },
    )
    assert adjacent.status_code == 201, adjacent.text

    accepted = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/zaakceptuj",
        headers={"Idempotency-Key": "r6b2-frozen-contract-accept"},
        json={"offer_version": 1},
    )
    assert accepted.status_code == 200, accepted.text
    reservation_id = accepted.json()["rezerwacja"]["id"]
    db.expire_all()
    reservation = db.get(models.Termin, reservation_id)
    assert reservation.godz_do == frozen_end
    assert reservation.kanal == "reczna"
    assert reservation.stolik_id == table_id
    assert frozen_room is None or frozen_room == db.get(
        models.Stolik, table_id,
    ).sala_id
    transferred_claims = {
        (row.stolik_id, row.minute)
        for row in db.query(models.RezerwacjaStolikClaim).filter_by(
            termin_id=reservation_id,
        ).all()
    }
    assert transferred_claims == frozen_claims


def test_legacy_topology_mutations_are_fenced_by_active_combination_offer(
    admin_client, db,
):
    first_id = _table(admin_client, "R6B2-LEGACY-4", 4)
    second_id = _table(admin_client, "R6B2-LEGACY-2", 2)
    table_ids = [first_id, second_id]
    combination = admin_client.post(
        "/api/kombinacje",
        json={
            "nazwa": "Legacy 4+2",
            "stoliki": table_ids,
            "pojemnosc_min": 6,
            "pojemnosc_max": 6,
        },
    )
    assert combination.status_code == 201, combination.text
    adjacency = admin_client.post(
        "/api/sasiedztwo",
        json={"stolik_a": first_id, "stolik_b": second_id},
    )
    assert adjacency.status_code == 201, adjacency.text
    waitlist_id = _waitlist(admin_client, party=6)
    offered = _offer(
        admin_client,
        waitlist_id,
        table_ids,
        key="r6b2-legacy-topology-offer",
    )
    assert offered.status_code == 200, offered.text

    mutations = [
        admin_client.put(
            f"/api/stoliki/{first_id}",
            json={"nazwa": "R6B2-LEGACY-4", "pojemnosc": 3},
        ),
        admin_client.put(
            f"/api/stoliki/{first_id}",
            json={
                "nazwa": "R6B2-LEGACY-4",
                "pojemnosc": 4,
                "aktywny": False,
            },
        ),
        admin_client.put(
            f"/api/kombinacje/{combination.json()['id']}",
            json={
                "nazwa": "Legacy 4+2 po zmianie",
                "stoliki": table_ids,
                "pojemnosc_min": 5,
                "pojemnosc_max": 6,
            },
        ),
        admin_client.delete(f"/api/kombinacje/{combination.json()['id']}"),
        admin_client.delete(f"/api/sasiedztwo/{adjacency.json()['id']}"),
    ]
    for response in mutations:
        assert response.status_code == 409, response.text
        assert response.json()["detail"]["code"] == (
            "WAITLIST_OFFER_TOPOLOGY_CONFLICT"
        )

    accepted = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/zaakceptuj",
        headers={"Idempotency-Key": "r6b2-legacy-topology-accept"},
        json={"offer_version": 1},
    )
    assert accepted.status_code == 200, accepted.text
    assert {
        accepted.json()["rezerwacja"]["stolik_id"],
        *accepted.json()["rezerwacja"]["stoliki_dodatkowe"],
    } == set(table_ids)
    db.expire_all()
    assert db.get(models.Stolik, first_id).pojemnosc == 4
    assert db.get(models.Stolik, first_id).aktywny is True
    assert db.get(models.KombinacjaStolow, combination.json()["id"]) is not None
    assert db.get(models.SasiedztwoStolow, adjacency.json()["id"]) is not None


def test_legacy_combination_create_cannot_invalidate_active_graph_offer(
    admin_client, db, monkeypatch,
):
    first_id = _table(admin_client, "R6B2-GRAPH-4", 4)
    second_id = _table(admin_client, "R6B2-GRAPH-2", 2)
    table_ids = [first_id, second_id]
    adjacency = admin_client.post(
        "/api/sasiedztwo",
        json={"stolik_a": first_id, "stolik_b": second_id},
    )
    assert adjacency.status_code == 201, adjacency.text
    waitlist_id = _waitlist(admin_client, party=5)
    offered = _offer(
        admin_client,
        waitlist_id,
        table_ids,
        key="r6b2-graph-4-plus-2-offer",
    )
    assert offered.status_code == 200, offered.text

    events = []
    original_begin = main.reservation_service.begin_floor_plan_write
    original_lock = main.reservation_service.lock_tables
    original_fence = main._blokuj_topologie_aktywnej_oferty

    def record_begin(session):
        events.append("begin_floor_plan_write")
        return original_begin(session)

    def record_lock(session, ids):
        ordered = tuple(sorted(ids))
        events.append(("lock_tables", ordered))
        return original_lock(session, ids)

    def record_fence(session, ids, **kwargs):
        ordered = tuple(sorted(ids))
        events.append(("active_offer_fence", ordered))
        return original_fence(session, ids, **kwargs)

    monkeypatch.setattr(
        main.reservation_service, "begin_floor_plan_write", record_begin,
    )
    monkeypatch.setattr(main.reservation_service, "lock_tables", record_lock)
    monkeypatch.setattr(main, "_blokuj_topologie_aktywnej_oferty", record_fence)

    # Jawny zakres 6..6 ma pierwszeństwo nad grafem i bez fence usunąłby
    # zamrożony wariant 4+2 dla pięciu osób podczas późniejszej akceptacji.
    blocked = admin_client.post(
        "/api/kombinacje",
        json={
            "nazwa": "R6b.2 4+2 tylko komplet",
            "stoliki": table_ids,
            "pojemnosc_min": 6,
            "pojemnosc_max": 6,
        },
    )
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["detail"]["code"] == (
        "WAITLIST_OFFER_TOPOLOGY_CONFLICT"
    )
    ordered_ids = tuple(sorted(table_ids))
    assert events[:3] == [
        "begin_floor_plan_write",
        ("lock_tables", ordered_ids),
        ("active_offer_fence", ordered_ids),
    ]
    db.expire_all()
    assert db.query(models.KombinacjaStolow).filter_by(
        nazwa="R6b.2 4+2 tylko komplet",
    ).first() is None

    accepted = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/zaakceptuj",
        headers={"Idempotency-Key": "r6b2-graph-4-plus-2-accept"},
        json={"offer_version": 1},
    )
    assert accepted.status_code == 200, accepted.text
    assert {
        accepted.json()["rezerwacja"]["stolik_id"],
        *accepted.json()["rezerwacja"]["stoliki_dodatkowe"],
    } == set(table_ids)


def test_legacy_combination_loader_locks_and_refreshes_postgresql_row():
    marker = object()

    class FakeQuery:
        def __init__(self):
            self.filter_values = None
            self.row_locked = False
            self.refreshed = False

        def filter_by(self, **values):
            self.filter_values = values
            return self

        def with_for_update(self):
            self.row_locked = True
            return self

        def populate_existing(self):
            self.refreshed = True
            return self

        def first(self):
            return marker

    query = FakeQuery()

    class FakeDb:
        def query(self, model):
            assert model is models.KombinacjaStolow
            return query

        def get_bind(self):
            class Dialect:
                name = "postgresql"

            class Bind:
                dialect = Dialect()

            return Bind()

    assert main._zablokuj_legacy_kombinacje(FakeDb(), 17) is marker
    assert query.filter_values == {"id": 17}
    assert query.row_locked is True
    assert query.refreshed is True


def test_priority_withdraw_and_legacy_aliases_preserve_generation_guards(
    admin_client,
):
    table_id = _table(admin_client, "R6B2-VERSIONS", 4)
    waitlist_id = _waitlist(admin_client)
    priority = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/priorytet",
        json={"priorytet": 7, "expected_offer_version": 0},
    )
    assert priority.status_code == 200, priority.text
    assert priority.json()["offer_version"] == 1

    stale_offer = _offer(
        admin_client, waitlist_id, [table_id], version=0, key="stale-offer",
    )
    assert stale_offer.status_code == 409
    assert stale_offer.json()["code"] == "WAITLIST_OFFER_VERSION_CONFLICT"
    offered = _offer(
        admin_client, waitlist_id, [table_id], version=1, key="offer-v2",
    )
    assert offered.status_code == 200, offered.text
    assert offered.json()["wpis"]["offer_version"] == 2

    assert admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/priorytet",
        json={"priorytet": 8, "expected_offer_version": 2},
    ).status_code == 409
    assert admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/zwolnij-hold",
    ).status_code == 409
    assert admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/odwolaj",
    ).status_code == 409
    assert admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/zrealizuj",
        json={"stolik_id": table_id, "tryb": "walk_in"},
    ).status_code == 409

    withdrawn = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/wycofaj-oferte",
        json={"offer_version": 2},
    )
    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["status"] == "oczekuje"
    assert withdrawn.json()["offer_version"] == 3
    reused = _offer(
        admin_client, waitlist_id, [table_id], version=3, key="offer-v2",
    )
    assert reused.status_code == 409
    assert reused.json()["code"] == "IDEMPOTENCY_KEY_REUSED"
    reoffered = _offer(
        admin_client, waitlist_id, [table_id], version=3, key="offer-v4",
    )
    assert reoffered.status_code == 200, reoffered.text
    cancelled = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/anuluj",
        json={"expected_offer_version": 4},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "anulowano"
    assert cancelled.json()["offer_version"] == 5


def test_oral_offer_redacts_contact_and_powiadom_requires_contact(admin_client, db):
    table_id = _table(admin_client, "R6B2-ORAL", 4)
    waitlist_id = _waitlist(admin_client)
    oral_client = _operator_client(contact=False)
    try:
        offered = _offer(
            oral_client,
            waitlist_id,
            [table_id],
            key="r6b2-oral-offer",
        )
        assert offered.status_code == 200, offered.text
        assert offered.json()["queued"] is False
        assert offered.json()["messages"] == []
        assert offered.json()["wpis"]["nazwisko"] == "Gość"
        assert offered.json()["wpis"]["email"] is None
        notify = oral_client.post(
            f"/api/lista-oczekujacych/{waitlist_id}/powiadom",
        )
        assert notify.status_code == 403
    finally:
        oral_client.close()
    assert db.query(models.RezerwacjaWiadomoscOutbox).filter_by(
        waitlist_id=waitlist_id,
    ).count() == 0
    first_notify = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/powiadom",
    )
    assert first_notify.status_code == 200, first_notify.text
    assert first_notify.json()["queued"] is True
    message_id = first_notify.json()["messages"][0]["id"]
    second_notify = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/powiadom",
    )
    assert second_notify.status_code == 200, second_notify.text
    assert second_notify.json()["messages"][0]["id"] == message_id
    assert db.query(models.RezerwacjaWiadomoscOutbox).filter_by(
        waitlist_id=waitlist_id,
    ).count() == 1


def test_expiry_worker_releases_claims_and_transitions_offer(admin_client, db):
    table_id = _table(admin_client, "R6B2-EXPIRY", 4)
    waitlist_id = _waitlist(admin_client)
    offered = _offer(
        admin_client, waitlist_id, [table_id], key="r6b2-expiry-offer",
    )
    assert offered.status_code == 200, offered.text
    expired_at = datetime.utcnow() - timedelta(seconds=1)
    owner = db.get(models.ListaOczekujacych, waitlist_id)
    owner.hold_do = expired_at
    owner.oferta_wygasa_at = expired_at
    db.query(models.RezerwacjaStolikClaim).filter_by(
        waitlist_id=waitlist_id,
    ).update({models.RezerwacjaStolikClaim.expires_at: expired_at})
    db.add(models.ListaOczekujacych(
        data=date.fromisoformat(DAY),
        godz_od=datetime.strptime("19:00", "%H:%M").time(),
        liczba_osob=2,
        nazwisko="Historyczny nieaktywny hold",
        status="zaakceptowano",
        utworzono_at=expired_at - timedelta(days=1),
        hold_do=expired_at,
    ))
    db.commit()

    assert communication.run_waitlist_expiry_once(now=datetime.utcnow()) == 1
    db.expire_all()
    owner = db.get(models.ListaOczekujacych, waitlist_id)
    assert owner.status == "wygasla"
    assert owner.offer_version == 2
    assert owner.wygasla_at is not None
    assert owner.hold_stolik_id is None
    assert db.query(models.RezerwacjaStolikClaim).filter_by(
        waitlist_id=waitlist_id,
    ).count() == 0
    assert db.query(models.AuditLog).filter_by(
        zasob=f"waitlist:{waitlist_id}",
        akcja="waitlist_offer_expired",
    ).count() == 1


def test_table_delete_cleans_expired_waitlist_claim_before_fk_delete(
    admin_client, db,
):
    table_id = _table(admin_client, "R6B2-EXPIRED-DELETE", 4)
    expired_at = datetime.utcnow() - timedelta(minutes=1)
    owner = models.ListaOczekujacych(
        data=date.fromisoformat(DAY),
        godz_od=datetime.strptime("18:00", "%H:%M").time(),
        liczba_osob=2,
        nazwisko="Wygasły claim",
        status="zaoferowano",
        utworzono_at=expired_at - timedelta(minutes=5),
        hold_stolik_id=table_id,
        hold_godz_od=datetime.strptime("18:00", "%H:%M").time(),
        hold_godz_do=datetime.strptime("20:00", "%H:%M").time(),
        hold_bufor_min=0,
        hold_do=expired_at,
        oferta_wygasa_at=expired_at,
    )
    db.add(owner)
    db.flush()
    db.add(models.RezerwacjaStolikClaim(
        waitlist_id=owner.id,
        stolik_id=table_id,
        data=owner.data,
        minute=18 * 60,
        expires_at=expired_at,
        created_at=expired_at - timedelta(minutes=5),
    ))
    db.commit()

    deleted = admin_client.delete(f"/api/stoliki/{table_id}")
    assert deleted.status_code == 204, deleted.text
    db.expire_all()
    assert db.get(models.Stolik, table_id) is None
    assert db.query(models.RezerwacjaStolikClaim).filter_by(
        waitlist_id=owner.id,
    ).count() == 0
    refreshed = db.get(models.ListaOczekujacych, owner.id)
    assert refreshed.status == "wygasla"
    assert refreshed.hold_stolik_id is None


def test_started_delivery_fences_reoffer_and_stale_finalize_never_stamps_owner(
    admin_client, admin, db,
):
    table_id = _table(admin_client, "R6B2-FENCE", 4)
    waitlist_id = _waitlist(admin_client)
    offered = _offer(
        admin_client, waitlist_id, [table_id], key="r6b2-fence-offer",
    )
    assert offered.status_code == 200, offered.text
    row = db.query(models.RezerwacjaWiadomoscOutbox).filter_by(
        waitlist_id=waitlist_id,
    ).one()
    started_at = datetime.utcnow()
    lease_token = "f" * 64
    row.stan = "processing"
    row.liczba_prob = 1
    row.lease_token = lease_token
    row.lease_expires_at = started_at + timedelta(minutes=2)
    row.updated_at = started_at
    db.add(models.RezerwacjaWiadomoscProba(
        wiadomosc_id=row.id,
        numer=1,
        provider=row.provider,
        provider_idempotency_key=row.provider_idempotency_key,
        provider_supports_idempotency=row.provider_supports_idempotency,
        provider_idempotency_header=row.provider_idempotency_header,
        lease_token=lease_token,
        claimed_at=started_at,
        started_at=started_at,
        finished_at=None,
        wynik="processing",
    ))
    db.commit()

    withdrawn = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/wycofaj-oferte",
        json={"offer_version": 1},
    )
    assert withdrawn.status_code == 200, withdrawn.text
    fenced = _offer(
        admin_client,
        waitlist_id,
        [table_id],
        version=2,
        key="r6b2-fence-reoffer",
    )
    assert fenced.status_code == 409
    assert fenced.json()["code"] == "WAITLIST_DELIVERY_RECONCILIATION_REQUIRED"

    claim = communication.ClaimedMessage(
        id=row.id,
        attempt_number=1,
        lease_token=lease_token,
        channel=row.kanal,
        recipient=row.odbiorca,
        subject=row.temat,
        body=row.tresc,
        provider_idempotency_key=row.provider_idempotency_key,
        provider_supports_idempotency=bool(row.provider_supports_idempotency),
        provider_idempotency_header=row.provider_idempotency_header,
    )
    db.expire_all()
    assert communication.finalize_claim(
        claim,
        DeliveryResult("sent", "accepted"),
        now=datetime.utcnow(),
    ) is True
    db.expire_all()
    owner = db.get(models.ListaOczekujacych, waitlist_id)
    assert owner.status == "oczekuje"
    assert owner.powiadomiono_at is None
    row = db.get(models.RezerwacjaWiadomoscOutbox, row.id)
    attempt = db.query(models.RezerwacjaWiadomoscProba).filter_by(
        wiadomosc_id=row.id,
        numer=1,
    ).one()
    assert row.stan == "uncertain"
    assert row.sent_at is not None
    assert row.last_error_code == communication.WAITLIST_STALE_DELIVERED_CODE
    assert attempt.wynik == "sent"

    still_fenced = _offer(
        admin_client,
        waitlist_id,
        [table_id],
        version=2,
        key="r6b2-fence-reoffer",
    )
    assert still_fenced.status_code == 409
    assert still_fenced.json()["code"] == "WAITLIST_DELIVERY_RECONCILIATION_REQUIRED"

    communication.reconcile_uncertain(
        db,
        row,
        outcome="sent",
        note="Wyjaśniono gościowi nieaktualną wiadomość.",
        actor=admin,
        now=datetime.utcnow(),
    )
    db.commit()
    reoffered = _offer(
        admin_client,
        waitlist_id,
        [table_id],
        version=2,
        key="r6b2-fence-reoffer",
    )
    assert reoffered.status_code == 200, reoffered.text
    assert reoffered.json()["wpis"]["offer_version"] == 3
    assert reoffered.json()["wpis"]["powiadomiono_at"] is None


def test_started_idempotent_lease_recovery_stays_uncertain_until_reconciled(
    admin_client, admin, db,
):
    table_id = _table(admin_client, "R6B2-LEASE", 4)
    waitlist_id = _waitlist(admin_client)
    offered = _offer(
        admin_client, waitlist_id, [table_id], key="r6b2-lease-offer",
    )
    assert offered.status_code == 200, offered.text
    row = db.query(models.RezerwacjaWiadomoscOutbox).filter_by(
        waitlist_id=waitlist_id,
    ).one()
    started_at = datetime.utcnow() - timedelta(minutes=5)
    lease_token = "e" * 64
    row.stan = "processing"
    row.liczba_prob = 1
    row.provider_supports_idempotency = True
    row.provider_idempotency_header = "Idempotency-Key"
    row.lease_token = lease_token
    row.lease_expires_at = started_at + timedelta(seconds=1)
    row.updated_at = started_at
    db.add(models.RezerwacjaWiadomoscProba(
        wiadomosc_id=row.id,
        numer=1,
        provider=row.provider,
        provider_idempotency_key=row.provider_idempotency_key,
        provider_supports_idempotency=True,
        provider_idempotency_header="Idempotency-Key",
        lease_token=lease_token,
        claimed_at=started_at,
        started_at=started_at,
        finished_at=None,
        wynik="processing",
    ))
    db.commit()
    withdrawn = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/wycofaj-oferte",
        json={"offer_version": 1},
    )
    assert withdrawn.status_code == 200, withdrawn.text

    assert communication._recover_expired_leases(db, datetime.utcnow()) == 1
    db.commit()
    db.expire_all()
    row = db.get(models.RezerwacjaWiadomoscOutbox, row.id)
    assert row.stan == "uncertain"
    assert row.last_error_code == "LEASE_EXPIRED_SUPERSEDED_AMBIGUOUS"
    fenced = _offer(
        admin_client,
        waitlist_id,
        [table_id],
        version=2,
        key="r6b2-lease-reoffer",
    )
    assert fenced.status_code == 409
    assert fenced.json()["code"] == "WAITLIST_DELIVERY_RECONCILIATION_REQUIRED"

    communication.reconcile_uncertain(
        db,
        row,
        outcome="failed",
        note="Provider potwierdził brak dostarczenia.",
        actor=admin,
        now=datetime.utcnow(),
    )
    db.commit()
    reoffered = _offer(
        admin_client,
        waitlist_id,
        [table_id],
        version=2,
        key="r6b2-lease-reoffer",
    )
    assert reoffered.status_code == 200, reoffered.text
