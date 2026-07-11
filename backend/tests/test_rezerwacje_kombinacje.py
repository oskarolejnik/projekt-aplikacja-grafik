"""Slice 2: rozszerzony model stołu (min/kształt/cechy/priorytet) + predefiniowane kombinacje
stołów (CRUD + walidacja + ekspozycja na planie sali)."""


def _stolik(admin_client, nazwa="S1", pojemnosc=4, **kw):
    r = admin_client.post("/api/stoliki", json={"nazwa": nazwa, "pojemnosc": pojemnosc, **kw})
    assert r.status_code == 201, r.text
    return r.json()


# ── Rozszerzony stół ─────────────────────────────────────────────────────────

def test_stolik_cechy_ksztalt_min_roundtrip(admin_client):
    s = _stolik(admin_client, nazwa="Loża 1", pojemnosc=8, pojemnosc_min=4,
                ksztalt="okragly", cechy=["okno", "loza"], priorytet=5)
    assert s["pojemnosc_min"] == 4 and s["ksztalt"] == "okragly"
    assert s["cechy"] == ["okno", "loza"] and s["priorytet"] == 5
    # GET zwraca te same pola
    lista = admin_client.get("/api/stoliki").json()["stoliki"]
    got = next(x for x in lista if x["id"] == s["id"])
    assert got["cechy"] == ["okno", "loza"] and got["pojemnosc_min"] == 4


def test_stolik_bez_nowych_pol_dziala(admin_client):
    # regresja: stary payload (tylko nazwa+pojemnosc) nadal działa, nowe pola = None/[]
    s = _stolik(admin_client)
    assert s["pojemnosc_min"] is None and s["cechy"] is None and s["ksztalt"] is None


# ── Kombinacje: CRUD + walidacja ─────────────────────────────────────────────

def test_kombinacja_tworzenie_liczy_pojemnosc(admin_client):
    a = _stolik(admin_client, nazwa="S1", pojemnosc=2)
    b = _stolik(admin_client, nazwa="S2", pojemnosc=4)
    r = admin_client.post("/api/kombinacje", json={"nazwa": "S1+S2", "stoliki": [a["id"], b["id"]]})
    assert r.status_code == 201, r.text
    k = r.json()
    assert k["stoliki"] == [a["id"], b["id"]]
    assert k["pojemnosc_max"] == 6              # suma pojemności składowych
    assert any(x["id"] == k["id"] for x in admin_client.get("/api/kombinacje").json()["kombinacje"])


def test_kombinacja_override_pojemnosci(admin_client):
    a = _stolik(admin_client, nazwa="S1", pojemnosc=2)
    b = _stolik(admin_client, nazwa="S2", pojemnosc=2)
    k = admin_client.post("/api/kombinacje", json={
        "nazwa": "Duży stół", "stoliki": [a["id"], b["id"]], "pojemnosc_max": 10, "pojemnosc_min": 6}).json()
    assert k["pojemnosc_max"] == 10 and k["pojemnosc_min"] == 6


def test_kombinacja_odrzuca_niespojny_lub_zerowy_zakres(admin_client):
    a = _stolik(admin_client, nazwa="S1", pojemnosc=2)
    b = _stolik(admin_client, nazwa="S2", pojemnosc=2)
    assert admin_client.post("/api/kombinacje", json={
        "nazwa": "Błędna", "stoliki": [a["id"], b["id"]],
        "pojemnosc_min": 5, "pojemnosc_max": 4,
    }).status_code == 400
    assert admin_client.post("/api/kombinacje", json={
        "nazwa": "Zero", "stoliki": [a["id"], b["id"]], "pojemnosc_max": 0,
    }).status_code == 422
    assert admin_client.get("/api/kombinacje").json()["kombinacje"] == []


def test_stolik_musi_miec_dodatnia_pojemnosc(admin_client):
    assert admin_client.post("/api/stoliki", json={
        "nazwa": "Uszkodzony", "pojemnosc": 0,
    }).status_code == 422
    assert admin_client.post("/api/stoliki", json={
        "nazwa": "Niespójny", "pojemnosc": 2, "pojemnosc_min": 3,
    }).status_code == 400
    assert admin_client.get("/api/stoliki").json()["stoliki"] == []


def test_kombinacja_wymaga_dwoch_roznych_stolow(admin_client):
    a = _stolik(admin_client, nazwa="S1")
    assert admin_client.post("/api/kombinacje", json={"nazwa": "X", "stoliki": [a["id"]]}).status_code == 400
    # duplikat = 1 unikat → też 400
    assert admin_client.post("/api/kombinacje", json={"nazwa": "X", "stoliki": [a["id"], a["id"]]}).status_code == 400


