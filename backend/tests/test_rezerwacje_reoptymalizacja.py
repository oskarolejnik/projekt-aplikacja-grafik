"""Slice v2 S4: re-optymalizacja przy zwolnieniu stołu (odwołanie/no-show/wyjście) + auto-no-show.

Scenariusz re-alokacji: grupa 3 osób ląduje na kombinacji S1+S2 (bo S3 zajęty); po odwołaniu blokady
na S3 auto-przydzielona rezerwacja przeskakuje na tańszy pojedynczy S3.
"""

import main as app_main

PRZESZLOSC = "2020-01-06"      # poniedziałek w przeszłości (auto-no-show zawsze przeterminowane)
PRZYSZLOSC = "2090-01-02"      # daleka przyszłość (nigdy nie przeterminowane)
DZIEN = "2026-07-13"           # poniedziałek — scenariusz re-alokacji


def _stolik(admin_client, nazwa, poj, **kw):
    r = admin_client.post("/api/stoliki", json={"nazwa": nazwa, "pojemnosc": poj, **kw})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _rez(admin_client, data, godz, osoby, stolik_id=None, nazwisko="Gość"):
    body = {"data": data, "godz_od": godz, "liczba_osob": osoby, "nazwisko": nazwisko}
    if stolik_id is not None:
        body["stolik_id"] = stolik_id
    r = admin_client.post("/api/rezerwacje-stolik", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _rez_out(admin_client, data, rid):
    lista = admin_client.get(f"/api/rezerwacje-stolik?start={data}&end={data}").json()["rezerwacje"]
    return next(r for r in lista if r["id"] == rid)


def _scenariusz_kombinacja(admin_client):
    """S1(2)+S2(2) sąsiadują (kombinacja cap 4), S3(4). Blokada 4 os. na S3 → grupa 3 idzie na S1+S2."""
    s1, s2, s3 = (_stolik(admin_client, "S1", 2), _stolik(admin_client, "S2", 2), _stolik(admin_client, "S3", 4))
    assert admin_client.post("/api/sasiedztwo", json={"stolik_a": s1, "stolik_b": s2}).status_code == 201
    blok = _rez(admin_client, DZIEN, "18:00", 4, stolik_id=s3, nazwisko="Blokada")
    grupa = _rez(admin_client, DZIEN, "18:00", 3, nazwisko="Trójka")
    wynik = admin_client.post(f"/api/rezerwacje-stolik/{grupa}/auto-przydziel")
    assert wynik.status_code == 200, wynik.text
    przydzial = wynik.json()["przydzial"]
    assert przydzial["kombinacja"] is True and set(przydzial["stoliki"]) == {s1, s2}
    return s1, s2, s3, blok, grupa


def test_odwolanie_realokuje_auto_na_lepszy_stol(admin_client):
    s1, s2, s3, blok, grupa = _scenariusz_kombinacja(admin_client)
    # odwołanie blokady zwalnia S3 → grupa przeskakuje na pojedynczy S3 (taniej niż kombinacja)
    assert admin_client.post(f"/api/rezerwacje-stolik/{blok}/status",
                             json={"status": "odwolana"}).status_code == 200
    g = _rez_out(admin_client, DZIEN, grupa)
    assert g["stolik_id"] == s3 and g["stoliki_dodatkowe"] == []


def test_reopt_nie_przenosi_przy_remisie_kosztu(admin_client):
    zwalniany = _stolik(admin_client, "A", 4)
    obecny = _stolik(admin_client, "B", 4)
    blokada = _rez(
        admin_client, DZIEN, "18:00", 4,
        stolik_id=zwalniany, nazwisko="Blokada",
    )
    grupa = _rez(admin_client, DZIEN, "18:00", 4, nazwisko="Remis")
    auto = admin_client.post(f"/api/rezerwacje-stolik/{grupa}/auto-przydziel")
    assert auto.status_code == 200, auto.text
    assert auto.json()["rezerwacja"]["stolik_id"] == obecny

    assert admin_client.post(
        f"/api/rezerwacje-stolik/{blokada}/status",
        json={"status": "odwolana"},
    ).status_code == 200

    po_reoptymalizacji = _rez_out(admin_client, DZIEN, grupa)
    assert po_reoptymalizacji["stolik_id"] == obecny
    assert po_reoptymalizacji["stoliki_dodatkowe"] == []


def test_reopt_nie_dubluje_stolu_dwoch_rezerwacji(admin_client, monkeypatch):
    """Regresja: gdy DWIE auto-rezerwacje nachodzą na to samo zwolnione okno, re-optymalizacja
    nie może posadzić obu na tym samym zwolnionym stole. Sesja ma autoflush=False — bezpieczeństwo
    zależy od tożsamościowej mapy ORM (przydział poprzedniej rezerwacji w pętli jest już widoczny)."""
    x = _stolik(admin_client, "X", 3)                 # dokładnie na grupę 3 (nadmiar 0 → najtańszy)
    z, w = _stolik(admin_client, "Z", 2), _stolik(admin_client, "W", 2)
    v, u = _stolik(admin_client, "V", 2), _stolik(admin_client, "U", 2)
    for a, b in [(z, w), (v, u)]:
        assert admin_client.post("/api/sasiedztwo", json={"stolik_a": a, "stolik_b": b}).status_code == 201
    blok = _rez(admin_client, DZIEN, "18:00", 3, stolik_id=x, nazwisko="Blokada")
    r_a = _rez(admin_client, DZIEN, "18:00", 3, nazwisko="A")
    r_b = _rez(admin_client, DZIEN, "18:00", 3, nazwisko="B")
    # A → kombinacja [Z,W], B → kombinacja [V,U] (X zajęty blokadą)
    assert set(admin_client.post(f"/api/rezerwacje-stolik/{r_a}/auto-przydziel").json()["przydzial"]["stoliki"]) == {z, w}
    assert set(admin_client.post(f"/api/rezerwacje-stolik/{r_b}/auto-przydziel").json()["przydzial"]["stoliki"]) == {v, u}
    lock_calls = []
    real_lock_tables = app_main.reservation_service.lock_tables

    def recording_lock_tables(db, table_ids):
        ids = tuple(table_ids)
        lock_calls.append(ids)
        return real_lock_tables(db, ids)

    monkeypatch.setattr(
        app_main.reservation_service, "lock_tables", recording_lock_tables,
    )
    # odwołanie blokady zwalnia X (cap 3) → jedna z rezerwacji może na niego przeskoczyć — ale NIE OBIE
    assert admin_client.post(f"/api/rezerwacje-stolik/{blok}/status", json={"status": "odwolana"}).status_code == 200
    # Pierwsza blokada reoptymalizacji obejmuje wszystkie aktywne stoły w jednej,
    # globalnie rosnącej kolejności. Dopiero potem wolno blokować podzbiory.
    assert lock_calls[0] == tuple(sorted((x, z, w, v, u)))
    ga, gb = _rez_out(admin_client, DZIEN, r_a), _rez_out(admin_client, DZIEN, r_b)
    stoly_a = set([ga["stolik_id"]] + ga["stoliki_dodatkowe"])
    stoly_b = set([gb["stolik_id"]] + gb["stoliki_dodatkowe"])
    assert not (stoly_a & stoly_b), f"Podwójna rezerwacja stołu: A={stoly_a} B={stoly_b}"


def test_posadzonej_nie_ruszamy(admin_client):
    s1, s2, s3, blok, grupa = _scenariusz_kombinacja(admin_client)
    # gość z grupy już posadzony na S1+S2 → obrót w toku, re-alokacja go pomija
    assert admin_client.post(f"/api/host/rezerwacja/{grupa}/faza",
                             json={"faza": "posadzony"}).status_code == 200
    assert admin_client.post(f"/api/rezerwacje-stolik/{blok}/status",
                             json={"status": "odwolana"}).status_code == 200
    g = _rez_out(admin_client, DZIEN, grupa)
    assert set([g["stolik_id"]] + g["stoliki_dodatkowe"]) == {s1, s2}     # bez zmian


def test_wyjscie_gosca_zwalnia_i_realokuje(admin_client):
    s1, s2, s3, blok, grupa = _scenariusz_kombinacja(admin_client)
    # blokadę sadzamy i wypuszczamy → S3 wolny → grupa przeskakuje na S3
    admin_client.post(f"/api/host/rezerwacja/{blok}/faza", json={"faza": "posadzony"})
    assert admin_client.post(f"/api/host/rezerwacja/{blok}/faza",
                             json={"faza": "wyszedl"}).status_code == 200
    g = _rez_out(admin_client, DZIEN, grupa)
    assert g["stolik_id"] == s3 and g["stoliki_dodatkowe"] == []


def test_auto_no_show_oznacza_przeterminowane(admin_client):
    admin_client.put("/api/lokal/config", json={"rez_no_show_po_min": 15})
    s = _stolik(admin_client, "S", 4)
    spozniona = _rez(admin_client, PRZESZLOSC, "12:00", 2, stolik_id=s)
    out = admin_client.post(f"/api/host/auto-no-show?data={PRZESZLOSC}").json()
    assert spozniona in out["oznaczone"]
    assert _rez_out(admin_client, PRZESZLOSC, spozniona)["status"] == "no_show"
    # idempotencja: drugi przebieg już nic nie oznacza (status terminalny)
    assert admin_client.post(f"/api/host/auto-no-show?data={PRZESZLOSC}").json()["oznaczone"] == []


def test_auto_no_show_pomija_przybylych_i_przyszlosc(admin_client):
    admin_client.put("/api/lokal/config", json={"rez_no_show_po_min": 15})
    przybyl = _rez(admin_client, PRZESZLOSC, "13:00", 2)
    admin_client.post(f"/api/host/rezerwacja/{przybyl}/faza", json={"faza": "przybyl"})
    przyszla = _rez(admin_client, PRZYSZLOSC, "12:00", 2)
    assert przybyl not in admin_client.post(f"/api/host/auto-no-show?data={PRZESZLOSC}").json()["oznaczone"]
    assert admin_client.post(f"/api/host/auto-no-show?data={PRZYSZLOSC}").json()["oznaczone"] == []
    assert _rez_out(admin_client, PRZYSZLOSC, przyszla)["status"] == "potwierdzona"


def test_auto_no_show_wylaczony_gdy_prog_zero(admin_client):
    admin_client.put("/api/lokal/config", json={"rez_no_show_po_min": 0})
    _rez(admin_client, PRZESZLOSC, "12:00", 2)
    assert admin_client.post(f"/api/host/auto-no-show?data={PRZESZLOSC}").json()["oznaczone"] == []
