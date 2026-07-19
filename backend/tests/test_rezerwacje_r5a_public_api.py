"""Integracyjny kontrakt publicznego widgetu rezerwacji R5a.

Testy przechodza przez HTTP i sprawdzaja trwale skutki w ledgerze, bez omijania
publicznego kontraktu endpointow. Daty sa wyliczane wzgledem dnia uruchomienia,
wiec zestaw nie starzeje sie wraz z kalendarzem.
"""

import json
from datetime import date, time, timedelta

from sqlalchemy import text

import main
import models
import reservation_communication as communication
import reservation_service
from crm_identity import identity_hash


SESSION_A = "r5a-browser-session-0001"
SESSION_B = "r5a-browser-session-0002"
HOLD_KEY = "r5a-public-hold-0001"
CREATE_KEY = "r5a-public-create-0001"


def _booking_date(offset=21):
    return date.today() + timedelta(days=offset)


def _enable_v2(admin_client):
    response = admin_client.put(
        "/api/lokal/config",
        json={
            "rezerwacje_online": True,
            "rezerwacje_widget_v2": True,
            "rezerwacje_auto_potwierdzenie": False,
            "rezerwacje_rodo_kontakt": "rodo@lokalo.test",
            "rezerwacje_rodo_adres": "ul. Testowa 1, 00-001 Warszawa",
            "rezerwacje_retencja_dni": 180,
        },
    )
    assert response.status_code == 200, response.text


def _widget_config(client):
    response = client.get("/api/online/widget-config")
    assert response.status_code == 200, response.text
    return response.json()


def _privacy_payload(config, sensitive_data=None):
    payload = {
        "privacy_notice_acknowledged": True,
        "privacy_notice_version": config["privacy"]["notice_version"],
        # Odmowa marketingu jest swiadomym, wersjonowanym wyborem.
        "marketing_consent": False,
        "marketing_consent_version": config["marketing"]["version"],
        "sensitive_data_consent": bool(sensitive_data),
    }
    if sensitive_data:
        payload.update({
            "sensitive_data": sensitive_data,
            "sensitive_data_consent_version": config["sensitive"]["version"],
        })
    return payload


def _prepare_multi_table_inventory(admin_client, booking_date):
    service = admin_client.post(
        "/api/godziny-otwarcia",
        json={
            "dzien_tygodnia": booking_date.weekday(),
            "godz_od": "12:00",
            "godz_do": "22:00",
            "krok_slotu_min": 60,
            "domyslny_turn_time_min": 120,
        },
    )
    assert service.status_code == 201, service.text

    table_ids = []
    for suffix in ("A", "B"):
        response = admin_client.post(
            "/api/stoliki",
            json={"nazwa": "R5a-" + suffix, "pojemnosc": 2},
        )
        assert response.status_code == 201, response.text
        table_ids.append(response.json()["id"])

    combination = admin_client.post(
        "/api/kombinacje",
        json={
            "nazwa": "R5a 2+2",
            "stoliki": table_ids,
            "pojemnosc_min": 3,
            "pojemnosc_max": 4,
            "priorytet": 1,
        },
    )
    assert combination.status_code == 201, combination.text
    return table_ids


