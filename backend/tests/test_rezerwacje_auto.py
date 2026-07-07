"""Slice 3: endpointy silnika sadzania — SUGESTIA (top-3) i AUTO (przydział best-fit),
w tym blokowanie stołów składowych kombinacji. 2026-07-13 = poniedziałek."""

PON = "2026-07-13"


def _stolik(admin_client, nazwa, pojemnosc, **kw):
    r = admin_client.post("/api/stoliki", json={"nazwa": nazwa, "pojemnosc": pojemnosc, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def _rez(admin_client, **kw):
    r = admin_client.post("/api/rezerwacje-stolik", json={"data": PON, "nazwisko": "A", **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_auto_przydziela_najmniejszy(admin_client):
    s2 = _stolik(admin_client, "S2", 2)
    _stolik(admin_client, "S4", 4)
    rid = _rez(admin_client, godz_od="18:00", liczba_osob=2)["id"]     # bez stołu
    r = admin_client.post(f"/api/rezerwacje-stolik/{rid}/auto-przydziel")
    assert r.status_code == 200, r.text
    body = r.json()["rezerwacja"]
    assert body["stolik_id"] == s2["id"] and body["auto_przydzielony"] is True
    assert body["stoliki_dodatkowe"] == []


def test_auto_dobiera_kombinacje_dla_duzej_grupy(admin_client):
    a = _stolik(admin_client, "S1", 4)
    b = _stolik(admin_client, "S2", 4)
    admin_client.post("/api/kombinacje", json={"nazwa": "S1+S2", "stoliki": [a["id"], b["id"]],
                                               "pojemnosc_min": 5})
    rid = _rez(admin_client, godz_od="18:00", liczba_osob=6)["id"]
    body = admin_client.post(f"/api/rezerwacje-stolik/{rid}/auto-przydziel").json()["rezerwacja"]
    assert {body["stolik_id"], *body["stoliki_dodatkowe"]} == {a["id"], b["id"]}


def test_auto_blokuje_stoly_skladowe_kombinacji(admin_client):
    a = _stolik(admin_client, "S1", 4)
    b = _stolik(admin_client, "S2", 4)
    admin_client.post("/api/kombinacje", json={"nazwa": "S1+S2", "stoliki": [a["id"], b["id"]],
                                               "pojemnosc_min": 5})
    rid = _rez(admin_client, godz_od="18:00", liczba_osob=6)["id"]
    admin_client.post(f"/api/rezerwacje-stolik/{rid}/auto-przydziel")
    # ręczna rezerwacja na stół A (składowy kombinacji) w nakładającym oknie → 409
    r = admin_client.post("/api/rezerwacje-stolik", json={"data": PON, "godz_od": "19:00",
                          "stolik_id": a["id"], "liczba_osob": 2, "nazwisko": "B"})
    assert r.status_code == 409


def test_auto_brak_miejsca_409(admin_client):
    _stolik(admin_client, "S1", 2)
    rid = _rez(admin_client, godz_od="18:00", liczba_osob=10)["id"]
    assert admin_client.post(f"/api/rezerwacje-stolik/{rid}/auto-przydziel").status_code == 409


def test_auto_bez_godziny_400(admin_client):
    _stolik(admin_client, "S1", 4)
    rid = _rez(admin_client, liczba_osob=2)["id"]     # bez godz_od
    assert admin_client.post(f"/api/rezerwacje-stolik/{rid}/auto-przydziel").status_code == 400


def test_sugestia_zwraca_top3_best_fit(admin_client):
    for i, poj in enumerate([2, 4, 6, 8]):
        _stolik(admin_client, f"S{i}", poj)
    r = admin_client.get(f"/api/host/sugestia-stolika?data={PON}&godz_od=18:00&osoby=2").json()
    assert len(r["kandydaci"]) == 3
    assert r["kandydaci"][0]["nadmiar_miejsc"] == 0      # najlepszy: stół na 2
    assert r["godz_do"] == "20:00"                       # 18:00 + domyślny turn-time 120


def test_sugestia_pomija_zajete(admin_client):
    s2 = _stolik(admin_client, "S2", 2)
    s4 = _stolik(admin_client, "S4", 4)
    _rez(admin_client, godz_od="18:00", stolik_id=s2["id"], liczba_osob=2)   # zajmuje S2
    r = admin_client.get(f"/api/host/sugestia-stolika?data={PON}&godz_od=18:30&osoby=2").json()
    stoly = [c["stoliki"] for c in r["kandydaci"]]
    assert [s2["id"]] not in stoly and [s4["id"]] in stoly


def test_sugestia_gating_pro(admin_client):
    assert admin_client.put("/api/lokal/config", json={"modul_rezerwacje": False}).status_code == 200
    assert admin_client.get(f"/api/host/sugestia-stolika?data={PON}&godz_od=18:00&osoby=2").status_code == 403
