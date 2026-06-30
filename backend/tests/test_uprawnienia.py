"""RBAC — granularne uprawnienia (macierz rola→uprawnienia + /api/me/uprawnienia)."""

import uprawnienia


def test_macierz_uprawnien():
    assert uprawnienia.ma("admin", "lokal.ustawienia")
    assert uprawnienia.ma("admin", "rezerwacje.zarzadzaj")
    assert not uprawnienia.ma("szef", "lokal.ustawienia")
    assert uprawnienia.ma("szef", "pulpit.podglad")
    assert uprawnienia.ma("szef_kuchni", "godziny_kuchni.podglad")
    assert uprawnienia.ma("employee", "me.dyspozycje")
    assert not uprawnienia.ma("employee", "rozliczenia.zarzadzaj")
    assert uprawnienia.uprawnienia("nieznana") == []


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
