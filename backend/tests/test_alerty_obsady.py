"""Alerty niedoboru obsady — GET /api/alerty-obsady (wymagane > obsadzone na stanowisku)."""

from datetime import date, timedelta

import factories
import models
from auth import create_access_token


def test_alert_gdy_niedobor(admin_client, db):
    sala = factories.StanowiskoFactory(nazwa="Sala")
    jutro = date.today() + timedelta(days=1)
    db.add(models.WymaganiaDnia(data=jutro, stanowisko_id=sala.id, liczba_osob=3))
    db.add(models.PrzydzialZmiany(data=jutro, stanowisko_id=sala.id, pracownik_id=factories.PracownikFactory().id))
    db.commit()
    r = admin_client.get("/api/alerty-obsady?dni=14").json()
    assert r["razem_brakuje"] == 2
    a = r["alerty"][0]
    assert a["stanowisko"] == "Sala" and a["wymagane"] == 3 and a["obsadzone"] == 1 and a["brakuje"] == 2


def test_brak_alertu_gdy_w_pelni_obsadzone(admin_client, db):
    sala = factories.StanowiskoFactory(nazwa="Sala")
    jutro = date.today() + timedelta(days=1)
    db.add(models.WymaganiaDnia(data=jutro, stanowisko_id=sala.id, liczba_osob=2))
    for _ in range(2):
        db.add(models.PrzydzialZmiany(data=jutro, stanowisko_id=sala.id, pracownik_id=factories.PracownikFactory().id))
    db.commit()
    assert admin_client.get("/api/alerty-obsady").json()["alerty"] == []


def test_pomija_dni_z_przeszlosci(admin_client, db):
    sala = factories.StanowiskoFactory(nazwa="Sala")
    wczoraj = date.today() - timedelta(days=1)
    db.add(models.WymaganiaDnia(data=wczoraj, stanowisko_id=sala.id, liczba_osob=5))   # brak obsady, ale w przeszłości
    db.commit()
    assert admin_client.get("/api/alerty-obsady").json()["alerty"] == []


def test_szef_widzi_alerty_obsady(db):
    from fastapi.testclient import TestClient
    import main
    szef = factories.UserFactory(login="szef_ob", rola="szef")
    c = TestClient(main.app)
    c.headers.update({"Authorization": f"Bearer {create_access_token(szef)}"})
    assert c.get("/api/alerty-obsady").status_code == 200


def test_pracownik_nie_widzi_alertow_obsady(make_employee_client, db):
    p = factories.PracownikFactory()
    ce, _ = make_employee_client(p)
    assert ce.get("/api/alerty-obsady").status_code == 403
