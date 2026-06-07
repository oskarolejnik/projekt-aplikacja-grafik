"""Rola 'szef' — oversight TYLKO DO ODCZYTU: wybrane GET dozwolone, reszta 403."""

import factories
from auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(u)}"}


def test_szef_ma_dostep_do_podgladow(client, db):
    szef = factories.UserFactory(login="szef1", rola="szef")
    h = _h(szef)
    dozwolone = (
        "/api/raporty/godziny?rok=2026&miesiac=6",
        "/api/imprezy?start=2026-06-01&end=2026-06-07",
        "/api/przydzialy?start=2026-06-01&end=2026-06-07",
        "/api/grafik/publikacja?start=2026-06-01&end=2026-06-07",
        "/api/pracownicy",
        "/api/stanowiska",
    )
    for path in dozwolone:
        assert client.get(path, headers=h).status_code == 200, path


def test_szef_nie_widzi_innych_zasobow(client, db):
    szef = factories.UserFactory(login="szef2", rola="szef")
    h = _h(szef)
    assert client.get("/api/dyspozycje?start=2026-06-01&end=2026-06-07", headers=h).status_code == 403
    assert client.get("/api/users", headers=h).status_code == 403
    assert client.get("/api/wymagania?start=2026-06-01&end=2026-06-07", headers=h).status_code == 403


def test_szef_nie_moze_modyfikowac(client, db):
    szef = factories.UserFactory(login="szef3", rola="szef")
    h = _h(szef)
    assert client.post("/api/pracownicy", headers=h,
                       json={"imie": "X", "nazwisko": "Y", "aktywny": True, "kwalifikacje_ids": []}).status_code == 403
    assert client.delete("/api/przydzialy?start=2026-06-01&end=2026-06-07", headers=h).status_code == 403


def test_admin_moze_zalozyc_konto_szefa(admin_client, db):
    r = admin_client.post("/api/users", json={"login": "szefnowy", "haslo": "Haslo123!", "rola": "szef"})
    assert r.status_code == 201
    assert r.json()["rola"] == "szef"
