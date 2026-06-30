"""Lista oczekujących (waitlist): CRUD + realizacja → rezerwacja, odwołanie."""


def _stolik(admin_client, nazwa="S1", pojemnosc=4):
    return admin_client.post("/api/stoliki", json={"nazwa": nazwa, "pojemnosc": pojemnosc}).json()


def test_lista_crud(admin_client):
    r = admin_client.post("/api/lista-oczekujacych", json={"data": "2026-07-01", "godz_od": "18:00",
                          "liczba_osob": 4, "nazwisko": "Nowak", "telefon": "600100200"})
    assert r.status_code == 201
    wid = r.json()["id"]
    assert r.json()["status"] == "oczekuje"
    lst = admin_client.get("/api/lista-oczekujacych?data=2026-07-01").json()["lista"]
    assert any(w["id"] == wid for w in lst)
    assert admin_client.delete(f"/api/lista-oczekujacych/{wid}").status_code == 204


def test_zrealizuj_tworzy_rezerwacje(admin_client):
    st = _stolik(admin_client)
    wid = admin_client.post("/api/lista-oczekujacych", json={"data": "2026-07-02", "godz_od": "19:00",
                            "liczba_osob": 3, "nazwisko": "Gość"}).json()["id"]
    r = admin_client.post(f"/api/lista-oczekujacych/{wid}/zrealizuj", json={"stolik_id": st["id"]})
    assert r.status_code == 200, r.text
    rez = r.json()["rezerwacja"]
    assert rez["nazwisko"] == "Gość" and rez["godz_od"] == "19:00" and rez["stolik_id"] == st["id"]
    assert rez["godz_do"] == "21:00"   # +120 min
    # wpis przeszedł w 'zrealizowany' i wskazuje na rezerwację
    w = next(x for x in admin_client.get("/api/lista-oczekujacych?data=2026-07-02").json()["lista"] if x["id"] == wid)
    assert w["status"] == "zrealizowany" and w["termin_id"] == rez["id"]
    # rezerwacja widoczna na liście rezerwacji stolików
    rezerwacje = admin_client.get("/api/rezerwacje-stolik?start=2026-07-02&end=2026-07-02").json()["rezerwacje"]
    assert any(x["id"] == rez["id"] for x in rezerwacje)


def test_zrealizuj_pojemnosc_blokuje(admin_client):
    st = _stolik(admin_client, nazwa="S2", pojemnosc=2)
    wid = admin_client.post("/api/lista-oczekujacych", json={"data": "2026-07-03", "godz_od": "18:00",
                            "liczba_osob": 5, "nazwisko": "ZaDuzo"}).json()["id"]
    assert admin_client.post(f"/api/lista-oczekujacych/{wid}/zrealizuj", json={"stolik_id": st["id"]}).status_code == 400


def test_zrealizuj_dwa_razy_409(admin_client):
    st = _stolik(admin_client, nazwa="S3")
    wid = admin_client.post("/api/lista-oczekujacych", json={"data": "2026-07-04", "godz_od": "18:00",
                            "liczba_osob": 2, "nazwisko": "A"}).json()["id"]
    assert admin_client.post(f"/api/lista-oczekujacych/{wid}/zrealizuj", json={"stolik_id": st["id"]}).status_code == 200
    assert admin_client.post(f"/api/lista-oczekujacych/{wid}/zrealizuj", json={"stolik_id": st["id"]}).status_code == 409


def test_odwolaj(admin_client):
    wid = admin_client.post("/api/lista-oczekujacych", json={"data": "2026-07-05", "nazwisko": "B"}).json()["id"]
    r = admin_client.post(f"/api/lista-oczekujacych/{wid}/odwolaj")
    assert r.status_code == 200 and r.json()["status"] == "odwolany"


def test_modul_off_403(admin_client):
    admin_client.put("/api/lokal/config", json={"modul_rezerwacje": False})
    assert admin_client.get("/api/lista-oczekujacych?data=2026-07-01").status_code == 403
