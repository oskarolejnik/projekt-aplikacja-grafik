"""Etap D — rozliczenia. D1: flagi przydziału „zamyka rewir" i „rozlicza imprezę"
(ustawiane w grafiku, widoczne w „Moim grafiku")."""

from datetime import datetime

import models
import factories
from auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(u)}"}


def test_przydzial_flagi_zamyka_rewir_i_rozlicza_imprize(admin_client, client, db):
    sala = factories.StanowiskoFactory(nazwa="Sala")
    p = factories.PracownikFactory(dzial="obsluga")
    u = factories.UserFactory(login="emp_d1", rola="employee", pracownik=p)
    d = factories.dzien(0)
    r = admin_client.post("/api/przydzialy", json={
        "data": str(d), "stanowisko_id": sala.id, "pracownik_id": p.id,
        "godz_od": "16:00", "rewir": "Parter", "zamyka_rewir": True, "rozlicza_imprize": True})
    assert r.status_code == 201
    aid = r.json()["id"]
    assert r.json()["zamyka_rewir"] is True and r.json()["rozlicza_imprize"] is True

    db.add(models.PublikacjaGrafiku(start=d, koniec=factories.dzien(6), opublikowano_at=datetime.utcnow()))
    db.commit()
    z = client.get("/api/me/grafik", headers=_h(u),
                   params={"start": str(d), "end": str(factories.dzien(6))}).json()["zmiany"][0]
    assert z["zamyka_rewir"] is True and z["rozlicza_imprize"] is True

    # PUT może je wyłączyć
    admin_client.put(f"/api/przydzialy/{aid}", json={
        "data": str(d), "stanowisko_id": sala.id, "pracownik_id": p.id, "rewir": "Parter",
        "zamyka_rewir": False, "rozlicza_imprize": False})
    db.expire_all()
    rec = db.get(models.PrzydzialZmiany, aid)
    assert rec.zamyka_rewir is False and rec.rozlicza_imprize is False


def test_flagi_domyslnie_false(admin_client, db):
    sala = factories.StanowiskoFactory(nazwa="Sala")
    p = factories.PracownikFactory(dzial="obsluga")
    r = admin_client.post("/api/przydzialy", json={
        "data": str(factories.dzien(1)), "stanowisko_id": sala.id, "pracownik_id": p.id})
    assert r.status_code == 201
    assert r.json()["zamyka_rewir"] is False and r.json()["rozlicza_imprize"] is False