def _create_hold(client, booking_date, session=SESSION_A, key=HOLD_KEY):
    response = client.post(
        "/api/online/hold",
        json={
            "data": booking_date.isoformat(),
            "godz_od": "18:00",
            "liczba_osob": 4,
        },
        headers={
            "X-Reservation-Session": session,
            "Idempotency-Key": key,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _reservation_payload(booking_date, config, party_size=4):
    return {
        "data": booking_date.isoformat(),
        "godz_od": "18:00",
        "liczba_osob": party_size,
        "nazwisko": "Gosc R5a",
        "telefon": "+48 600 700 800",
        "email": "gosc-r5a@example.test",
        "notatka": "Stolik z miejscem na wozek.",
        **_privacy_payload(config, "Silna alergia na orzechy."),
    }


def test_widget_v2_exposes_ready_versioned_privacy_contract(admin_client, client):
    _enable_v2(admin_client)

    config = _widget_config(client)

    assert config["version"] == 2
    assert config["ready"] is True
    assert config["hold_ttl_seconds"] > 0
    assert config["privacy"]["notice_version"] == main.PUBLIC_PRIVACY_NOTICE_VERSION
    assert config["privacy"]["contact"] == "rodo@lokalo.test"
    assert config["privacy"]["address"] == "ul. Testowa 1, 00-001 Warszawa"
    assert config["privacy"]["retention_days"] == 180
    assert config["privacy"]["notice_text"]
    assert config["marketing"] == {
        "version": main.PUBLIC_MARKETING_CONSENT_VERSION,
        "label": config["marketing"]["label"],
        "optional": True,
    }
    assert config["sensitive"]["version"] == main.PUBLIC_SENSITIVE_CONSENT_VERSION
    assert config["sensitive"]["optional"] is True


def test_hold_create_transfers_every_table_and_keeps_tokens_hash_only(
    admin_client, client, db,
):
    _enable_v2(admin_client)
    config = _widget_config(client)
    booking_date = _booking_date()
    table_ids = _prepare_multi_table_inventory(admin_client, booking_date)

    hold_body = _create_hold(client, booking_date)
    hold_token = hold_body["hold_token"]
    hold = db.query(models.RezerwacjaPublicznyHold).one()
    assert hold.state == "active"
    assert hold.token_hash == reservation_service.hash_public_hold_token(
        hold_token, secret=main.SECRET_KEY,
    )
    assert hold.token_hash != hold_token
    assert {hold.stolik_id, *(hold.stoliki_dodatkowe or [])} == set(table_ids)
    hold_claims = db.query(models.RezerwacjaStolikClaim).filter_by(
        public_hold_id=hold.id,
    ).all()
    assert hold_claims
    assert {claim.stolik_id for claim in hold_claims} == set(table_ids)
    assert all(claim.termin_id is None for claim in hold_claims)

    payload = _reservation_payload(booking_date, config)
    headers = {
        "X-Reservation-Session": SESSION_A,
        "X-Reservation-Hold": hold_token,
        "Idempotency-Key": CREATE_KEY,
    }
    created = client.post("/api/online/rezerwacja", json=payload, headers=headers)
    assert created.status_code == 201, created.text
    created_body = created.json()
    management_token = created_body["management_token"]
    assert created_body["token"] == management_token
    assert "token" not in created_body["rezerwacja"]
    assert created_body["rezerwacja"]["stolik"] is None

    # Idempotentny retry odtwarza credential deterministycznie bez duplikowania wizyty.
    replayed = client.post("/api/online/rezerwacja", json=payload, headers=headers)
    assert replayed.status_code == 201, replayed.text
    assert replayed.json()["management_token"] == management_token
    assert db.query(models.Termin).filter_by(kanal="online").count() == 1

    db.expire_all()
    termin = db.query(models.Termin).filter_by(kanal="online").one()
    hold = db.get(models.RezerwacjaPublicznyHold, hold.id)
    assert termin.token_potwierdzenia is None
    assert {termin.stolik_id, *(termin.stoliki_dodatkowe or [])} == set(table_ids)
    assert hold.state == "consumed"
    assert hold.termin_id == termin.id
    assert db.query(models.RezerwacjaStolikClaim).filter_by(
        public_hold_id=hold.id,
    ).count() == 0
    termin_claims = db.query(models.RezerwacjaStolikClaim).filter_by(
        termin_id=termin.id,
    ).all()
    assert termin_claims
    assert {claim.stolik_id for claim in termin_claims} == set(table_ids)
    assert all(
        claim.public_hold_id is None
        and claim.waitlist_id is None
        and claim.expires_at is None
        for claim in termin_claims
    )

    token_row = db.query(models.RezerwacjaTokenZarzadzania).one()
    assert token_row.token_hash == reservation_service.hash_management_token(
        management_token, secret=main.SECRET_KEY,
    )
    assert token_row.token_hash != management_token
    idempotency = db.query(models.RezerwacjaIdempotencja).one()
    cached_response = json.loads(idempotency.response_enc)
    assert "token" not in cached_response
    assert "management_token" not in cached_response
    assert management_token not in idempotency.response_enc
    raw_cache = db.execute(
        text("SELECT response_enc FROM rezerwacje_idempotencja WHERE id=:id"),
        {"id": idempotency.id},
    ).scalar_one()
    assert management_token not in str(raw_cache)

    consent = db.query(models.RezerwacjaZgodaPubliczna).filter_by(
        termin_id=termin.id,
    ).one()
    assert consent.notice_version == config["privacy"]["notice_version"]
    assert consent.marketing is False
    assert consent.marketing_version == config["marketing"]["version"]
    assert consent.sensitive is True
    assert consent.sensitive_version == config["sensitive"]["version"]
    assert consent.sensitive_data == "Silna alergia na orzechy."
    assert consent.retention_until.date() == booking_date + timedelta(days=180)
    raw_sensitive = db.execute(
        text("SELECT sensitive_data FROM rezerwacje_zgody_publiczne WHERE id=:id"),
        {"id": consent.id},
    ).scalar_one()
    assert "Silna alergia na orzechy." not in str(raw_sensitive)

    public_view = client.get(
        "/api/online/zarzadzanie/rezerwacja",
        headers={"X-Reservation-Token": management_token},
    )
    assert public_view.status_code == 200, public_view.text
    assert "telefon" not in public_view.json()
    assert "email" not in public_view.json()
    assert "notatka" not in public_view.json()

    confirm_headers = {
        "X-Reservation-Token": management_token,
        "Idempotency-Key": "r5a-confirm-operation-0001",
    }
    confirmed = client.post(
        "/api/online/zarzadzanie/potwierdz", headers=confirm_headers,
    )
    assert confirmed.status_code == 200, confirmed.text
    rotated_token = confirmed.json()["management_token"]
    assert rotated_token != management_token
    retry = client.post(
        "/api/online/zarzadzanie/potwierdz", headers=confirm_headers,
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["management_token"] == rotated_token
    assert db.query(models.RezerwacjaTokenZarzadzania).count() == 2

    exported = client.get(
        "/api/online/zarzadzanie/dane",
        headers={"X-Reservation-Token": rotated_token},
    )
    assert exported.status_code == 200, exported.text
    export_body = exported.json()
    assert export_body["rezerwacja"]["telefon"] == "+48 600 700 800"
    assert export_body["rezerwacja"]["email"] == "gosc-r5a@example.test"
    assert export_body["rezerwacja"]["kanal_komunikacji"] == "auto"
    assert len(export_body["prywatnosc"]) == 1
    assert export_body["prywatnosc"][0]["marketing"] is False
    assert export_body["prywatnosc"][0]["sensitive_data"] == "Silna alergia na orzechy."
    communication_history = export_body["komunikacja_operacyjna"]
    assert communication_history
    assert communication_history[0]["typ"] == "confirmation"
    assert communication_history[0]["odbiorca"] == "gosc-r5a@example.test"
    assert communication_history[0]["tresc"]
    assert all(secret_field not in exported.text for secret_field in (
        "provider_idempotency_key", "provider_idempotency_header", "lease_token",
        "subject_phone_ref", "subject_email_ref",
    ))

    db.add_all([
        models.ProfilGoscia(
            klucz_hash=identity_hash(termin),
            nazwisko=termin.nazwisko,
            telefon=termin.telefon,
            email=termin.email,
            alergie="Silna alergia na orzechy.",
            notatka="Poufny profil utworzony przez managera.",
        ),
        models.KpZadatek(
            id="r5a-self-delete-kp",
            kwota=100.0,
            opis="Zadatek od Gosc R5a",
            data=date.today(),
            nazwisko="Gosc R5a",
            termin_id=termin.id,
        ),
        models.WiadomoscImprezy(
            termin_id=termin.id,
            autor="klient",
            tresc="Poufne ustalenia rezerwacji",
            utworzono_at=main.utcnow_naive(),
        ),
    ])
    db.commit()

    delete_headers = {
        "X-Reservation-Token": rotated_token,
        "Idempotency-Key": "r5a-delete-data-operation-0001",
    }
    deleted = client.post(
        "/api/online/zarzadzanie/dane/usun",
        json={"potwierdz": True},
        headers=delete_headers,
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"status": "usuniete"}
    delete_retry = client.post(
        "/api/online/zarzadzanie/dane/usun",
        json={"potwierdz": True},
        headers=delete_headers,
    )
    assert delete_retry.status_code == 200, delete_retry.text
    assert delete_retry.json() == {"status": "usuniete"}

    db.expire_all()
    termin = db.get(models.Termin, termin.id)
    assert termin.status == "odwolana"
    assert termin.nazwisko == "[anonimizacja RODO]"
    assert termin.telefon is None
    assert termin.email is None
    assert termin.notatka is None
    assert db.query(models.RezerwacjaZgodaPubliczna).filter_by(
        termin_id=termin.id,
    ).count() == 0
    assert db.query(models.RezerwacjaIdempotencja).filter_by(
        termin_id=termin.id,
    ).count() == 0
    assert db.query(models.RezerwacjaPublicznyHold).filter_by(
        termin_id=termin.id,
    ).count() == 0
    assert db.query(models.ProfilGoscia).count() == 0
    zadatek = db.get(models.KpZadatek, "r5a-self-delete-kp")
    assert zadatek.nazwisko is None
    assert zadatek.opis == "[anonimizacja RODO]"
    assert db.query(models.WiadomoscImprezy).filter_by(
        termin_id=termin.id,
    ).count() == 0
    assert db.query(models.RezerwacjaStolikClaim).filter_by(
        termin_id=termin.id,
    ).count() == 0
    token_rows = db.query(models.RezerwacjaTokenZarzadzania).filter_by(
        termin_id=termin.id,
    ).all()
    assert len(token_rows) == 2
    assert all(row.revoked_at is not None for row in token_rows)
    assert client.get(
        "/api/online/zarzadzanie/dane",
        headers={"X-Reservation-Token": rotated_token},
    ).status_code == 410


def test_public_self_delete_returns_safe_conflict_while_delivery_is_processing(
    admin_client,
    client,
    db,
):
    _enable_v2(admin_client)
    config = _widget_config(client)
    booking_date = _booking_date(23)
    _prepare_multi_table_inventory(admin_client, booking_date)
    hold_token = _create_hold(
        client,
        booking_date,
        key="r5b-rodo-processing-hold-0001",
    )["hold_token"]
    created = client.post(
        "/api/online/rezerwacja",
        json=_reservation_payload(booking_date, config),
        headers={
            "X-Reservation-Session": SESSION_A,
            "X-Reservation-Hold": hold_token,
            "Idempotency-Key": "r5b-rodo-processing-create-0001",
        },
    )
    assert created.status_code == 201, created.text
    management_token = created.json()["management_token"]
    message = db.query(models.RezerwacjaWiadomoscOutbox).filter_by(
        typ_zdarzenia="confirmation",
    ).one()
    claim = communication.claim_next(now=main.utcnow_naive())
    assert claim.id == message.id
    assert communication.mark_claim_started(
        claim,
        now=main.utcnow_naive(),
    ) is not None

    response = client.post(
        "/api/online/zarzadzanie/dane/usun",
        json={"potwierdz": True},
        headers={
            "X-Reservation-Token": management_token,
            "Idempotency-Key": "r5b-rodo-processing-delete-0001",
        },
    )

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "COMMUNICATION_DELIVERY_IN_PROGRESS"
    assert "gosc-r5a@example.test" not in response.text
    assert "+48 600 700 800" not in response.text
    # The failed erasure transaction must not consume/rotate the capability.
    retry_export = client.get(
        "/api/online/zarzadzanie/dane",
        headers={"X-Reservation-Token": management_token},
    )
    assert retry_export.status_code == 200, retry_export.text
    db.expire_all()
    termin = db.query(models.Termin).filter_by(kanal="online").one()
    assert termin.nazwisko == "Gosc R5a"
    assert db.get(models.RezerwacjaWiadomoscOutbox, message.id).stan == "processing"


def test_public_data_export_is_capability_and_current_snapshot_scoped(
    admin_client,
    client,
    db,
):
    _enable_v2(admin_client)
    now = main.utcnow_naive()
    visit_date = _booking_date(24)
    old_contact = {
        "telefon": "+48 600 111 222",
        "email": "old-owner@example.test",
    }
    shared_contact = {
        "telefon": "+48 700 333 444",
        "email": "shared-owner@example.test",
    }

    reservation_a = models.Termin(
        data=visit_date,
        godz_od=time(18, 0),
        nazwisko="Capability A",
        liczba_osob=2,
        **old_contact,
        kanal_komunikacji="email",
        status="potwierdzona",
        rodzaj="stolik",
        kanal="online",
        utworzono_at=now,
    )
    reservation_b = models.Termin(
        data=visit_date + timedelta(days=1),
        godz_od=time(19, 0),
        nazwisko="Capability B",
        liczba_osob=3,
        **shared_contact,
        kanal_komunikacji="email",
        status="potwierdzona",
        rodzaj="stolik",
        kanal="online",
        utworzono_at=now,
    )
    db.add_all([reservation_a, reservation_b])
    db.flush()

    historical_a = communication.enqueue_reservation(
        db,
        reservation_a,
        "confirmation",
        dedupe_key="capability-export-historical-a",
        available_at=now + timedelta(hours=1),
        expires_at=now + timedelta(days=1),
    )[0]
    other_owner = communication.enqueue_reservation(
        db,
        reservation_b,
        "confirmation",
        dedupe_key="capability-export-other-owner",
        available_at=now + timedelta(hours=1),
        expires_at=now + timedelta(days=1),
    )[0]

    reservation_a.telefon = shared_contact["telefon"]
    reservation_a.email = shared_contact["email"]
    current_a = communication.enqueue_reservation(
        db,
        reservation_a,
        "change",
        dedupe_key="capability-export-current-a",
        available_at=now + timedelta(hours=1),
        expires_at=now + timedelta(days=1),
    )[0]
    issued = reservation_service.create_management_token(
        db,
        termin_id=reservation_a.id,
        scopes=("data:export",),
        secret=main.SECRET_KEY,
        now=now,
        idempotency_key="capability-export-token-a",
    )
    db.commit()
    historical_a_id = historical_a.id
    other_owner_id = other_owner.id
    current_a_id = current_a.id

    exported = client.get(
        "/api/online/zarzadzanie/dane",
        headers={"X-Reservation-Token": issued.raw_token},
    )

    assert exported.status_code == 200, exported.text
    history = exported.json()["komunikacja_operacyjna"]
    assert {entry["wiadomosc_id"] for entry in history} == {current_a_id}
    assert {entry["wlasciciel_id"] for entry in history} == {reservation_a.id}
    assert history[0]["odbiorca"] == shared_contact["email"]
    assert historical_a_id not in {entry["wiadomosc_id"] for entry in history}
    assert other_owner_id not in {entry["wiadomosc_id"] for entry in history}


def test_admin_delete_public_booking_removes_r5a_secrets_and_idempotency(
    admin_client, client, db,
):
    _enable_v2(admin_client)
    config = _widget_config(client)
    booking_date = _booking_date(24)
    _prepare_multi_table_inventory(admin_client, booking_date)
    hold_token = _create_hold(
        client,
        booking_date,
        key="r5a-admin-delete-hold-0001",
    )["hold_token"]
    created = client.post(
        "/api/online/rezerwacja",
        json=_reservation_payload(booking_date, config),
        headers={
            "X-Reservation-Session": SESSION_A,
            "X-Reservation-Hold": hold_token,
            "Idempotency-Key": "r5a-admin-delete-create-0001",
        },
    )
    assert created.status_code == 201, created.text
    termin = db.query(models.Termin).filter_by(kanal="online").one()
    termin_id = termin.id
    assert db.query(models.RezerwacjaPublicznyHold).filter_by(
        termin_id=termin.id,
    ).count() == 1
    assert db.query(models.RezerwacjaIdempotencja).filter_by(
        termin_id=termin.id,
    ).count() == 1

    deleted = admin_client.delete(f"/api/rezerwacje-stolik/{termin_id}")

    assert deleted.status_code == 204, deleted.text
    db.expire_all()
    assert db.get(models.Termin, termin_id) is None
    assert db.query(models.RezerwacjaPublicznyHold).count() == 0
    assert db.query(models.RezerwacjaZgodaPubliczna).count() == 0
    assert db.query(models.RezerwacjaTokenZarzadzania).count() == 0
    assert db.query(models.RezerwacjaIdempotencja).count() == 0


def test_v2_rejects_session_notice_and_hold_payload_mismatches_without_consuming(
    admin_client, client, db,
):
    _enable_v2(admin_client)
    config = _widget_config(client)
    booking_date = _booking_date(28)
    _prepare_multi_table_inventory(admin_client, booking_date)
    hold_body = _create_hold(client, booking_date)
    hold_token = hold_body["hold_token"]
    base_payload = _reservation_payload(booking_date, config)

    # Sekret w JSON jest ignorowany i bez właściwego capability headera nie daje
    # dostępu do holdu ani nie trafia do fingerprintu idempotencji.
    body_only = client.post(
        "/api/online/rezerwacja",
        json={**base_payload, "hold_token": hold_token},
        headers={
            "X-Reservation-Session": SESSION_A,
            "Idempotency-Key": "r5a-body-hold-rejected-0001",
        },
    )
    assert body_only.status_code == 400, body_only.text

    wrong_session = client.post(
        "/api/online/rezerwacja",
        json=base_payload,
        headers={
            "X-Reservation-Session": SESSION_B,
            "X-Reservation-Hold": hold_token,
            "Idempotency-Key": "r5a-wrong-session-0001",
        },
    )
    assert wrong_session.status_code == 404, wrong_session.text

    stale_notice = dict(base_payload)
    stale_notice["privacy_notice_version"] = "reservation-privacy-stale"
    stale = client.post(
        "/api/online/rezerwacja",
        json=stale_notice,
        headers={
            "X-Reservation-Session": SESSION_A,
            "X-Reservation-Hold": hold_token,
            "Idempotency-Key": "r5a-stale-notice-0001",
        },
    )
    assert stale.status_code == 409, stale.text

    mismatched_payload = _reservation_payload(booking_date, config, party_size=3)
    mismatch = client.post(
        "/api/online/rezerwacja",
        json=mismatched_payload,
        headers={
            "X-Reservation-Session": SESSION_A,
            "X-Reservation-Hold": hold_token,
            "Idempotency-Key": "r5a-hold-payload-mismatch-0001",
        },
    )
    assert mismatch.status_code == 409, mismatch.text

    db.expire_all()
    hold = db.query(models.RezerwacjaPublicznyHold).one()
    assert hold.state == "active"
    assert hold.termin_id is None
    assert db.query(models.RezerwacjaStolikClaim).filter_by(
        public_hold_id=hold.id,
    ).count() > 0
    assert db.query(models.Termin).filter_by(kanal="online").count() == 0


def test_waitlist_v2_records_declined_marketing_without_issuing_token(
    admin_client, client, db,
):
    _enable_v2(admin_client)
    config = _widget_config(client)
    booking_date = _booking_date(35)
    payload = {
        "data": booking_date.isoformat(),
        "godz_od": "19:00",
        "liczba_osob": 4,
        "nazwisko": "Gosc waitlist R5a",
        "telefon": "+48 500 600 700",
        "email": "waitlist-r5a@example.test",
        **_privacy_payload(config),
    }

    response = client.post(
        "/api/online/lista-oczekujacych",
        json=payload,
        headers={
            "X-Reservation-Session": SESSION_A,
            "Idempotency-Key": "r72-waitlist-create-r5a-0001",
        },
    )

    assert response.status_code == 201, response.text
    assert "token" not in json.dumps(response.json())
    waitlist = db.query(models.ListaOczekujacych).one()
    assert waitlist.kanal == "online"
    assert waitlist.token is None
    consent = db.query(models.RezerwacjaZgodaPubliczna).one()
    assert consent.termin_id is None
    assert consent.waitlist_id == waitlist.id
    assert consent.notice_version == config["privacy"]["notice_version"]
    assert consent.marketing is False
    assert consent.marketing_version == config["marketing"]["version"]
    assert consent.sensitive is False
    assert consent.sensitive_data is None
