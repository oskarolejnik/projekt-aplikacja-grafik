"""RBAC — domyślna rola, wyjątki per konto i redakcja wrażliwych stawek."""

from types import SimpleNamespace

import factories
import models
import uprawnienia
from auth import create_access_token


def _h(user):
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def test_macierz_uprawnien():
    assert uprawnienia.ma("admin", "lokal.ustawienia")
    assert uprawnienia.ma("admin", "rezerwacje.zarzadzaj")
    assert not uprawnienia.ma("szef", "lokal.ustawienia")
    assert uprawnienia.ma("szef", "pulpit.podglad")
    assert uprawnienia.ma("szef_kuchni", "godziny_kuchni.podglad")
    assert uprawnienia.ma("employee", "me.dyspozycje")
    assert not uprawnienia.ma("employee", "rozliczenia.zarzadzaj")
    assert uprawnienia.uprawnienia("nieznana") == []


def test_resolver_naklada_tylko_znane_boolowskie_override():
    user = SimpleNamespace(
        rola="szef",
        uprawnienia_override={
            "wyplaty.podglad": False,
            "grafik.podglad": "false",
            "nieznane.podglad": True,
        },
    )
    assert not uprawnienia.ma_user(user, "wyplaty.podglad")
    assert uprawnienia.ma_user(user, "grafik.podglad")  # nie-bool jest ignorowany
    assert not uprawnienia.ma_user(user, "nieznane.podglad")


def test_admin_zawsze_ma_pelny_katalog():
    admin = SimpleNamespace(
        rola="admin",
        uprawnienia_override={"wyplaty.podglad": False},
    )
    assert uprawnienia.efektywne(admin) == uprawnienia.WSZYSTKIE
    assert uprawnienia.ma_user(admin, "wyplaty.podglad")


def test_nieznana_rola_nie_dostaje_uprawnien_z_override():
    user = SimpleNamespace(rola="stara_rola", uprawnienia_override={"wyplaty.podglad": True})
    assert uprawnienia.efektywne(user) == []


def test_me_uprawnienia_admin(admin_client):
    r = admin_client.get("/api/me/uprawnienia")
    assert r.status_code == 200
    b = r.json()
    assert b["rola"] == "admin"
    assert "lokal.ustawienia" in b["uprawnienia"]
    assert "rezerwacje.zarzadzaj" in b["uprawnienia"]


def test_me_uprawnienia_pracownik(make_employee_client, company):
    prac = company["pracownicy"][0]["obj"]
    c, _ = make_employee_client(prac)
    b = c.get("/api/me/uprawnienia").json()
    assert b["rola"] == "employee"
    assert "me.dyspozycje" in b["uprawnienia"]
    assert "lokal.ustawienia" not in b["uprawnienia"]


def test_me_uprawnienia_wymaga_logowania(client):
    assert client.get("/api/me/uprawnienia").status_code == 401


def test_me_uprawnienia_zwraca_efektywne_override(client):
    szef = factories.UserFactory(
        login="szef_override_me",
        rola="szef",
        pracownik=None,
        uprawnienia_override={"wyplaty.podglad": False},
    )
    body = client.get("/api/me/uprawnienia", headers=_h(szef)).json()
    assert "wyplaty.podglad" not in body["uprawnienia"]
    assert "grafik.podglad" in body["uprawnienia"]


def test_admin_ustawia_i_resetuje_override_do_roli(admin_client, db):
    szef = factories.UserFactory(login="szef_uprawnienia", rola="szef", pracownik=None)

    r = admin_client.put(
        f"/api/users/{szef.id}/uprawnienia",
        json={"uprawnienia_override": {
            "wyplaty.podglad": False,
            "grafik.podglad": True,  # równe domyślnej — nie zapisujemy
        }},
    )
    assert r.status_code == 200
    assert r.json()["uprawnienia_override"] == {"wyplaty.podglad": False}
    assert "wyplaty.podglad" not in r.json()["uprawnienia"]

    r = admin_client.put(
        f"/api/users/{szef.id}/uprawnienia",
        json={"uprawnienia_override": {"wyplaty.podglad": True}},
    )
    assert r.status_code == 200
    assert r.json()["uprawnienia_override"] == {}
    db.expire_all()
    assert db.get(models.User, szef.id).uprawnienia_override is None


def test_put_uprawnien_odrzuca_nieznany_klucz_i_nie_admina(admin_client, client):
    szef = factories.UserFactory(login="szef_walidacja", rola="szef", pracownik=None)
    r = admin_client.put(
        f"/api/users/{szef.id}/uprawnienia",
        json={"uprawnienia_override": {"sekret.nieznany": True}},
    )
    assert r.status_code == 400

    inny_szef = factories.UserFactory(login="szef_bez_admina", rola="szef", pracownik=None)
    r = client.put(
        f"/api/users/{szef.id}/uprawnienia",
        headers=_h(inny_szef),
        json={"uprawnienia_override": {"wyplaty.podglad": False}},
    )
    assert r.status_code == 403


def test_put_uprawnien_odrzuca_konto_inne_niz_szef(admin_client):
    for rola in ("admin", "employee", "kuchnia", "szef_kuchni"):
        konto = factories.UserFactory(
            login=f"bez_override_{rola}",
            rola=rola,
            pracownik=None,
        )
        r = admin_client.put(
            f"/api/users/{konto.id}/uprawnienia",
            json={"uprawnienia_override": {}},
        )
        assert r.status_code == 400, rola


def test_zmiana_roli_czysci_override(admin_client, db):
    szef = factories.UserFactory(
        login="szef_zmiana_roli",
        rola="szef",
        pracownik=None,
        uprawnienia_override={"wyplaty.podglad": False},
    )
    r = admin_client.put(f"/api/users/{szef.id}", json={"rola": "employee"})
    assert r.status_code == 200
    assert r.json()["uprawnienia_override"] == {}
    db.expire_all()
    assert db.get(models.User, szef.id).uprawnienia_override is None


def test_szef_bez_wyplat_nie_widzi_stawek_pracownikow(client, db):
    stanowisko = factories.StanowiskoFactory(nazwa="Sala test stawek")
    pracownik = factories.PracownikFactory(imie="Jan", nazwisko="Stawkowy")
    db.add(models.StawkaPracownika(
        pracownik_id=pracownik.id,
        stanowisko_id=stanowisko.id,
        stawka=42.5,
    ))
    db.commit()
    szef = factories.UserFactory(
        login="szef_bez_wyplat",
        rola="szef",
        pracownik=None,
        uprawnienia_override={"wyplaty.podglad": False},
    )
    admin = factories.UserFactory(login="admin_stawki", rola="admin", pracownik=None)

    r = client.get("/api/pracownicy", headers=_h(szef))
    assert r.status_code == 200
    row = next(p for p in r.json() if p["id"] == pracownik.id)
    assert row["stawki"] == []

    r = client.get("/api/pracownicy", headers=_h(admin))
    row = next(p for p in r.json() if p["id"] == pracownik.id)
    assert row["stawki"] == [{
        "stanowisko_id": stanowisko.id,
        "stawka": 42.5,
    }]
