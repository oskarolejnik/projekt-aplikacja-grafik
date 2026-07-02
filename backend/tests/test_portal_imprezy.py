"""Portal klienta imprezy (roadmapa v2, TOP 2) — token, dane, goście, wątek, limity.

UWAGA na fixtures: admin_client mutuje nagłówki współdzielonego `client`, więc do wywołań
PUBLICZNYCH (bez tokena) używamy osobnego, świeżego klienta `anon`.
"""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

import main
import models
from deps import utcnow_naive
from routers import portal_imprezy as mod

JUTRO = date.today() + timedelta(days=30)


@pytest.fixture
def anon():
    """Klient bez JWT — publiczna strona portalu (allowlista /api/online/)."""
    with TestClient(main.app) as c:
        yield c


def _termin(db, **over):
    dane = dict(data=JUTRO, nazwisko="Nowakowie", typ="wesele", liczba_osob=100,
                sala="Duża", status="rezerwacja", zadatek=500.0, utworzono_at=utcnow_naive())
    dane.update(over)
    t = models.Termin(**dane)
    db.add(t); db.commit(); db.refresh(t)
    return t


def _portal(admin_client, tid):
    return admin_client.post(f"/api/terminy/{tid}/portal").json()


# ── Token (admin) ────────────────────────────────────────────────────────────

def test_generowanie_i_regeneracja_tokenu(admin_client, anon, db):
    t = _termin(db)
    p1 = _portal(admin_client, t.id)
    assert p1["url"] == f"/?impreza={p1['token']}" and len(p1["token"]) >= 24
    p2 = _portal(admin_client, t.id)                      # regeneracja
    assert p2["token"] != p1["token"]
    assert anon.get(f"/api/online/imprezy/{p1['token']}").status_code == 404  # stary unieważniony
    assert anon.get(f"/api/online/imprezy/{p2['token']}").status_code == 200


def test_generowanie_wymaga_logowania(anon, db):
    t = _termin(db)
    assert anon.post(f"/api/terminy/{t.id}/portal").status_code == 401   # role_guard


def test_generowanie_404_dla_brakujacego_terminu(admin_client):
    assert admin_client.post("/api/terminy/99999/portal").status_code == 404


def test_wylaczenie_portalu(admin_client, anon, db):
    t = _termin(db)
    tok = _portal(admin_client, t.id)["token"]
    assert admin_client.delete(f"/api/terminy/{t.id}/portal").status_code == 204
    assert anon.get(f"/api/online/imprezy/{tok}").status_code == 404


# ── Publiczny odczyt ─────────────────────────────────────────────────────────

def test_dane_portalu(admin_client, anon, db):
    t = _termin(db)
    db.add(models.KpZadatek(id="test-guid-0001", kwota=1000.0, data=date.today(), termin_id=t.id))
    db.commit()
    tok = _portal(admin_client, t.id)["token"]
    body = anon.get(f"/api/online/imprezy/{tok}").json()
    assert body["termin"]["nazwisko"] == "Nowakowie"
    assert body["termin"]["liczba_osob"] == 100
    assert body["termin"]["zadatek_kp"] == 1000.0
    assert body["termin"]["edycja_gosci"] is True
    assert body["wiadomosci"] == []


def test_zly_token_404(anon):
    assert anon.get("/api/online/imprezy/nie-ma-takiego").status_code == 404


# ── Liczba gości ─────────────────────────────────────────────────────────────

def test_aktualizacja_gosci_z_notka_systemowa(admin_client, anon, db):
    t = _termin(db)
    tok = _portal(admin_client, t.id)["token"]
    r = anon.put(f"/api/online/imprezy/{tok}/goscie", json={"liczba_osob": 130})
    assert r.status_code == 200 and r.json()["liczba_osob"] == 130
    body = anon.get(f"/api/online/imprezy/{tok}").json()
    assert body["termin"]["liczba_osob"] == 130
    assert any(w["autor"] == "system" and "100 → 130" in w["tresc"] for w in body["wiadomosci"])


