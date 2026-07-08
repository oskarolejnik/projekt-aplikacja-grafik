"""Slice v2 S1: polityka rezerwacji (LokalConfig) + WyjatekKalendarza (blackout / godziny specjalne).
Egzekwowanie polityki online jest w S2 — tu model, config i wpływ wyjątków na dostępność.
2026-07-13 = poniedziałek (weekday=0)."""

PON = "2026-07-13"


def _enable_online(admin_client):
    assert admin_client.put("/api/lokal/config", json={"rezerwacje_online": True}).status_code == 200


def _serwis(admin_client, **kw):
    dane = {"dzien_tygodnia": 0, "godz_od": "12:00", "godz_do": "22:00"}
    dane.update(kw)
    assert admin_client.post("/api/godziny-otwarcia", json=dane).status_code == 201


def test_config_polityka_pola(admin_client):
    cfg = admin_client.get("/api/lokal/config").json()
    assert cfg["rez_min_grupa_online"] == 1 and cfg["rez_okno_wyprzedzenia_dni"] == 0
    admin_client.put("/api/lokal/config", json={"rez_okno_wyprzedzenia_dni": 30, "rez_bufor_min": 15})
    cfg = admin_client.get("/api/lokal/config").json()
    assert cfg["rez_okno_wyprzedzenia_dni"] == 30 and cfg["rez_bufor_min"] == 15
    admin_client.put("/api/lokal/config", json={"rez_cutoff_min": 60})   # partial nie zeruje reszty
    cfg = admin_client.get("/api/lokal/config").json()
    assert cfg["rez_okno_wyprzedzenia_dni"] == 30 and cfg["rez_cutoff_min"] == 60


def test_wyjatek_crud_i_walidacja(admin_client):
    r = admin_client.post("/api/wyjatki-kalendarza", json={"data": PON, "typ": "blackout", "nazwa": "Remont"})
    assert r.status_code == 201 and r.json()["typ"] == "blackout"
    assert admin_client.post("/api/wyjatki-kalendarza", json={"data": PON, "typ": "xyz"}).status_code == 400
    assert admin_client.post("/api/wyjatki-kalendarza",
                             json={"data": PON, "typ": "godziny_specjalne"}).status_code == 400   # brak godzin
    lista = admin_client.get(f"/api/wyjatki-kalendarza?od={PON}&do={PON}").json()["wyjatki"]
    assert len(lista) == 1
    assert admin_client.delete(f"/api/wyjatki-kalendarza/{lista[0]['id']}").status_code == 204


def test_blackout_zamyka_dostepnosc(admin_client, client):
    _enable_online(admin_client)
    admin_client.post("/api/stoliki", json={"nazwa": "S1", "pojemnosc": 4})
    _serwis(admin_client, dlugosc_slotu_min=120)
    assert len(client.get(f"/api/online/dostepnosc?data={PON}&osoby=2").json()["sloty"]) > 0
    admin_client.post("/api/wyjatki-kalendarza", json={"data": PON, "typ": "blackout"})
    assert client.get(f"/api/online/dostepnosc?data={PON}&osoby=2").json()["sloty"] == []


def test_godziny_specjalne_nadpisuja_okno(admin_client, client):
    _enable_online(admin_client)
    admin_client.post("/api/stoliki", json={"nazwa": "S1", "pojemnosc": 4})
    _serwis(admin_client, godz_od="12:00", godz_do="22:00", dlugosc_slotu_min=120)
    admin_client.post("/api/wyjatki-kalendarza", json={"data": PON, "typ": "godziny_specjalne",
                      "godz_od": "16:00", "godz_do": "20:00", "dlugosc_slotu_min": 120})
    godziny = [s["godz_od"] for s in client.get(f"/api/online/dostepnosc?data={PON}&osoby=2").json()["sloty"]]
    assert "12:00" not in godziny and "16:00" in godziny


def test_wyjatki_gating_pro(admin_client):
    admin_client.put("/api/lokal/config", json={"modul_rezerwacje": False})
    assert admin_client.get("/api/wyjatki-kalendarza").status_code == 403
