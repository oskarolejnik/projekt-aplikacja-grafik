"""Grafik sprzątania: reguły generatora (codziennie / niedziela / dzień po imprezie
z mapowaniem R2P→Zielona, R2Piw→Lustrzana, R2G→Kryształowa), korekty admina
(dodaj/usuń + powrót do automatu) i odhaczanie ✓ (tylko dział techniczny)."""

import models
import factories
import sprzatanie
from auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(u)}"}


# factories.dzien(0) = 2026-06-01 (poniedziałek), dzien(6) = 2026-06-07 (niedziela)

def test_generator_codziennie_i_niedziela(db):
    poz = sprzatanie.generuj(db, factories.dzien(0), factories.dzien(6))
    pon = {p["sala"] for p in poz if p["data"] == str(factories.dzien(0))}
    assert pon == {"Parter (R1)", "Góra (R1)"}                  # zwykły dzień: tylko codzienne
    nd = [p for p in poz if p["data"] == str(factories.dzien(6))]
    assert {p["sala"] for p in nd} == {"Parter (R1)", "Góra (R1)", "Zielona"}  # niedziela: + Zielona
    ziel = next(p for p in nd if p["sala"] == "Zielona")
    assert ziel["powody"] == ["niedziela"]


def test_generator_dzien_po_imprezie_z_mapowaniem(db):
    db.add(models.Impreza(data=factories.dzien(2), klient="A", sala="R2Piw", sciezka_pliku="a.xlsx"))
    db.add(models.Impreza(data=factories.dzien(2), klient="B", sala="R2G", sciezka_pliku="b.xlsx"))
    db.add(models.Impreza(data=factories.dzien(2), klient="C", sala="R1", sciezka_pliku="c.xlsx"))  # R1 -> nic ekstra
    db.commit()
    poz = sprzatanie.generuj(db, factories.dzien(3), factories.dzien(3))
    sale = {p["sala"] for p in poz}
    assert sale == {"Parter (R1)", "Góra (R1)", "Lustrzana", "Kryształowa"}
    lus = next(p for p in poz if p["sala"] == "Lustrzana")
    assert lus["powody"] and lus["powody"][0].startswith("po imprezie z")


def test_generator_zielona_niedziela_plus_impreza_jedna_pozycja(db):
    # impreza R2P w sobotę -> Zielona w niedzielę: JEDNA pozycja z dwoma powodami
    db.add(models.Impreza(data=factories.dzien(5), klient="W", sala="R2P", sciezka_pliku="d.xlsx"))
    db.commit()
    poz = sprzatanie.generuj(db, factories.dzien(6), factories.dzien(6))
    ziel = [p for p in poz if p["sala"] == "Zielona"]
    assert len(ziel) == 1 and len(ziel[0]["powody"]) == 2


def test_korekty_usun_dodaj_i_powrot_do_automatu(admin_client, db):
    d = str(factories.dzien(0))
    # usuń wygenerowaną pozycję
    r = admin_client.post("/api/sprzatanie/korekty", json={"data": d, "sala": "Parter (R1)", "akcja": "usun"})
    assert r.status_code == 204
    sale = {p["sala"] for p in admin_client.get(f"/api/sprzatanie?start={d}&end={d}").json()["pozycje"]}
    assert "Parter (R1)" not in sale
    # dodaj pozycję spoza reguł
    admin_client.post("/api/sprzatanie/korekty", json={"data": d, "sala": "Lustrzana", "akcja": "dodaj"})
    poz = admin_client.get(f"/api/sprzatanie?start={d}&end={d}").json()["pozycje"]
    lus = next(p for p in poz if p["sala"] == "Lustrzana")
    assert lus["powody"] == ["dodane ręcznie"]
    # przeciwne akcje cofają obie korekty (powrót do automatu)
    admin_client.post("/api/sprzatanie/korekty", json={"data": d, "sala": "Parter (R1)", "akcja": "dodaj"})
    admin_client.post("/api/sprzatanie/korekty", json={"data": d, "sala": "Lustrzana", "akcja": "usun"})
    sale = {p["sala"] for p in admin_client.get(f"/api/sprzatanie?start={d}&end={d}").json()["pozycje"]}
    assert sale == {"Parter (R1)", "Góra (R1)"}
    assert db.query(models.SprzatanieKorekta).count() == 0   # korekty zniknęły, nie nawarstwiają się


def test_sprzatanie_tylko_dzial_techniczny(client, db):
    obs = factories.PracownikFactory()
    uobs = factories.UserFactory(login="obsspr", rola="employee", pracownik=obs)
    d = str(factories.dzien(0))
    assert client.get(f"/api/me/sprzatanie?start={d}&end={d}", headers=_h(uobs)).status_code == 403


def test_odhaczanie_zapisuje_pracownika(client, db):
    tech = factories.PracownikFactory(imie="Pani", nazwisko="Sprzatajaca", dzial="techniczny")
    utech = factories.UserFactory(login="sprz1", rola="employee", pracownik=tech)
    d = str(factories.dzien(0))
    r = client.get(f"/api/me/sprzatanie?start={d}&end={d}", headers=_h(utech))
    assert r.status_code == 200 and len(r.json()["pozycje"]) == 2
    # odhacz ✓
    r = client.put("/api/me/sprzatanie/zrobione", headers=_h(utech),
                   json={"data": d, "sala": "Parter (R1)", "zrobione": True})
    assert r.status_code == 204
    poz = client.get(f"/api/me/sprzatanie?start={d}&end={d}", headers=_h(utech)).json()["pozycje"]
    parter = next(p for p in poz if p["sala"] == "Parter (R1)")
    assert parter["zrobione"] is True and parter["zrobione_przez"] == "Pani Sprzatajaca"
    # odznacz
    client.put("/api/me/sprzatanie/zrobione", headers=_h(utech),
               json={"data": d, "sala": "Parter (R1)", "zrobione": False})
    poz = client.get(f"/api/me/sprzatanie?start={d}&end={d}", headers=_h(utech)).json()["pozycje"]
    assert next(p for p in poz if p["sala"] == "Parter (R1)")["zrobione"] is False


def test_login_zwraca_dzial(client, db):
    tech = factories.PracownikFactory(dzial="techniczny")
    factories.UserFactory(login="techlog", rola="employee", pracownik=tech, haslo="Tech1234!")
    r = client.post("/api/auth/login", json={"login": "techlog", "haslo": "Tech1234!"})
    assert r.status_code == 200
    assert r.json()["user"]["dzial"] == "techniczny"
