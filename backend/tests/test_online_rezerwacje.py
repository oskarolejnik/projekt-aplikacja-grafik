"""Publiczne rezerwacje online (widget): dostępność, tworzenie, token (confirm/cancel), anty-spam."""

import datetime as dt


def _fut(days=7):
    return dt.date.today() + dt.timedelta(days=days)


def _enable(admin_client, **extra):
    assert admin_client.put("/api/lokal/config", json={"rezerwacje_online": True, **extra}).status_code == 200


def test_online_wylaczone_404(admin_client, client):
    # domyślnie rezerwacje online wyłączone → publiczne endpointy 404
    assert client.get("/api/online/dostepnosc?data=2026-07-01").status_code == 404
    assert client.post("/api/online/rezerwacja", json={"data": "2026-07-01", "godz_od": "18:00", "nazwisko": "X"}).status_code == 404


def test_online_dostepnosc(admin_client, client):
    _enable(admin_client)
    fut = _fut()
    admin_client.post("/api/godziny-otwarcia", json={"dzien_tygodnia": fut.weekday(), "godz_od": "12:00", "godz_do": "22:00", "dlugosc_slotu_min": 120})
    admin_client.post("/api/stoliki", json={"nazwa": "S1", "pojemnosc": 4})
    r = client.get(f"/api/online/dostepnosc?data={fut.isoformat()}&osoby=2")
    assert r.status_code == 200
    sloty = r.json()["sloty"]
    assert len(sloty) >= 1
    assert sloty[0]["godz_od"] == "12:00" and sloty[0]["wolne"] == 1


def test_online_rezerwacja_flow(admin_client, client):
    _enable(admin_client)
    admin_client.post("/api/stoliki", json={"nazwa": "S1", "pojemnosc": 4})
    fut = _fut().isoformat()
    r = client.post("/api/online/rezerwacja", json={"data": fut, "godz_od": "18:00", "liczba_osob": 3,
                    "nazwisko": "Gość Online", "email": "gosc@example.pl"})
    assert r.status_code == 201, r.text
    body = r.json()
    token = body["token"]
    assert token and body["rezerwacja"]["status"] == "rezerwacja"   # auto-potwierdzenie off
    assert body["rezerwacja"]["stolik"] == "S1" and body["rezerwacja"]["godz_do"] == "20:00"
    # podgląd po tokenie
    g = client.get(f"/api/online/rezerwacja/{token}").json()
    assert g["nazwisko"] == "Gość Online"
    # potwierdzenie po tokenie
    assert client.post(f"/api/online/rezerwacja/{token}/potwierdz").json()["status"] == "potwierdzona"
    # odwołanie po tokenie
    assert client.post(f"/api/online/rezerwacja/{token}/odwolaj").json()["status"] == "odwolana"
    # zły token → 404
    assert client.get("/api/online/rezerwacja/zly-token").status_code == 404


def test_online_auto_potwierdzenie(admin_client, client):
    _enable(admin_client, rezerwacje_auto_potwierdzenie=True)
    admin_client.post("/api/stoliki", json={"nazwa": "S1", "pojemnosc": 4})
    r = client.post("/api/online/rezerwacja", json={"data": _fut().isoformat(), "godz_od": "18:00",
                    "liczba_osob": 2, "nazwisko": "Auto"})
    assert r.json()["rezerwacja"]["status"] == "potwierdzona"


def test_online_brak_stolika_409(admin_client, client):
    _enable(admin_client)
    admin_client.post("/api/stoliki", json={"nazwa": "S1", "pojemnosc": 2})
    r = client.post("/api/online/rezerwacja", json={"data": _fut().isoformat(), "godz_od": "18:00",
                    "liczba_osob": 5, "nazwisko": "ZaDuzo"})
    assert r.status_code == 409


def test_online_wstecz_400(admin_client, client):
    _enable(admin_client)
    admin_client.post("/api/stoliki", json={"nazwa": "S1", "pojemnosc": 4})
    assert client.post("/api/online/rezerwacja", json={"data": "2020-01-01", "godz_od": "18:00",
                       "liczba_osob": 2, "nazwisko": "Wstecz"}).status_code == 400


def test_online_limit_per_ip_bez_kontaktu(admin_client, client, monkeypatch):
    """Regresja anty-DoS: rezerwacje online BEZ telefonu/e-maila omijały limit per-kontakt
    (warunek `if telefon or email`). Teraz twardy limit per-IP/dzień łapie je niezależnie."""
    import main
    monkeypatch.setattr(main, "ONLINE_LIMIT_IP_DZIENNY", 3)
    _enable(admin_client)
    admin_client.post("/api/stoliki", json={"nazwa": "S1", "pojemnosc": 4})
    fut = _fut().isoformat()
    for g in ["10:00", "12:00", "14:00"]:                 # 3x bez kontaktu → mieszczą się w limicie IP
        assert client.post("/api/online/rezerwacja", json={"data": fut, "godz_od": g,
                           "liczba_osob": 2, "nazwisko": "Anon"}).status_code == 201
    r4 = client.post("/api/online/rezerwacja", json={"data": fut, "godz_od": "16:00",
                     "liczba_osob": 2, "nazwisko": "Anon"})   # 4-ta z tego samego IP → blokada
    assert r4.status_code == 429


def test_online_antyspam_429(admin_client, client):
    _enable(admin_client)
    admin_client.post("/api/stoliki", json={"nazwa": "S1", "pojemnosc": 4})
    fut = _fut().isoformat()
    for g in ["10:00", "12:00", "14:00", "16:00", "18:00"]:   # 5x, brak kolizji (sloty 120 min)
        rr = client.post("/api/online/rezerwacja", json={"data": fut, "godz_od": g, "liczba_osob": 2,
                         "nazwisko": "Spam", "telefon": "600100200"})
        assert rr.status_code == 201, rr.text
    r6 = client.post("/api/online/rezerwacja", json={"data": fut, "godz_od": "20:00", "liczba_osob": 2,
                     "nazwisko": "Spam", "telefon": "600100200"})
    assert r6.status_code == 429
