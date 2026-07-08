"""Slice v2 S3: graf sąsiedztwa (auto-kombinacje) + sekcje kelnerskie (balans) + hold-back dużych stołów.

Dwie warstwy:
  • silnik czysty (backend/seating.py) — auto-kombinacje z krawędzi, balans obłożenia, kwadratowy hold-back;
  • CRUD /api/sasiedztwo — normalizacja a<b, walidacja, gating Pro.
"""

import seating


def _t(id, poj, **kw):
    return {"id": id, "nazwa": f"S{id}", "pojemnosc": poj, **kw}


# ── Silnik: auto-kombinacje z grafu ──────────────────────────────────────────

def test_bez_grafu_duza_grupa_bez_dopasowania():
    stoly = [_t(1, 4), _t(2, 4), _t(3, 4)]
    assert seating.dopasuj(7, stoly, [], zajete=set()) == []       # brak predefiniowanych kombinacji


def test_auto_kombinacja_z_sasiedztwa():
    stoly = [_t(1, 4), _t(2, 4), _t(3, 4)]
    k = seating.dopasuj(7, stoly, [], zajete=set(), sasiedztwo=[(1, 2)])
    assert k and k[0]["stoliki"] == [1, 2] and k[0]["kombinacja"] is True


def test_graf_wymaga_spojnosci():
    stoly = [_t(1, 4), _t(2, 4), _t(3, 4)]
    # tylko krawędź 1-2: stół 3 izolowany → 1+2=8 < 10, brak drogi do 3
    assert seating.dopasuj(10, stoly, [], zajete=set(), sasiedztwo=[(1, 2)]) == []
    # łańcuch 1-2-3 = 12 ≥ 10
    k = seating.dopasuj(10, stoly, [], zajete=set(), sasiedztwo=[(1, 2), (2, 3)])
    assert k and set(k[0]["stoliki"]) == {1, 2, 3}


def test_graf_pomija_zajety_skladnik():
    stoly = [_t(1, 4), _t(2, 4)]
    assert seating.dopasuj(7, stoly, [], zajete={2}, sasiedztwo=[(1, 2)]) == []


def test_graf_woli_pojedynczy_gdy_sie_miesci():
    # grupa 4 mieści się na jednym stole → auto-kombinacja nie wypiera pojedynczego
    stoly = [_t(1, 4), _t(2, 4)]
    k = seating.dopasuj(4, stoly, [], zajete=set(), sasiedztwo=[(1, 2)])
    assert k[0]["stoliki"] == [1] and k[0]["kombinacja"] is False


# ── Silnik: hold-back (kwadratowa kara za nadmiar ≥ progu) ────────────────────

def test_holdback_dolicza_kwadratowa_kare():
    kand = {"stoliki": [1], "suma_pojemnosci": 12, "kombinacja": False, "_stoly": [_t(1, 12)]}
    c_bez = seating.koszt(kand, 4, set(), None, {"holdback": 0})       # nadmiar 8, kara wyłączona
    c_z = seating.koszt(kand, 4, set(), None, None)                    # domyślny holdback 0.6
    assert c_z - c_bez == seating.DOMYSLNE_WAGI["holdback"] * (12 - 4) ** 2


def test_holdback_nieaktywny_ponizej_progu():
    kand = {"stoliki": [1], "suma_pojemnosci": 5, "kombinacja": False, "_stoly": [_t(1, 5)]}
    # nadmiar 2 < HOLDBACK_PROG (4) → kara nie rusza
    assert seating.koszt(kand, 3, set(), None, None) == seating.koszt(kand, 3, set(), None, {"holdback": 0})


def test_holdback_chroni_duzy_stol_przed_mala_grupa():
    # grupa 4: mały stół (nadmiar 2, bez holdback) wygrywa z dużym (nadmiar 8, holdback)
    stoly = [_t(1, 6), _t(2, 12)]
    k = seating.dopasuj(4, stoly, [], zajete=set())
    assert k[0]["stoliki"] == [1]


# ── Silnik: balans sekcji kelnerskich ────────────────────────────────────────

def test_balans_dolicza_kare_za_obciazona_sekcje():
    kand = {"stoliki": [1], "suma_pojemnosci": 4, "kombinacja": False, "_stoly": [_t(1, 4, sekcja="A")]}
    c_bez = seating.koszt(kand, 4, set(), None, None)
    c_obc = seating.koszt(kand, 4, set(), None, None, obciazenie_sekcji={"A": 3})
    assert round(c_obc - c_bez, 3) == round(seating.DOMYSLNE_WAGI["balans_sekcji"] * 3, 3)


def test_balans_wybiera_mniej_obciazona_sekcje():
    stoly = [_t(1, 4, sekcja="A"), _t(2, 4, sekcja="B")]
    k = seating.dopasuj(4, stoly, [], zajete=set(), obciazenie_sekcji={"A": 5, "B": 0})
    assert k[0]["stoliki"] == [2]              # sekcja B mniej obłożona → tańsza


# ── CRUD /api/sasiedztwo ─────────────────────────────────────────────────────

def _stolik(admin_client, nazwa, poj=4):
    r = admin_client.post("/api/stoliki", json={"nazwa": nazwa, "pojemnosc": poj})
    assert r.status_code == 201
    return r.json()["id"]


def test_stolik_przyjmuje_sekcje(admin_client):
    r = admin_client.post("/api/stoliki", json={"nazwa": "S1", "pojemnosc": 4, "sekcja": "Ogród"})
    assert r.status_code == 201 and r.json()["sekcja"] == "Ogród"


def test_sasiedztwo_crud_normalizuje(admin_client):
    a, b = _stolik(admin_client, "A"), _stolik(admin_client, "B")
    r = admin_client.post("/api/sasiedztwo", json={"stolik_a": max(a, b), "stolik_b": min(a, b)})
    assert r.status_code == 201
    d = r.json()
    assert d["stolik_a"] == min(a, b) and d["stolik_b"] == max(a, b)   # normalizacja a<b
    lista = admin_client.get("/api/sasiedztwo").json()["krawedzie"]
    assert len(lista) == 1 and lista[0]["id"] == d["id"]
    assert admin_client.delete(f"/api/sasiedztwo/{d['id']}").status_code == 204
    assert admin_client.get("/api/sasiedztwo").json()["krawedzie"] == []


def test_sasiedztwo_walidacja(admin_client):
    a, b = _stolik(admin_client, "A"), _stolik(admin_client, "B")
    assert admin_client.post("/api/sasiedztwo", json={"stolik_a": a, "stolik_b": a}).status_code == 400
    assert admin_client.post("/api/sasiedztwo", json={"stolik_a": a, "stolik_b": 999999}).status_code == 400
    assert admin_client.post("/api/sasiedztwo", json={"stolik_a": a, "stolik_b": b}).status_code == 201
    # duplikat po normalizacji (odwrotna kolejność)
    assert admin_client.post("/api/sasiedztwo", json={"stolik_a": b, "stolik_b": a}).status_code == 409


def test_sasiedztwo_gating_pro(admin_client):
    admin_client.put("/api/lokal/config", json={"modul_rezerwacje": False})
    assert admin_client.get("/api/sasiedztwo").status_code == 403
