"""Rezerwacje (Google Calendar): parsowanie (liczba osób z opisu, per dzień/godzina)
+ endpointy (admin/szef pełne z godzinami, pracownik tylko sumy dzienne)."""

import rezerwacje
import factories
from auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(u)}"}


def _ev(start_dt, osoby):
    return {"start": {"dateTime": start_dt}, "description": f"REZERWACJA STOLIKA\nLiczba osób: {osoby}\nTelefon: x"}


def test_parsuj_agreguje_dzien_i_godzine():
    events = [
        _ev("2026-06-13T14:00:00+02:00", 5),
        _ev("2026-06-13T14:00:00+02:00", 2),
        _ev("2026-06-13T18:00:00+02:00", 4),
        _ev("2026-06-14T12:00:00+02:00", 3),
    ]
    dni = rezerwacje.parsuj(events)
    d13 = next(d for d in dni if d["data"] == "2026-06-13")
    assert d13["liczba"] == 3 and d13["osoby"] == 11      # 5+2+4
    godz = {g["godzina"]: g for g in d13["godziny"]}
    assert godz["14:00"]["liczba"] == 2 and godz["14:00"]["osoby"] == 7
    assert godz["18:00"]["liczba"] == 1 and godz["18:00"]["osoby"] == 4


def test_parsuj_bez_liczby_osob_daje_zero():
    dni = rezerwacje.parsuj([{"start": {"dateTime": "2026-06-13T10:00:00+02:00"}, "description": "Brak pola osob"}])
    assert dni[0]["liczba"] == 1 and dni[0]["osoby"] == 0


def test_endpoint_admin_pelny_pracownik_tylko_sumy(client, admin_client, db, monkeypatch):
    dane = [{"data": "2026-06-13", "liczba": 3, "osoby": 11,
             "godziny": [{"godzina": "14:00", "liczba": 2, "osoby": 7}]}]
    monkeypatch.setattr(rezerwacje, "rezerwacje_per_dzien", lambda dni_naprzod=30: dane)

    r = admin_client.get("/api/rezerwacje")          # admin -> pełne (z godzinami)
    assert r.status_code == 200
    assert r.json()["dni"][0]["godziny"][0]["godzina"] == "14:00"

    prac = factories.PracownikFactory()              # pracownik -> tylko sumy
    emp = factories.UserFactory(login="emprez", rola="employee", pracownik=prac)
    r2 = client.get("/api/me/rezerwacje", headers=_h(emp))
    assert r2.status_code == 200
    d = r2.json()["dni"][0]
    assert d["liczba"] == 3 and d["osoby"] == 11
    assert "godziny" not in d                         # pracownik NIE dostaje rozbicia godzinowego


def test_szef_widzi_rezerwacje(client, db, monkeypatch):
    monkeypatch.setattr(rezerwacje, "rezerwacje_per_dzien", lambda dni_naprzod=30: [])
    szef = factories.UserFactory(login="szefrez", rola="szef")
    assert client.get("/api/rezerwacje", headers=_h(szef)).status_code == 200
