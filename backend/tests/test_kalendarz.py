"""Kalendarz imprez — CRUD terminów (admin)."""

import factories


def test_terminy_crud(admin_client, db):
    d = factories.dzien(0)
    r = admin_client.post("/api/terminy", json={
        "data": str(d), "nazwisko": "Nowak", "typ": "wesele", "liczba_osob": 80,
        "telefon": "500100200", "sala": "Kryształowa", "zadatek": 500})
    assert r.status_code == 201
    tid = r.json()["id"]
    assert r.json()["nazwisko"] == "Nowak" and r.json()["typ"] == "wesele" and r.json()["liczba_osob"] == 80

    lst = admin_client.get(f"/api/terminy?start={d}&end={d}").json()["terminy"]
    assert len(lst) == 1 and lst[0]["zadatek"] == 500 and lst[0]["sala"] == "Kryształowa"

    admin_client.put(f"/api/terminy/{tid}", json={"data": str(d), "nazwisko": "Nowak", "status": "odbyla", "zadatek": 500})
    assert admin_client.get(f"/api/terminy?start={d}&end={d}").json()["terminy"][0]["status"] == "odbyla"

    assert admin_client.delete(f"/api/terminy/{tid}").status_code == 204
    assert admin_client.get(f"/api/terminy?start={d}&end={d}").json()["terminy"] == []


def test_terminy_tylko_w_zakresie(admin_client, db):
    d0, d9 = factories.dzien(0), factories.dzien(9)
    admin_client.post("/api/terminy", json={"data": str(d0), "nazwisko": "A"})
    admin_client.post("/api/terminy", json={"data": str(d9), "nazwisko": "B"})
    lst = admin_client.get(f"/api/terminy?start={d0}&end={factories.dzien(6)}").json()["terminy"]
    assert [t["nazwisko"] for t in lst] == ["A"]   # B poza zakresem
