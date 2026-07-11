"""Moduł rezerwacji (MVP): stoliki, godziny otwarcia, rezerwacje stolika na encji Termin.

Pokrywa: CRUD stolika, flagę modul_rezerwacje (403 gdy off), tworzenie rezerwacji + walidację
pojemności i kolizji slotów, przejścia statusów, zwolnienie slotu po odwołaniu, separację od
kalendarza imprez (rodzaj=impreza nie wycieka do listy rezerwacji stolików).
"""


def _stolik(admin_client, nazwa="S1", pojemnosc=4):
    r = admin_client.post("/api/stoliki", json={"nazwa": nazwa, "pojemnosc": pojemnosc})
    assert r.status_code == 201, r.text
    return r.json()


def _rez(admin_client, **kw):
    return admin_client.post("/api/rezerwacje-stolik", json=kw)


def test_stolik_crud(admin_client):
    s = _stolik(admin_client)
    assert s["nazwa"] == "S1" and s["pojemnosc"] == 4
    assert any(x["id"] == s["id"] for x in admin_client.get("/api/stoliki").json()["stoliki"])
    r = admin_client.put(f"/api/stoliki/{s['id']}", json={"nazwa": "S1b", "pojemnosc": 6})
    assert r.status_code == 200 and r.json()["pojemnosc"] == 6
    assert admin_client.delete(f"/api/stoliki/{s['id']}").status_code == 204


def test_nie_mozna_usunac_stolika_z_historii_rezerwacji(admin_client):
    s = _stolik(admin_client)
    rid = _rez(admin_client, data="2026-01-01", godz_od="18:00", stolik_id=s["id"],
               nazwisko="Historia", liczba_osob=2).json()["id"]
    assert admin_client.post(
        f"/api/rezerwacje-stolik/{rid}/status", json={"status": "odbyla"}).status_code == 200

    assert admin_client.delete(f"/api/stoliki/{s['id']}").status_code == 409
    assert any(x["id"] == s["id"] for x in admin_client.get("/api/stoliki").json()["stoliki"])


def test_config_zawiera_flage_modul_rezerwacje(admin_client):
    # Regresja: LokalConfigOut musi zwracać modul_rezerwacje (inaczej front nie pokaże zakładki).
    cfg = admin_client.get("/api/lokal/config").json()
    assert cfg["modul_rezerwacje"] is True


def test_modul_off_daje_403(admin_client):
    assert admin_client.put("/api/lokal/config", json={"modul_rezerwacje": False}).status_code == 200
    assert admin_client.get("/api/stoliki").status_code == 403
    assert admin_client.get("/api/rezerwacje-stolik?start=2026-07-01&end=2026-07-31").status_code == 403


def test_rezerwacja_tworzenie_i_pojemnosc(admin_client):
    s = _stolik(admin_client, pojemnosc=4)
    r = _rez(admin_client, data="2026-07-01", godz_od="18:00", stolik_id=s["id"],
             liczba_osob=4, nazwisko="Kowalski", telefon="600100200")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "potwierdzona"
    assert body["godz_do"] == "20:00"          # +120 min (domyślny slot)
    # przekroczona pojemność
    r2 = _rez(admin_client, data="2026-07-01", godz_od="12:00", stolik_id=s["id"],
              liczba_osob=5, nazwisko="ZaDuzo")
    assert r2.status_code == 400
    assert _rez(admin_client, data="2026-07-01", godz_od="12:00",
                liczba_osob=0, nazwisko="Zero").status_code == 422


def test_kolizja_slotow(admin_client):
    s = _stolik(admin_client)
    s2 = _stolik(admin_client, nazwa="S2")
    base = dict(data="2026-07-05", stolik_id=s["id"], nazwisko="A", liczba_osob=2)
    assert _rez(admin_client, **base, godz_od="18:00").status_code == 201   # 18:00–20:00
    assert _rez(admin_client, **base, godz_od="19:00").status_code == 409   # nachodzi
    assert _rez(admin_client, **base, godz_od="20:00").status_code == 201   # styk granicy = OK
    # inny stolik w tym samym czasie = OK
    assert _rez(admin_client, data="2026-07-05", stolik_id=s2["id"], nazwisko="B",
                liczba_osob=2, godz_od="18:00").status_code == 201


