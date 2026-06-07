"""Stoły (live z Gastro): ingest tokenem agenta, grupowanie wewnątrz/zewnątrz/wynos, dostęp szefa.
Ścieżka addytywna — nie dotyka RCP/godzin."""

import factories
from auth import create_access_token

TOKEN = {"X-RCP-Token": "test-rcp-token"}


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(u)}"}


def test_ingest_stoly_wymaga_tokenu(client):
    assert client.post("/api/gastro/stoly", json={"stoly": []}).status_code == 401


def test_ingest_i_grupowanie(client, admin_client, db):
    payload = {"stoly": [
        {"rewir_nr": 42, "otwarte": 4},   # Parter
        {"rewir_nr": 52, "otwarte": 5},   # Góra
        {"rewir_nr": 56, "otwarte": 10},  # Zielona
        {"rewir_nr": 54, "otwarte": 7},   # TARAS (zewnątrz)
        {"rewir_nr": 55, "otwarte": 4},   # STRZECHA (zewnątrz)
        {"rewir_nr": 108, "otwarte": 5},  # Zetka+Ka (zewnątrz)
        {"rewir_nr": 46, "otwarte": 3},   # WYNOS
    ]}
    assert client.post("/api/gastro/stoly", headers=TOKEN, json=payload).status_code == 200
    d = admin_client.get("/api/gastro/stoly").json()
    assert [w["nazwa"] for w in d["wewnatrz"]] == ["Parter", "Góra", "Zielona", "Kryształowa"]
    assert d["wewnatrz"][3]["liczba"] == 0     # Kryształowa nieprzysłana -> 0
    assert d["wewnatrz_suma"] == 19            # 4+5+10+0
    assert d["na_zewnatrz"] == 16              # 7+4+0(FLINSTONY brak)+5
    assert d["wynos"] == 3


def test_upsert_nadpisuje_snapshot(client, admin_client, db):
    client.post("/api/gastro/stoly", headers=TOKEN, json={"stoly": [{"rewir_nr": 42, "otwarte": 4}]})
    client.post("/api/gastro/stoly", headers=TOKEN, json={"stoly": [{"rewir_nr": 42, "otwarte": 9}]})
    d = admin_client.get("/api/gastro/stoly").json()
    assert d["wewnatrz"][0]["liczba"] == 9


def test_szef_widzi_stoly_a_pracownik_nie(client, db, make_employee_client):
    szef = factories.UserFactory(login="szefstoly", rola="szef")
    assert client.get("/api/gastro/stoly", headers=_h(szef)).status_code == 200
    prac = factories.PracownikFactory()
    c, _ = make_employee_client(prac)
    assert c.get("/api/gastro/stoly").status_code == 403
