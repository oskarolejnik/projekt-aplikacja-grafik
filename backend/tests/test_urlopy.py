"""Urlopy (obsługa): wniosek tylko dla obsługi, akceptacja/odrzucenie przez admina,
push w obie strony, wycofanie tylko oczekującego, a zaakceptowany urlop BLOKUJE auto-przydział."""

from datetime import datetime, time

import main
import models
import factories
from algorithm import auto_assign
from auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(u)}"}


def _obsluga(db, login="obs1"):
    p = factories.PracownikFactory(imie="Anna", nazwisko="Obslugowa", dzial="obsluga")
    u = factories.UserFactory(login=login, rola="employee", pracownik=p)
    return p, u


def test_obsluga_sklada_wniosek(client, db):
    p, u = _obsluga(db)
    r = client.post("/api/me/urlopy", headers=_h(u),
                    json={"start": str(factories.dzien(0)), "koniec": str(factories.dzien(3)), "powod": "wakacje"})
    assert r.status_code == 201
    lista = client.get("/api/me/urlopy", headers=_h(u)).json()["urlopy"]
    assert len(lista) == 1 and lista[0]["status"] == "oczekuje" and lista[0]["powod"] == "wakacje"


def test_tylko_obsluga_sklada(client, db):
    for dzial in ("kuchnia", "techniczny"):
        p = factories.PracownikFactory(dzial=dzial)
        u = factories.UserFactory(login=f"u_{dzial}", rola="employee", pracownik=p)
        r = client.post("/api/me/urlopy", headers=_h(u),
                        json={"start": str(factories.dzien(0)), "koniec": str(factories.dzien(0))})
        assert r.status_code == 403


def test_koniec_przed_startem_400(client, db):
    p, u = _obsluga(db)
    r = client.post("/api/me/urlopy", headers=_h(u),
                    json={"start": str(factories.dzien(3)), "koniec": str(factories.dzien(1))})
    assert r.status_code == 400


def test_wniosek_pcha_push_do_adminow(client, db, monkeypatch):
    n = {"c": 0}
    monkeypatch.setattr(main, "wyslij_push_do_adminow", lambda *a, **k: n.__setitem__("c", n["c"] + 1) or 1)
    p, u = _obsluga(db)
    client.post("/api/me/urlopy", headers=_h(u),
                json={"start": str(factories.dzien(0)), "koniec": str(factories.dzien(0))})
    assert n["c"] == 1


def test_admin_akceptuje_pcha_push_do_pracownika(client, admin_client, db, monkeypatch):
    pushe = []
    monkeypatch.setattr(main, "wyslij_push_do_pracownika", lambda db, pid, t, tr, url="/": pushe.append(pid) or 1)
    p, u = _obsluga(db)
    uid = client.post("/api/me/urlopy", headers=_h(u),
                      json={"start": str(factories.dzien(0)), "koniec": str(factories.dzien(2))}).json()["id"]
    assert any(x["id"] == uid and x["pracownik"] == "Anna Obslugowa"
               for x in admin_client.get("/api/urlopy").json()["urlopy"])
    assert admin_client.put(f"/api/urlopy/{uid}/status", json={"status": "zaakceptowany"}).status_code == 204
    db.expire_all()
    assert db.get(models.Urlop, uid).status == "zaakceptowany"
    assert pushe == [p.id]


def test_wycofanie_tylko_oczekujacego(client, admin_client, db):
    p, u = _obsluga(db)
    uid = client.post("/api/me/urlopy", headers=_h(u),
                      json={"start": str(factories.dzien(0)), "koniec": str(factories.dzien(0))}).json()["id"]
    admin_client.put(f"/api/urlopy/{uid}/status", json={"status": "zaakceptowany"})
    assert client.delete(f"/api/me/urlopy/{uid}", headers=_h(u)).status_code == 400   # rozpatrzony — nie
    uid2 = client.post("/api/me/urlopy", headers=_h(u),
                       json={"start": str(factories.dzien(5)), "koniec": str(factories.dzien(5))}).json()["id"]
    assert client.delete(f"/api/me/urlopy/{uid2}", headers=_h(u)).status_code == 204   # oczekujący — tak


def test_zaakceptowany_urlop_blokuje_auto_przydzial(db):
    sala = factories.StanowiskoFactory(nazwa="Sala")
    p = factories.PracownikFactory(dzial="obsluga")
    p.kwalifikacje = [sala]
    db.commit()
    d = factories.dzien(0)
    factories.DyspozycjaFactory(pracownik=p, data=d, dostepnosc=True, godz_od=None)  # dostępny
    factories.WymaganieFactory(stanowisko=sala, data=d, liczba_osob=1)
    # bez urlopu -> obsadzony
    w1 = auto_assign(db, d, d)
    assert w1["przydzielone"] == 1
    db.query(models.PrzydzialZmiany).delete(synchronize_session=False)
    db.commit()
    # z zaakceptowanym urlopem -> NIE obsadzony (niedobór)
    db.add(models.Urlop(pracownik_id=p.id, start=d, koniec=d, status="zaakceptowany", utworzono_at=datetime.utcnow()))
    db.commit()
    w2 = auto_assign(db, d, d)
    assert w2["przydzielone"] == 0 and len(w2["niedobory"]) == 1


def test_oczekujacy_urlop_NIE_blokuje(db):
    """Tylko ZAAKCEPTOWANY urlop blokuje — oczekujący jeszcze nie."""
    sala = factories.StanowiskoFactory(nazwa="Sala")
    p = factories.PracownikFactory(dzial="obsluga")
    p.kwalifikacje = [sala]
    db.commit()
    d = factories.dzien(0)
    factories.DyspozycjaFactory(pracownik=p, data=d, dostepnosc=True, godz_od=None)
    factories.WymaganieFactory(stanowisko=sala, data=d, liczba_osob=1)
    db.add(models.Urlop(pracownik_id=p.id, start=d, koniec=d, status="oczekuje", utworzono_at=datetime.utcnow()))
    db.commit()
    assert auto_assign(db, d, d)["przydzielone"] == 1


def test_oversight_tylko_admin(client, db):
    p, u = _obsluga(db)
    assert client.get("/api/urlopy", headers=_h(u)).status_code == 403
