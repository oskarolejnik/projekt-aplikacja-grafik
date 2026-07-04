"""Zamówienia sprzątaczki: tylko dział techniczny z kwalifikacją „Sprzątaczka" składa formularz,
obieg statusów nowe→odczytane→zamowione, push (nowe→admini, status→autorka), zdjęcie (flaga + pobranie),
auto-utworzenie kwalifikacji Sprzątaczka/Stróż."""

import main
import models
import factories
from auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(u)}"}


def _sprzataczka(db, login="sprz1"):
    spr = db.query(models.Stanowisko).filter_by(nazwa="Sprzątaczka").first() or factories.StanowiskoFactory(nazwa="Sprzątaczka")
    p = factories.PracownikFactory(imie="Pani", nazwisko="Czysto", dzial="techniczny")
    p.kwalifikacje = [spr]
    db.commit()
    u = factories.UserFactory(login=login, rola="employee", pracownik=p)
    return p, u


def test_ensure_kwalifikacje_techniczne(admin_client, db):
    admin_client.get("/api/stanowiska")   # endpoint dba o istnienie kwalifikacji
    nazwy = {s.nazwa for s in db.query(models.Stanowisko).all()}
    assert "Sprzątaczka" in nazwy and "Stróż" in nazwy


def test_sprzataczka_tworzy_i_widzi_swoje(client, db):
    p, u = _sprzataczka(db)
    r = client.post("/api/me/zamowienia", headers=_h(u),
                    json={"nazwa": "Płyn do podłóg", "ilosc": "5 l", "notatka": "kończy się"})
    assert r.status_code == 201
    r = client.get("/api/me/zamowienia", headers=_h(u))
    z = r.json()["zamowienia"][0]
    assert z["nazwa"] == "Płyn do podłóg" and z["ilosc"] == "5 l"
    assert z["status"] == "nowe" and z["ma_zdjecie"] is False and z["pracownik"] == "Pani Czysto"


def test_tylko_sprzataczka_moze_skladac(client, db):
    # techniczny BEZ kwalifikacji Sprzątaczka
    tech = factories.PracownikFactory(dzial="techniczny")
    ut = factories.UserFactory(login="techx", rola="employee", pracownik=tech)
    assert client.post("/api/me/zamowienia", headers=_h(ut), json={"nazwa": "X"}).status_code == 403
    # obsługa
    obs = factories.PracownikFactory(dzial="obsluga")
    uo = factories.UserFactory(login="obsx", rola="employee", pracownik=obs)
    assert client.post("/api/me/zamowienia", headers=_h(uo), json={"nazwa": "X"}).status_code == 403
    assert client.get("/api/me/zamowienia", headers=_h(uo)).status_code == 403


def test_tworzenie_pcha_push_do_adminow(client, db, monkeypatch):
    from routers import moje   # POST /api/me/zamowienia mieszka w routers/moje.py (dekompozycja main)
    licznik = {"n": 0}
    monkeypatch.setattr(moje, "wyslij_push_do_adminow",
                        lambda *a, **k: licznik.__setitem__("n", licznik["n"] + 1) or 1)
    p, u = _sprzataczka(db)
    client.post("/api/me/zamowienia", headers=_h(u), json={"nazwa": "Mop"})
    assert licznik["n"] == 1


def test_admin_lista_i_zmiana_statusu_pcha_push_do_autorki(client, admin_client, db, monkeypatch):
    pushe = []
    monkeypatch.setattr(main, "wyslij_push_do_pracownika",
                        lambda db, pid, t, tr, url="/": pushe.append((pid, tr)) or 1)
    p, u = _sprzataczka(db)
    zid = client.post("/api/me/zamowienia", headers=_h(u), json={"nazwa": "Worki"}).json()["id"]
    # admin widzi zamówienie z autorką
    r = admin_client.get("/api/zamowienia")
    assert any(z["id"] == zid and z["pracownik"] == "Pani Czysto" for z in r.json()["zamowienia"])
    # nowe -> odczytane -> zamowione (push do autorki za każdym razem)
    assert admin_client.put(f"/api/zamowienia/{zid}/status", json={"status": "odczytane"}).status_code == 204
    assert admin_client.put(f"/api/zamowienia/{zid}/status", json={"status": "zamowione"}).status_code == 204
    db.expire_all()
    z = db.get(models.ZamowienieSprzataczki, zid)
    assert z.status == "zamowione" and z.odczytano_at is not None and z.zamowiono_at is not None
    assert len(pushe) == 2 and all(pid == p.id for pid, _ in pushe)


def test_zdjecie_flaga_i_pobranie(client, db):
    p, u = _sprzataczka(db)
    img = "data:image/png;base64,AAAABBBB"
    zid = client.post("/api/me/zamowienia", headers=_h(u),
                      json={"nazwa": "Rękawice", "zdjecie": img}).json()["id"]
    z = client.get("/api/me/zamowienia", headers=_h(u)).json()["zamowienia"][0]
    assert z["ma_zdjecie"] is True
    r = client.get(f"/api/me/zamowienia/{zid}/zdjecie", headers=_h(u))
    assert r.status_code == 200 and r.json()["zdjecie"] == img


def test_login_zwraca_flage_sprzataczki(client, db):
    _sprzataczka(db, login="sprzlog")
    r = client.post("/api/auth/login", json={"login": "sprzlog", "haslo": "Haslo123!"})
    assert r.status_code == 200 and r.json()["user"]["sprzataczka"] is True
    tech = factories.PracownikFactory(dzial="techniczny")   # techniczny bez kwalifikacji
    factories.UserFactory(login="techlog2", rola="employee", pracownik=tech)
    r = client.post("/api/auth/login", json={"login": "techlog2", "haslo": "Haslo123!"})
    assert r.json()["user"]["sprzataczka"] is False


def test_zamowienia_oversight_tylko_admin(client, db):
    """Listę wszystkich i zmianę statusu widzi tylko admin (middleware)."""
    p, u = _sprzataczka(db)   # sprzątaczka NIE ma dostępu do /api/zamowienia (to panel admina)
    assert client.get("/api/zamowienia", headers=_h(u)).status_code == 403
