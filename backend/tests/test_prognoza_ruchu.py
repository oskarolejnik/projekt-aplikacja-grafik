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


def test_prognoza_trend_na_pelnym_oknie_niezaleznie_od_dni(admin_client, db):
    """Regresja: trend liczony na WŁASNYM, pełnym oknie 56 dni (symetryczne 28 vs 28), niezależnie
    od parametru `dni`. Krótszy wybór (dni=30) nie zostawia okna0 pustego → przy stałym ruchu trend=0,
    a nie absurdalne setki %."""
    today = dt.date.today()
    for k in range(56):                          # stały ruch 50/dzień przez ostatnie 56 dni
        db.add(models.StolikiHistoria(data=today - dt.timedelta(days=k), liczba=50))
    db.commit()
    assert admin_client.get("/api/prognoza-ruchu?dni=30").json()["trend_28d_proc"] == 0.0


def test_auto_obsada_z_prognozy(admin_client, db):
    """Auto-obsada: POST /api/wymagania/z-prognozy tworzy wymagania na 7 dni z sugerowanej obsady.
    Historia ~40 rachunków/dzień → ceil(40/20)=2 (domyślny config)."""
    import factories
    sala = factories.StanowiskoFactory(nazwa="Sala")
    today = dt.date.today()
    for k in range(1, 85):                        # 12 tygodni historii po 40 rachunków
        db.add(models.StolikiHistoria(data=today - dt.timedelta(days=k), liczba=40))
    db.commit()
    r = admin_client.post("/api/wymagania/z-prognozy", json={"stanowisko_id": sala.id}).json()
    assert r["zastosowano"] == 7 and r["stanowisko"] == "Sala"
    wym = db.query(models.WymaganiaDnia).filter_by(stanowisko_id=sala.id).all()
    assert len(wym) == 7 and all(w.liczba_osob == 2 for w in wym)


def test_auto_obsada_upsert_bez_dubli(admin_client, db):
    import factories
    sala = factories.StanowiskoFactory(nazwa="Sala")
    admin_client.post("/api/wymagania/z-prognozy", json={"stanowisko_id": sala.id})
    admin_client.post("/api/wymagania/z-prognozy", json={"stanowisko_id": sala.id})
    assert db.query(models.WymaganiaDnia).filter_by(stanowisko_id=sala.id).count() == 7   # nie 14


def test_auto_obsada_zle_stanowisko_404(admin_client):
    assert admin_client.post("/api/wymagania/z-prognozy", json={"stanowisko_id": 99999}).status_code == 404


def test_auto_obsada_tylko_admin(make_employee_client, db):
    import factories
    sala = factories.StanowiskoFactory(nazwa="Sala")
    p = factories.PracownikFactory()
    ce, _ = make_employee_client(p)
    assert ce.post("/api/wymagania/z-prognozy", json={"stanowisko_id": sala.id}).status_code == 403


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


def _zasiej_ruch(db, dni_wstecz, liczba):
    """Dodaje po jednej próbce ruchu na każdy z ostatnich `dni_wstecz` dni."""
    today = dt.date.today()
    for k in range(1, dni_wstecz + 1):
        db.add(models.StolikiHistoria(data=today - dt.timedelta(days=k), liczba=liczba))
    db.commit()


def test_prognoza_obsada_domyslne_parametry(admin_client, db):
    # ~40 rachunków każdego dnia → ceil(40/20) = 2 osoby na zmianę (domyślne 20/1).
    _zasiej_ruch(db, 28, 40)
    b = admin_client.get("/api/prognoza-ruchu").json()
    assert b["parametry_obsady"] == {"rachunki_na_osobe": 20, "min": 1}
    assert len(b["projekcja_7dni"]) == 7
    assert all("sugerowana_obsada" in p for p in b["projekcja_7dni"])
    assert all(p["sugerowana_obsada"] == 2 for p in b["projekcja_7dni"])


def test_prognoza_obsada_pusty_ruch_to_minimum(admin_client):
    # Brak danych → prognoza 0 → obsada = obsada_min (domyślnie 1).
    b = admin_client.get("/api/prognoza-ruchu").json()
    assert all(p["prognoza"] == 0 for p in b["projekcja_7dni"])
    assert all(p["sugerowana_obsada"] == 1 for p in b["projekcja_7dni"])


def test_prognoza_obsada_reaguje_na_config(admin_client, db):
    _zasiej_ruch(db, 28, 40)
    # Zmiana: 1 osoba obsługuje 10 rachunków, minimum 3 → ceil(40/10)=4 (>3).
    r = admin_client.put("/api/lokal/config", json={"obsada_rachunki_na_osobe": 10, "obsada_min": 3})
    assert r.status_code == 200
    b = admin_client.get("/api/prognoza-ruchu").json()
    assert b["parametry_obsady"] == {"rachunki_na_osobe": 10, "min": 3}
    assert all(p["sugerowana_obsada"] == 4 for p in b["projekcja_7dni"])


def test_config_domyslne_pola_obsady(admin_client):
    cfg = admin_client.get("/api/lokal/config").json()
    assert cfg["obsada_rachunki_na_osobe"] == 20
    assert cfg["obsada_min"] == 1
