"""Slice v2 S6: tor gościa online — najbliższy termin i magic-link.

Publiczne endpointy działają pod /api/online (osobny TestClient ``client``).
Daty testowe zawsze wskazują przyszły poniedziałek, więc zestaw nie starzeje się
wraz z kalendarzem.
"""

from datetime import date, timedelta

import models

_dzis = date.today()
_dni_do_poniedzialku = (7 - _dzis.weekday()) % 7 or 7
_poniedzialek = _dzis + timedelta(days=_dni_do_poniedzialku)
PON = str(_poniedzialek)
WTOREK = str(_poniedzialek + timedelta(days=1))


def _online_online(admin_client):
    assert admin_client.put("/api/lokal/config", json={"rezerwacje_online": True}).status_code == 200


def _stolik(admin_client, nazwa="S1", poj=4):
    r = admin_client.post("/api/stoliki", json={"nazwa": nazwa, "pojemnosc": poj})
    assert r.status_code == 201
    return r.json()["id"]


def _serwis(admin_client, dzien):
    assert admin_client.post("/api/godziny-otwarcia", json={
        "dzien_tygodnia": dzien, "godz_od": "12:00", "godz_do": "22:00",
        "krok_slotu_min": 60, "domyslny_turn_time_min": 120}).status_code == 201


def _online_rez(client, data, godz, osoby=2):
    r = client.post("/api/online/rezerwacja",
                    json={"data": data, "godz_od": godz, "liczba_osob": osoby, "nazwisko": "Gość Online"})
    assert r.status_code == 201, r.text
    return r.json()["token"]


# ── najbliższy termin ────────────────────────────────────────────────────────

def test_najblizszy_termin_zwraca_pierwszy_wolny(admin_client, client):
    _online_online(admin_client)
    _stolik(admin_client)
    _serwis(admin_client, 0)
    r = client.get(f"/api/online/najblizszy-termin?osoby=2&od={PON}").json()
    assert r["data"] == PON and r["slot"]["godz_od"] == "12:00"


def test_najblizszy_termin_pomija_blackout(admin_client, client):
    _online_online(admin_client)
    _stolik(admin_client)
    _serwis(admin_client, 0)          # poniedziałek
    _serwis(admin_client, 1)          # wtorek
    admin_client.post("/api/wyjatki-kalendarza", json={"data": PON, "typ": "blackout"})
    r = client.get(f"/api/online/najblizszy-termin?osoby=2&od={PON}").json()
    assert r["data"] == WTOREK        # PON zamknięty → pierwszy wolny to wtorek


def test_najblizszy_termin_null_gdy_brak(admin_client, client):
    _online_online(admin_client)      # brak stołów i godzin → brak slotów
    r = client.get(f"/api/online/najblizszy-termin?osoby=2&od={PON}&dni=3").json()
    assert r["data"] is None and r["slot"] is None


# ── magic-link: edycja ───────────────────────────────────────────────────────

def test_edytuj_zmienia_termin_i_realokuje(admin_client, client, db):
    _online_online(admin_client)
    _stolik(admin_client)
    _serwis(admin_client, _poniedzialek.weekday())
    token = _online_rez(client, PON, "18:00", 2)
    r = client.post(f"/api/online/rezerwacja/{token}/edytuj", json={"godz_od": "19:00", "liczba_osob": 3})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["godz_od"] == "19:00" and out["liczba_osob"] == 3
    assert out["stolik"] is None  # publiczny kontrakt nie ujawnia układu sali
    saved = db.query(models.Termin).filter_by(token_potwierdzenia=token).one()
    assert saved.stolik_id is not None


def test_edytuj_blackout_odrzucony(admin_client, client):
    _online_online(admin_client)
    _stolik(admin_client)
    _serwis(admin_client, _poniedzialek.weekday())
    _serwis(admin_client, (_poniedzialek + timedelta(days=1)).weekday())
    token = _online_rez(client, PON, "18:00", 2)
    admin_client.post("/api/wyjatki-kalendarza", json={"data": WTOREK, "typ": "blackout"})
    r = client.post(f"/api/online/rezerwacja/{token}/edytuj", json={"data": WTOREK})
    assert r.status_code == 409


def test_edytuj_respektuje_okno_anulacji(admin_client, client):
    admin_client.put("/api/lokal/config", json={"rezerwacje_online": True, "rez_anulacja_do_h": 48})
    _stolik(admin_client)
    blisko = date.today() + timedelta(days=1)    # jutro — wewnątrz okna 48 h
    _serwis(admin_client, blisko.weekday())
    token = _online_rez(client, str(blisko), "18:00", 2)
    r = client.post(f"/api/online/rezerwacja/{token}/edytuj", json={"liczba_osob": 3})
    assert r.status_code == 400


# ── magic-link: anulacja z egzekwowaniem polityki ────────────────────────────

def test_odwolaj_respektuje_okno_anulacji(admin_client, client):
    admin_client.put("/api/lokal/config", json={"rezerwacje_online": True, "rez_anulacja_do_h": 48})
    _stolik(admin_client)
    blisko = date.today() + timedelta(days=1)
    _serwis(admin_client, blisko.weekday())
    token = _online_rez(client, str(blisko), "18:00", 2)
    assert client.post(f"/api/online/rezerwacja/{token}/odwolaj").status_code == 400


def test_odwolaj_dozwolone_bez_polityki(admin_client, client):
    _online_online(admin_client)                       # rez_anulacja_do_h = 0 (domyślnie) → zawsze można
    _stolik(admin_client)
    _serwis(admin_client, _poniedzialek.weekday())
    token = _online_rez(client, PON, "18:00", 2)
    r = client.post(f"/api/online/rezerwacja/{token}/odwolaj")
    assert r.status_code == 200 and r.json()["status"] == "odwolana"
