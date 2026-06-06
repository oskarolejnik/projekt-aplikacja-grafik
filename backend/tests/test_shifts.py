"""CEL 3 — Różnorodne godziny pracy i zmiany.

Aplikacja modeluje zmianę przez godzinę startu (`godz_od`) + rewir; nie ma osobnego
typu ani godziny końca. Dlatego „poranna/wieczorna/nocna" = różne `godz_od`.

Reguła biznesowa: pracownik może mieć maks. JEDNĄ zmianę dziennie.

Testujemy też próby konfliktów na ręcznym przydziale (POST /api/przydzialy):
  • druga zmiana tego samego dnia (dowolna godzina)     -> blokada 400 (maks. 1/dzień),
  • dokładny duplikat (ta sama data+pracownik+godzina)  -> blokada 400,
  • stanowisko weekend-only w dzień roboczy             -> blokada 400.
"""

import pytest

import models
import factories
from factories import (
    ZMIANA_PORANNA, ZMIANA_DZIENNA, ZMIANA_WIECZORNA, ZMIANA_NOCNA,
)

DZIEN_ROBOCZY = factories.dzien(0)   # poniedziałek 2026-06-01
SOBOTA = factories.dzien(5)          # 2026-06-06


def _przydzial(stan, prac, data, godz_od=None, rewir=None):
    body = {
        "data": str(data),
        "stanowisko_id": stan.id,
        "pracownik_id": prac.id,
        "rewir": rewir,
    }
    if godz_od is not None:
        body["godz_od"] = godz_od.strftime("%H:%M")
    return body


# ── Różne typy zmian (godziny) ────────────────────────────────────────────────
@pytest.mark.parametrize(
    "etykieta,godz",
    [
        ("poranna", ZMIANA_PORANNA),
        ("dzienna", ZMIANA_DZIENNA),
        ("wieczorna", ZMIANA_WIECZORNA),
        ("nocna", ZMIANA_NOCNA),
    ],
)
def test_rozne_godziny_zmian_zapisane(admin_client, etykieta, godz):
    stan = factories.StanowiskoFactory()
    prac = factories.PracownikFactory()
    r = admin_client.post("/api/przydzialy", json=_przydzial(stan, prac, DZIEN_ROBOCZY, godz))
    assert r.status_code == 201, r.text
    assert r.json()["godz_od"].startswith(godz.strftime("%H:%M"))


def test_niestandardowa_godzina_akceptowana(admin_client):
    """Nietypowa godzina (03:30 — środek nocy) jest poprawnie zapisywana."""
    stan = factories.StanowiskoFactory()
    prac = factories.PracownikFactory()
    from datetime import time

    r = admin_client.post("/api/przydzialy", json=_przydzial(stan, prac, DZIEN_ROBOCZY, time(3, 30)))
    assert r.status_code == 201
    assert r.json()["godz_od"].startswith("03:30")


def test_zmiana_bez_godziny_dozwolona(admin_client):
    """godz_od = None oznacza 'dowolna/cały dzień' — dozwolone."""
    stan = factories.StanowiskoFactory()
    prac = factories.PracownikFactory()
    r = admin_client.post("/api/przydzialy", json=_przydzial(stan, prac, DZIEN_ROBOCZY, None))
    assert r.status_code == 201
    assert r.json()["godz_od"] is None


# ── Maks. 1 zmiana na pracownika dziennie ─────────────────────────────────────
def test_druga_zmiana_tego_samego_dnia_zablokowana(admin_client, db):
    """Reguła biznesowa: pracownik ma maks. JEDNĄ zmianę dziennie. Druga zmiana tego
    samego dnia (nawet o innej godzinie: rano + wieczorem) jest odrzucana (400)."""
    stan = factories.StanowiskoFactory()
    prac = factories.PracownikFactory()
    r1 = admin_client.post("/api/przydzialy", json=_przydzial(stan, prac, DZIEN_ROBOCZY, ZMIANA_PORANNA))
    r2 = admin_client.post("/api/przydzialy", json=_przydzial(stan, prac, DZIEN_ROBOCZY, ZMIANA_WIECZORNA))
    assert r1.status_code == 201
    assert r2.status_code == 400
    assert db.query(models.PrzydzialZmiany).filter_by(pracownik_id=prac.id, data=DZIEN_ROBOCZY).count() == 1


# ── Konflikty ─────────────────────────────────────────────────────────────────
def test_dokladny_duplikat_zablokowany(admin_client):
    """Ta sama data + pracownik + godzina = 400 (krytyczna walidacja w create_przydział)."""
    stan = factories.StanowiskoFactory()
    prac = factories.PracownikFactory()
    body = _przydzial(stan, prac, DZIEN_ROBOCZY, ZMIANA_DZIENNA)
    assert admin_client.post("/api/przydzialy", json=body).status_code == 201
    r = admin_client.post("/api/przydzialy", json=body)
    assert r.status_code == 400
    assert "już" in r.json()["detail"]


def test_stanowisko_weekendowe_w_dzien_roboczy_zablokowane(admin_client):
    stan = factories.StanowiskoFactory(nazwa="Eventy", tylko_weekend=True)
    prac = factories.PracownikFactory()
    r = admin_client.post("/api/przydzialy", json=_przydzial(stan, prac, DZIEN_ROBOCZY, ZMIANA_WIECZORNA))
    assert r.status_code == 400
    assert "weekend" in r.json()["detail"].lower()


def test_stanowisko_weekendowe_w_sobote_dozwolone(admin_client):
    stan = factories.StanowiskoFactory(nazwa="Eventy", tylko_weekend=True)
    prac = factories.PracownikFactory()
    r = admin_client.post("/api/przydzialy", json=_przydzial(stan, prac, SOBOTA, ZMIANA_WIECZORNA))
    assert r.status_code == 201


def test_nakladajace_sie_godziny_blokowane_przez_limit_dzienny(admin_client, db):
    """Zmiany nie mają godziny końca, więc realnego nakładania (10:00 vs 11:00) nie da się
    wykryć wprost — ale reguła „maks. 1 zmiana/dzień" i tak blokuje drugi przydział."""
    from datetime import time

    stan = factories.StanowiskoFactory()
    prac = factories.PracownikFactory()
    r1 = admin_client.post("/api/przydzialy", json=_przydzial(stan, prac, DZIEN_ROBOCZY, time(10, 0)))
    r2 = admin_client.post("/api/przydzialy", json=_przydzial(stan, prac, DZIEN_ROBOCZY, time(11, 0)))
    assert r1.status_code == 201
    assert r2.status_code == 400
    assert db.query(models.PrzydzialZmiany).filter_by(pracownik_id=prac.id, data=DZIEN_ROBOCZY).count() == 1


def test_ten_sam_slot_rozni_pracownicy_dozwoleni(admin_client):
    """Dwóch różnych pracowników na to samo stanowisko/godzinę = OK (obsada > 1)."""
    stan = factories.StanowiskoFactory()
    p1 = factories.PracownikFactory()
    p2 = factories.PracownikFactory()
    assert admin_client.post("/api/przydzialy", json=_przydzial(stan, p1, DZIEN_ROBOCZY, ZMIANA_DZIENNA)).status_code == 201
    assert admin_client.post("/api/przydzialy", json=_przydzial(stan, p2, DZIEN_ROBOCZY, ZMIANA_DZIENNA)).status_code == 201
