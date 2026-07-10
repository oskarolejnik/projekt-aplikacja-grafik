"""Efektywne uprawnienia konta szefa: dokładne ścieżki i redakcja finansów."""

from datetime import date
from unittest.mock import Mock

import pytest

import factories
import main
import models
from auth import create_access_token


def _h(user):
    return {"Authorization": f"Bearer {create_access_token(user)}"}


@pytest.mark.parametrize(
    ("permission", "path"),
    [
        ("grafik.podglad", "/api/przydzialy?start=2026-06-01&end=2026-06-07"),
        ("raporty.podglad", "/api/raporty/godziny?rok=2026&miesiac=6"),
        ("zeszyt.podglad", "/api/szef/zeszyt?start=2026-06-01&end=2026-06-07"),
        ("imprezy.podglad", "/api/imprezy?start=2026-06-01&end=2026-06-07"),
        ("imprezy.podglad", "/api/me/imprezy"),
        ("rezerwacje.podglad", "/api/rezerwacje"),
        ("rezerwacje.podglad", "/api/me/rezerwacje"),
    ],
)
def test_jawne_odebranie_uprawnienia_blokuje_endpoint(client, permission, path):
    szef = factories.UserFactory(
        login=f"deny-{permission}",
        rola="szef",
        uprawnienia_override={permission: False},
    )

    response = client.get(path, headers=_h(szef))

    assert response.status_code == 403


def test_imprezy_podglad_nie_otwiera_rozliczen(client):
    szef = factories.UserFactory(login="szef-imprezy", rola="szef")

    assert client.get("/api/imprezy?start=2026-06-01&end=2026-06-07", headers=_h(szef)).status_code == 200
    assert client.get("/api/imprezy/rozliczenia", headers=_h(szef)).status_code == 403


def test_szef_ma_dostep_do_historii_stolow(client):
    szef = factories.UserFactory(login="szef-stoly", rola="szef")

    assert client.get("/api/gastro/stoly-historia", headers=_h(szef)).status_code == 200


def test_zeszyt_bez_prawa_do_wyplat_ukrywa_pozycje_placowe(client, db):
    db.add_all([
        models.ZeszytPozycja(data=date(2026, 6, 1), kolumna="koszty", opis="Chemia", kwota=80),
        models.ZeszytPozycja(data=date(2026, 6, 1), kolumna="wyplaty", opis="Wypłata Anna", kwota=2400),
    ])
    db.commit()
    szef = factories.UserFactory(
        login="szef-zeszyt-bez-wyplat",
        rola="szef",
        uprawnienia_override={"wyplaty.podglad": False},
    )

    response = client.get(
        "/api/szef/zeszyt?start=2026-06-01&end=2026-06-01",
        headers=_h(szef),
    )

    assert response.status_code == 200
    pozycje = response.json()["dni"][0]["rozchod"]
    assert pozycje == [{
        "id": pozycje[0]["id"],
        "kolumna": "koszty",
        "opis": "Chemia",
        "kwota": 80.0,
    }]
    assert response.json()["stan_poczatkowy"] is None
    assert response.json()["dane_czesciowo_ukryte"] is True
    assert response.json()["dni"][0]["rozchod_suma"] == 80.0
    assert response.json()["dni"][0]["stan"] is None
    assert "Wypłata Anna" not in response.text
    assert "2400" not in response.text


def test_raport_godzin_bez_prawa_do_wyplat_nie_zwraca_kwot(client, monkeypatch):
    szef = factories.UserFactory(
        login="szef-bez-wyplat",
        rola="szef",
        uprawnienia_override={"wyplaty.podglad": False},
    )
    raport = {
        "rok": 2026,
        "miesiac": 6,
        "pracownicy": [{
            "pracownik_id": 1,
            "pracownik": "Anna Testowa",
            "dzial": "obsluga",
            "suma_godzin": 2,
            "stanowiska": [{"stanowisko": "Sala", "godziny": 2, "stawka": 50, "kwota": 100}],
            "do_wyplaty": 100,
            "do_wyplaty_po_zaliczkach": 80,
            "zaliczki_kwota": 20,
            "zaoszczedzone_godziny": 1,
            "zaoszczedzone_kwota": 50,
        }],
        "zaoszczedzone": {"godziny": 1, "kwota": 50},
        "stanowiska_podsumowanie": [{"stanowisko": "Sala", "godziny": 2, "kwota": 100}],
        "poza_grafikiem": [],
        "bez_stawki": [{"pracownik_id": 1, "godziny": 2}],
        "duze_ciecia": [],
        "male_ciecia": [],
        "niedopasowani_rcp": [],
        "przyszly_koszt": 999999,
    }
    audyt = Mock()
    monkeypatch.setattr(main.raporty, "raport_godzin_miesiac", lambda *_args, **_kwargs: raport)
    monkeypatch.setattr(main, "_trwajace_zmiany", lambda _db: [])
    monkeypatch.setattr(main, "zapisz_audyt", audyt)

    response = client.get("/api/raporty/godziny?rok=2026&miesiac=6", headers=_h(szef))

    assert response.status_code == 200
    body = response.json()
    assert body["pracownicy"] == [{
        "pracownik_id": 1,
        "pracownik": "Anna Testowa",
        "dzial": "obsluga",
        "suma_godzin": 2,
        "stanowiska": [{"stanowisko": "Sala", "godziny": 2}],
        "zaoszczedzone_godziny": 1,
    }]
    assert body["zaoszczedzone"] == {"godziny": 1}
    assert body["stanowiska_podsumowanie"] == [{"stanowisko": "Sala", "godziny": 2}]
    assert "bez_stawki" not in body
    assert "przyszly_koszt" not in body
    audyt.assert_not_called()


def test_pulpit_redaguje_place_i_kase_po_odebraniu_praw(client, monkeypatch):
    szef = factories.UserFactory(
        login="szef-pulpit-redakcja",
        rola="szef",
        uprawnienia_override={
            "wyplaty.podglad": False,
            "zeszyt.podglad": False,
            "rezerwacje.podglad": False,
        },
    )
    monkeypatch.setattr(main.raporty, "raport_godzin_miesiac", lambda *_args, **_kwargs: {"pracownicy": []})

    response = client.get(
        "/api/pulpit?start=2026-06-01&end=2026-06-01",
        headers=_h(szef),
    )

    assert response.status_code == 200
    body = response.json()
    for field in ("przychod", "rozchod", "saldo_kasy", "alerty_kasowe", "koszt_pracy_miesiac", "wynik"):
        assert field not in body
    assert "ruch" in body
    assert "rezerwacje" not in body


def test_pulpit_bez_wyplat_nie_zwraca_agregatow_pozwalajacych_je_odtworzyc(client, monkeypatch):
    szef = factories.UserFactory(
        login="szef-pulpit-bez-wyplat",
        rola="szef",
        uprawnienia_override={"wyplaty.podglad": False},
    )
    monkeypatch.setattr(main.raporty, "raport_godzin_miesiac", lambda *_args, **_kwargs: {"pracownicy": []})

    response = client.get(
        "/api/pulpit?start=2026-06-01&end=2026-06-01",
        headers=_h(szef),
    )

    assert response.status_code == 200
    body = response.json()
    for field in ("koszt_pracy_miesiac", "rozchod", "saldo_kasy", "wynik"):
        assert field not in body
    assert "przychod" in body
    assert all("rozchod" not in dzien for dzien in body["przychod"]["dzienny"])