def test_goscie_walidacja_i_status(admin_client, anon, db):
    t = _termin(db)
    tok = _portal(admin_client, t.id)["token"]
    assert anon.put(f"/api/online/imprezy/{tok}/goscie", json={"liczba_osob": 0}).status_code == 400
    assert anon.put(f"/api/online/imprezy/{tok}/goscie", json={"liczba_osob": 5000}).status_code == 400
    t2 = _termin(db, status="odwolana")
    tok2 = _portal(admin_client, t2.id)["token"]
    assert anon.put(f"/api/online/imprezy/{tok2}/goscie", json={"liczba_osob": 50}).status_code == 409


def test_goscie_synchronizuja_sparowana_impreze(admin_client, anon, db):
    t = _termin(db, ical_uid="uid-123")
    imp = models.Impreza(data=t.data, klient="Nowakowie", liczba_osob=100, sala="Duża",
                         sciezka_pliku="ical:uid-123")
    db.add(imp); db.commit()
    tok = _portal(admin_client, t.id)["token"]
    anon.put(f"/api/online/imprezy/{tok}/goscie", json={"liczba_osob": 150})
    db.refresh(imp)
    assert imp.liczba_osob == 150     # obsada przeliczy się z odświeżonych wymagań


# ── Wątek wiadomości ─────────────────────────────────────────────────────────

def test_watek_klient_i_lokal(admin_client, anon, db):
    t = _termin(db)
    tok = _portal(admin_client, t.id)["token"]
    assert anon.post(f"/api/online/imprezy/{tok}/wiadomosci",
                     json={"tresc": "Czy możemy dostawić stolik dla dzieci?"}).status_code == 201
    assert admin_client.post(f"/api/terminy/{t.id}/wiadomosci",
                             json={"tresc": "Oczywiście, dostawimy."}).status_code == 201
    watek = anon.get(f"/api/online/imprezy/{tok}").json()["wiadomosci"]
    assert [w["autor"] for w in watek] == ["klient", "lokal"]
    assert admin_client.get(f"/api/terminy/{t.id}/wiadomosci").json() == watek


def test_pusta_wiadomosc_400(admin_client, anon, db):
    t = _termin(db)
    tok = _portal(admin_client, t.id)["token"]
    assert anon.post(f"/api/online/imprezy/{tok}/wiadomosci", json={"tresc": "   "}).status_code == 400


def test_limit_ip_na_publicznych_postach(admin_client, anon, db, monkeypatch):
    monkeypatch.setattr(mod, "PORTAL_LIMIT_IP_DZIENNY", 2)
    t = _termin(db)
    tok = _portal(admin_client, t.id)["token"]
    for _ in range(2):
        assert anon.post(f"/api/online/imprezy/{tok}/wiadomosci",
                         json={"tresc": "ping"}).status_code == 201
    assert anon.post(f"/api/online/imprezy/{tok}/wiadomosci",
                     json={"tresc": "ping"}).status_code == 429


# ═════════════════════════════════════════════════════════════════════════════
# ETAP 2: menu + raty
# ═════════════════════════════════════════════════════════════════════════════

def _oferta(admin_client, **over):
    dane = dict(nazwa="Menu Klasyczne", opis="3 dania + bufet", cena_od_osoby=250.0, aktywna=True)
    dane.update(over)
    return admin_client.post("/api/oferty-menu", json=dane)


def test_oferty_menu_crud(admin_client):
    o = _oferta(admin_client).json()
    assert o["cena_od_osoby"] == 250.0 and o["aktywna"] is True
    r = admin_client.put(f"/api/oferty-menu/{o['id']}", json={
        "nazwa": "Menu Premium", "opis": "", "cena_od_osoby": 320, "aktywna": False})
    assert r.json()["nazwa"] == "Menu Premium" and r.json()["aktywna"] is False
    assert admin_client.delete(f"/api/oferty-menu/{o['id']}").status_code == 204
    assert admin_client.get("/api/oferty-menu").json() == []
    assert _oferta(admin_client, nazwa="  ").status_code == 400


