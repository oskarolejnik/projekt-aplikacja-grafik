"""Slice 4a: widok hosta — kolejka dnia, fazy operacyjne (przybył→…→wyszedł), przydział stołu.
2026-07-13 = poniedziałek."""

PON = "2026-07-13"


def _stolik(admin_client, nazwa, pojemnosc):
    return admin_client.post("/api/stoliki", json={"nazwa": nazwa, "pojemnosc": pojemnosc}).json()


def _rez(admin_client, **kw):
    return admin_client.post("/api/rezerwacje-stolik",
                             json={"data": PON, "nazwisko": "A", **kw}).json()


def _faza(admin_client, rid, faza):
    return admin_client.post(f"/api/host/rezerwacja/{rid}/faza", json={"faza": faza})


# ── Fazy hosta ───────────────────────────────────────────────────────────────

def test_przejscia_faz_hosta(admin_client):
    s = _stolik(admin_client, "S1", 4)
    rid = _rez(admin_client, godz_od="18:00", stolik_id=s["id"], liczba_osob=2)["id"]
    assert _faza(admin_client, rid, "przybyl").status_code == 200
    r = _faza(admin_client, rid, "posadzony")
    assert r.status_code == 200 and r.json()["faza_hosta"] == "posadzony"
    assert _faza(admin_client, rid, "rachunek").status_code == 200
    assert _faza(admin_client, rid, "oplacony").status_code == 200
    assert _faza(admin_client, rid, "wyszedl").status_code == 200


def test_niedozwolone_przejscie_fazy_409(admin_client):
    s = _stolik(admin_client, "S1", 4)
    rid = _rez(admin_client, godz_od="18:00", stolik_id=s["id"], liczba_osob=2)["id"]
    _faza(admin_client, rid, "posadzony")
    # posadzony → przybyl jest cofnięciem = niedozwolone
    assert _faza(admin_client, rid, "przybyl").status_code == 409


def test_wyszedl_domyka_status_odbyla(admin_client):
    s = _stolik(admin_client, "S1", 4)
    rid = _rez(admin_client, godz_od="18:00", stolik_id=s["id"], liczba_osob=2)["id"]
    _faza(admin_client, rid, "posadzony")
    _faza(admin_client, rid, "wyszedl")
    # status księgowy = odbyla
    lista = admin_client.get(f"/api/rezerwacje-stolik?start={PON}&end={PON}").json()["rezerwacje"]
    assert next(x for x in lista if x["id"] == rid)["status"] == "odbyla"


def test_posadzony_potwierdza_rezerwacje(admin_client):
    s = _stolik(admin_client, "S1", 4)
    # rezerwacja online startuje ze statusem 'rezerwacja' — tu tworzymy ręcznie, ale sprawdzamy sam mechanizm
    rid = _rez(admin_client, godz_od="18:00", stolik_id=s["id"], liczba_osob=2)["id"]
    _faza(admin_client, rid, "posadzony")   # nie wywala się na potwierdzonej rezerwacji
    assert _faza(admin_client, rid, "rachunek").status_code == 200


def test_nieznana_faza_400(admin_client):
    s = _stolik(admin_client, "S1", 4)
    rid = _rez(admin_client, godz_od="18:00", stolik_id=s["id"], liczba_osob=2)["id"]
    assert _faza(admin_client, rid, "xyz").status_code == 400


# ── Kolejka dnia ─────────────────────────────────────────────────────────────

