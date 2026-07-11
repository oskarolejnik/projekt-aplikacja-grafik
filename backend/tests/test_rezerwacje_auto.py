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


def test_edycja_danych_zachowuje_pojedynczy_auto_przydzial(admin_client):
    s2 = _stolik(admin_client, "S2", 2)
    rid = _rez(admin_client, godz_od="18:00", liczba_osob=2)["id"]
    admin_client.post(f"/api/rezerwacje-stolik/{rid}/auto-przydziel")

    wynik = admin_client.put(f"/api/rezerwacje-stolik/{rid}", json={
        "data": PON, "godz_od": "18:15", "stolik_id": s2["id"],
        "liczba_osob": 2, "nazwisko": "Tylko nowe nazwisko",
    })

    assert wynik.status_code == 200, wynik.text
    assert wynik.json()["stolik_id"] == s2["id"]
    assert wynik.json()["stoliki_dodatkowe"] == []
    assert wynik.json()["auto_przydzielony"] is True


def test_auto_dobiera_kombinacje_dla_duzej_grupy(admin_client):
    a = _stolik(admin_client, "S1", 4)
    b = _stolik(admin_client, "S2", 4)
    admin_client.post("/api/kombinacje", json={"nazwa": "S1+S2", "stoliki": [a["id"], b["id"]],
                                               "pojemnosc_min": 5})
    rid = _rez(admin_client, godz_od="18:00", liczba_osob=6)["id"]
    body = admin_client.post(f"/api/rezerwacje-stolik/{rid}/auto-przydziel").json()["rezerwacja"]
    assert {body["stolik_id"], *body["stoliki_dodatkowe"]} == {a["id"], b["id"]}
    dodatkowy = body["stoliki_dodatkowe"][0]
    filtrowane = admin_client.get(
        f"/api/rezerwacje-stolik?start={PON}&end={PON}&stolik_id={dodatkowy}").json()["rezerwacje"]
    assert [r["id"] for r in filtrowane] == [rid]


def test_zmiana_liczby_osob_respektuje_min_i_max_kombinacji(admin_client):
    a = _stolik(admin_client, "S1", 4)
    b = _stolik(admin_client, "S2", 4)
    admin_client.post("/api/kombinacje", json={
        "nazwa": "S1+S2", "stoliki": [a["id"], b["id"]],
        "pojemnosc_min": 5, "pojemnosc_max": 6,
    })
    rid = _rez(admin_client, godz_od="18:00", liczba_osob=6)["id"]
    auto = admin_client.post(f"/api/rezerwacje-stolik/{rid}/auto-przydziel").json()["rezerwacja"]

    for osoby in (8, 2):
        wynik = admin_client.put(f"/api/rezerwacje-stolik/{rid}", json={
            "data": PON, "godz_od": "18:00", "stolik_id": auto["stolik_id"],
            "liczba_osob": osoby, "nazwisko": "Po zmianie",
        })
        assert wynik.status_code == 400


def test_edycja_zachowuje_jawny_override_pojemnosci_kombinacji(admin_client):
    a = _stolik(admin_client, "S1", 2)
    b = _stolik(admin_client, "S2", 2)
    admin_client.post("/api/kombinacje", json={
        "nazwa": "Rozsuwany", "stoliki": [a["id"], b["id"]],
        "pojemnosc_min": 6, "pojemnosc_max": 10,
    })
    rid = _rez(admin_client, godz_od="18:00", liczba_osob=8)["id"]
    auto = admin_client.post(f"/api/rezerwacje-stolik/{rid}/auto-przydziel").json()["rezerwacja"]

    wynik = admin_client.put(f"/api/rezerwacje-stolik/{rid}", json={
        "data": PON, "godz_od": "18:15", "stolik_id": auto["stolik_id"],
        "liczba_osob": 8, "nazwisko": "Tylko korekta danych",
    })
    assert wynik.status_code == 200, wynik.text
    assert wynik.json()["auto_przydzielony"] is True


def test_edycja_danych_zachowuje_kombinacje_a_reczna_zmiana_ja_czysci(admin_client):
    a = _stolik(admin_client, "S1", 4)
    b = _stolik(admin_client, "S2", 4)
    admin_client.post("/api/kombinacje", json={"nazwa": "S1+S2", "stoliki": [a["id"], b["id"]],
                                               "pojemnosc_min": 5})
    rid = _rez(admin_client, godz_od="18:00", liczba_osob=6)["id"]
    auto = admin_client.post(f"/api/rezerwacje-stolik/{rid}/auto-przydziel").json()["rezerwacja"]
    glowny = auto["stolik_id"]

    # Zmiana danych gościa/czasu przy tym samym stole zachowuje pełny przydział i waliduje go łącznie.
    zachowana = admin_client.put(f"/api/rezerwacje-stolik/{rid}", json={
        "data": PON, "godz_od": "18:15", "stolik_id": glowny,
        "liczba_osob": 6, "nazwisko": "Po korekcie",
    })
    assert zachowana.status_code == 200, zachowana.text
    assert {zachowana.json()["stolik_id"], *zachowana.json()["stoliki_dodatkowe"]} == {a["id"], b["id"]}
    assert zachowana.json()["auto_przydzielony"] is True

    # Jawny wybór innego stołu zamienia kombinację na ręczny pojedynczy przydział.
    c = _stolik(admin_client, "S3", 6)
    reczna = admin_client.put(f"/api/rezerwacje-stolik/{rid}", json={
        "data": PON, "godz_od": "18:15", "stolik_id": c["id"],
        "liczba_osob": 6, "nazwisko": "Po korekcie",
    })
    assert reczna.status_code == 200, reczna.text
    assert reczna.json()["stolik_id"] == c["id"]
    assert reczna.json()["stoliki_dodatkowe"] == []
    assert reczna.json()["auto_przydzielony"] is False


