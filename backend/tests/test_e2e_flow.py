"""Testy E2E / integracyjne — pełne przepływy przez API i kontrola dostępu (RBAC).

Pokrywają: ochronę tras (middleware role_guard), rejestrację/logowanie oraz pełen
przepływ grafiku: pracownik składa dyspozycyjność → admin tworzy wymagania → auto-assign
→ publikacja → pracownik widzi swój grafik dopiero po publikacji.
"""

import pytest

import models
import factories
from auth import create_access_token

pytestmark = pytest.mark.e2e


def _h(user):
    return {"Authorization": f"Bearer {create_access_token(user)}"}


# ── RBAC / ochrona tras ───────────────────────────────────────────────────────
def test_brak_tokenu_blokuje_admina(client):
    assert client.get("/api/pracownicy").status_code == 401


def test_niepoprawny_token_401(client):
    client.headers.update({"Authorization": "Bearer to-nie-jest-jwt"})
    assert client.get("/api/pracownicy").status_code == 401


def test_employee_nie_wejdzie_na_trase_admina(make_employee_client):
    prac = factories.PracownikFactory()
    c, _ = make_employee_client(prac)
    assert c.get("/api/pracownicy").status_code == 403


def test_employee_ma_dostep_do_me(make_employee_client):
    prac = factories.PracownikFactory()
    c, _ = make_employee_client(prac)
    assert c.get("/api/me/dyspozycje").status_code == 200


def test_admin_ma_pelny_dostep(admin_client):
    assert admin_client.get("/api/pracownicy").status_code == 200
    assert admin_client.get("/api/stanowiska").status_code == 200


# ── Rejestracja / logowanie ───────────────────────────────────────────────────
def test_rejestracja_i_logowanie(client):
    r = client.post(
        "/api/auth/register",
        json={"login": "janek1", "haslo": "Haslo123!", "imie": "Jan", "nazwisko": "Kowalski"},
    )
    assert r.status_code == 201, r.text
    assert "access_token" in r.json()
    r2 = client.post("/api/auth/login", json={"login": "janek1", "haslo": "Haslo123!"})
    assert r2.status_code == 200
    assert r2.json()["user"]["rola"] == "employee"


def test_rejestracja_zbyt_krotki_login(client):
    r = client.post(
        "/api/auth/register",
        json={"login": "abc", "haslo": "Haslo123!", "imie": "A", "nazwisko": "B"},
    )
    assert r.status_code == 400


def test_rejestracja_slabe_haslo(client):
    r = client.post(
        "/api/auth/register",
        json={"login": "janek2", "haslo": "slabe", "imie": "A", "nazwisko": "B"},
    )
    assert r.status_code == 400


def test_logowanie_zle_haslo(client):
    client.post(
        "/api/auth/register",
        json={"login": "ola123", "haslo": "Haslo123!", "imie": "Ola", "nazwisko": "X"},
    )
    r = client.post("/api/auth/login", json={"login": "ola123", "haslo": "ZleHaslo1!"})
    assert r.status_code == 401


# ── Izolacja danych pracownika ────────────────────────────────────────────────
def test_pracownik_widzi_tylko_swoja_dyspozycyjnosc(client):
    p1 = factories.PracownikFactory()
    p2 = factories.PracownikFactory()
    u1 = factories.UserFactory(login="emp1", rola="employee", pracownik=p1)
    u2 = factories.UserFactory(login="emp2", rola="employee", pracownik=p2)
    factories.DyspozycjaFactory(pracownik=p1, data=factories.dzien(0))
    factories.DyspozycjaFactory(pracownik=p2, data=factories.dzien(0))

    r1 = client.get("/api/me/dyspozycje", headers=_h(u1))
    assert r1.status_code == 200
    assert {d["pracownik_id"] for d in r1.json()} == {p1.id}


# ── Pełny przepływ grafiku ────────────────────────────────────────────────────
def test_pelny_przeplyw_od_dyspozycyjnosci_do_grafiku(client, db):
    # Aktorzy i dane wejściowe
    admin = factories.UserFactory(login="adminx", rola="admin", pracownik=None)
    stan = factories.StanowiskoFactory(nazwa="Sala")
    prac = factories.PracownikFactory()
    prac.kwalifikacje = [stan]
    factories.Session.commit()
    emp = factories.UserFactory(login="pracx", rola="employee", pracownik=prac)

    tydzien = [factories.dzien(i) for i in range(7)]
    start, end = str(tydzien[0]), str(tydzien[6])

    # 1) Pracownik składa dyspozycyjność (cały tydzień dostępny)
    r = client.put(
        "/api/me/dyspozycje",
        headers=_h(emp),
        json={"dyspozycje": [{"data": str(d), "dostepnosc": True, "godz_od": None} for d in tydzien]},
    )
    assert r.status_code == 200 and r.json()["zapisano"] == 7

    # 2) Admin tworzy wymaganie (poniedziałek, 1 osoba na Sali)
    r = client.post(
        "/api/wymagania",
        headers=_h(admin),
        json={"data": start, "stanowisko_id": stan.id, "liczba_osob": 1},
    )
    assert r.status_code == 201

    # 3) Pracownik: grafik PRZED publikacją — nieopublikowany, brak zmian
    r = client.get("/api/me/grafik", headers=_h(emp), params={"start": start, "end": end})
    assert r.status_code == 200
    assert r.json()["opublikowany"] is False
    assert r.json()["zmiany"] == []

    # 4) Admin: automatyczne układanie grafiku
    r = client.post("/api/auto-assign", headers=_h(admin), params={"start": start, "end": end})
    assert r.status_code == 200
    assert r.json()["przydzielone"] == 1

    # 5) Admin: publikacja tygodnia
    r = client.post("/api/grafik/publikuj", headers=_h(admin), params={"start": start, "end": end})
    assert r.status_code == 200

    # 6) Pracownik: grafik PO publikacji — widzi swoją zmianę
    r = client.get("/api/me/grafik", headers=_h(emp), params={"start": start, "end": end})
    body = r.json()
    assert body["opublikowany"] is True
    assert len(body["zmiany"]) == 1
    assert body["zmiany"][0]["stanowisko"] == "Sala"
    assert body["zmiany"][0]["data"] == start


def test_kopiowanie_wymagan_na_kolejny_tydzien(admin_client, db):
    """Integracja: wymagania z tygodnia źródłowego kopiowane dzień-w-dzień na docelowy."""
    stan = factories.StanowiskoFactory(nazwa="Sala")
    src_start = factories.dzien(0)
    # 2 wymagania w tygodniu źródłowym
    factories.WymaganieFactory(stanowisko=stan, data=src_start, liczba_osob=2)
    factories.WymaganieFactory(stanowisko=stan, data=factories.dzien(2), liczba_osob=3)
    dst_start = factories.dzien(7)  # kolejny tydzień

    r = admin_client.post(
        "/api/wymagania/kopiuj-tydzien",
        json={"source_start": str(src_start), "target_start": str(dst_start)},
    )
    assert r.status_code == 200
    assert r.json()["skopiowano"] == 2
    # Wymagania pojawiły się w docelowym tygodniu (offset +7 dni)
    skopiowane = db.query(models.WymaganiaDnia).filter(
        models.WymaganiaDnia.data >= dst_start
    ).all()
    assert len(skopiowane) == 2
    assert {w.liczba_osob for w in skopiowane} == {2, 3}
