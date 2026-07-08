"""Slice v2 S5: waitlist v2 — powiadomienie „stolik gotowy", HOLD stołu (blokada w rdzeniu zajętości),
publiczny zapis online. HOLD blokuje AUTOMATYCZNY dobór (auto-przydział / online), nie ręczny admina.
2026-07-13 = poniedziałek w przyszłości (online nie odrzuca jako wstecz)."""

DZIEN = "2026-07-13"


def _stolik(admin_client, nazwa, poj=4):
    r = admin_client.post("/api/stoliki", json={"nazwa": nazwa, "pojemnosc": poj})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _wait(admin_client, data, godz, osoby, nazwisko="Czekacz", email=None):
    body = {"data": data, "godz_od": godz, "liczba_osob": osoby, "nazwisko": nazwisko}
    if email:
        body["email"] = email
    r = admin_client.post("/api/lista-oczekujacych", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _rez(admin_client, data, godz, osoby):
    r = admin_client.post("/api/rezerwacje-stolik",
                          json={"data": data, "godz_od": godz, "liczba_osob": osoby, "nazwisko": "Gość"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_hold_blokuje_auto_przydzial(admin_client):
    s1, s2 = _stolik(admin_client, "S1", 2), _stolik(admin_client, "S2", 2)
    e = _wait(admin_client, DZIEN, "18:00", 2)
    assert admin_client.post(f"/api/lista-oczekujacych/{e}/hold",
                             json={"stolik_id": s1, "minuty": 30}).status_code == 200
    r = _rez(admin_client, DZIEN, "18:00", 2)
    przydzial = admin_client.post(f"/api/rezerwacje-stolik/{r}/auto-przydziel").json()["przydzial"]
    assert przydzial["stoliki"] == [s2]                 # S1 pod holdem → silnik go pomija


def test_zwolnienie_holdu_odblokowuje(admin_client):
    s1 = _stolik(admin_client, "S1", 2)
    e = _wait(admin_client, DZIEN, "18:00", 2)
    admin_client.post(f"/api/lista-oczekujacych/{e}/hold", json={"stolik_id": s1, "minuty": 30})
    r = _rez(admin_client, DZIEN, "18:00", 2)
    # jedyny stół trzymany → brak wolnego
    assert admin_client.post(f"/api/rezerwacje-stolik/{r}/auto-przydziel").status_code == 409
    assert admin_client.post(f"/api/lista-oczekujacych/{e}/zwolnij-hold").status_code == 200
    # po zwolnieniu holdu stół wraca do puli
    assert admin_client.post(f"/api/rezerwacje-stolik/{r}/auto-przydziel").status_code == 200


def test_hold_waliduje_stolik(admin_client):
    e = _wait(admin_client, DZIEN, "18:00", 2)
    assert admin_client.post(f"/api/lista-oczekujacych/{e}/hold",
                             json={"stolik_id": 999999, "minuty": 30}).status_code == 400


def test_realizacja_konczy_wlasny_hold(admin_client):
    s1 = _stolik(admin_client, "S1", 4)
    e = _wait(admin_client, DZIEN, "18:00", 2)
    admin_client.post(f"/api/lista-oczekujacych/{e}/hold", json={"stolik_id": s1, "minuty": 30})
    # realizacja na TRZYMANYM stole nie może kolidować z własnym holdem (hold czyszczony przed walidacją)
    r = admin_client.post(f"/api/lista-oczekujacych/{e}/zrealizuj", json={"stolik_id": s1})
    assert r.status_code == 200, r.text
    wpis = r.json()["wpis"]
    assert wpis["status"] == "zrealizowany" and wpis["hold_stolik_id"] is None


def test_powiadom_stempluje_i_nie_dubluje(admin_client):
    e = _wait(admin_client, DZIEN, "18:00", 2, email="g@x.pl")
    r1 = admin_client.post(f"/api/lista-oczekujacych/{e}/powiadom")
    assert r1.status_code == 200 and r1.json()["wpis"]["powiadomiono_at"] is not None
    r2 = admin_client.post(f"/api/lista-oczekujacych/{e}/powiadom")
    assert r2.json().get("juz_powiadomiony") is True


def test_online_zapis_na_liste_oczekujacych(admin_client, client):
    admin_client.put("/api/lokal/config", json={"rezerwacje_online": True})
    r = client.post("/api/online/lista-oczekujacych",
                    json={"data": DZIEN, "godz_od": "18:00", "liczba_osob": 2, "nazwisko": "Online Gość"})
    assert r.status_code == 201, r.text
    assert r.json()["token"] and r.json()["wpis"]["status"] == "oczekuje"
    lista = admin_client.get(f"/api/lista-oczekujacych?data={DZIEN}").json()["lista"]
    assert any(w["kanal"] == "online" for w in lista)


def test_online_zapis_wymaga_wlaczonego_online(admin_client, client):
    admin_client.put("/api/lokal/config", json={"rezerwacje_online": False})
    r = client.post("/api/online/lista-oczekujacych",
                    json={"data": DZIEN, "godz_od": "18:00", "liczba_osob": 2, "nazwisko": "X"})
    assert r.status_code == 404          # moduł online wyłączony
