"""CEL 3 — Różnorodne godziny pracy i zmiany.

Aplikacja modeluje zmianę przez godzinę startu (`godz_od`) + rewir; nie ma osobnego
typu ani godziny końca. Dlatego „poranna/wieczorna/nocna" = różne `godz_od`, a
„zmiana dzielona (split)" = dwa przydziały tego samego dnia o różnych godzinach.

Testujemy też próby konfliktów na ręcznym przydziale (POST /api/przydzialy):
  • dokładny duplikat (ta sama data+pracownik+godzina)  -> blokada 400,
  • stanowisko weekend-only w dzień roboczy             -> blokada 400,
  • split / różne godziny tego samego dnia              -> dozwolone (świadoma decyzja),
  • nakładające się godziny (np. 10:00 i 11:00)         -> NIE wykrywane (brak godz. końca).
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


# ── Zmiana dzielona (split shift) ─────────────────────────────────────────────
def test_split_shift_dwie_zmiany_tego_samego_dnia(admin_client, db):
    """Ten sam pracownik może mieć rano i wieczorem (różne godz_od) — split shift."""
    stan = factories.StanowiskoFactory()
    prac = factories.PracownikFactory()
    r1 = admin_client.post("/api/przydzialy", json=_przydzial(stan, prac, DZIEN_ROBOCZY, ZMIANA_PORANNA))
    r2 = admin_client.post("/api/przydzialy", json=_przydzial(stan, prac, DZIEN_ROBOCZY, ZMIANA_WIECZORNA))
    assert r1.status_code == 201 and r2.status_code == 201
    assert db.query(models.PrzydzialZmiany).filter_by(pracownik_id=prac.id, data=DZIEN_ROBOCZY).count() == 2


# ── Konflikty ─────────────────────────────────────────────────────────────────
def test_dokladny_duplikat_zablokowany(admin_client):
    """Ta sama data + pracownik + godzina = 400 (krytyczna walidacja w create_przydział)."""
    stan = factories.StanowiskoFactory()
    prac = factories.PracownikFactory()
    body = _przydzial(stan, prac, DZIEN_ROBOCZY, ZMIANA_DZIENNA)
    assert admin_client.post("/api/przydzialy", json=body).status_code == 201
    r = admin_client.post("/api/przydzialy", json=body)
    assert r.status_code == 400
    assert "już przydział" in r.json()["detail"]


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


def test_nakladajace_sie_godziny_nie_sa_wykrywane(admin_client, db):
    """OGRANICZENIE APLIKACJI: zmiany nie mają godziny końca, więc realne nakładanie
    (np. 10:00 trwająca 8h vs 11:00) NIE jest wykrywane — oba przydziały przechodzą.
    Test dokumentuje obecne zachowanie (charakteryzacja). Patrz test_constraint_gaps.py.
    """
    from datetime import time

    stan = factories.StanowiskoFactory()
    prac = factories.PracownikFactory()
    r1 = admin_client.post("/api/przydzialy", json=_przydzial(stan, prac, DZIEN_ROBOCZY, time(10, 0)))
    r2 = admin_client.post("/api/przydzialy", json=_przydzial(stan, prac, DZIEN_ROBOCZY, time(11, 0)))
    assert r1.status_code == 201
    assert r2.status_code == 201, "Brak detekcji nakładania (brak godziny końca zmiany)"
    assert db.query(models.PrzydzialZmiany).filter_by(pracownik_id=prac.id, data=DZIEN_ROBOCZY).count() == 2


def test_ten_sam_slot_rozni_pracownicy_dozwoleni(admin_client):
    """Dwóch różnych pracowników na to samo stanowisko/godzinę = OK (obsada > 1)."""
    stan = factories.StanowiskoFactory()
    p1 = factories.PracownikFactory()
    p2 = factories.PracownikFactory()
    assert admin_client.post("/api/przydzialy", json=_przydzial(stan, p1, DZIEN_ROBOCZY, ZMIANA_DZIENNA)).status_code == 201
    assert admin_client.post("/api/przydzialy", json=_przydzial(stan, p2, DZIEN_ROBOCZY, ZMIANA_DZIENNA)).status_code == 201
