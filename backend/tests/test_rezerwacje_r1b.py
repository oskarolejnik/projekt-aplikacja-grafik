"""R1b: bezpieczna baza rezerwacji, wyszukiwanie PII i detail do deep-linków."""

from datetime import date, datetime, time

import factories
import main
import models
import uprawnienia
from auth import create_access_token


SEARCH_PATH = "/api/rezerwacje-stolik/wyszukaj"


def _headers(user):
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def _reception():
    return factories.UserFactory(
        login="recepcja_r1b",
        rola="szef",
        pracownik=None,
        uprawnienia_override=uprawnienia.override_dla_presetu(
            "szef", uprawnienia.PRESET_RECEPCJA_HOST,
        ),
    )


def _operator_without_contact():
    return factories.UserFactory(
        login="operator_r1b_bez_kontaktu",
        rola="szef",
        pracownik=None,
        uprawnienia_override={"rezerwacje.operacje": True},
    )


def _termin(
    db,
    *,
    data=date(2026, 7, 20),
    godz_od=time(18, 0),
    nazwisko="Anna Kowalska",
    telefon="+48 600 100 200",
    email="anna@example.test",
    status="potwierdzona",
    rodzaj="stolik",
    notatka="Poufna notatka",
    zadatek=150,
):
    termin = models.Termin(
        data=data,
        godz_od=godz_od,
        godz_do=time(20, 0),
        nazwisko=nazwisko,
        telefon=telefon,
        email=email,
        liczba_osob=2,
        status=status,
        rodzaj=rodzaj,
        kanal="reczna",
        notatka=notatka,
        zadatek=zadatek,
        utworzono_at=datetime(2026, 7, 1, 12, 0),
    )
    db.add(termin)
    db.commit()
    db.refresh(termin)
    return termin


def _search(client, *, headers=None, **overrides):
    payload = {
        "start": "2026-01-01",
        "end": "2026-12-31",
        "limit": 50,
        "offset": 0,
        **overrides,
    }
    return client.post(SEARCH_PATH, headers=headers, json=payload)


def test_detail_uzywa_biezacych_praw_i_nie_ujawnia_innego_rodzaju(admin_client, client, db):
    reservation = _termin(db)
    event = _termin(db, nazwisko="Wesele Sekret", rodzaj="impreza")

    admin = admin_client.get(f"/api/rezerwacje-stolik/{reservation.id}")
    assert admin.status_code == 200
    assert admin.json()["nazwisko"] == "Anna Kowalska"

    operator = _operator_without_contact()
    redacted = client.get(
        f"/api/rezerwacje-stolik/{reservation.id}", headers=_headers(operator),
    )
    assert redacted.status_code == 200
    body = redacted.json()
    assert body["nazwisko"] == "Gość"
    assert body["telefon"] is None and body["email"] is None
    assert body["notatka"] is None and body["zadatek"] is None
    assert set(body["ukryte_pola"]) == {"nazwisko", "telefon", "email", "notatka", "zadatek"}
    assert "Anna Kowalska" not in redacted.text
    assert admin_client.get(f"/api/rezerwacje-stolik/{event.id}").status_code == 404
    assert admin_client.get("/api/rezerwacje-stolik/999999").status_code == 404


def test_wyszukiwanie_laczy_zakres_status_nazwisko_i_telefon(admin_client, db):
    wanted = _termin(
        db,
        data=date(2026, 7, 20),
        nazwisko="Żaneta Łącka",
        telefon="+48 600-100-200",
        status="potwierdzona",
    )
    _termin(
        db,
        data=date(2026, 7, 21),
        nazwisko="Jan Kowalski",
        telefon="700 300 400",
        status="odbyla",
    )
    _termin(db, data=date(2025, 12, 31), nazwisko="Żaneta Poza Zakresem")
    _termin(db, nazwisko="Żaneta Impreza", rodzaj="impreza")

    by_name = _search(
        admin_client,
        start="2026-07-01",
        end="2026-07-31",
        query="  ŁĄC  ",
        status="potwierdzona",
    )
    assert by_name.status_code == 200, by_name.text
    assert by_name.json()["total"] == 1
    assert by_name.json()["rezerwacje"][0]["id"] == wanted.id

    by_phone = _search(
        admin_client,
        start="2026-07-01",
        end="2026-07-31",
        query="600 100 200",
    )
    assert by_phone.status_code == 200, by_phone.text
    assert [row["id"] for row in by_phone.json()["rezerwacje"]] == [wanted.id]
    assert "query" not in by_phone.json()


