"""R6b.1: jeden, wersjonowany snapshot operacyjny stanowiska hosta."""

from datetime import datetime, timedelta
import json

import factories
import main
import models
import reservation_communication as communication
from auth import create_access_token
from delivery_result import DeliveryResult


DAY = "2035-07-16"


def _headers(user):
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def _published_table(admin_client):
    room_response = admin_client.post(
        "/api/sale-rezerwacyjne",
        json={"nazwa": "Sala snapshotu", "aktywna": True, "kolejnosc": 0},
    )
    assert room_response.status_code == 201, room_response.text
    room = room_response.json()
    draft = admin_client.post(
        f"/api/sale-rezerwacyjne/{room['id']}/plan/szkic",
    ).json()
    created_response = admin_client.post(
        f"/api/sale-rezerwacyjne/{room['id']}/plan/szkic/stoliki",
        json={
            "expected_revision": draft["wersja"]["rewizja"],
            "nazwa": "P1",
            "pojemnosc": 4,
            "plan_x": 24,
            "plan_y": 36,
        },
    )
    assert created_response.status_code == 201, created_response.text
    created = created_response.json()
    table = next(row for row in created["stoliki"] if row["nazwa"] == "P1")
    published = admin_client.post(
        f"/api/sale-rezerwacyjne/{room['id']}/plan/publikuj",
        json={"expected_revision": created["wersja"]["rewizja"]},
    )
    assert published.status_code == 200, published.text
    return room, table


