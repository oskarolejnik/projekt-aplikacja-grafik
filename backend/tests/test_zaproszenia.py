"""Zaproszenia pracowników do kont (feedback UX): manager generuje link,
pracownik rejestruje się TYLKO z tokenu; otwarta rejestracja domyślnie wyłączona."""

from datetime import timedelta

from fastapi.testclient import TestClient

import deps
import main
import models
from deps import utcnow_naive


def _wylacz_otwarta_rejestracje(db):
    cfg = deps.get_lokal_config(db)
    cfg.rejestracja_otwarta = False
    db.commit()


def test_register_403_gdy_rejestracja_zamknieta(client, db):
    """Produkcyjny default: publiczny register odmawia i kieruje po link."""
    _wylacz_otwarta_rejestracje(db)
    r = client.post("/api/auth/register", json={
        "login": "nowyprac1", "haslo": "Haslo123!", "imie": "Jan", "nazwisko": "Nowy"})
    assert r.status_code == 403
    assert "zaproszeni" in r.json()["detail"].lower()


def test_admin_tworzy_zaproszenie_dla_nowego_pracownika(admin_client, db):
    r = admin_client.post("/api/zaproszenia", json={"imie": "Ola", "nazwisko": "Zaproszona"})
    assert r.status_code == 201
    z = r.json()
    assert z["status"] == "aktywne"
    assert z["link"] == f"/?zaproszenie={z['token']}"
    assert z["pracownik"] == "Ola Zaproszona"
    # Pracownik założony przy okazji, bez konta:
    prac = db.get(models.Pracownik, z["pracownik_id"])
    assert prac is not None and prac.aktywny


def test_pelny_przeplyw_rejestracji_z_linku(admin_client, db):
    """Zaproszenie → publiczny podgląd → rejestracja → konto przypięte + auto-login."""
    z = admin_client.post("/api/zaproszenia",
                          json={"imie": "Kuba", "nazwisko": "Linkowy", "rola": "kuchnia"}).json()

    anon = TestClient(main.app)   # świeży klient BEZ nagłówków admina (admin_client mutuje shared client)
    # Publiczny podgląd zaproszenia (ekran powitania):
    pod = anon.get(f"/api/online/zaproszenie/{z['token']}")
    assert pod.status_code == 200
    assert pod.json()["imie"] == "Kuba" and "nazwa_lokalu" in pod.json()

    # Rejestracja z tokenu:
    rej = anon.post(f"/api/online/zaproszenie/{z['token']}/rejestracja",
                    json={"login": "kubalinkowy", "haslo": "Haslo123!"})
    assert rej.status_code == 201
    dane = rej.json()
    assert dane["user"]["rola"] == "kuchnia"

    # Konto przypięte do pracownika z zaproszenia:
    u = db.query(models.User).filter(models.User.login == "kubalinkowy").first()
    assert u is not None and u.pracownik_id == z["pracownik_id"]

    # Auto-login działa (token z odpowiedzi otwiera przestrzeń /api/me/*):
    me = anon.get("/api/me/ogloszenia", headers={"Authorization": f"Bearer {dane['access_token']}"})
    assert me.status_code == 200

    # Token jednorazowy:
    drugi = anon.post(f"/api/online/zaproszenie/{z['token']}/rejestracja",
                      json={"login": "ktosinny1", "haslo": "Haslo123!"})
    assert drugi.status_code == 400


def test_wygasle_zaproszenie_odmawia(admin_client, db):
    z = admin_client.post("/api/zaproszenia", json={"imie": "Ewa", "nazwisko": "Spozniona"}).json()
    rec = db.query(models.Zaproszenie).filter_by(id=z["id"]).first()
    rec.wygasa_at = utcnow_naive() - timedelta(days=1)
    db.commit()
    anon = TestClient(main.app)
    assert anon.get(f"/api/online/zaproszenie/{z['token']}").status_code == 400
    r = anon.post(f"/api/online/zaproszenie/{z['token']}/rejestracja",
                  json={"login": "spozniona1", "haslo": "Haslo123!"})
    assert r.status_code == 400


def test_ponowne_zaproszenie_uniewaznia_stare(admin_client, db):
    a = admin_client.post("/api/zaproszenia", json={"imie": "Tom", "nazwisko": "Dwutokenowy"}).json()
    b = admin_client.post("/api/zaproszenia", json={"pracownik_id": a["pracownik_id"]}).json()
    assert b["pracownik_id"] == a["pracownik_id"] and b["token"] != a["token"]
    anon = TestClient(main.app)
    assert anon.get(f"/api/online/zaproszenie/{a['token']}").status_code == 404   # stary skasowany
    assert anon.get(f"/api/online/zaproszenie/{b['token']}").status_code == 200


def test_zaproszenie_dla_pracownika_z_kontem_400(admin_client, db):
    prac = models.Pracownik(imie="Ma", nazwisko="Konto", aktywny=True)
    db.add(prac); db.flush()
    db.add(models.User(login="makonto1", haslo_hash="x", rola="employee", pracownik_id=prac.id))
    db.commit()
    r = admin_client.post("/api/zaproszenia", json={"pracownik_id": prac.id})
    assert r.status_code == 400


def test_lista_i_uniewaznienie(admin_client, db):
    z = admin_client.post("/api/zaproszenia", json={"imie": "Iga", "nazwisko": "Dousuniecia"}).json()
    lista = admin_client.get("/api/zaproszenia").json()["zaproszenia"]
    assert any(x["id"] == z["id"] for x in lista)
    assert admin_client.delete(f"/api/zaproszenia/{z['id']}").status_code == 204
    anon = TestClient(main.app)
    assert anon.get(f"/api/online/zaproszenie/{z['token']}").status_code == 404


def test_zla_rola_zaproszenia_400(admin_client):
    r = admin_client.post("/api/zaproszenia", json={"imie": "Zly", "nazwisko": "Admin", "rola": "admin"})
    assert r.status_code == 400
