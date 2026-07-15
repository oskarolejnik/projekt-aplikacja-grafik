"""Slice v2 S2: egzekwowanie polityki rezerwacji online (okno wyprzedzenia, cutoff, min/max grupa,
blackout) + bufor sprzątania w rdzeniu kolizji. Daty względne do dziś (deterministyczne)."""

import datetime as dt

DZIS = dt.date.today()


def _enable(admin_client):
    assert admin_client.put("/api/lokal/config", json={"rezerwacje_online": True}).status_code == 200


def _setup_dzis(admin_client, pojemnosc=4):
    """Stolik + serwis dla dnia tygodnia DZIS (żeby DZIS i DZIS+7 miały okno)."""
    admin_client.post("/api/stoliki", json={"nazwa": "S1", "pojemnosc": pojemnosc})
    _serwis_dla_daty(admin_client, DZIS)


def _serwis_dla_daty(admin_client, data):
    response = admin_client.post("/api/godziny-otwarcia", json={
        "dzien_tygodnia": data.weekday(),
        "godz_od": "08:00",
        "godz_do": "23:00",
        "krok_slotu_min": 60,
        "domyslny_turn_time_min": 120,
    })
    assert response.status_code == 201, response.text


def _rez(client, data, osoby=2, godz="18:00"):
    return client.post("/api/online/rezerwacja",
                       json={"data": str(data), "godz_od": godz, "liczba_osob": osoby, "nazwisko": "X"})


def test_okno_wyprzedzenia(admin_client, client):
    _enable(admin_client); _setup_dzis(admin_client)
    admin_client.put("/api/lokal/config", json={"rez_okno_wyprzedzenia_dni": 7})
    assert _rez(client, DZIS + dt.timedelta(days=14)).status_code == 400   # za daleko
    granica = _rez(client, DZIS + dt.timedelta(days=7))
    assert granica.status_code == 201, granica.text                       # dokładnie w oknie
    poza = client.get(f"/api/online/dostepnosc?data={DZIS + dt.timedelta(days=20)}&osoby=2").json()
    assert poza["sloty"] == []


def test_cutoff(admin_client, client):
    _enable(admin_client); _setup_dzis(admin_client)
    admin_client.put("/api/lokal/config", json={"rez_cutoff_min": 1440})   # 24 h przed
    assert _rez(client, DZIS).status_code == 409                            # dziś < 24 h → za późno
    assert _rez(client, DZIS + dt.timedelta(days=7)).status_code == 201     # za tydzień → OK


def test_min_max_grupa(admin_client, client):
    _enable(admin_client); _setup_dzis(admin_client, pojemnosc=12)
    admin_client.put("/api/lokal/config", json={"rez_min_grupa_online": 2, "rez_max_grupa_online": 6})
    d7 = DZIS + dt.timedelta(days=7)
    assert _rez(client, d7, osoby=1).status_code == 400    # < min
    assert _rez(client, d7, osoby=8).status_code == 400    # > max
    assert _rez(client, d7, osoby=4).status_code == 201    # w zakresie


def test_blackout_blokuje_rezerwacje_online(admin_client, client):
    _enable(admin_client); _setup_dzis(admin_client)
    d7 = DZIS + dt.timedelta(days=7)
    admin_client.post("/api/wyjatki-kalendarza", json={"data": str(d7), "typ": "blackout"})
    assert _rez(client, d7).status_code == 409             # dzień zamknięty


def test_bufor_miedzy_rezerwacjami(admin_client):
    # bufor działa też w torze admina (fizyka sali). Bez serwisu → turn-time DOMYSLNY 120 min.
    admin_client.put("/api/lokal/config", json={"rez_bufor_min": 30})
    s = admin_client.post("/api/stoliki", json={"nazwa": "S1", "pojemnosc": 4}).json()
    d = "2026-07-13"

    def rez(godz, nazw):
        return admin_client.post("/api/rezerwacje-stolik", json={"data": d, "godz_od": godz,
                                 "stolik_id": s["id"], "liczba_osob": 2, "nazwisko": nazw})

    assert rez("18:00", "A").status_code == 201            # 18:00–20:00
    assert rez("20:15", "B").status_code == 409            # bez bufora OK, z buforem 30 min koliduje (do 20:30)
    assert rez("20:45", "C").status_code == 201            # poza buforem → wolne


def test_bez_polityki_zachowanie_bez_zmian(admin_client, client):
    # regresja: wszystkie pola polityki = default (0/1) → tor online działa jak dotąd.
    _enable(admin_client); _setup_dzis(admin_client)
    data_rezerwacji = DZIS + dt.timedelta(days=3)
    _serwis_dla_daty(admin_client, data_rezerwacji)
    assert _rez(client, data_rezerwacji).status_code == 201