def test_portal_pokazuje_tylko_aktywne_oferty(admin_client, anon, db):
    t = _termin(db)
    tok = _portal(admin_client, t.id)["token"]
    aktywna = _oferta(admin_client).json()
    _oferta(admin_client, nazwa="Wycofane", aktywna=False)
    body = anon.get(f"/api/online/imprezy/{tok}").json()
    assert [o["id"] for o in body["oferty_menu"]] == [aktywna["id"]]
    assert body["menu_oferta_id"] is None


def test_klient_wybiera_menu_z_notka(admin_client, anon, db):
    t = _termin(db)
    tok = _portal(admin_client, t.id)["token"]
    o = _oferta(admin_client).json()
    r = anon.post(f"/api/online/imprezy/{tok}/menu", json={"oferta_id": o["id"]})
    assert r.status_code == 200 and r.json()["menu_oferta_id"] == o["id"]
    body = anon.get(f"/api/online/imprezy/{tok}").json()
    assert body["menu_oferta_id"] == o["id"]
    assert any(w["autor"] == "system" and "Menu Klasyczne" in w["tresc"] for w in body["wiadomosci"])


def test_wybor_menu_walidacje(admin_client, anon, db):
    t = _termin(db)
    tok = _portal(admin_client, t.id)["token"]
    nieaktywna = _oferta(admin_client, aktywna=False).json()
    assert anon.post(f"/api/online/imprezy/{tok}/menu", json={"oferta_id": 999}).status_code == 404
    assert anon.post(f"/api/online/imprezy/{tok}/menu", json={"oferta_id": nieaktywna["id"]}).status_code == 404
    t2 = _termin(db, status="odwolana")
    tok2 = _portal(admin_client, t2.id)["token"]
    o = _oferta(admin_client).json()
    assert anon.post(f"/api/online/imprezy/{tok2}/menu", json={"oferta_id": o["id"]}).status_code == 409


def test_usuniecie_oferty_odpina_wybory(admin_client, anon, db):
    t = _termin(db)
    tok = _portal(admin_client, t.id)["token"]
    o = _oferta(admin_client).json()
    anon.post(f"/api/online/imprezy/{tok}/menu", json={"oferta_id": o["id"]})
    admin_client.delete(f"/api/oferty-menu/{o['id']}")
    assert anon.get(f"/api/online/imprezy/{tok}").json()["menu_oferta_id"] is None


def test_raty_crud_i_portal(admin_client, anon, db):
    t = _termin(db)
    tok = _portal(admin_client, t.id)["token"]
    r1 = admin_client.post(f"/api/terminy/{t.id}/raty", json={
        "nazwa": "Zadatek", "kwota": 1000, "termin_platnosci": str(JUTRO - timedelta(days=20))}).json()
    admin_client.post(f"/api/terminy/{t.id}/raty", json={
        "nazwa": "II rata", "kwota": 3000, "termin_platnosci": str(JUTRO - timedelta(days=5))})
    body = anon.get(f"/api/online/imprezy/{tok}").json()
    assert [x["nazwa"] for x in body["raty"]] == ["Zadatek", "II rata"]   # sortowanie po terminie
    # lokal oznacza zapłaconą → notka systemowa w portalu
    admin_client.put(f"/api/raty/{r1['id']}", json={
        "nazwa": "Zadatek", "kwota": 1000, "termin_platnosci": str(JUTRO - timedelta(days=20)),
        "zaplacona": True})
    body = anon.get(f"/api/online/imprezy/{tok}").json()
    assert body["raty"][0]["zaplacona"] is True and body["raty"][0]["zaplacona_at"]
    assert any(w["autor"] == "system" and "Zadatek" in w["tresc"] and "zapłaconą" in w["tresc"]
               for w in body["wiadomosci"])
    assert admin_client.delete(f"/api/raty/{r1['id']}").status_code == 204
    assert len(admin_client.get(f"/api/terminy/{t.id}/raty").json()) == 1


def test_raty_admin_only(anon, db):
    t = _termin(db)
    assert anon.get(f"/api/terminy/{t.id}/raty").status_code == 401
    assert anon.post(f"/api/terminy/{t.id}/raty", json={"nazwa": "X"}).status_code == 401