def test_reczne_odpiecie_czysci_caly_auto_przydzial(admin_client):
    a = _stolik(admin_client, "S1", 4)
    b = _stolik(admin_client, "S2", 4)
    admin_client.post("/api/kombinacje", json={"nazwa": "S1+S2", "stoliki": [a["id"], b["id"]],
                                               "pojemnosc_min": 5})
    rid = _rez(admin_client, godz_od="18:00", liczba_osob=6)["id"]
    admin_client.post(f"/api/rezerwacje-stolik/{rid}/auto-przydziel")

    wynik = admin_client.put(f"/api/rezerwacje-stolik/{rid}", json={
        "data": PON, "godz_od": "18:00", "stolik_id": None,
        "liczba_osob": 6, "nazwisko": "Bez stolika",
    })
    assert wynik.status_code == 200, wynik.text
    assert wynik.json()["stolik_id"] is None
    assert wynik.json()["stoliki_dodatkowe"] == []
    assert wynik.json()["auto_przydzielony"] is False


def test_edycja_kombinacji_wykrywa_kolizje_na_dodatkowym_stole(admin_client):
    a = _stolik(admin_client, "S1", 4)
    b = _stolik(admin_client, "S2", 4)
    admin_client.post("/api/kombinacje", json={"nazwa": "S1+S2", "stoliki": [a["id"], b["id"]],
                                               "pojemnosc_min": 5})
    rid = _rez(admin_client, godz_od="18:00", liczba_osob=6)["id"]
    auto = admin_client.post(f"/api/rezerwacje-stolik/{rid}/auto-przydziel").json()["rezerwacja"]
    dodatkowy = auto["stoliki_dodatkowe"][0]
    assert _rez(admin_client, godz_od="20:00", stolik_id=dodatkowy,
                liczba_osob=2, nazwisko="Późniejsza")["id"]

    konflikt = admin_client.put(f"/api/rezerwacje-stolik/{rid}", json={
        "data": PON, "godz_od": "19:00", "stolik_id": auto["stolik_id"],
        "liczba_osob": 6, "nazwisko": "Przesunięta",
    })
    assert konflikt.status_code == 409


def test_nie_mozna_dezaktywowac_dodatkowego_stolu_przyszlej_rezerwacji(
    admin_client, monkeypatch,
):
    przyszlosc = "2035-07-13"
    import main
    from datetime import datetime
    monkeypatch.setattr(main, "_teraz_lokalnie", lambda: datetime(2035, 7, 13, 0, 30))
    a = _stolik(admin_client, "S1", 4)
    b = _stolik(admin_client, "S2", 4)
    admin_client.post("/api/kombinacje", json={"nazwa": "S1+S2", "stoliki": [a["id"], b["id"]],
                                               "pojemnosc_min": 5})
    rid = admin_client.post("/api/rezerwacje-stolik", json={
        "data": przyszlosc, "godz_od": "18:00", "nazwisko": "Przyszła", "liczba_osob": 6,
    }).json()["id"]
    przydzial = admin_client.post(
        f"/api/rezerwacje-stolik/{rid}/auto-przydziel").json()["rezerwacja"]
    dodatkowy = przydzial["stoliki_dodatkowe"][0]
    stolik = next(s for s in (a, b) if s["id"] == dodatkowy)

    wynik = admin_client.put(f"/api/stoliki/{dodatkowy}", json={
        "nazwa": stolik["nazwa"], "pojemnosc": stolik["pojemnosc"], "aktywny": False,
    })

    assert wynik.status_code == 409
    assert next(s for s in admin_client.get("/api/stoliki").json()["stoliki"]
                if s["id"] == dodatkowy)["aktywny"] is True


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


def test_delete_blokuje_stol_zapisany_tylko_w_dodatkowych_json(admin_client):
    a = _stolik(admin_client, "G1", 4)
    b = _stolik(admin_client, "G2", 4)
    assert admin_client.post("/api/sasiedztwo", json={
        "stolik_a": a["id"], "stolik_b": b["id"],
    }).status_code == 201
    rid = _rez(admin_client, godz_od="18:00", liczba_osob=6)["id"]
    auto = admin_client.post(f"/api/rezerwacje-stolik/{rid}/auto-przydziel").json()["rezerwacja"]
    dodatkowy = auto["stoliki_dodatkowe"][0]

    assert admin_client.delete(f"/api/stoliki/{dodatkowy}").status_code == 409
    po_probie = admin_client.get(
        f"/api/rezerwacje-stolik?start={PON}&end={PON}").json()["rezerwacje"]
    zapis = next(r for r in po_probie if r["id"] == rid)
    assert dodatkowy in zapis["stoliki_dodatkowe"]
    assert any(s["id"] == dodatkowy for s in admin_client.get("/api/stoliki").json()["stoliki"])


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
