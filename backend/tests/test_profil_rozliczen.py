"""Profil rozliczeń per lokal (de-Rajculizacja, krok 1): nowe pola konfiguracji,
przełącznik „imprezy rozliczane osobno" i bramka modułu imprez.

Defaulty odtwarzają zachowanie historyczne — testy pilnują OBU trybów."""

from datetime import date, datetime

import models
from deps import get_lokal_config


def _dzis():
    return date.today()


def _seed_impreza(db, kwota=100.0):
    prac = models.Pracownik(imie="Iga", nazwisko="Imprezowa", dzial="obsluga")
    db.add(prac); db.commit(); db.refresh(prac)
    imp = models.RozliczenieImprezy(data=_dzis(), pracownik_id=prac.id, utworzono_at=datetime.utcnow())
    imp.pozycje.append(models.RozliczenieImprezyPozycja(forma="gotowka", kwota=kwota, sfiskalizowane=True))
    db.add(imp); db.commit()
    return imp


def test_config_roundtrip_nowych_pol(admin_client):
    r = admin_client.get("/api/lokal/config").json()
    # defaulty = Rajcula
    assert r["impreza_osobne_rozliczenie"] is True
    assert r["rozliczenia_tryb_kelnera"] == "indywidualnie"
    assert r["rozliczenia_nazwy_kas"] is None and r["rozliczenia_nazwy_terminali"] is None
    assert r["grafik_cykl"] == "tydzien"

    w = admin_client.put("/api/lokal/config", json={
        "impreza_osobne_rozliczenie": False,
        "rozliczenia_tryb_kelnera": "pula",
        "rozliczenia_nazwy_kas": ["Kasa główna", "  Kasa bar  ", ""],
        "rozliczenia_nazwy_terminali": ["Terminal 1"],
        "grafik_cykl": "miesiac",
    })
    assert w.status_code == 200
    r2 = admin_client.get("/api/lokal/config").json()
    assert r2["impreza_osobne_rozliczenie"] is False
    assert r2["rozliczenia_tryb_kelnera"] == "pula"
    assert r2["rozliczenia_nazwy_kas"] == ["Kasa główna", "Kasa bar"]   # trim + odrzucone puste
    assert r2["rozliczenia_nazwy_terminali"] == ["Terminal 1"]
    assert r2["grafik_cykl"] == "miesiac"

    # pusta lista etykiet = powrót do wolnego wpisu (NULL)
    admin_client.put("/api/lokal/config", json={"rozliczenia_nazwy_kas": []})
    assert admin_client.get("/api/lokal/config").json()["rozliczenia_nazwy_kas"] is None


def test_config_walidacja_wartosci(admin_client):
    assert admin_client.put("/api/lokal/config", json={"rozliczenia_tryb_kelnera": "krecha"}).status_code == 422
    assert admin_client.put("/api/lokal/config", json={"grafik_cykl": "kwartal"}).status_code == 422


def test_imprezy_w_ogolnym_obrocie_znikaja_z_imp_i_zeszytu(admin_client, db):
    _seed_impreza(db, kwota=250.0)
    d = str(_dzis())

    # Default (osobne rozliczenie): IMP z imprezy widoczny w rozliczeniu i w zeszycie.
    w = admin_client.get(f"/api/rozliczenie?data={d}").json()["wynik"]
    assert w["imp"]["gotowka_sfiskalizowana"] == 250.0
    zeszyt = admin_client.get(f"/api/zeszyt?start={d}&end={d}").json()
    zrodla = [x["zrodlo"] for x in zeszyt["dni"][0]["wiersze"]]
    assert any(z != "SALA" for z in zrodla)   # wiersz imprezy obecny

    # Tryb „imprezy w ogólnym obrocie": IMP=0, zeszyt bez wierszy imprez, pulpit impreza=0.
    admin_client.put("/api/lokal/config", json={"impreza_osobne_rozliczenie": False})
    w2 = admin_client.get(f"/api/rozliczenie?data={d}").json()["wynik"]
    assert w2["imp"]["gotowka_sfiskalizowana"] == 0.0 and w2["imp"]["karta"] == 0.0
    zeszyt2 = admin_client.get(f"/api/zeszyt?start={d}&end={d}").json()
    assert all(x["zrodlo"] == "SALA" or x.get("manualny") for x in zeszyt2["dni"][0]["wiersze"])
    pulpit = admin_client.get(f"/api/pulpit?start={d}&end={d}").json()
    assert pulpit["przychod"]["impreza"] == 0.0


def test_bramka_modulu_imprez(admin_client, db):
    # moduł włączony (default) — endpointy działają
    assert admin_client.get("/api/terminy?start=2026-01-01&end=2026-01-31").status_code == 200
    assert admin_client.get("/api/imprezy/rozliczenia?start=2026-01-01&end=2026-01-31").status_code == 200

    cfg = get_lokal_config(db)
    cfg.modul_imprezy = False
    db.commit()

    assert admin_client.get("/api/terminy?start=2026-01-01&end=2026-01-31").status_code == 403
    assert admin_client.post("/api/terminy", json={
        "data": "2026-08-01", "nazwisko": "Test", "typ": "wesele", "liczba_osob": 50,
    }).status_code == 403
    assert admin_client.get("/api/imprezy/rozliczenia?start=2026-01-01&end=2026-01-31").status_code == 403
