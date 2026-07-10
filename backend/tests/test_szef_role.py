"""Rola 'szef' — oversight TYLKO DO ODCZYTU: wybrane GET dozwolone, reszta 403."""

from datetime import date, datetime

import factories
import models
from auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(u)}"}


def test_szef_ma_dostep_do_podgladow(client, db):
    szef = factories.UserFactory(login="szef1", rola="szef")
    h = _h(szef)
    dozwolone = (
        "/api/raporty/godziny?rok=2026&miesiac=6",
        "/api/imprezy?start=2026-06-01&end=2026-06-07",
        "/api/szef/grafik?start=2026-06-01&end=2026-06-07",
        "/api/pracownicy",
        "/api/stanowiska",
    )
    for path in dozwolone:
        assert client.get(path, headers=h).status_code == 200, path


def test_szef_nie_widzi_innych_zasobow(client, db):
    szef = factories.UserFactory(login="szef2", rola="szef")
    h = _h(szef)
    assert client.get("/api/dyspozycje?start=2026-06-01&end=2026-06-07", headers=h).status_code == 403
    assert client.get("/api/users", headers=h).status_code == 403
    assert client.get("/api/wymagania?start=2026-06-01&end=2026-06-07", headers=h).status_code == 403
    assert client.get("/api/przydzialy?start=2026-06-01&end=2026-06-07", headers=h).status_code == 403
    assert client.get("/api/grafik/publikacja?start=2026-06-01&end=2026-06-07", headers=h).status_code == 403
    assert client.get("/api/alerty-obsady", headers=h).status_code == 403


def test_szef_grafik_nie_ujawnia_szkicu_i_zwraca_dane_dopiero_po_publikacji(client, db):
    today = date.today()
    stanowisko = factories.StanowiskoFactory(nazwa="Sala")
    pracownik = factories.PracownikFactory(imie="Anna", nazwisko="Testowa")
    db.add(models.PrzydzialZmiany(
        data=today,
        stanowisko_id=stanowisko.id,
        pracownik_id=pracownik.id,
    ))
    db.add(models.WymaganiaDnia(
        data=today,
        stanowisko_id=stanowisko.id,
        liczba_osob=2,
    ))
    db.commit()
    szef = factories.UserFactory(login="szef_published_only", rola="szef")
    path = f"/api/szef/grafik?start={today}&end={today}"

    szkic = client.get(path, headers=_h(szef))

    assert szkic.status_code == 200
    assert szkic.json()["opublikowany"] is False
    assert szkic.json()["przydzialy"] == []
    assert szkic.json()["alerty_dzis"] == []

    db.add(models.PublikacjaGrafiku(
        start=today,
        koniec=today,
        opublikowano_at=datetime.utcnow(),
    ))
    db.commit()

    opublikowany = client.get(path, headers=_h(szef))

    assert opublikowany.status_code == 200
    assert opublikowany.json()["opublikowany"] is True
    assert len(opublikowany.json()["przydzialy"]) == 1
    assert opublikowany.json()["przydzialy"][0]["pracownik_id"] == pracownik.id
    assert opublikowany.json()["razem_brakuje_dzis"] == 1
    assert opublikowany.json()["alerty_dzis"][0]["stanowisko"] == "Sala"


def test_szef_nie_moze_modyfikowac(client, db):
    szef = factories.UserFactory(login="szef3", rola="szef")
    h = _h(szef)
    assert client.post("/api/pracownicy", headers=h,
                       json={"imie": "X", "nazwisko": "Y", "aktywny": True, "kwalifikacje_ids": []}).status_code == 403
    assert client.delete("/api/przydzialy?start=2026-06-01&end=2026-06-07", headers=h).status_code == 403


def test_admin_moze_zalozyc_konto_szefa(admin_client, db):
    r = admin_client.post("/api/users", json={"login": "szefnowy", "haslo": "Haslo123!", "rola": "szef"})
    assert r.status_code == 201
    assert r.json()["rola"] == "szef"
