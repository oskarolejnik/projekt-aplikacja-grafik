"""R1a: macierz Recepcja/Host, redakcja PII i natychmiastowa revokacja."""

import factories
import main
import models
import uprawnienia
from auth import create_access_token


DAY = "2026-07-20"


def _headers(user):
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def _reception():
    return factories.UserFactory(
        login="recepcja_r1a",
        rola="szef",
        pracownik=None,
        uprawnienia_override=uprawnienia.override_dla_presetu(
            "szef", uprawnienia.PRESET_RECEPCJA_HOST,
        ),
    )


def _reservation(admin_client, table_id, **extra):
    body = {
        "data": DAY,
        "godz_od": "18:00",
        "stolik_id": table_id,
        "liczba_osob": 2,
        "nazwisko": "Kowalska",
        "telefon": "600100200",
        "email": "gosc@example.com",
        "notatka": "Poufna notatka",
        "zadatek": 150,
        **extra,
    }
    response = admin_client.post("/api/rezerwacje-stolik", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_preset_recepcji_otwiera_operacje_i_hosta_but_nie_konfiguracje(admin_client, client):
    table = admin_client.post("/api/stoliki", json={"nazwa": "R1", "pojemnosc": 4}).json()
    reservation = _reservation(admin_client, table["id"])
    user = _reception()
    headers = _headers(user)

    assert client.get(
        f"/api/rezerwacje-stolik?start={DAY}&end={DAY}", headers=headers,
    ).status_code == 200
    assert client.get("/api/stoliki", headers=headers).status_code == 200
    assert client.get("/api/rezerwacje/config", headers=headers).status_code == 200
    assert client.get(f"/api/host/kolejka?data={DAY}", headers=headers).status_code == 200
    assert client.post(
        f"/api/rezerwacje-stolik/{reservation['id']}/status",
        headers=headers,
        json={"status": "odwolana"},
    ).status_code == 200

    assert client.post(
        "/api/stoliki", headers=headers, json={"nazwa": "Zakazany", "pojemnosc": 2},
    ).status_code == 403
    assert client.post(
        "/api/godziny-otwarcia",
        headers=headers,
        json={"dzien_tygodnia": 0, "godz_od": "12:00", "godz_do": "22:00"},
    ).status_code == 403
    assert client.get(
        f"/api/analityka/rezerwacje?start={DAY}&end={DAY}", headers=headers,
    ).status_code == 403
    assert client.delete(
        f"/api/rezerwacje-stolik/{reservation['id']}", headers=headers,
    ).status_code == 403
    assert client.get("/api/lokal/config", headers=headers).status_code == 403
    assert client.get("/api/users", headers=headers).status_code == 403
    assert client.get("/api/host/przyszla-trasa-admina", headers=headers).status_code == 403


def test_recepcja_widzi_kontakt_ale_nie_notatke_i_finanse(admin_client, client, db):
    table = admin_client.post("/api/stoliki", json={"nazwa": "R2", "pojemnosc": 4}).json()
    reservation = _reservation(admin_client, table["id"])
    user = _reception()
    headers = _headers(user)

    response = client.get(
        f"/api/rezerwacje-stolik?start={DAY}&end={DAY}", headers=headers,
    )
    row = response.json()["rezerwacje"][0]
    assert row["nazwisko"] == "Kowalska"
    assert row["telefon"] == "600100200"
    assert row["email"] == "gosc@example.com"
    assert row["notatka"] is None
    assert row["zadatek"] is None
    assert set(row["ukryte_pola"]) == {"notatka", "zadatek"}

    edited = client.put(
        f"/api/rezerwacje-stolik/{reservation['id']}",
        headers=headers,
        json={
            "data": DAY,
            "godz_od": "18:30",
            "stolik_id": table["id"],
            "liczba_osob": 3,
            "nazwisko": "Kowalska-Nowa",
            "telefon": "600100201",
            "email": "nowy@example.com",
            "notatka": "Próba nadpisania",
            "zadatek": 999,
        },
    )
    assert edited.status_code == 200, edited.text
    db.expire_all()
    saved = db.get(models.Termin, reservation["id"])
    assert saved.nazwisko == "Kowalska-Nowa"
    assert saved.notatka == "Poufna notatka"
    assert saved.zadatek == 150


def test_operacje_bez_prawa_do_kontaktu_sa_redagowane_i_nie_pozwalaja_pisac(
    admin_client, client,
):
    table = admin_client.post("/api/stoliki", json={"nazwa": "R3", "pojemnosc": 4}).json()
    reservation = _reservation(admin_client, table["id"])
    user = factories.UserFactory(
        login="operator_bez_pii",
        rola="szef",
        pracownik=None,
        uprawnienia_override={
            "rezerwacje.operacje": True,
            "rezerwacje.host": True,
        },
    )
    headers = _headers(user)

    row = client.get(
        f"/api/rezerwacje-stolik?start={DAY}&end={DAY}", headers=headers,
    ).json()["rezerwacje"][0]
    assert row["nazwisko"] == "Gość"
    assert row["telefon"] is None and row["email"] is None
    assert "Kowalska" not in str(row)
    assert client.post(
        "/api/rezerwacje-stolik",
        headers=headers,
        json={"data": DAY, "nazwisko": "Nowy"},
    ).status_code == 403
    assert client.put(
        f"/api/rezerwacje-stolik/{reservation['id']}",
        headers=headers,
        json={"data": DAY, "nazwisko": "Zmieniony"},
    ).status_code == 403


def test_recepcja_nie_widzi_plaintextu_alergii(admin_client, client, db):
    table = admin_client.post("/api/stoliki", json={"nazwa": "R4", "pojemnosc": 4}).json()
    reservation = _reservation(admin_client, table["id"], telefon="600200300")
    termin = db.get(models.Termin, reservation["id"])
    db.add(models.ProfilGoscia(
        klucz_hash=main._crm_hash(termin),
        nazwisko="Kowalska",
        alergie="orzechy i sezam",
        tagi=["alergik"],
        vip=True,
    ))
    db.commit()
    user = _reception()

    body = client.get(
        f"/api/host/kolejka?data={DAY}", headers=_headers(user),
    ).json()
    guest = body["nadchodzace"][0]["gosc"]
    assert guest["vip"] is True and guest["ma_alergie"] is None
    assert guest["alergie"] is None and guest["tagi"] == []
    assert guest["dane_wrazliwe_ukryte"] is False
    assert "orzechy" not in str(body)


def test_cofniecie_presetu_blokuje_ten_sam_token_natychmiast(admin_client, client, db):
    user = _reception()
    headers = _headers(user)
    path = f"/api/rezerwacje-stolik?start={DAY}&end={DAY}"
    assert client.get(path, headers=headers).status_code == 200

    saved = db.get(models.User, user.id)
    saved.uprawnienia_override = None
    db.commit()

    assert client.get(path, headers=headers).status_code == 403


def test_polityka_nie_dopasowuje_podobnych_prefiksow():
    assert main.reservation_access.requirement_for("GET", "/api/rezerwacje") is None
    assert main.reservation_access.requirement_for("GET", "/api/rezerwacje-stolik-zly") is None
    unknown = main.reservation_access.requirement_for("GET", "/api/rezerwacje-stolik/1/nowa-akcja")
    assert unknown is not None and unknown.admin_only is True


def test_przekroczenie_pacingu_wymaga_jawnego_prawa(admin_client, client):
    assert admin_client.post("/api/godziny-otwarcia", json={
        "dzien_tygodnia": 0,
        "godz_od": "12:00",
        "godz_do": "22:00",
        "pacing_max_rez": 1,
        "pacing_okno_min": 120,
    }).status_code == 201
    first_table = admin_client.post("/api/stoliki", json={"nazwa": "P1", "pojemnosc": 4}).json()
    second_table = admin_client.post("/api/stoliki", json={"nazwa": "P2", "pojemnosc": 4}).json()
    assert admin_client.post("/api/rezerwacje-stolik", json={
        "data": DAY, "godz_od": "18:00", "stolik_id": first_table["id"],
        "liczba_osob": 2, "nazwisko": "Pierwsza",
    }).status_code == 201
    payload = {
        "data": DAY, "godz_od": "18:00", "stolik_id": second_table["id"],
        "liczba_osob": 2, "nazwisko": "Druga", "przekrocz_limity": True,
    }
    without_override = factories.UserFactory(
        login="operator_bez_override",
        rola="szef",
        pracownik=None,
        uprawnienia_override={
            "rezerwacje.operacje": True,
            "rezerwacje.dane_kontaktowe": True,
        },
    )
    assert client.post(
        "/api/rezerwacje-stolik", json=payload, headers=_headers(without_override),
    ).status_code == 403

    reception = _reception()
    assert client.post(
        "/api/rezerwacje-stolik", json=payload, headers=_headers(reception),
    ).status_code == 201
