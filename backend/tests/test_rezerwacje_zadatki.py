"""Slice v2 S9: zadatki online + no-show fee (za flagą; sandbox — realne pobieranie po wpięciu bramki).
Zadatek = Platnosc(status=oczekuje) z linkiem; opłacenie zapisuje kwotę na Termin.zadatek.
2026-07-13 = poniedziałek (przyszłość — online nie odrzuca jako wstecz)."""

PON = "2026-07-13"


def _online(admin_client):
    admin_client.put("/api/lokal/config", json={"rezerwacje_online": True})


def _stolik(admin_client, poj=6):
    r = admin_client.post("/api/stoliki", json={"nazwa": "S1", "pojemnosc": poj})
    assert r.status_code == 201


def _rez_reczna(admin_client, osoby=2, nazwisko="Gość"):
    r = admin_client.post("/api/rezerwacje-stolik",
                          json={"data": PON, "godz_od": "18:00", "liczba_osob": osoby, "nazwisko": nazwisko})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_zadatek_online_tworzy_platnosc_sandbox(admin_client, client):
    _online(admin_client); _stolik(admin_client)
    admin_client.put("/api/lokal/config", json={"zadatek_wymagany": True, "zadatek_kwota_os": 20, "zadatek_prog_osob": 4})
    r = client.post("/api/online/rezerwacja", json={"data": PON, "godz_od": "18:00", "liczba_osob": 4, "nazwisko": "Grupa"})
    assert r.status_code == 201, r.text
    pl = r.json()["platnosc"]
    assert pl["kwota"] == 80.0 and pl["status"] == "oczekuje" and "/?platnosc=" in pl["link"]   # 20 zł × 4 os.


def test_zadatek_ponizej_progu_brak(admin_client, client):
    _online(admin_client); _stolik(admin_client)
    admin_client.put("/api/lokal/config", json={"zadatek_wymagany": True, "zadatek_kwota_os": 20, "zadatek_prog_osob": 6})
    r = client.post("/api/online/rezerwacja", json={"data": PON, "godz_od": "18:00", "liczba_osob": 2, "nazwisko": "Para"})
    assert r.status_code == 201 and "platnosc" not in r.json()   # 2 < próg 6


def test_zadatek_wylaczony_domyslnie_brak(admin_client, client):
    _online(admin_client); _stolik(admin_client)                 # zadatek_wymagany = False (default)
    r = client.post("/api/online/rezerwacja", json={"data": PON, "godz_od": "18:00", "liczba_osob": 4, "nazwisko": "X"})
    assert r.status_code == 201 and "platnosc" not in r.json()


def test_no_show_fee_tworzy_naleznosc(admin_client):
    _stolik(admin_client)
    admin_client.put("/api/lokal/config", json={"no_show_fee": 50})
    rid = _rez_reczna(admin_client, nazwisko="Nieobecny")
    assert admin_client.post(f"/api/rezerwacje-stolik/{rid}/status", json={"status": "no_show"}).status_code == 200
    pl = admin_client.get(f"/api/platnosci?termin_id={rid}").json()
    assert len(pl) == 1 and pl[0]["kwota"] == 50.0


def test_no_show_fee_wylaczona_brak(admin_client):
    _stolik(admin_client)                                        # no_show_fee = 0 (default)
    rid = _rez_reczna(admin_client)
    admin_client.post(f"/api/rezerwacje-stolik/{rid}/status", json={"status": "no_show"})
    assert admin_client.get(f"/api/platnosci?termin_id={rid}").json() == []


def test_oplacona_zapisuje_zadatek_na_terminie(admin_client):
    _stolik(admin_client)
    rid = _rez_reczna(admin_client)
    p = admin_client.post("/api/platnosci", json={"termin_id": rid, "kwota": 40}).json()
    assert admin_client.post(f"/api/platnosci/{p['id']}/oplacona").json()["status"] == "oplacona"
    rez = admin_client.get(f"/api/rezerwacje-stolik?start={PON}&end={PON}").json()["rezerwacje"]
    assert next(x for x in rez if x["id"] == rid)["zadatek"] == 40.0


def test_platnosci_gating_pro(admin_client):
    admin_client.put("/api/lokal/config", json={"modul_rezerwacje": False})
    assert admin_client.get("/api/platnosci").status_code == 403
    assert admin_client.post("/api/platnosci", json={"termin_id": 1, "kwota": 10}).status_code == 403
