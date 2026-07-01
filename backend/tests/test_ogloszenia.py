"""Ogłoszenia zespołowe — /api/ogloszenia (manager) + /api/me/ogloszenia (pracownik)."""

from datetime import date, timedelta

import factories
import models


def test_admin_tworzy_i_listuje_ogloszenie(admin_client, db):
    r = admin_client.post("/api/ogloszenia", json={"tytul": "Zebranie", "tresc": "W piątek o 10.", "przypiete": True})
    assert r.status_code == 201, r.text
    o = r.json()
    assert o["tytul"] == "Zebranie" and o["przypiete"] is True
    assert o["liczba_potwierdzen"] == 0
    lista = admin_client.get("/api/ogloszenia").json()
    assert len(lista) == 1 and lista[0]["autor"] == "admin_test"


def test_pusty_tytul_lub_tresc_400(admin_client):
    assert admin_client.post("/api/ogloszenia", json={"tytul": "  ", "tresc": "x"}).status_code == 400
    assert admin_client.post("/api/ogloszenia", json={"tytul": "x", "tresc": ""}).status_code == 400


def test_pracownik_widzi_aktywne_i_potwierdza(make_employee_client, admin_client, db):
    prac = factories.PracownikFactory()
    ce, _ = make_employee_client(prac)
    oid = admin_client.post("/api/ogloszenia", json={"tytul": "Uwaga", "tresc": "Nowy regulamin."}).json()["id"]

    widok = ce.get("/api/me/ogloszenia").json()
    assert widok["nieprzeczytane"] == 1
    assert widok["ogloszenia"][0]["przeczytane"] is False
    assert widok["ogloszenia"][0]["tytul"] == "Uwaga"

    assert ce.post(f"/api/me/ogloszenia/{oid}/potwierdz").status_code == 204
    assert ce.post(f"/api/me/ogloszenia/{oid}/potwierdz").status_code == 204   # idempotentne
    widok2 = ce.get("/api/me/ogloszenia").json()
    assert widok2["nieprzeczytane"] == 0 and widok2["ogloszenia"][0]["przeczytane"] is True
    # potwierdzenie zapisane raz (bez dubli)
    assert db.query(models.OgloszeniePotwierdzenie).filter_by(ogloszenie_id=oid).count() == 1


def test_manager_widzi_licznik_i_kto_potwierdzil(make_employee_client, admin_client, db):
    a = factories.PracownikFactory(imie="Ala", nazwisko="Kowalska")
    b = factories.PracownikFactory(imie="Bartek", nazwisko="Nowak")
    ca, _ = make_employee_client(a)
    oid = admin_client.post("/api/ogloszenia", json={"tytul": "T", "tresc": "Treść"}).json()["id"]
    ca.post(f"/api/me/ogloszenia/{oid}/potwierdz")

    o = admin_client.get("/api/ogloszenia").json()[0]
    assert o["liczba_potwierdzen"] == 1 and o["liczba_odbiorcow"] == 2   # 2 aktywnych pracowników
    kto = admin_client.get(f"/api/ogloszenia/{oid}/potwierdzenia").json()
    assert len(kto) == 1 and kto[0]["pracownik"] == "Ala Kowalska"


def test_wazne_do_chowa_wygasle_przed_pracownikiem(make_employee_client, admin_client, db):
    prac = factories.PracownikFactory()
    ce, _ = make_employee_client(prac)
    wczoraj = str(date.today() - timedelta(days=1))
    admin_client.post("/api/ogloszenia", json={"tytul": "Stare", "tresc": "x", "wazne_do": wczoraj})
    admin_client.post("/api/ogloszenia", json={"tytul": "Aktualne", "tresc": "y"})
    widok = ce.get("/api/me/ogloszenia").json()
    tytuly = [o["tytul"] for o in widok["ogloszenia"]]
    assert "Aktualne" in tytuly and "Stare" not in tytuly     # wygasłe niewidoczne dla pracownika
    assert len(admin_client.get("/api/ogloszenia").json()) == 2   # manager widzi oba


def test_edycja_i_usuniecie_kasuje_potwierdzenia(make_employee_client, admin_client, db):
    prac = factories.PracownikFactory()
    ce, _ = make_employee_client(prac)
    oid = admin_client.post("/api/ogloszenia", json={"tytul": "T", "tresc": "x"}).json()["id"]
    ce.post(f"/api/me/ogloszenia/{oid}/potwierdz")

    assert admin_client.put(f"/api/ogloszenia/{oid}", json={"tytul": "T2", "tresc": "y", "przypiete": True}).json()["tytul"] == "T2"
    assert admin_client.delete(f"/api/ogloszenia/{oid}").status_code == 204
    assert db.query(models.Ogloszenie).count() == 0
    assert db.query(models.OgloszeniePotwierdzenie).count() == 0   # kaskada ORM


def test_pracownik_nie_ma_dostepu_do_endpointow_managera(make_employee_client, db):
    prac = factories.PracownikFactory()
    ce, _ = make_employee_client(prac)
    assert ce.get("/api/ogloszenia").status_code == 403
    assert ce.post("/api/ogloszenia", json={"tytul": "x", "tresc": "y"}).status_code == 403
