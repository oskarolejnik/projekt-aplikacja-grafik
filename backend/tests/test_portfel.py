"""Portfel pracownika (roadmapa v2, oś C) — zarobek na żywo, zaliczki, potrącenie w raporcie.

Zarobek liczony przez tę samą ścieżkę co raport wypłat (raporty.raport_godzin_miesiac) —
seed jak w test_eksport_wyplaty: stawka 30 zł/h × 8 h odbicia = 240 zł.
Uwaga na współdzielone nagłówki klienta (patrz test_portal_imprezy) — pracownik dostaje
własny, świeży TestClient.
"""

from datetime import date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient

import factories
import main
import models
import raporty
from auth import create_access_token

DZIS = date.today()
MIES = f"{DZIS.year}-{DZIS.month:02d}"


@pytest.fixture(autouse=True)
def _przycinanie_od_zawsze(monkeypatch):
    monkeypatch.setattr(raporty, "PRZYCINANIE_OD", date(2000, 1, 1))


def _klient_pracownika(user):
    c = TestClient(main.app)
    c.headers.update({"Authorization": f"Bearer {create_access_token(user)}"})
    return c


def _seed_zarobek(db, imie="Jan", nazwisko="Kowalski"):
    """Pracownik z 8 h odbicia × 30 zł/h = 240 zł w BIEŻĄCYM miesiącu (portfel liczy dziś)."""
    sala = factories.StanowiskoFactory()
    p = factories.PracownikFactory(imie=imie, nazwisko=nazwisko)
    user = factories.UserFactory(login=f"prac_{p.id}", rola="employee", pracownik=p)
    db.add(models.StawkaPracownika(pracownik_id=p.id, stanowisko_id=sala.id, stawka=30))
    db.add(models.PrzydzialZmiany(data=DZIS, stanowisko_id=sala.id, pracownik_id=p.id, godz_od=time(10, 0)))
    # publikacja ma UNIQUE(start, koniec) — przy wielokrotnym seedzie dodaj tylko raz
    if not db.query(models.PublikacjaGrafiku).filter_by(start=DZIS - timedelta(days=7)).first():
        db.add(models.PublikacjaGrafiku(start=DZIS - timedelta(days=7), koniec=DZIS + timedelta(days=7),
                                        opublikowano_at=datetime.now()))
    db.add(models.OdbicieRcp(rcp_id=f"pf-{p.id}", imie_nazwisko=f"{imie} {nazwisko}", pracownik_id=p.id,
                             data=DZIS, wejscie=datetime.combine(DZIS, time(10, 0)),
                             wyjscie=datetime.combine(DZIS, time(18, 0)), godziny=8.0))
    db.commit()
    return p, user


# ── Portfel pracownika ───────────────────────────────────────────────────────

def test_portfel_zarobek_i_limit(db):
    p, user = _seed_zarobek(db)
    c = _klient_pracownika(user)
    w = c.get("/api/me/portfel").json()
    assert w["miesiac"] == MIES
    assert w["zarobek"] == 240.0 and w["godziny"] == 8.0
    assert w["limit_procent"] == 50 and w["dostepna_zaliczka"] == 120.0
    assert w["zaliczki"] == []


def test_wniosek_zmniejsza_limit_i_walidacje(db):
    p, user = _seed_zarobek(db)
    c = _klient_pracownika(user)
    assert c.post("/api/me/portfel/zaliczki", json={"kwota": 100}).status_code == 201
    w = c.get("/api/me/portfel").json()
    assert w["dostepna_zaliczka"] == 20.0
    assert len(w["zaliczki"]) == 1 and w["zaliczki"][0]["status"] == "oczekuje"
    assert c.post("/api/me/portfel/zaliczki", json={"kwota": 50}).status_code == 400   # ponad limit
    assert c.post("/api/me/portfel/zaliczki", json={"kwota": 0}).status_code == 400
    assert c.post("/api/me/portfel/zaliczki", json={"kwota": -5}).status_code == 400


def test_portfel_wymaga_powiazania_z_pracownikiem(admin_client):
    assert admin_client.get("/api/me/portfel").status_code == 400   # admin bez pracownika


def test_wycofanie_wniosku(db):
    p, user = _seed_zarobek(db)
    c = _klient_pracownika(user)
    zid = c.post("/api/me/portfel/zaliczki", json={"kwota": 50}).json()["id"]
    p2, user2 = _seed_zarobek(db, imie="Ewa", nazwisko="Nowak")
    c2 = _klient_pracownika(user2)
    assert c2.delete(f"/api/me/portfel/zaliczki/{zid}").status_code == 404   # cudzy wniosek
    assert c.delete(f"/api/me/portfel/zaliczki/{zid}").status_code == 204
    assert c.get("/api/me/portfel").json()["zaliczki"] == []


# ── Decyzje admina + potrącenie ──────────────────────────────────────────────

def test_decyzja_admina_i_potracenie_w_raporcie(admin_client, db):
    p, user = _seed_zarobek(db)
    c = _klient_pracownika(user)
    zid = c.post("/api/me/portfel/zaliczki", json={"kwota": 100}).json()["id"]

    lista = admin_client.get("/api/zaliczki").json()
    assert lista and lista[0]["pracownik"] == "Jan Kowalski" and lista[0]["status"] == "oczekuje"

    r = admin_client.put(f"/api/zaliczki/{zid}", json={"status": "zaakceptowana"})
    assert r.status_code == 200 and r.json()["decyzja_at"]

    raport = admin_client.get(f"/api/raporty/godziny?rok={DZIS.year}&miesiac={DZIS.month}").json()
    moj = next(x for x in raport["pracownicy"] if x["pracownik_id"] == p.id)
    assert moj["do_wyplaty"] == 240.0
    assert moj["zaliczki_kwota"] == 100.0
    assert moj["do_wyplaty_po_zaliczkach"] == 140.0

    # rozpatrzonego nie można wycofać ani rozpatrzyć ponownie
    assert c.delete(f"/api/me/portfel/zaliczki/{zid}").status_code == 409
    assert admin_client.put(f"/api/zaliczki/{zid}", json={"status": "odrzucona"}).status_code == 409


def test_odrzucona_nie_potraca_ale_zwalnia_limit(admin_client, db):
    p, user = _seed_zarobek(db)
    c = _klient_pracownika(user)
    zid = c.post("/api/me/portfel/zaliczki", json={"kwota": 100}).json()["id"]
    admin_client.put(f"/api/zaliczki/{zid}", json={"status": "odrzucona"})
    w = c.get("/api/me/portfel").json()
    assert w["dostepna_zaliczka"] == 120.0                      # odrzucona zwalnia limit
    raport = admin_client.get(f"/api/raporty/godziny?rok={DZIS.year}&miesiac={DZIS.month}").json()
    moj = next(x for x in raport["pracownicy"] if x["pracownik_id"] == p.id)
    assert moj["zaliczki_kwota"] == 0.0 and moj["do_wyplaty_po_zaliczkach"] == 240.0


def test_zla_decyzja_400_i_admin_only(db, admin_client):
    p, user = _seed_zarobek(db)
    c = _klient_pracownika(user)
    zid = c.post("/api/me/portfel/zaliczki", json={"kwota": 10}).json()["id"]
    assert admin_client.put(f"/api/zaliczki/{zid}", json={"status": "dziwny"}).status_code == 400
    assert c.get("/api/zaliczki").status_code == 403            # pracownik nie widzi cudzych
