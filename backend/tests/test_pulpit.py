"""Pulpit właściciela (/api/pulpit) — agregacja KPI z istniejących danych."""

import datetime as dt

import models


def test_pulpit_pusty(admin_client):
    r = admin_client.get("/api/pulpit?start=2026-07-01&end=2026-07-07")
    assert r.status_code == 200
    b = r.json()
    assert b["przychod"]["razem"] == 0
    assert b["rozchod"]["razem"] == 0
    assert b["saldo_kasy"] == 0
    assert b["ruch"]["rachunki"] == 0
    assert b["rezerwacje"]["razem"] == 0
    assert b["koszt_pracy_miesiac"]["kwota"] == 0


def test_pulpit_agreguje(admin_client, db):
    # przychód (gotówka 1000 + karta 500) i rozchód 200 w zeszycie kasowym
    admin_client.post("/api/zeszyt/przychod", json={"data": "2026-07-02", "zrodlo": "Test", "gotowka": 1000, "terminal": 500})
    admin_client.post("/api/zeszyt/pozycja", json={"data": "2026-07-02", "kolumna": "towar", "opis": "x", "kwota": 200})
    # ruch (rachunki z POS)
    db.add(models.StolikiHistoria(data=dt.date(2026, 7, 2), liczba=37)); db.commit()
    # rezerwacja stolika
    st = admin_client.post("/api/stoliki", json={"nazwa": "S1", "pojemnosc": 4}).json()
    admin_client.post("/api/rezerwacje-stolik", json={"data": "2026-07-02", "godz_od": "18:00",
                      "stolik_id": st["id"], "liczba_osob": 4, "nazwisko": "Gość"})

    b = admin_client.get("/api/pulpit?start=2026-07-01&end=2026-07-07").json()
    assert b["przychod"]["gotowka"] == 1000
    assert b["przychod"]["karta"] == 500
    assert b["przychod"]["razem"] == 1500
    assert b["rozchod"]["razem"] == 200
    assert b["saldo_kasy"] == 800          # 1000 gotówki − 200 rozchodu (karta nie wchodzi do salda gotówkowego)
    assert b["ruch"]["rachunki"] == 37
    assert b["rezerwacje"]["razem"] == 1
    assert b["rezerwacje"]["goscie"] == 4
    assert b["rezerwacje"]["wg_statusu"]["potwierdzona"] == 1


def test_pulpit_filtruje_okres(admin_client, db):
    db.add(models.StolikiHistoria(data=dt.date(2026, 8, 15), liczba=10)); db.commit()
    b = admin_client.get("/api/pulpit?start=2026-07-01&end=2026-07-31").json()
    assert b["ruch"]["rachunki"] == 0      # sierpień poza okresem


def test_pulpit_zly_zakres(admin_client):
    assert admin_client.get("/api/pulpit?start=2026-07-31&end=2026-07-01").status_code == 400
