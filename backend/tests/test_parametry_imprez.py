"""Parametryzacja obsady imprez (Rec#4 audytu) — parametry z LokalConfig zamiast zaszytych.

Sprawdza, że domyślne parametry zachowują historyczne zachowanie oraz że ich zmiana
realnie wpływa na wynik przelicz_imprezy_na_wymagania. Konfiguracja przez /api/lokal/config.
"""

from datetime import time

import factories
from algorithm import przelicz_imprezy_na_wymagania


def _impreza(godzina="18:00", osoby=30, sala="R1"):
    return factories.ImprezaFactory.build(godzina=godzina, liczba_osob=osoby, sala=sala)


# ── domyślne = zachowanie historyczne ─────────────────────────────────────────
def test_domyslne_zachowanie_bez_zmian():
    out = przelicz_imprezy_na_wymagania([_impreza(godzina="18:00", osoby=30, sala="R1")])
    assert out[0]["godz_od"] == time(16, 0)      # 18:00 − 2h
    assert out[0]["liczba_osob"] == 2            # 30 / 15


# ── parametry zmieniają wynik ─────────────────────────────────────────────────
def test_param_wyprzedzenie_min():
    out = przelicz_imprezy_na_wymagania([_impreza(godzina="18:00")], {"wyprzedzenie_min": 60})
    assert out[0]["godz_od"] == time(17, 0)      # 18:00 − 1h


def test_param_najwczesniej():
    out = przelicz_imprezy_na_wymagania([_impreza(godzina="11:00")], {"najwczesniej": "12:00"})
    assert out[0]["godz_od"] == time(12, 0)      # 11−2=9 → podniesione do 12:00


def test_param_osoby_na_obsluge():
    out = przelicz_imprezy_na_wymagania([_impreza(osoby=15, sala="R1")], {"osoby_na_obsluge": 10})
    assert out[0]["liczba_osob"] == 2            # 15 / 10 → 2 (domyślnie 15/15 → 1)


def test_param_sale_min2():
    # R1 staje się salą „specjalną" (min 2), a R2Piw przestaje nią być.
    a = przelicz_imprezy_na_wymagania([_impreza(osoby=1, sala="R1")], {"sale_min2": ["R1"]})
    assert a[0]["liczba_osob"] == 2
    b = przelicz_imprezy_na_wymagania([_impreza(osoby=1, sala="R2Piw")], {"sale_min2": ["R1"]})
    assert b[0]["liczba_osob"] == 1


# ── konfiguracja przez endpoint ───────────────────────────────────────────────
def test_config_domyslne_pola(admin_client):
    cfg = admin_client.get("/api/lokal/config").json()
    assert cfg["impreza_osoby_na_obsluge"] == 15
    assert cfg["impreza_wyprzedzenie_min"] == 120
    assert cfg["impreza_najwczesniej"] == "10:00"
    assert cfg["impreza_sale_min2"] == "R2Piw,R2G"


def test_config_edycja_pol(admin_client):
    admin_client.put("/api/lokal/config",
                     json={"impreza_osoby_na_obsluge": 20, "impreza_najwczesniej": "09:00"})
    cfg = admin_client.get("/api/lokal/config").json()
    assert cfg["impreza_osoby_na_obsluge"] == 20
    assert cfg["impreza_najwczesniej"] == "09:00"
    assert cfg["impreza_wyprzedzenie_min"] == 120     # niezmienione zostaje domyślne
