"""Admin może ustawiać / zmieniać / czyścić dyspozycyjność pracowników.

POST /api/dyspozycje  – upsert (jedna na pracownika+dzień),
DELETE /api/dyspozycje/{id} – „wyczyść" (powrót do braku zgłoszenia).
Endpoint jest admin-only (middleware) — pracownik dostaje 403.
"""

import factories
import models

DATA = str(factories.dzien(0))  # poniedziałek 2026-06-01


def test_admin_tworzy_dyspozycje(admin_client, db):
    prac = factories.PracownikFactory()
    r = admin_client.post("/api/dyspozycje", json={"pracownik_id": prac.id, "data": DATA, "dostepnosc": True, "godz_od": "12:00"})
    assert r.status_code == 201
    d = db.query(models.Dyspozycja).filter_by(pracownik_id=prac.id).one()
    assert d.dostepnosc is True
    assert d.godz_od.strftime("%H:%M") == "12:00"


def test_admin_nadpisuje_istniejaca_dyspozycje(admin_client, db):
    prac = factories.PracownikFactory()
    admin_client.post("/api/dyspozycje", json={"pracownik_id": prac.id, "data": DATA, "dostepnosc": True, "godz_od": None})
    r = admin_client.post("/api/dyspozycje", json={"pracownik_id": prac.id, "data": DATA, "dostepnosc": False, "godz_od": None})
    assert r.status_code == 201
    # upsert — nadal jeden wiersz, ale zmieniony stan
    assert db.query(models.Dyspozycja).filter_by(pracownik_id=prac.id).count() == 1
    assert db.query(models.Dyspozycja).filter_by(pracownik_id=prac.id).one().dostepnosc is False


def test_admin_czysci_dyspozycje(admin_client, db):
    prac = factories.PracownikFactory()
    did = admin_client.post(
        "/api/dyspozycje", json={"pracownik_id": prac.id, "data": DATA, "dostepnosc": True, "godz_od": None}
    ).json()["id"]
    r = admin_client.delete(f"/api/dyspozycje/{did}")
    assert r.status_code == 204
    assert db.query(models.Dyspozycja).filter_by(pracownik_id=prac.id).count() == 0


def test_delete_nieistniejacej_404(admin_client):
    assert admin_client.delete("/api/dyspozycje/999999").status_code == 404


def test_pracownik_nie_edytuje_dyspozycji_przez_admin_endpoint(make_employee_client):
    prac = factories.PracownikFactory()
    c, _ = make_employee_client(prac)
    r = c.post("/api/dyspozycje", json={"pracownik_id": prac.id, "data": DATA, "dostepnosc": True, "godz_od": None})
    assert r.status_code == 403
