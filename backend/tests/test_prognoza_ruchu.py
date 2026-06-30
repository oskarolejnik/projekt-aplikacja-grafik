"""Prognoza ruchu (/api/prognoza-ruchu) — średnia rachunków per dzień tygodnia z StolikiHistoria."""

import datetime as dt

import models


def test_prognoza_pusta(admin_client):
    r = admin_client.get("/api/prognoza-ruchu")
    assert r.status_code == 200
    b = r.json()
    assert len(b["per_dzien_tygodnia"]) == 7
    assert b["srednia_dzienna"] == 0
    assert b["trend_28d_proc"] is None
    assert len(b["projekcja_7dni"]) == 7
    # Każdy dzień tygodnia obecny, z zerową próbką.
    assert all(p["probek"] == 0 and p["srednia"] == 0 for p in b["per_dzien_tygodnia"])


def test_prognoza_srednia_per_dzien_tygodnia(admin_client, db):
    today = dt.date.today()
    pon = today - dt.timedelta(days=today.weekday())     # najbliższy poniedziałek wstecz (weekday 0)
    # Trzy ostatnie poniedziałki: 10, 20, 30 → średnia 20, max 30, 3 próbki.
    for k, liczba in enumerate([10, 20, 30]):
        db.add(models.StolikiHistoria(data=pon - dt.timedelta(days=7 * k), liczba=liczba))
    db.commit()

    b = admin_client.get("/api/prognoza-ruchu").json()
    pon_stat = next(p for p in b["per_dzien_tygodnia"] if p["dzien"] == 0)
    assert pon_stat["nazwa"] == "Poniedziałek"
    assert pon_stat["srednia"] == 20.0
    assert pon_stat["max"] == 30
    assert pon_stat["probek"] == 3
    assert b["probek"] == 3
    assert b["srednia_dzienna"] == 20.0
    # Projekcja na najbliższy poniedziałek = średnia poniedziałków.
    proj_pon = next(p for p in b["projekcja_7dni"] if p["nazwa"] == "Poniedziałek")
    assert proj_pon["prognoza"] == 20.0


def test_prognoza_pomija_dane_spoza_okna(admin_client, db):
    today = dt.date.today()
    db.add(models.StolikiHistoria(data=today - dt.timedelta(days=400), liczba=999))  # poza max 365 dni
    db.commit()
    b = admin_client.get("/api/prognoza-ruchu?dni=30").json()
    assert b["probek"] == 0
    assert b["srednia_dzienna"] == 0