def _reservation(admin_client, table_id):
    response = admin_client.post(
        "/api/rezerwacje-stolik",
        json={
            "data": DAY,
            "godz_od": "18:00",
            "stolik_id": table_id,
            "liczba_osob": 3,
            "nazwisko": "Kowalska-Snapshot",
            "telefon": "600700800",
            "email": "snapshot@example.com",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_snapshot_ma_stabilny_kontrakt_i_jest_zgodny_ze_starymi_endpointami(
    admin_client,
):
    room, table = _published_table(admin_client)
    reservation = _reservation(admin_client, table["id"])

    # Nowy szkic nie moze wyciec do operacyjnego, published-only snapshotu.
    draft = admin_client.post(
        f"/api/sale-rezerwacyjne/{room['id']}/plan/szkic",
    ).json()
    draft_only = admin_client.post(
        f"/api/sale-rezerwacyjne/{room['id']}/plan/szkic/stoliki",
        json={
            "expected_revision": draft["wersja"]["rewizja"],
            "nazwa": "Tylko szkic",
            "pojemnosc": 2,
        },
    )
    assert draft_only.status_code == 201, draft_only.text

    response = admin_client.get(f"/api/host/snapshot?data={DAY}")
    assert response.status_code == 200, response.text
    body = response.json()

    assert set(body) == {
        "version",
        "schema_version",
        "data",
        "generated_at",
        "kolejka",
        "os_czasu",
        "plan_sali",
    }
    assert body["schema_version"] == main.HOST_SNAPSHOT_SCHEMA_VERSION == 1
    assert body["version"] == body["generated_at"]
    assert body["generated_at"].endswith("Z")
    assert datetime.fromisoformat(body["generated_at"].replace("Z", "+00:00")).tzinfo
    assert body["data"] == DAY

    assert body["kolejka"] == admin_client.get(
        f"/api/host/kolejka?data={DAY}",
    ).json()
    assert body["os_czasu"] == admin_client.get(
        f"/api/host/os-czasu?data={DAY}",
    ).json()
    assert body["plan_sali"] == admin_client.get(
        f"/api/plan-sali?data={DAY}",
    ).json()
    assert body["plan_sali"]["sala_id"] is None
    assert [row["id"] for row in body["plan_sali"]["stoliki"]] == [table["id"]]
    assert "Tylko szkic" not in response.text
    assert any(
        row["rezerwacja_id"] == reservation["id"]
        for row in body["os_czasu"]["zajetosci"]
    )

    assert response.headers["cache-control"] == "private, no-store"
    vary = {value.strip().casefold() for value in response.headers["vary"].split(",")}
    assert {"authorization", "cookie"} <= vary


def test_snapshot_stosuje_centralne_uprawnienie_hosta_i_redaguje_pii(
    admin_client,
    client,
    db,
):
    _, table = _published_table(admin_client)
    reservation = _reservation(admin_client, table["id"])
    waitlist = admin_client.post(
        "/api/lista-oczekujacych",
        json={
            "data": DAY,
            "godz_od": "19:00",
            "liczba_osob": 2,
            "nazwisko": "Waitlist-Sekret",
            "telefon": "500400300",
        },
    )
    assert waitlist.status_code == 201, waitlist.text
    termin = db.get(models.Termin, reservation["id"])
    db.add(models.ProfilGoscia(
        klucz_hash=main._crm_hash(termin),
        nazwisko="Profil-Sekret",
        alergie="orzechy-snapshot",
        tagi=["tag-snapshot"],
        vip=True,
    ))
    db.commit()

    host = factories.UserFactory(
        login="host_snapshot_no_pii",
        rola="szef",
        pracownik=None,
        uprawnienia_override={"rezerwacje.host": True},
    )
    response = client.get(
        f"/api/host/snapshot?data={DAY}",
        headers=_headers(host),
    )
    assert response.status_code == 200, response.text
    body = response.json()

    queue_row = body["kolejka"]["nadchodzace"][0]
    assert queue_row["nazwisko"] == "Gość"
    assert queue_row["telefon"] is None and queue_row["email"] is None
    assert queue_row["gosc"] == {
        "vip": True,
        "ma_alergie": None,
        "alergie": None,
        "okazja_typ": None,
        "okazja_data": None,
        "tagi": [],
        "dane_wrazliwe_ukryte": False,
    }
    assert body["kolejka"]["waitlista"][0]["nazwisko"] == "Gość"
    assert body["os_czasu"]["zajetosci"][0]["nazwisko"] == "Gość"
    assert body["plan_sali"]["stoliki"][0]["rezerwacje"][0]["nazwisko"] == "Gość"
    for secret in (
        "Kowalska-Snapshot",
        "600700800",
        "snapshot@example.com",
        "Waitlist-Sekret",
        "500400300",
        "Profil-Sekret",
        "orzechy-snapshot",
        "tag-snapshot",
    ):
        assert secret not in response.text

    operations_only = factories.UserFactory(
        login="snapshot_operations_only",
        rola="szef",
        pracownik=None,
        uprawnienia_override={"rezerwacje.operacje": True},
    )
    denied = client.get(
        f"/api/host/snapshot?data={DAY}",
        headers=_headers(operations_only),
    )
    assert denied.status_code == 403


def test_snapshot_daje_host_contact_osobny_terminalny_inbox_komunikacji(
    admin_client,
    client,
    db,
):
    _, table = _published_table(admin_client)
    waitlist = admin_client.post(
        "/api/lista-oczekujacych",
        json={
            "data": DAY,
            "godz_od": "20:00",
            "liczba_osob": 2,
            "nazwisko": "Waitlist-Attention",
            "telefon": "500111222",
            "kanal_komunikacji": "sms",
        },
    )
    assert waitlist.status_code == 201, waitlist.text
    waitlist_id = waitlist.json()["id"]
    offered = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/oferta",
        headers={"Idempotency-Key": "host-snapshot-terminal-attention"},
        json={
            "stolik_id": table["id"],
            "minuty": 30,
            "expected_offer_version": 0,
        },
    )
    assert offered.status_code == 200, offered.text
    message = db.query(models.RezerwacjaWiadomoscOutbox).filter_by(
        waitlist_id=waitlist_id,
        typ_zdarzenia="table_ready",
    ).one()
    started_at = datetime.utcnow()
    lease_token = "a" * 64
    message.stan = "processing"
    message.liczba_prob = 1
    message.lease_token = lease_token
    message.lease_expires_at = started_at + timedelta(minutes=2)
    message.updated_at = started_at
    db.add(models.RezerwacjaWiadomoscProba(
        wiadomosc_id=message.id,
        numer=1,
        provider=message.provider,
        provider_idempotency_key=message.provider_idempotency_key,
        provider_supports_idempotency=message.provider_supports_idempotency,
        provider_idempotency_header=message.provider_idempotency_header,
        lease_token=lease_token,
        claimed_at=started_at,
        started_at=started_at,
        wynik="processing",
    ))
    db.commit()

    cancelled = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/anuluj",
        json={"expected_offer_version": 1},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "anulowano"

    claim = communication.ClaimedMessage(
        id=message.id,
        attempt_number=1,
        lease_token=lease_token,
        channel=message.kanal,
        recipient=message.odbiorca,
        subject=message.temat,
        body=message.tresc,
        provider_idempotency_key=message.provider_idempotency_key,
        provider_supports_idempotency=bool(message.provider_supports_idempotency),
        provider_idempotency_header=message.provider_idempotency_header,
    )
    finalized_at = datetime.utcnow()
    assert communication.finalize_claim(
        claim,
        DeliveryResult("sent", "PROVIDER_ACCEPTED", provider_message_id="provider-1"),
        now=finalized_at,
    ) is True
    db.expire_all()
    message = db.get(models.RezerwacjaWiadomoscOutbox, message.id)
    attempt = db.query(models.RezerwacjaWiadomoscProba).filter_by(
        wiadomosc_id=message.id,
        numer=1,
    ).one()
    assert message.stan == "uncertain"
    assert message.sent_at == finalized_at
    assert message.last_error_code == communication.WAITLIST_STALE_DELIVERED_CODE
    assert attempt.wynik == "sent"
    detected = db.query(models.AuditLog).filter_by(
        akcja="waitlist_stale_delivery_detected",
        zasob=f"message:{message.id}",
    ).one()
    assert json.loads(detected.szczegoly) == {
        "provider_outcome": "sent",
        "relevance_error": "MESSAGE_OWNER_NOT_CURRENT",
        "waitlist_id": waitlist_id,
    }

    host_contact = factories.UserFactory(
        login="host_snapshot_contact_only",
        rola="szef",
        pracownik=None,
        uprawnienia_override={
            "rezerwacje.host": True,
            "rezerwacje.operacje": False,
            "rezerwacje.dane_kontaktowe": True,
        },
    )
    contact_headers = _headers(host_contact)
    visible = client.get(
        f"/api/host/snapshot?data={DAY}",
        headers=contact_headers,
    )
    assert visible.status_code == 200, visible.text
    queue = visible.json()["kolejka"]
    assert queue["waitlista"] == []
    assert queue["podsumowanie"]["waitlista"] == 0
    assert queue["komunikacja_waitlist"] == [{
        "id": waitlist_id,
        "nazwisko": "Waitlist-Attention",
        "status": "anulowano",
        "communication_summary": queue["komunikacja_waitlist"][0]["communication_summary"],
    }]
    assert queue["komunikacja_waitlist"][0]["communication_summary"]["attention_required"] is True

    history = client.get(
        f"/api/lista-oczekujacych/{waitlist_id}/komunikacja",
        headers=contact_headers,
    )
    assert history.status_code == 200, history.text
    history_message = history.json()["messages"][0]
    assert history_message["state"] == "uncertain"
    assert history_message["attention_required"] is True
    assert history_message["retry_allowed"] is False
    assert history_message["sent_at"] == finalized_at.isoformat()
    assert history_message["last_error_code"] == communication.WAITLIST_STALE_DELIVERED_CODE
    assert history_message["attempts"][0]["state"] == "sent"

    host_without_contact = factories.UserFactory(
        login="host_snapshot_without_contact",
        rola="szef",
        pracownik=None,
        uprawnienia_override={
            "rezerwacje.host": True,
            "rezerwacje.operacje": False,
            "rezerwacje.dane_kontaktowe": False,
        },
    )
    hidden_headers = _headers(host_without_contact)
    hidden = client.get(
        f"/api/host/snapshot?data={DAY}",
        headers=hidden_headers,
    )
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()["kolejka"]["komunikacja_waitlist"] == []
    assert "Waitlist-Attention" not in hidden.text
    assert client.get(
        f"/api/lista-oczekujacych/{waitlist_id}/komunikacja",
        headers=hidden_headers,
    ).status_code == 403

    reconciled = client.post(
        f"/api/rezerwacje/komunikacja/{message.id}/reconcile",
        headers=contact_headers,
        json={"wynik": "sent", "notatka": "Potwierdzone u dostawcy"},
    )
    assert reconciled.status_code == 200, reconciled.text
    assert reconciled.json()["state"] == "sent"
    assert reconciled.json()["sent_at"] == finalized_at.isoformat()
    reconcile_audit = db.query(models.AuditLog).filter_by(
        akcja="rezerwacje_komunikacja_reconcile",
        zasob=f"message:{message.id}",
    ).one()
    assert json.loads(reconcile_audit.szczegoly) == {
        "outcome": "sent",
        "previous_error_code": communication.WAITLIST_STALE_DELIVERED_CODE,
        "stale_delivery_acknowledged": True,
    }
    after = client.get(
        f"/api/host/snapshot?data={DAY}",
        headers=contact_headers,
    )
    assert after.status_code == 200, after.text
    assert after.json()["kolejka"]["komunikacja_waitlist"] == []
