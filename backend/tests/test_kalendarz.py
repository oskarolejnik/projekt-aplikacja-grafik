"""Kalendarz imprez — CRUD terminów + parsowanie/dopasowanie zadatków KP."""

import datetime as dt
from datetime import date

import factories
import models


def test_kalendarz_imprez_nie_pokazuje_rezerwacji_stolikow(admin_client, db):
    """Kalendarz imprez i rezerwacje stolików to OSOBNE byty (choć obie na encji Termin).
    /api/terminy zwraca tylko imprezy (rodzaj≠stolik); rezerwacji stolika nie da się też
    edytować/usunąć przez API imprez."""
    d = factories.dzien(0)
    admin_client.post("/api/terminy", json={"data": str(d), "nazwisko": "Wesele Nowak", "typ": "wesele"})
    db.add(models.Termin(rodzaj="stolik", data=d, nazwisko="Gość Stolik", status="potwierdzona",
                         kanal="reczna", zadatek=0.0, liczba_osob=2, godz_od=dt.time(18, 0),
                         utworzono_at=dt.datetime.utcnow()))
    db.commit()

    lst = admin_client.get(f"/api/terminy?start={d}&end={d}").json()["terminy"]
    assert [t["nazwisko"] for t in lst] == ["Wesele Nowak"]     # rezerwacja stolika NIE trafia do kalendarza

    sid = db.query(models.Termin).filter_by(rodzaj="stolik").first().id
    assert admin_client.put(f"/api/terminy/{sid}", json={"data": str(d), "nazwisko": "X"}).status_code == 404
    assert admin_client.delete(f"/api/terminy/{sid}").status_code == 404


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


def test_parsowanie_i_dopasowanie_zadatkow(client, admin_client, db, monkeypatch):
    import main
    monkeypatch.setenv("RCP_INGEST_TOKEN", "tok123")   # helper czyta env w momencie wywolania
    # parser
    assert main._parsuj_zadatek("Zadatek za komunie p.Nowak 15.05.2027") == ("Nowak", date(2027, 5, 15))
    assert main._parsuj_zadatek("26.07.2026 p. Wojtyra zadatek za chrzciny") == ("Wojtyra", date(2026, 7, 26))
    assert main._parsuj_zadatek("kaucja za koryta") == (None, None)
    # termin dla Nowaka na 2027-05-15
    admin_client.post("/api/terminy", json={"data": "2027-05-15", "nazwisko": "Nowak", "typ": "komunia"})
    # ingest dwóch KP -> jeden się dopasuje, drugi do skrzynki
    client.post("/api/gastro/zadatki", json={"zadatki": [
        {"id": "z1", "kwota": 500, "opis": "Zadatek za komunie p.Nowak 15.05.2027", "data": "2026-06-10"},
        {"id": "z2", "kwota": 500, "opis": "kaucja za koryta", "data": "2026-06-10"},
    ]}, headers={"X-RCP-Token": "tok123"})
    # auto-dopasowanie przy ingescie: z1 (Nowak 15.05.2027) dopina się do terminu → zadatek_kp;
    # z2 (bez rozpoznanej daty) zostaje niedopasowany. Ręczna skrzynka KP (/api/zadatki) usunięta.
    t = admin_client.get("/api/terminy?start=2027-05-01&end=2027-05-31").json()["terminy"][0]
    assert t["zadatek_kp"] == 500.0