def test_kolejka_grupuje_po_fazie(admin_client):
    s1 = _stolik(admin_client, "S1", 4)
    s2 = _stolik(admin_client, "S2", 4)
    s3 = _stolik(admin_client, "S3", 4)
    r_nad = _rez(admin_client, godz_od="20:00", stolik_id=s1["id"], liczba_osob=2)["id"]  # nadchodzący
    r_sala = _rez(admin_client, godz_od="18:00", stolik_id=s2["id"], liczba_osob=3)["id"]
    r_kon = _rez(admin_client, godz_od="12:00", stolik_id=s3["id"], liczba_osob=2)["id"]
    _faza(admin_client, r_sala, "posadzony")
    _faza(admin_client, r_kon, "posadzony"); _faza(admin_client, r_kon, "wyszedl")

    k = admin_client.get(f"/api/host/kolejka?data={PON}").json()
    assert [x["id"] for x in k["nadchodzace"]] == [r_nad]
    assert [x["id"] for x in k["na_sali"]] == [r_sala]
    assert r_kon in [x["id"] for x in k["zakonczone"]]
    assert k["podsumowanie"]["coverow_na_sali"] == 3
    # timer obrotu obecny dla siedzących
    assert "minuty_od_posadzenia" in k["na_sali"][0]


def test_kolejka_pomija_odwolane(admin_client):
    s = _stolik(admin_client, "S1", 4)
    rid = _rez(admin_client, godz_od="18:00", stolik_id=s["id"], liczba_osob=2)["id"]
    admin_client.post(f"/api/rezerwacje-stolik/{rid}/status", json={"status": "odwolana"})
    k = admin_client.get(f"/api/host/kolejka?data={PON}").json()
    ids = [x["id"] for grp in ("nadchodzace", "na_sali", "zakonczone") for x in k[grp]]
    assert rid not in ids


# ── Przydział / przeniesienie stołu ──────────────────────────────────────────

def test_host_przydziel_i_przenies_stolik(admin_client):
    s1 = _stolik(admin_client, "S1", 4)
    s2 = _stolik(admin_client, "S2", 4)
    rid = _rez(admin_client, godz_od="18:00", liczba_osob=2)["id"]         # bez stołu
    r = admin_client.post(f"/api/host/rezerwacja/{rid}/przydziel-stolik", json={"stolik_id": s1["id"]})
    assert r.status_code == 200 and r.json()["stolik_id"] == s1["id"]
    # przeniesienie na S2
    r2 = admin_client.post(f"/api/host/rezerwacja/{rid}/przydziel-stolik", json={"stolik_id": s2["id"]})
    assert r2.status_code == 200 and r2.json()["stolik_id"] == s2["id"]


def test_host_reczny_przydzial_czysci_auto_kombinacje(admin_client):
    s1 = _stolik(admin_client, "S1", 4)
    s2 = _stolik(admin_client, "S2", 4)
    admin_client.post("/api/kombinacje", json={
        "nazwa": "S1+S2", "stoliki": [s1["id"], s2["id"]], "pojemnosc_min": 5,
    })
    rid = _rez(admin_client, godz_od="18:00", liczba_osob=6)["id"]
    auto = admin_client.post(f"/api/rezerwacje-stolik/{rid}/auto-przydziel").json()["rezerwacja"]
    assert auto["auto_przydzielony"] is True and auto["stoliki_dodatkowe"]

    s3 = _stolik(admin_client, "S3", 6)
    reczna = admin_client.post(
        f"/api/host/rezerwacja/{rid}/przydziel-stolik", json={"stolik_id": s3["id"]})
    assert reczna.status_code == 200, reczna.text
    assert reczna.json()["stolik_id"] == s3["id"]
    assert reczna.json()["stoliki_dodatkowe"] == []
    assert reczna.json()["auto_przydzielony"] is False


def test_host_przydziel_kolizja_409(admin_client):
    s1 = _stolik(admin_client, "S1", 4)
    _rez(admin_client, godz_od="18:00", stolik_id=s1["id"], liczba_osob=2)      # S1 zajęty 18–20
    rid = _rez(admin_client, godz_od="19:00", liczba_osob=2)["id"]
    assert admin_client.post(f"/api/host/rezerwacja/{rid}/przydziel-stolik",
                             json={"stolik_id": s1["id"]}).status_code == 409


def test_host_gating_pro(admin_client):
    admin_client.put("/api/lokal/config", json={"modul_rezerwacje": False})
    assert admin_client.get(f"/api/host/kolejka?data={PON}").status_code == 403
