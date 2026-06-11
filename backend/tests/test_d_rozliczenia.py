"""Etap D — rozliczenia. D1: flagi przydziału „zamyka rewir" i „rozlicza imprezę"
(ustawiane w grafiku, widoczne w „Moim grafiku")."""

from datetime import datetime

import models
import factories
from auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(u)}"}


def test_przydzial_flagi_zamyka_rewir_i_rozlicza_imprize(admin_client, client, db):
    sala = factories.StanowiskoFactory(nazwa="Sala")
    p = factories.PracownikFactory(dzial="obsluga")
    u = factories.UserFactory(login="emp_d1", rola="employee", pracownik=p)
    d = factories.dzien(0)
    r = admin_client.post("/api/przydzialy", json={
        "data": str(d), "stanowisko_id": sala.id, "pracownik_id": p.id,
        "godz_od": "16:00", "rewir": "Parter", "zamyka_rewir": True, "rozlicza_imprize": True})
    assert r.status_code == 201
    aid = r.json()["id"]
    assert r.json()["zamyka_rewir"] is True and r.json()["rozlicza_imprize"] is True

    db.add(models.PublikacjaGrafiku(start=d, koniec=factories.dzien(6), opublikowano_at=datetime.utcnow()))
    db.commit()
    z = client.get("/api/me/grafik", headers=_h(u),
                   params={"start": str(d), "end": str(factories.dzien(6))}).json()["zmiany"][0]
    assert z["zamyka_rewir"] is True and z["rozlicza_imprize"] is True

    # PUT może je wyłączyć
    admin_client.put(f"/api/przydzialy/{aid}", json={
        "data": str(d), "stanowisko_id": sala.id, "pracownik_id": p.id, "rewir": "Parter",
        "zamyka_rewir": False, "rozlicza_imprize": False})
    db.expire_all()
    rec = db.get(models.PrzydzialZmiany, aid)
    assert rec.zamyka_rewir is False and rec.rozlicza_imprize is False


def test_flagi_domyslnie_false(admin_client, db):
    sala = factories.StanowiskoFactory(nazwa="Sala")
    p = factories.PracownikFactory(dzial="obsluga")
    r = admin_client.post("/api/przydzialy", json={
        "data": str(factories.dzien(1)), "stanowisko_id": sala.id, "pracownik_id": p.id})
    assert r.status_code == 201
    assert r.json()["zamyka_rewir"] is False and r.json()["rozlicza_imprize"] is False


# ── D-imprezy: rozliczanie imprez + IMP ───────────────────────────────────────

def _rozliczajacy(db, login="imp1"):
    imprezy = factories.StanowiskoFactory(nazwa="Imprezy")
    p = factories.PracownikFactory(dzial="obsluga")
    u = factories.UserFactory(login=login, rola="employee", pracownik=p)
    d = factories.dzien(0)
    db.add(models.PrzydzialZmiany(data=d, stanowisko_id=imprezy.id, pracownik_id=p.id,
                                  rozlicza_imprize=True, rewir="IMPREZA: Wesele (R2P)"))
    db.commit()
    return p, u, d


def test_rozliczanie_imprezy_upsert_i_imp(client, db):
    import main
    p, u, d = _rozliczajacy(db)
    r = client.post("/api/me/imprezy/rozlicz", headers=_h(u), json={"data": str(d), "pozycje": [
        {"forma": "gotowka", "kwota": 1000, "sfiskalizowane": True},
        {"forma": "gotowka", "kwota": 500, "sfiskalizowane": False},
        {"forma": "karta", "kwota": 2000},
        {"forma": "przelew", "kwota": 300},
    ]})
    assert r.status_code == 201
    # IMP = gotówka sfiskalizowana (1000) + karta (2000); niesfisk 500 i przelew 300 NIE wchodzą
    assert main.imp_dla_dnia(db, d) == {"gotowka_sfiskalizowana": 1000.0, "karta": 2000.0}
    # upsert: ponowny submit ZASTĘPUJE pozycje (nie dubluje)
    client.post("/api/me/imprezy/rozlicz", headers=_h(u), json={"data": str(d), "pozycje": [{"forma": "karta", "kwota": 999}]})
    assert db.query(models.RozliczenieImprezyPozycja).count() == 1
    assert main.imp_dla_dnia(db, d)["karta"] == 999.0


def test_tylko_wyznaczony_rozlicza_imprize(client, db):
    imprezy = factories.StanowiskoFactory(nazwa="Imprezy")
    p = factories.PracownikFactory(dzial="obsluga")
    u = factories.UserFactory(login="imp_no", rola="employee", pracownik=p)
    d = factories.dzien(0)
    db.add(models.PrzydzialZmiany(data=d, stanowisko_id=imprezy.id, pracownik_id=p.id, rozlicza_imprize=False))
    db.commit()
    assert client.post("/api/me/imprezy/rozlicz", headers=_h(u), json={"data": str(d), "pozycje": []}).status_code == 403


def test_rejestr_imprez_admin(client, admin_client, db):
    p, u, d = _rozliczajacy(db)
    client.post("/api/me/imprezy/rozlicz", headers=_h(u), json={"data": str(d), "pozycje": [
        {"forma": "gotowka", "kwota": 1000, "sfiskalizowane": True}, {"forma": "karta", "kwota": 2000}]})
    r = admin_client.get(f"/api/imprezy/rozliczenia?start={d}&end={d}")
    assert r.status_code == 200
    rozl = r.json()["rozliczenia"]
    assert len(rozl) == 1 and rozl[0]["suma_gotowka"] == 1000 and rozl[0]["suma_karta"] == 2000
    assert rozl[0]["pracownik"] == f"{p.imie} {p.nazwisko}"
    assert r.json()["razem"]["suma_karta"] == 2000
    assert client.get(f"/api/imprezy/rozliczenia?start={d}&end={d}", headers=_h(u)).status_code == 403  # nie-admin


def test_prefill_rozliczenia_imprezy(client, db):
    p, u, d = _rozliczajacy(db)
    pre = client.get(f"/api/me/imprezy/rozlicz?data={d}", headers=_h(u)).json()
    assert pre["moze"] is True and pre["pozycje"] == [] and pre["rewir"] == "Impreza (R2P)"
    client.post("/api/me/imprezy/rozlicz", headers=_h(u), json={"data": str(d), "pozycje": [{"forma": "karta", "kwota": 50}]})
    pre2 = client.get(f"/api/me/imprezy/rozlicz?data={d}", headers=_h(u)).json()
    assert len(pre2["pozycje"]) == 1 and pre2["pozycje"][0]["forma"] == "karta"
