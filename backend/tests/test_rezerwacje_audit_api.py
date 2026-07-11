"""R1a: dziennik audytu jest częścią tych samych transakcji co endpointy."""

import json

import factories
import models
import reservation_audit
import uprawnienia
from auth import create_access_token


DAY = "2026-07-22"


def _table(admin_client, name="A1"):
    response = admin_client.post("/api/stoliki", json={"nazwa": name, "pojemnosc": 6})
    assert response.status_code == 201, response.text
    return response.json()


def _body(table_id, **extra):
    return {
        "data": DAY,
        "godz_od": "18:00",
        "stolik_id": table_id,
        "liczba_osob": 3,
        "nazwisko": "Sekretny Gość",
        "telefon": "600700800",
        "email": "sekret@example.com",
        "notatka": "Poufna alergia",
        **extra,
    }


def _headers(user, **extra):
    return {"Authorization": f"Bearer {create_access_token(user)}", **extra}


def test_create_edit_cancel_maja_jeden_audyt_bez_pii(admin_client, db):
    table = _table(admin_client)
    headers = {"Idempotency-Key": "audit-r1a-create-1"}
    first = admin_client.post(
        "/api/rezerwacje-stolik", json=_body(table["id"]), headers=headers,
    )
    replay = admin_client.post(
        "/api/rezerwacje-stolik", json=_body(table["id"]), headers=headers,
    )
    assert first.status_code == replay.status_code == 201
    reservation_id = first.json()["id"]

    assert admin_client.put(
        f"/api/rezerwacje-stolik/{reservation_id}",
        json=_body(
            table["id"],
            godz_od="19:00",
            liczba_osob=4,
            telefon="600700801",
            notatka="Inna poufna treść",
        ),
    ).status_code == 200
    assert admin_client.post(
        f"/api/rezerwacje-stolik/{reservation_id}/status",
        json={"status": "odwolana"},
    ).status_code == 200

    rows = db.query(models.ReservationAudit).filter_by(termin_id=reservation_id).order_by(
        models.ReservationAudit.id,
    ).all()
    assert [row.action for row in rows] == ["create", "edit", "cancel"]
    assert all(row.actor_user_id is not None and row.actor_login == "admin_test" for row in rows)
    assert rows[1].diff["changes"]["liczba_osob"] == {"before": 3, "after": 4}
    assert set(rows[1].diff["pii_changed"]) == {"telefon", "notatka"}
    encoded = json.dumps([row.diff for row in rows], ensure_ascii=False)
    for secret in (
        "Sekretny Gość", "600700800", "600700801", "sekret@example.com",
        "Poufna alergia", "Inna poufna treść",
    ):
        assert secret not in encoded


def test_blad_zapisu_audytu_cofa_rezerwacje_ledger_i_idempotencje(
    admin_client, db, monkeypatch,
):
    table = _table(admin_client, "A2")
    original = reservation_audit.add_reservation_audit

    def invalid_audit(*args, **kwargs):
        record = original(*args, **kwargs)
        record.action = "invalid"
        return record

    monkeypatch.setattr(reservation_audit, "add_reservation_audit", invalid_audit)
    response = admin_client.post(
        "/api/rezerwacje-stolik",
        json=_body(table["id"]),
        headers={"Idempotency-Key": "audit-r1a-rollback-1"},
    )
    assert response.status_code == 503
    assert db.query(models.Termin).filter_by(rodzaj="stolik").count() == 0
    assert db.query(models.RezerwacjaStolikClaim).count() == 0
    assert db.query(models.RezerwacjaPacingLedger).count() == 0
    assert db.query(models.RezerwacjaIdempotencja).count() == 0
    assert db.query(models.ReservationAudit).count() == 0


def test_twarde_usuniecie_zostawia_historie_bez_fk_do_terminu(admin_client, db):
    table = _table(admin_client, "A3")
    created = admin_client.post(
        "/api/rezerwacje-stolik", json=_body(table["id"], godz_od="21:00"),
    ).json()
    reservation_id = created["id"]
    create_audit = db.query(models.ReservationAudit).filter_by(
        termin_id=reservation_id, action="create",
    ).one()
    reference = create_audit.reservation_ref

    assert admin_client.delete(f"/api/rezerwacje-stolik/{reservation_id}").status_code == 204
    db.expire_all()
    assert db.get(models.Termin, reservation_id) is None
    rows = db.query(models.ReservationAudit).filter_by(reservation_ref=reference).order_by(
        models.ReservationAudit.id,
    ).all()
    assert [row.action for row in rows] == ["create", "delete"]
    assert all(row.termin_id is None for row in rows)


def test_replay_manualny_renderuje_odpowiedz_wedlug_biezacych_praw(client, db):
    user = factories.UserFactory(
        login="operator_replay",
        rola="szef",
        pracownik=None,
        uprawnienia_override={
            "rezerwacje.operacje": True,
            "rezerwacje.dane_kontaktowe": True,
            "rezerwacje.notatki_wewnetrzne": True,
            "rezerwacje.finanse": True,
        },
    )
    table = models.Stolik(nazwa="Replay", pojemnosc=6, aktywny=True)
    db.add(table); db.commit()
    payload = _body(table.id, zadatek=125)
    headers = _headers(user, **{"Idempotency-Key": "replay-current-permissions"})

    first = client.post("/api/rezerwacje-stolik", json=payload, headers=headers)
    assert first.status_code == 201
    assert first.json()["notatka"] == "Poufna alergia"
    assert first.json()["zadatek"] == 125

    saved_user = db.get(models.User, user.id)
    saved_user.uprawnienia_override = {
        "rezerwacje.operacje": True,
        "rezerwacje.dane_kontaktowe": True,
    }
    db.commit()

    replay = client.post("/api/rezerwacje-stolik", json=payload, headers=headers)
    assert replay.status_code == 201
    assert replay.json()["notatka"] is None
    assert replay.json()["zadatek"] is None
    assert set(replay.json()["ukryte_pola"]) == {"notatka", "zadatek"}
    assert db.query(models.ReservationAudit).filter_by(action="create").count() == 1


def test_replay_waitlisty_nie_oddaje_notatki_pierwszego_aktora(
    admin_client, client, db,
):
    table = _table(admin_client, "A4")
    waitlist = admin_client.post("/api/lista-oczekujacych", json={
        "data": DAY,
        "godz_od": "17:00",
        "liczba_osob": 2,
        "nazwisko": "Waitlist Sekret",
        "telefon": "600999888",
        "notatka": "Tajna notatka waitlisty",
    }).json()
    payload = {"stolik_id": table["id"]}
    idem = {"Idempotency-Key": "waitlist-replay-current-permissions"}
    first = admin_client.post(
        f"/api/lista-oczekujacych/{waitlist['id']}/zrealizuj",
        json=payload,
        headers=idem,
    )
    assert first.status_code == 200
    assert first.json()["rezerwacja"]["notatka"] == "Tajna notatka waitlisty"

    reception = factories.UserFactory(
        login="recepcja_replay",
        rola="szef",
        pracownik=None,
        uprawnienia_override=uprawnienia.override_dla_presetu(
            "szef", uprawnienia.PRESET_RECEPCJA_HOST,
        ),
    )
    replay = client.post(
        f"/api/lista-oczekujacych/{waitlist['id']}/zrealizuj",
        json=payload,
        headers=_headers(reception, **idem),
    )
    assert replay.status_code == 200
    assert replay.json()["rezerwacja"]["notatka"] is None
    assert replay.json()["wpis"]["notatka"] is None
    assert "Tajna notatka" not in replay.text
