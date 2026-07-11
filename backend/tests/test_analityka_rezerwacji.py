"""Slice 5a: analityka rezerwacji — covery, statusy (no-show %/konwersja), mix kanałów,
lead time, rozkład grup, szczyty. Terminy wstawiane wprost przez `db` (pełna kontrola statusu/
kanału/utworzono_at, których admin API nie ustawia). 2026-07-13 = poniedziałek."""

import datetime as dt

import models


def test_analityka_odrzuca_zbyt_szeroki_i_odwrocony_zakres(admin_client):
    for endpoint in ("rezerwacje", "oblozenie"):
        assert admin_client.get(
            f"/api/analityka/{endpoint}?start=2025-01-01&end=2026-12-31"
        ).status_code == 400
        assert admin_client.get(
            f"/api/analityka/{endpoint}?start=2026-07-02&end=2026-07-01"
        ).status_code == 400


def _termin(db, **kw):
    base = dict(rodzaj="stolik", nazwisko="Gość", status="potwierdzona", kanal="reczna",
                zadatek=0.0, utworzono_at=dt.datetime(2026, 7, 1, 12, 0))
    base.update(kw)
    t = models.Termin(**base)
    db.add(t); db.commit()
    return t


def test_covery_i_statusy(admin_client, db):
    D = dt.date(2026, 7, 13)
    _termin(db, data=D, godz_od=dt.time(18, 0), liczba_osob=4, status="odbyla")
    _termin(db, data=D, godz_od=dt.time(19, 0), liczba_osob=2, status="no_show")
    _termin(db, data=D, godz_od=dt.time(20, 0), liczba_osob=3, status="odwolana")
    _termin(db, data=D, godz_od=dt.time(18, 0), liczba_osob=2, status="potwierdzona")
    r = admin_client.get(f"/api/analityka/rezerwacje?start={D}&end={D}").json()
    assert r["covery"]["suma"] == 8               # 4+2+2 (anulowana pominięta)
    s = r["statusy"]
    assert (s["odbyla"], s["no_show"], s["odwolana"], s["aktywne"]) == (1, 1, 1, 1)
    assert s["no_show_proc"] == 33                # 1/(1+1+1)
    assert s["konwersja_proc"] == 50             # odbyla/(odbyla+no_show)


def test_mix_kanalow(admin_client, db):
    D = dt.date(2026, 7, 13)
    for k in ("online", "online", "reczna"):
        _termin(db, data=D, godz_od=dt.time(18, 0), liczba_osob=2, kanal=k)
    r = admin_client.get(f"/api/analityka/rezerwacje?start={D}&end={D}").json()
    kan = {x["kanal"]: x for x in r["kanaly"]}
    assert kan["online"]["liczba"] == 2 and kan["online"]["proc"] == 67
    assert r["kanaly"][0]["kanal"] == "online"   # sortowane malejąco


def test_lead_time(admin_client, db):
    D = dt.date(2026, 7, 20)
    _termin(db, data=D, godz_od=dt.time(18, 0), liczba_osob=2, utworzono_at=dt.datetime(2026, 7, 13, 10, 0))  # 7 dni
    _termin(db, data=D, godz_od=dt.time(18, 0), liczba_osob=2, utworzono_at=dt.datetime(2026, 7, 17, 10, 0))  # 3 dni
    r = admin_client.get(f"/api/analityka/rezerwacje?start={D}&end={D}").json()
    assert r["lead_time"]["mediana_dni"] == 5.0 and r["lead_time"]["srednia_dni"] == 5.0


def test_szczyty_i_grupy(admin_client, db):
    D = dt.date(2026, 7, 13)   # poniedziałek
    _termin(db, data=D, godz_od=dt.time(18, 0), liczba_osob=2)
    _termin(db, data=D, godz_od=dt.time(18, 30), liczba_osob=12)   # duża grupa → kubełek 10+
    r = admin_client.get(f"/api/analityka/rezerwacje?start={D}&end={D}").json()
    pon = next(x for x in r["szczyty"]["wg_dnia_tygodnia"] if x["dzien"] == "Pon")
    assert pon["covery"] == 14
    g18 = next(x for x in r["szczyty"]["wg_godziny"] if x["godz"] == "18:00")
    assert g18["covery"] == 14
    duza = next(x for x in r["wielkosc_grup"] if x["etykieta"] == "10+")
    assert duza["liczba"] == 1


def test_srednia_dzienna_po_oknie(admin_client, db):
    # 8 coverów rozłożone na 4 dni okna → średnia dzienna 2.0
    _termin(db, data=dt.date(2026, 7, 13), godz_od=dt.time(18, 0), liczba_osob=8, status="odbyla")
    r = admin_client.get("/api/analityka/rezerwacje?start=2026-07-13&end=2026-07-16").json()
    assert r["dni"] == 4 and r["covery"]["srednia_dzienna"] == 2.0


def test_puste_okno_nie_wybucha(admin_client):
    r = admin_client.get("/api/analityka/rezerwacje?start=2026-07-13&end=2026-07-13").json()
    assert r["covery"]["suma"] == 0 and r["kanaly"] == [] and r["statusy"]["no_show_proc"] == 0


def test_analityka_gating_pro(admin_client):
    admin_client.put("/api/lokal/config", json={"modul_rezerwacje": False})
    assert admin_client.get("/api/analityka/rezerwacje?start=2026-07-13&end=2026-07-13").status_code == 403
