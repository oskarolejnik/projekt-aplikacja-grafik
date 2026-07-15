"""Integracyjne kontrakty atomowego zapisu rezerwacji R0b.

Te testy przechodzą przez publiczne API, a następnie sprawdzają trwały ledger. Dzięki
temu chronią nie tylko komunikat HTTP, lecz także brak bocznych ścieżek omijających
alokację, pacing, idempotencję albo zwolnienie zasobu.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

import models


BOOKING_DATE = date.today() + timedelta(days=30)


def _stolik(admin_client, nazwa: str = "S1", pojemnosc: int = 8) -> int:
    response = admin_client.post(
        "/api/stoliki",
        json={"nazwa": nazwa, "pojemnosc": pojemnosc},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _manual_body(
    table_id: int,
    *,
    nazwisko: str = "Gość ręczny",
    godz_od: str = "18:00",
    osoby: int = 2,
) -> dict:
    return {
        "data": BOOKING_DATE.isoformat(),
        "godz_od": godz_od,
        "stolik_id": table_id,
        "liczba_osob": osoby,
        "nazwisko": nazwisko,
    }


def _manual_create(admin_client, table_id: int, **kwargs):
    return admin_client.post(
        "/api/rezerwacje-stolik",
        json=_manual_body(table_id, **kwargs),
    )


def _enable_online(admin_client) -> None:
    response = admin_client.put(
        "/api/lokal/config",
        json={"rezerwacje_online": True},
    )
    assert response.status_code == 200, response.text


def _serwis(
    admin_client,
    *,
    max_rezerwacji: int | None = None,
    max_osob: int | None = None,
) -> None:
    response = admin_client.post(
        "/api/godziny-otwarcia",
        json={
            "dzien_tygodnia": BOOKING_DATE.weekday(),
            "godz_od": "12:00",
            "godz_do": "22:00",
            "ostatni_zasiadek": "20:00",
            "dlugosc_slotu_min": 120,
            "pacing_max_rez": max_rezerwacji,
            "pacing_max_osob": max_osob,
            "pacing_okno_min": 120,
        },
    )
    assert response.status_code == 201, response.text


def _online_create(
    client,
    *,
    nazwisko: str,
    osoby: int = 2,
    godz_od: str = "18:00",
    headers: dict | None = None,
):
    return client.post(
        "/api/online/rezerwacja",
        json={
            "data": BOOKING_DATE.isoformat(),
            "godz_od": godz_od,
            "liczba_osob": osoby,
            "nazwisko": nazwisko,
        },
        headers=headers,
    )


def _fresh(db) -> None:
    """Kończy ewentualny stary snapshot sesji używanej do asercji."""

    db.rollback()
    db.expire_all()


def _ledger_counts(db, termin_id: int) -> tuple[int, int]:
    _fresh(db)
    table_claims = db.query(models.RezerwacjaStolikClaim).filter_by(
        termin_id=termin_id,
    ).count()
    pacing_rows = db.query(models.RezerwacjaPacingLedger).filter_by(
        termin_id=termin_id,
    ).count()
    return table_claims, pacing_rows


def _assert_conflict(response, code: str, rule: str) -> dict:
    assert response.status_code == 409, response.text
    payload = response.json()
    assert payload["detail"]
    assert payload["code"] == code
    availability = payload["availability"]
    assert availability["available"] is False
    assert availability["code"] == code
    assert availability["rule"] == rule
    assert isinstance(availability["candidates"], list)
    assert isinstance(availability["alternatives"], list)
    return payload


def test_manual_idempotency_replays_exact_result_once(admin_client, db):
    table_id = _stolik(admin_client)
    body = _manual_body(table_id, nazwisko="Idempotentna Anna")
    headers = {"Idempotency-Key": "manual-create-anna-001"}

    first = admin_client.post("/api/rezerwacje-stolik", json=body, headers=headers)
    second = admin_client.post("/api/rezerwacje-stolik", json=body, headers=headers)

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert second.json() == first.json()

    _fresh(db)
    reservations = db.query(models.Termin).filter_by(
        rodzaj="stolik",
        data=BOOKING_DATE,
    ).all()
    idempotency = db.query(models.RezerwacjaIdempotencja).all()
    assert [reservation.id for reservation in reservations] == [first.json()["id"]]
    assert len(idempotency) == 1
    assert idempotency[0].status == "succeeded"
    assert idempotency[0].termin_id == first.json()["id"]
    assert idempotency[0].response_enc
    assert idempotency[0].key_hash != headers["Idempotency-Key"]


def test_manual_idempotency_rejects_key_reuse_with_other_request(admin_client, db):
    table_id = _stolik(admin_client)
    headers = {"Idempotency-Key": "manual-create-reuse-001"}
    first = admin_client.post(
        "/api/rezerwacje-stolik",
        json=_manual_body(table_id, nazwisko="Pierwsza treść", godz_od="18:00"),
        headers=headers,
    )
    assert first.status_code == 201, first.text

    reused = admin_client.post(
        "/api/rezerwacje-stolik",
        json=_manual_body(table_id, nazwisko="Inna treść", godz_od="20:00"),
        headers=headers,
    )
    _assert_conflict(reused, "IDEMPOTENCY_KEY_REUSED", "idempotency")

    _fresh(db)
    assert db.query(models.Termin).filter_by(
        rodzaj="stolik",
        data=BOOKING_DATE,
    ).count() == 1
    assert db.query(models.RezerwacjaIdempotencja).count() == 1


def test_manual_table_conflict_has_stable_availability_contract(admin_client, db):
    table_id = _stolik(admin_client)
    first = _manual_create(admin_client, table_id, nazwisko="Pierwsza")
    assert first.status_code == 201, first.text

    conflict = _manual_create(
        admin_client,
        table_id,
        nazwisko="Nachodząca",
        godz_od="19:00",
    )
    _assert_conflict(conflict, "TABLE_CONFLICT", "table")

    _fresh(db)
    assert db.query(models.Termin).filter_by(
        rodzaj="stolik",
        data=BOOKING_DATE,
    ).count() == 1
    assert _ledger_counts(db, first.json()["id"]) == (120, 1)


def test_public_create_enforces_pacing_with_stable_code(admin_client, client, db):
    _enable_online(admin_client)
    _serwis(admin_client, max_rezerwacji=1)
    _stolik(admin_client, "S1")
    _stolik(admin_client, "S2")

    first = _online_create(client, nazwisko="Pierwszy online")
    assert first.status_code == 201, first.text
    second = _online_create(client, nazwisko="Drugi online")
    _assert_conflict(second, "PACING_RESERVATION_LIMIT", "pacing_reservations")

    _fresh(db)
    rows = db.query(models.RezerwacjaPacingLedger).filter_by(data=BOOKING_DATE).all()
    assert len(rows) == 1
    assert rows[0].covers == 2
    assert rows[0].override is False


def test_public_idempotency_replays_reservation_and_payment_once(admin_client, client, db):
    _enable_online(admin_client)
    _serwis(admin_client)
    _stolik(admin_client)
    config = admin_client.put(
        "/api/lokal/config",
        json={
            "zadatek_wymagany": True,
            "zadatek_kwota_os": 20,
            "zadatek_prog_osob": 2,
        },
    )
    assert config.status_code == 200, config.text
    headers = {"Idempotency-Key": "online-create-payment-001"}

    first = _online_create(
        client,
        nazwisko="Idempotentny zadatek",
        headers=headers,
    )
    replay = _online_create(
        client,
        nazwisko="Idempotentny zadatek",
        headers=headers,
    )

    assert first.status_code == 201, first.text
    assert replay.status_code == 201, replay.text
    assert replay.json() == first.json()
    assert replay.json()["platnosc"]["kwota"] == 40.0
    _fresh(db)
    termin = db.query(models.Termin).filter_by(
        token_potwierdzenia=first.json()["token"],
    ).one()
    assert db.query(models.Termin).filter_by(
        rodzaj="stolik", data=BOOKING_DATE,
    ).count() == 1
    assert db.query(models.Platnosc).filter_by(termin_id=termin.id).count() == 1
    assert db.query(models.RezerwacjaIdempotencja).filter_by(
        operation="reservation.create.online:v1",
    ).count() == 1
    assert _ledger_counts(db, termin.id) == (120, 1)


def test_public_availability_and_create_use_three_table_combination(admin_client, client, db):
    _enable_online(admin_client)
    _serwis(admin_client)
    table_ids = [_stolik(admin_client, f"S{index}", pojemnosc=6) for index in range(1, 4)]
    combination = admin_client.post(
        "/api/kombinacje",
        json={"nazwa": "Bankiet 18", "stoliki": table_ids, "pojemnosc_max": 18},
    )
    assert combination.status_code == 201, combination.text

    availability = client.get(
        f"/api/online/dostepnosc?data={BOOKING_DATE.isoformat()}&osoby=18"
    )
    assert availability.status_code == 200, availability.text
    slot = next(item for item in availability.json()["sloty"] if item["godz_od"] == "18:00")
    assert slot["wolne_stoly"] == 1
    assert slot["wolne"] == 1
    assert slot["dostepny"] is True

    created = _online_create(client, nazwisko="Bankiet osiemnaście", osoby=18)
    assert created.status_code == 201, created.text
    _fresh(db)
    termin = db.query(models.Termin).filter_by(
        token_potwierdzenia=created.json()["token"],
    ).one()
    assert {termin.stolik_id, *(termin.stoliki_dodatkowe or [])} == set(table_ids)
    assert _ledger_counts(db, termin.id) == (360, 1)


def test_public_party_size_only_edit_rechecks_cover_pacing(admin_client, client, db):
    _enable_online(admin_client)
    _serwis(admin_client, max_osob=4)
    _stolik(admin_client, "S1")
    _stolik(admin_client, "S2")

    first = _online_create(client, nazwisko="Pierwsza para", osoby=2)
    second = _online_create(client, nazwisko="Druga para", osoby=2)
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text

    token = first.json()["token"]
    edit = client.post(
        f"/api/online/rezerwacja/{token}/edytuj",
        json={"liczba_osob": 3},
    )
    _assert_conflict(edit, "PACING_COVERS_LIMIT", "pacing_covers")

    unchanged = client.get(f"/api/online/rezerwacja/{token}")
    assert unchanged.status_code == 200
    assert unchanged.json()["liczba_osob"] == 2

    _fresh(db)
    rows = db.query(models.RezerwacjaPacingLedger).filter_by(data=BOOKING_DATE).all()
    assert len(rows) == 2
    assert sum(row.covers for row in rows) == 4


@pytest.mark.parametrize("terminal_status", ["odwolana", "odbyla"])
def test_terminal_status_releases_table_and_pacing_ledger(
    admin_client,
    db,
    terminal_status,
):
    table_id = _stolik(admin_client)
    created = _manual_create(admin_client, table_id, nazwisko=f"Status {terminal_status}")
    assert created.status_code == 201, created.text
    reservation_id = created.json()["id"]
    assert _ledger_counts(db, reservation_id) == (120, 1)

    changed = admin_client.post(
        f"/api/rezerwacje-stolik/{reservation_id}/status",
        json={"status": terminal_status},
    )
    assert changed.status_code == 200, changed.text
    assert _ledger_counts(db, reservation_id) == (0, 0)

    replacement = _manual_create(admin_client, table_id, nazwisko="Po zwolnieniu")
    assert replacement.status_code == 201, replacement.text


def test_public_cancellation_releases_ledger(admin_client, client, db):
    _enable_online(admin_client)
    _serwis(admin_client)
    table_id = _stolik(admin_client)
    created = _online_create(client, nazwisko="Anulowana online")
    assert created.status_code == 201, created.text
    token = created.json()["token"]

    _fresh(db)
    termin = db.query(models.Termin).filter_by(token_potwierdzenia=token).one()
    termin_id = termin.id
    assert termin.stolik_id == table_id
    assert _ledger_counts(db, termin_id) == (120, 1)

    cancelled = client.post(f"/api/online/rezerwacja/{token}/odwolaj")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "odwolana"
    assert _ledger_counts(db, termin_id) == (0, 0)

    replacement = _online_create(client, nazwisko="Po anulowaniu")
    assert replacement.status_code == 201, replacement.text


def test_waitlist_hold_release_removes_only_visit_window_claims(admin_client, db):
    table_id = _stolik(admin_client)
    wait = admin_client.post(
        "/api/lista-oczekujacych",
        json={
            "data": BOOKING_DATE.isoformat(),
            "godz_od": "18:00",
            "liczba_osob": 2,
            "nazwisko": "Czekający gość",
        },
    )
    assert wait.status_code == 201, wait.text
    waitlist_id = wait.json()["id"]

    held = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/hold",
        json={"stolik_id": table_id, "minuty": 30},
    )
    assert held.status_code == 200, held.text

    _fresh(db)
    claims = db.query(models.RezerwacjaStolikClaim).filter_by(
        waitlist_id=waitlist_id,
        stolik_id=table_id,
        data=BOOKING_DATE,
    ).all()
    assert len(claims) == 120
    assert {claim.minute for claim in claims} == set(range(18 * 60, 20 * 60))
    assert all(claim.expires_at is not None for claim in claims)

    released = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/zwolnij-hold"
    )
    assert released.status_code == 200, released.text
    _fresh(db)
    assert db.query(models.RezerwacjaStolikClaim).filter_by(
        waitlist_id=waitlist_id,
    ).count() == 0


def test_expired_hold_is_cleaned_before_new_table_claim(admin_client, db):
    table_id = _stolik(admin_client)
    wait = admin_client.post(
        "/api/lista-oczekujacych",
        json={
            "data": BOOKING_DATE.isoformat(),
            "godz_od": "18:00",
            "liczba_osob": 2,
            "nazwisko": "Wygasły hold",
        },
    )
    waitlist_id = wait.json()["id"]
    held = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/hold",
        json={"stolik_id": table_id, "minuty": 30},
    )
    assert held.status_code == 200, held.text

    _fresh(db)
    expired_at = datetime(2000, 1, 1)
    db.query(models.RezerwacjaStolikClaim).filter_by(
        waitlist_id=waitlist_id,
    ).update({"expires_at": expired_at})
    wait_row = db.get(models.ListaOczekujacych, waitlist_id)
    wait_row.hold_do = expired_at
    db.commit()

    created = _manual_create(admin_client, table_id, nazwisko="Po wygaśnięciu holdu")
    assert created.status_code == 201, created.text
    assert _ledger_counts(db, created.json()["id"]) == (120, 1)
    _fresh(db)
    wait_row = db.get(models.ListaOczekujacych, waitlist_id)
    assert wait_row.hold_stolik_id is None
    assert wait_row.hold_do is None
    assert db.query(models.RezerwacjaStolikClaim).filter_by(
        waitlist_id=waitlist_id,
    ).count() == 0


def test_table_with_active_hold_cannot_be_deleted(admin_client):
    table_id = _stolik(admin_client)
    wait = admin_client.post(
        "/api/lista-oczekujacych",
        json={
            "data": BOOKING_DATE.isoformat(),
            "godz_od": "18:00",
            "liczba_osob": 2,
            "nazwisko": "Hold chroni stolik",
        },
    )
    waitlist_id = wait.json()["id"]
    held = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/hold",
        json={"stolik_id": table_id, "minuty": 30},
    )
    assert held.status_code == 200, held.text

    blocked = admin_client.delete(f"/api/stoliki/{table_id}")
    assert blocked.status_code == 409, blocked.text
    released = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist_id}/zwolnij-hold"
    )
    assert released.status_code == 200, released.text
    assert admin_client.delete(f"/api/stoliki/{table_id}").status_code == 204