def test_przejscia_statusow(admin_client):
    s = _stolik(admin_client)
    rid = _rez(admin_client, data="2026-07-06", godz_od="18:00", stolik_id=s["id"],
               nazwisko="A", liczba_osob=2).json()["id"]
    # potwierdzona → odbyla OK
    assert admin_client.post(f"/api/rezerwacje-stolik/{rid}/status", json={"status": "odbyla"}).status_code == 200
    # odbyla terminalny → kolejne przejście 409
    assert admin_client.post(f"/api/rezerwacje-stolik/{rid}/status", json={"status": "odwolana"}).status_code == 409
    # nieznany status → 400
    rid2 = _rez(admin_client, data="2026-07-06", godz_od="12:00", stolik_id=s["id"],
                nazwisko="B", liczba_osob=2).json()["id"]
    assert admin_client.post(f"/api/rezerwacje-stolik/{rid2}/status", json={"status": "xyz"}).status_code == 400


def test_odwolanie_zwalnia_slot(admin_client):
    s = _stolik(admin_client)
    rid = _rez(admin_client, data="2026-07-07", godz_od="18:00", stolik_id=s["id"],
               nazwisko="A", liczba_osob=2).json()["id"]
    assert admin_client.post(f"/api/rezerwacje-stolik/{rid}/status", json={"status": "odwolana"}).status_code == 200
    # ten sam slot znów wolny
    assert _rez(admin_client, data="2026-07-07", godz_od="18:00", stolik_id=s["id"],
                nazwisko="B", liczba_osob=2).status_code == 201


def test_edycja_rewaliduje_kolizje(admin_client):
    s = _stolik(admin_client)
    _rez(admin_client, data="2026-07-09", godz_od="18:00", stolik_id=s["id"], nazwisko="A", liczba_osob=2)
    rid = _rez(admin_client, data="2026-07-09", godz_od="21:00", stolik_id=s["id"],
               nazwisko="B", liczba_osob=2).json()["id"]
    # przesunięcie B na 19:00 koliduje z A (18:00–20:00)
    r = admin_client.put(f"/api/rezerwacje-stolik/{rid}", json={"data": "2026-07-09", "godz_od": "19:00",
                         "stolik_id": s["id"], "nazwisko": "B", "liczba_osob": 2})
    assert r.status_code == 409


def test_rezerwacje_filtruja_tylko_stoliki(admin_client):
    s = _stolik(admin_client)
    # wesele przez kalendarz imprez (rodzaj=impreza domyślnie) — nie powinno wejść do listy rezerwacji
    assert admin_client.post("/api/terminy", json={"data": "2026-07-08", "nazwisko": "Wesele X"}).status_code == 201
    _rez(admin_client, data="2026-07-08", godz_od="18:00", stolik_id=s["id"], nazwisko="Stolik Y", liczba_osob=2)
    lista = admin_client.get("/api/rezerwacje-stolik?start=2026-07-08&end=2026-07-08").json()["rezerwacje"]
    assert len(lista) == 1 and lista[0]["nazwisko"] == "Stolik Y"


def test_godziny_otwarcia_wplywaja_na_dlugosc_slotu(admin_client):
    # 2026-07-13 to poniedziałek (weekday=0); ustaw slot 90 min
    assert admin_client.post("/api/godziny-otwarcia", json={"dzien_tygodnia": 0, "godz_od": "12:00",
                             "godz_do": "22:00", "dlugosc_slotu_min": 90}).status_code == 201
    s = _stolik(admin_client)
    body = _rez(admin_client, data="2026-07-13", godz_od="18:00", stolik_id=s["id"],
                nazwisko="A", liczba_osob=2).json()
    assert body["godz_do"] == "19:30"   # 18:00 + 90 min
