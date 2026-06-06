"""Test dymny — weryfikuje, że harness (baza testowa, klient, fabryki, auth) działa."""

import models
import factories


def test_health_publiczny(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_fabryka_zapisuje_do_bazy(db):
    s = factories.StanowiskoFactory(nazwa="Kuchnia")
    assert s.id is not None
    assert db.query(models.Stanowisko).filter_by(nazwa="Kuchnia").count() == 1


def test_izolacja_bazy(db):
    # Po poprzednim teście baza jest czyszczona — brak stanowisk na starcie.
    assert db.query(models.Stanowisko).count() == 0


def test_admin_ma_dostep(admin_client):
    assert admin_client.get("/api/pracownicy").status_code == 200


def test_brak_tokenu_blokuje_trase_admina(client):
    assert client.get("/api/pracownicy").status_code == 401


def test_build_company_daje_15_pracownikow(company, db):
    assert len(company["pracownicy"]) >= 15
    assert db.query(models.Pracownik).count() >= 15