def test_kombinacja_nieznany_stolik_400(admin_client):
    a = _stolik(admin_client, nazwa="S1")
    assert admin_client.post("/api/kombinacje", json={"nazwa": "X", "stoliki": [a["id"], 99999]}).status_code == 400


def test_kombinacja_edycja_i_usuwanie(admin_client):
    a = _stolik(admin_client, nazwa="S1", pojemnosc=2)
    b = _stolik(admin_client, nazwa="S2", pojemnosc=2)
    c = _stolik(admin_client, nazwa="S3", pojemnosc=4)
    k = admin_client.post("/api/kombinacje", json={"nazwa": "S1+S2", "stoliki": [a["id"], b["id"]]}).json()
    r = admin_client.put(f"/api/kombinacje/{k['id']}", json={"nazwa": "S1+S2+S3",
        "stoliki": [a["id"], b["id"], c["id"]]})
    assert r.status_code == 200 and r.json()["pojemnosc_max"] == 8   # 2+2+4
    assert admin_client.delete(f"/api/kombinacje/{k['id']}").status_code == 204
    assert admin_client.get("/api/kombinacje").json()["kombinacje"] == []


def test_nie_mozna_usunac_stolika_uzytego_w_kombinacji(admin_client):
    a = _stolik(admin_client, nazwa="S1", pojemnosc=2)
    b = _stolik(admin_client, nazwa="S2", pojemnosc=2)
    kombinacja = admin_client.post(
        "/api/kombinacje", json={"nazwa": "S1+S2", "stoliki": [a["id"], b["id"]]}
    ).json()

    r = admin_client.delete(f"/api/stoliki/{a['id']}")

    assert r.status_code == 409
    pozostale = admin_client.get("/api/kombinacje").json()["kombinacje"]
    assert next(k for k in pozostale if k["id"] == kombinacja["id"])["stoliki"] == [
        a["id"], b["id"]
    ]
    assert any(s["id"] == a["id"] for s in admin_client.get("/api/stoliki").json()["stoliki"])


def test_kombinacje_sortowane_po_priorytecie(admin_client):
    a = _stolik(admin_client, nazwa="S1")
    b = _stolik(admin_client, nazwa="S2")
    admin_client.post("/api/kombinacje", json={"nazwa": "B", "stoliki": [a["id"], b["id"]], "priorytet": 5})
    admin_client.post("/api/kombinacje", json={"nazwa": "A", "stoliki": [a["id"], b["id"]], "priorytet": 1})
    nazwy = [k["nazwa"] for k in admin_client.get("/api/kombinacje").json()["kombinacje"]]
    assert nazwy == ["A", "B"]


def test_silnik_respektuje_priorytet_predefiniowanej_kombinacji(admin_client):
    a = _stolik(admin_client, nazwa="S1", pojemnosc=4)
    b = _stolik(admin_client, nazwa="S2", pojemnosc=4)
    c = _stolik(admin_client, nazwa="S3", pojemnosc=4)
    d = _stolik(admin_client, nazwa="S4", pojemnosc=4)
    admin_client.post(
        "/api/kombinacje",
        json={"nazwa": "S1+S2", "stoliki": [a["id"], b["id"]], "priorytet": 10},
    )
    admin_client.post(
        "/api/kombinacje",
        json={"nazwa": "S3+S4", "stoliki": [c["id"], d["id"]], "priorytet": 1},
    )

    r = admin_client.get(
        "/api/host/sugestia-stolika?data=2026-07-13&godz_od=18:00&osoby=8"
    )

    assert r.status_code == 200, r.text
    assert r.json()["kandydaci"][0]["stoliki"] == [c["id"], d["id"]]


# ── Ekspozycja na planie sali ────────────────────────────────────────────────

def test_plan_sali_zwraca_kombinacje_i_cechy(admin_client):
    a = _stolik(admin_client, nazwa="S1", pojemnosc=2, cechy=["okno"])
    b = _stolik(admin_client, nazwa="S2", pojemnosc=4)
    admin_client.post("/api/kombinacje", json={"nazwa": "S1+S2", "stoliki": [a["id"], b["id"]]})
    plan = admin_client.get("/api/plan-sali?data=2026-07-13").json()
    assert len(plan["kombinacje"]) == 1 and plan["kombinacje"][0]["pojemnosc_max"] == 6
    st = next(x for x in plan["stoliki"] if x["id"] == a["id"])
    assert st["cechy"] == ["okno"]


def test_kombinacje_gating_pro(admin_client):
    assert admin_client.put("/api/lokal/config", json={"modul_rezerwacje": False}).status_code == 200
    assert admin_client.get("/api/kombinacje").status_code == 403
