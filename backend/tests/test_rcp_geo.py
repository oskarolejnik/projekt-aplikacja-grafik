"""RCP mobilne (geofencing) — pracownik odbija start/koniec zmiany telefonem.

Weryfikacja serwerowa: haversine ≤ promień z konfiguracji lokalu, limit dokładności GPS,
znaczniki czasu z zegara serwera, jedna otwarta zmiana GEO, auto-domknięcie zapomnianego
odbicia. Rekordy agenta POS (inne zrodlo) pozostają nietknięte.
"""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import factories
import main
import models
from auth import create_access_token
from deps import get_lokal_config
from routers.moje import _haversine_m

# Punkt odniesienia lokalu (okolice Krakowa). 0.001° szer. geogr. ≈ 111 m.
LAT, LNG = 50.0, 19.0
BLISKO = {"lat": LAT + 0.0005, "lng": LNG, "dokladnosc_m": 20}     # ~56 m od lokalu
DALEKO = {"lat": LAT + 0.01, "lng": LNG, "dokladnosc_m": 20}       # ~1.1 km od lokalu


def _klient(user):
    """Świeży TestClient per użytkownik — nie mutujemy nagłówków współdzielonego klienta."""
    c = TestClient(main.app)
    c.headers.update({"Authorization": f"Bearer {create_access_token(user)}"})
    return c


def _pracownik_z_kontem(db):
    p = factories.PracownikFactory(imie="Jan", nazwisko="Kowalski")
    user = factories.UserFactory(login=f"geo_{p.id}", rola="employee", pracownik=p)
    db.commit()
    return p, user


def _wlacz_geo(db, lat=LAT, lng=LNG, promien=150):
    cfg = get_lokal_config(db)
    cfg.rcp_mobilne, cfg.rcp_geo_lat, cfg.rcp_geo_lng, cfg.rcp_geo_promien_m = True, lat, lng, promien
    db.commit()


# ── Haversine ────────────────────────────────────────────────────────────────

def test_haversine_znane_odleglosci():
    assert _haversine_m(LAT, LNG, LAT, LNG) == 0
    assert 105 < _haversine_m(LAT, LNG, LAT + 0.001, LNG) < 115          # ~111 m
    assert 1_050 < _haversine_m(LAT, LNG, LAT + 0.01, LNG) < 1_150      # ~1.1 km


# ── Bramki konfiguracji / konta ──────────────────────────────────────────────

def test_wylaczone_status_i_odbicie(db):
    _, user = _pracownik_z_kontem(db)
    c = _klient(user)
    assert c.get("/api/me/rcp").json() == {"aktywne": False, "zmiana": None}
    assert c.post("/api/me/rcp/odbij", json=BLISKO).status_code == 409


def test_wlaczone_bez_polozenia_dalej_wylaczone(db):
    cfg = get_lokal_config(db)
    cfg.rcp_mobilne = True   # włącznik bez lat/lng nie wystarcza
    db.commit()
    _, user = _pracownik_z_kontem(db)
    c = _klient(user)
    assert c.get("/api/me/rcp").json()["aktywne"] is False
    assert c.post("/api/me/rcp/odbij", json=BLISKO).status_code == 409


def test_konto_bez_pracownika(db):
    _wlacz_geo(db)
    user = factories.UserFactory(login="geo_bez_prac", rola="employee", pracownik=None)
    db.commit()
    assert _klient(user).post("/api/me/rcp/odbij", json=BLISKO).status_code == 400


# ── Odbicie: wejście → wyjście ───────────────────────────────────────────────

def test_wejscie_i_wyjscie_w_zasiegu(db):
    _wlacz_geo(db)
    p, user = _pracownik_z_kontem(db)
    c = _klient(user)

    st = c.get("/api/me/rcp").json()
    assert st["aktywne"] is True and st["promien_m"] == 150 and st["zmiana"] is None

    r = c.post("/api/me/rcp/odbij", json=BLISKO)
    assert r.status_code == 200 and r.json()["kierunek"] == "wejscie"
    rec = db.query(models.OdbicieRcp).filter_by(pracownik_id=p.id, zrodlo="geo").one()
    assert rec.rcp_id.startswith("geo:") and rec.imie_nazwisko == "Jan Kowalski"
    assert rec.wejscie is not None and rec.wyjscie is None
    assert rec.wejscie_lat == BLISKO["lat"] and rec.wejscie_dokladnosc_m == 20
    # samoobsługa nie generuje pushy „start/koniec zmiany" ścieżką agenta
    assert rec.powiadomiono_wejscie is True and rec.powiadomiono_wyjscie is True

    # otwarta zmiana widoczna w statusie ORAZ jako aktywna_zmiana w /me/godziny
    assert c.get("/api/me/rcp").json()["zmiana"]["wejscie"] == rec.wejscie.isoformat()
    g = c.get(f"/api/me/godziny?rok={rec.data.year}&miesiac={rec.data.month}").json()
    assert g["aktywna_zmiana"] is not None

    r = c.post("/api/me/rcp/odbij", json=BLISKO)
    assert r.status_code == 200 and r.json()["kierunek"] == "wyjscie"
    db.refresh(rec)
    assert rec.wyjscie is not None and rec.godziny == pytest.approx(0.0)
    assert rec.wyjscie_lat == BLISKO["lat"]
    assert c.get("/api/me/rcp").json()["zmiana"] is None