def test_wyszukiwanie_ma_total_deterministyczny_sort_i_paginacje(admin_client, db):
    first = _termin(db, data=date(2026, 7, 20), godz_od=time(12, 0), nazwisko="Celina")
    second = _termin(db, data=date(2026, 7, 21), godz_od=time(12, 0), nazwisko="Anna")
    third = _termin(db, data=date(2026, 7, 22), godz_od=time(12, 0), nazwisko="Beata")
    fourth = _termin(db, data=date(2026, 7, 23), godz_od=time(12, 0), nazwisko="Dorota")

    page = _search(
        admin_client,
        start="2026-07-20",
        end="2026-07-23",
        sort="data_desc",
        offset=1,
        limit=2,
    )
    assert page.status_code == 200, page.text
    assert page.json()["total"] == 4
    assert page.json()["offset"] == 1 and page.json()["limit"] == 2
    assert [row["id"] for row in page.json()["rezerwacje"]] == [third.id, second.id]

    ascending = _search(
        admin_client,
        start="2026-07-20",
        end="2026-07-23",
        sort="data_asc",
    )
    assert [row["id"] for row in ascending.json()["rezerwacje"]] == [
        first.id, second.id, third.id, fourth.id,
    ]

    by_name = _search(
        admin_client,
        start="2026-07-20",
        end="2026-07-23",
        sort="nazwisko_asc",
    )
    assert [row["nazwisko"] for row in by_name.json()["rezerwacje"]] == [
        "Anna", "Beata", "Celina", "Dorota",
    ]


def test_wyszukiwanie_wymaga_operacji_i_danych_kontaktowych(client, db):
    reservation = _termin(db)
    reception = _reception()
    allowed = _search(client, headers=_headers(reception), query="Kowalska")
    assert allowed.status_code == 200
    assert allowed.json()["rezerwacje"][0]["id"] == reservation.id
    assert allowed.json()["rezerwacje"][0]["notatka"] is None
    assert allowed.json()["rezerwacje"][0]["zadatek"] is None

    no_contact = _operator_without_contact()
    denied = _search(client, headers=_headers(no_contact), query="Kowalska")
    assert denied.status_code == 403
    assert "Kowalska" not in denied.text

    contact_without_operations = factories.UserFactory(
        login="kontakt_bez_operacji_r1b",
        rola="szef",
        pracownik=None,
        uprawnienia_override={"rezerwacje.dane_kontaktowe": True},
    )
    assert _search(
        client, headers=_headers(contact_without_operations), query="Kowalska",
    ).status_code == 403


def test_wyszukiwanie_waliduje_zakres_i_parametry(admin_client):
    inverted = _search(admin_client, start="2026-07-31", end="2026-07-01")
    assert inverted.status_code == 400

    too_wide = _search(admin_client, start="2025-01-01", end="2026-01-02")
    assert too_wide.status_code == 400
    allowed = _search(admin_client, start="2025-01-01", end="2026-01-01")
    assert allowed.status_code == 200

    assert _search(admin_client, limit=101).status_code == 422
    assert _search(admin_client, offset=-1).status_code == 422
    assert _search(admin_client, query="x").status_code == 422
    assert _search(admin_client, status="nieznany").status_code == 422
    assert _search(admin_client, sort="losowo").status_code == 422


def test_wyszukiwanie_jako_odczyt_dziala_po_wygasnieciu_subskrypcji(admin_client, db):
    _termin(db)
    assert admin_client.put(
        "/api/subskrypcja", json={"tier": "premium", "status": "wygasla"},
    ).status_code == 200

    response = _search(admin_client, query="Kowalska")
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert admin_client.post(
        "/api/stoliki", json={"nazwa": "Nadal zapis", "pojemnosc": 2},
    ).status_code == 402


def test_nowe_endpointy_respektuja_flage_modulu(admin_client, db):
    reservation = _termin(db)
    assert admin_client.put(
        "/api/lokal/config", json={"modul_rezerwacje": False},
    ).status_code == 200
    assert admin_client.get(f"/api/rezerwacje-stolik/{reservation.id}").status_code == 403
    assert _search(admin_client, query="Kowalska").status_code == 403


def test_polityka_r1b_jest_dokladna_i_fail_closed():
    assert SEARCH_PATH in main.READ_ONLY_POST_ODCZYT
    assert f"{SEARCH_PATH}/przyszly-zapis" not in main.READ_ONLY_POST_ODCZYT

    search = main.reservation_access.requirement_for("POST", SEARCH_PATH)
    assert search is not None
    assert search.all_of == (
        "rezerwacje.operacje", "rezerwacje.dane_kontaktowe",
    )
    assert main.reservation_access.requirement_for("GET", SEARCH_PATH).admin_only is True

    detail = main.reservation_access.requirement_for("GET", "/api/rezerwacje-stolik/123")
    assert detail is not None and detail.all_of == ("rezerwacje.operacje",)
    unknown = main.reservation_access.requirement_for(
        "GET", "/api/rezerwacje-stolik/123/przyszla-akcja",
    )
    assert unknown is not None and unknown.admin_only is True
    similar = main.reservation_access.requirement_for(
        "POST", "/api/rezerwacje-stolik/wyszukaj-zly",
    )
    assert similar is not None and similar.admin_only is True
