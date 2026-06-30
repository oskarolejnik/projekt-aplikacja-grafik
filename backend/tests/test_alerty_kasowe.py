"""Alerty anomalii kasowych (/api/alerty-kasowe) + podsumowanie w /api/pulpit."""

import datetime as dt

import models


def _rozliczenie(db, data, prac, kelner, terminale, kasy):
    roz = models.RozliczenieDnia(data=data, status="robocze", utworzono_at=dt.datetime.utcnow())
    db.add(roz); db.flush()
    db.add(models.RozliczenieKelner(rozliczenie_id=roz.id, pracownik_id=prac.id, **kelner))
    roz.terminale = terminale
    roz.kasy = kasy
    db.commit()
    return roz


def test_alerty_pusty(admin_client):
    r = admin_client.get("/api/alerty-kasowe?start=2026-07-01&end=2026-07-31")
    assert r.status_code == 200
    assert r.json()["dni_z_anomalia"] == 0


def test_alerty_wykrywa_brak_na_kartach(admin_client, db, company):
    prac = company["pracownicy"][0]["obj"]
    # karta zadeklarowana 500, terminale 450 -> różnica kart -50; kasa zbalansowana (kasy=500)
    _rozliczenie(db, dt.date(2026, 7, 2), prac, {"gotowka": 0, "karta": 500},
                 [{"etykieta": "T1", "kwota": 450, "rewir": None}], [{"etykieta": "K1", "kwota": 500, "rewir": None}])
    r = admin_client.get("/api/alerty-kasowe?start=2026-07-01&end=2026-07-31&prog=1").json()
    assert r["dni_z_anomalia"] == 1
    a = r["alerty"][0]
    assert a["data"] == "2026-07-02"
    karty = next(p for p in a["problemy"] if p["typ"] == "karty")
    assert karty["roznica"] == -50
    assert a["braki"] == -50
    assert r["suma_braki"] == -50


def test_alerty_zbalansowany_brak_alertu(admin_client, db, company):
    prac = company["pracownicy"][0]["obj"]
    # gotówka 100 + karta 200; terminale 200; kasy 300 -> obie różnice = 0
    _rozliczenie(db, dt.date(2026, 8, 2), prac, {"gotowka": 100, "karta": 200},
                 [{"etykieta": "T1", "kwota": 200, "rewir": None}], [{"etykieta": "K1", "kwota": 300, "rewir": None}])
    r = admin_client.get("/api/alerty-kasowe?start=2026-08-01&end=2026-08-31&prog=1").json()
    assert r["dni_z_anomalia"] == 0


def test_alerty_w_pulpicie(admin_client, db, company):
    prac = company["pracownicy"][0]["obj"]
    _rozliczenie(db, dt.date(2026, 7, 3), prac, {"gotowka": 0, "karta": 500},
                 [{"etykieta": "T1", "kwota": 450, "rewir": None}], [{"etykieta": "K1", "kwota": 500, "rewir": None}])
    p = admin_client.get("/api/pulpit?start=2026-07-01&end=2026-07-31").json()
    assert p["alerty_kasowe"]["dni_z_anomalia"] == 1
    assert p["alerty_kasowe"]["suma_braki"] == -50


def test_alerty_zly_zakres(admin_client):
    assert admin_client.get("/api/alerty-kasowe?start=2026-07-31&end=2026-07-01").status_code == 400
