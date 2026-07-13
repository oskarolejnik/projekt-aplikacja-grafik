"""PII-safe agregat rezerwacji stolikowych z kanonicznego ``Termin`` (integracja Google wycofana)."""

from datetime import date, time, timedelta

import factories
import models
import rezerwacje
from auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(u)}"}


def _termin(db, data_rezerwacji, *, godz_od=time(18, 0), osoby=4,
            status="rezerwacja", rodzaj="stolik", nazwisko="Klient Sekretny"):
    termin = models.Termin(
        data=data_rezerwacji,
        godz_od=godz_od,
        liczba_osob=osoby,
        status=status,
        rodzaj=rodzaj,
        nazwisko=nazwisko,
        telefon="+48 999 888 777",
        email="sekretny@example.test",
        notatka="ALERGIA-PII-NIE-LOGUJ",
        kanal="reczna",
        zadatek=0,
    )
    db.add(termin)
    db.commit()
    return termin


def test_kanoniczny_agregat_filtruje_zakres_status_i_rodzaj_bez_pii(db):
    start = date(2026, 7, 10)
    _termin(db, start - timedelta(days=1))
    _termin(db, start, godz_od=time(18, 0), osoby=5, status="rezerwacja")
    _termin(db, start, godz_od=time(18, 0), osoby=2, status="potwierdzona")
    _termin(db, start, godz_od=None, osoby=None, status="odbyla")
    _termin(db, start + timedelta(days=1), status="odwolana")
    _termin(db, start + timedelta(days=1), status="no_show")
    _termin(db, start + timedelta(days=1), rodzaj="impreza")
    _termin(db, start + timedelta(days=3))  # prawy koniec zakresu jest wyłączny

    wynik = rezerwacje.rezerwacje_z_terminow(db, dni_naprzod=3, start=start)

    assert wynik == [{
        "data": "2026-07-10",
        "liczba": 3,
        "osoby": 7,
        "godziny": [
            {"godzina": "18:00", "liczba": 2, "osoby": 7},
            {"godzina": "—", "liczba": 1, "osoby": 0},
        ],
    }]
    serialized = repr(wynik)
    assert "Klient Sekretny" not in serialized
    assert "+48 999 888 777" not in serialized
    assert "sekretny@example.test" not in serialized
    assert "ALERGIA-PII-NIE-LOGUJ" not in serialized


def test_czytaj_rezerwacje_jest_kanoniczny_bez_google(db):
    start = date(2026, 7, 10)
    _termin(db, start, osoby=6)
    wynik = rezerwacje.czytaj_rezerwacje(db, dni_naprzod=1, start=start)
    assert wynik[0]["liczba"] == 1 and wynik[0]["osoby"] == 6


def test_endpointy_uzywaja_kanonicznego_agregatu_i_redaguja_pracownika(client, admin_client, db):
    dzien = rezerwacje._dzis_lokalnie() + timedelta(days=1)
    _termin(db, dzien, godz_od=time(14, 0), osoby=7)

    admin_response = admin_client.get("/api/rezerwacje")
    assert admin_response.status_code == 200
    assert admin_response.json()["dni"][0]["godziny"][0]["godzina"] == "14:00"

    pracownik = factories.PracownikFactory()
    employee = factories.UserFactory(login="obsrez", rola="employee", pracownik=pracownik)
    employee_full = client.get("/api/rezerwacje", headers=_h(employee))
    assert employee_full.status_code == 200
    assert employee_full.json()["dni"][0]["godziny"][0]["godzina"] == "14:00"

    employee_safe = client.get("/api/me/rezerwacje", headers=_h(employee))
    assert employee_safe.status_code == 200
    assert employee_safe.json()["dni"] == [{
        "data": dzien.isoformat(), "liczba": 1, "osoby": 7,
    }]

    for response in (admin_response, employee_full, employee_safe):
        body = response.text
        assert "Klient Sekretny" not in body
        assert "+48 999 888 777" not in body
        assert "sekretny@example.test" not in body
        assert "ALERGIA-PII-NIE-LOGUJ" not in body

    szef = factories.UserFactory(login="szefrez", rola="szef")
    assert client.get("/api/rezerwacje", headers=_h(szef)).status_code == 200
    assert client.get("/api/pracownicy", headers=_h(employee)).status_code == 403
