"""Slice v2 S7: widok hosta — oś czasu (stoły × godziny, paski zajętości z rozbiciem kombinacji)
+ wzbogacenie kolejki o flagi gościa z ProfilGoscia (VIP/alergie/okazja/tagi), join po bezpiecznym
identyfikatorze kontaktu albo dokładnej rezerwacji. 2026-07-13 = poniedziałek."""

PON = "2026-07-13"


def _stolik(admin_client, nazwa, poj=4, **kw):
    r = admin_client.post("/api/stoliki", json={"nazwa": nazwa, "pojemnosc": poj, **kw})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _rez(admin_client, data, godz, osoby, nazwisko="Gość", stolik_id=None):
    body = {"data": data, "godz_od": godz, "liczba_osob": osoby, "nazwisko": nazwisko}
    if stolik_id is not None:
        body["stolik_id"] = stolik_id
    r = admin_client.post("/api/rezerwacje-stolik", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_os_czasu_stoly_i_paski(admin_client):
    s1 = _stolik(admin_client, "S1", 4, sekcja="Sala")
    s2 = _stolik(admin_client, "S2", 4)
    r = _rez(admin_client, PON, "18:00", 2, stolik_id=s1)
    out = admin_client.get(f"/api/host/os-czasu?data={PON}").json()
    assert {s["id"] for s in out["stoly"]} >= {s1, s2}
    assert any(s["id"] == s1 and s["sekcja"] == "Sala" for s in out["stoly"])
    paski = [z for z in out["zajetosci"] if z["rezerwacja_id"] == r]
    assert paski and paski[0]["stolik_id"] == s1 and paski[0]["godz_od"] == "18:00"
    assert paski[0]["faza_hosta"] is None and paski[0]["nazwisko"] == "Gość"


def test_os_czasu_rozbija_kombinacje_na_paski(admin_client):
    s1, s2 = _stolik(admin_client, "S1", 2), _stolik(admin_client, "S2", 2)
    assert admin_client.post("/api/sasiedztwo", json={"stolik_a": s1, "stolik_b": s2}).status_code == 201
    r = _rez(admin_client, PON, "18:00", 3)                     # grupa 3 → auto kombinacja S1+S2
    assert admin_client.post(f"/api/rezerwacje-stolik/{r}/auto-przydziel").status_code == 200
    out = admin_client.get(f"/api/host/os-czasu?data={PON}").json()
    stoly_paska = {z["stolik_id"] for z in out["zajetosci"] if z["rezerwacja_id"] == r}
    assert stoly_paska == {s1, s2}                              # kombinacja = pasek na każdym stole


def test_os_czasu_pomija_odwolane(admin_client):
    s1 = _stolik(admin_client, "S1", 4)
    r = _rez(admin_client, PON, "18:00", 2, stolik_id=s1)
    admin_client.post(f"/api/rezerwacje-stolik/{r}/status", json={"status": "odwolana"})
    out = admin_client.get(f"/api/host/os-czasu?data={PON}").json()
    assert all(z["rezerwacja_id"] != r for z in out["zajetosci"])   # anulowana nie zajmuje osi


def test_kolejka_wzbogaca_flagami_goscia(admin_client):
    _stolik(admin_client, "S1", 4)
    r = _rez(admin_client, PON, "18:00", 2, nazwisko="Kowalski")
    admin_client.put(f"/api/crm/rezerwacje/{r}/profil",
                     json={"vip": True, "tagi": ["VIP"], "alergie": "orzechy", "okazja_typ": "urodziny"})
    kol = admin_client.get(f"/api/host/kolejka?data={PON}").json()
    wpis = next(w for w in kol["nadchodzace"] if w["id"] == r)
    assert wpis["gosc"]["vip"] is True and wpis["gosc"]["ma_alergie"] is True
    assert wpis["gosc"]["alergie"] == "orzechy" and wpis["gosc"]["okazja_typ"] == "urodziny"
    assert "VIP" in wpis["gosc"]["tagi"]


def test_kolejka_brak_profilu_gosc_none(admin_client):
    _stolik(admin_client, "S1", 4)
    r = _rez(admin_client, PON, "18:00", 2, nazwisko="Anonim Bezprofilu")
    kol = admin_client.get(f"/api/host/kolejka?data={PON}").json()
    wpis = next(w for w in kol["nadchodzace"] if w["id"] == r)
    assert wpis["gosc"] is None