def test_poza_zasiegiem_403(db):
    _wlacz_geo(db)
    _, user = _pracownik_z_kontem(db)
    r = _klient(user).post("/api/me/rcp/odbij", json=DALEKO)
    assert r.status_code == 403 and "m od lokalu" in r.json()["detail"]


def test_wiekszy_promien_wpuszcza(db):
    _wlacz_geo(db, promien=2000)
    _, user = _pracownik_z_kontem(db)
    assert _klient(user).post("/api/me/rcp/odbij", json=DALEKO).status_code == 200


def test_slaba_dokladnosc_400(db):
    _wlacz_geo(db)
    _, user = _pracownik_z_kontem(db)
    r = _klient(user).post("/api/me/rcp/odbij", json=dict(BLISKO, dokladnosc_m=400))
    assert r.status_code == 400 and "sygnał GPS" in r.json()["detail"]


def test_walidacja_wspolrzednych_422(db):
    _wlacz_geo(db)
    _, user = _pracownik_z_kontem(db)
    assert _klient(user).post("/api/me/rcp/odbij", json={"lat": 123, "lng": 19}).status_code == 422


# ── Zapomniane odbicie + izolacja od agenta POS ──────────────────────────────

def test_zapomniane_odbicie_domykane_zerem(db):
    _wlacz_geo(db)
    p, user = _pracownik_z_kontem(db)
    stare_wejscie = datetime.now().replace(microsecond=0) - timedelta(hours=30)
    db.add(models.OdbicieRcp(rcp_id="geo:stare", imie_nazwisko="Jan Kowalski", pracownik_id=p.id,
                             zrodlo="geo", data=stare_wejscie.date(), wejscie=stare_wejscie))
    db.commit()
    c = _klient(user)
    assert c.get("/api/me/rcp").json()["zmiana"] is None   # >18 h = nie pokazujemy jako aktywnej
    assert c.post("/api/me/rcp/odbij", json=BLISKO).json()["kierunek"] == "wejscie"
    stary = db.query(models.OdbicieRcp).filter_by(rcp_id="geo:stare").one()
    assert stary.wyjscie == stary.wejscie and stary.godziny == 0.0
    assert db.query(models.OdbicieRcp).filter_by(pracownik_id=p.id, zrodlo="geo").count() == 2


def test_otwarte_odbicie_agenta_nie_jest_ruszane(db):
    """Otwarta zmiana z POS (inne zrodlo) nie blokuje odbicia GEO i nie jest domykana."""
    _wlacz_geo(db)
    p, user = _pracownik_z_kontem(db)
    teraz = datetime.now().replace(microsecond=0)
    db.add(models.OdbicieRcp(rcp_id="pos-1", imie_nazwisko="Jan Kowalski", pracownik_id=p.id,
                             zrodlo="gastro", data=teraz.date(), wejscie=teraz))
    db.commit()
    assert _klient(user).post("/api/me/rcp/odbij", json=BLISKO).json()["kierunek"] == "wejscie"
    pos = db.query(models.OdbicieRcp).filter_by(rcp_id="pos-1").one()
    assert pos.wyjscie is None


# ── Konfiguracja przez /api/lokal/config (admin) ─────────────────────────────

def test_admin_konfiguruje_geo(admin_client):
    r = admin_client.put("/api/lokal/config", json={
        "rcp_mobilne": True, "rcp_geo_lat": LAT, "rcp_geo_lng": LNG, "rcp_geo_promien_m": 300,
    })
    assert r.status_code == 200
    out = r.json()
    assert out["rcp_mobilne"] is True and out["rcp_geo_lat"] == LAT and out["rcp_geo_promien_m"] == 300


def test_admin_walidacja_promienia_i_wspolrzednych(admin_client):
    assert admin_client.put("/api/lokal/config", json={"rcp_geo_promien_m": 5}).status_code == 422
    assert admin_client.put("/api/lokal/config", json={"rcp_geo_lat": 91}).status_code == 422
