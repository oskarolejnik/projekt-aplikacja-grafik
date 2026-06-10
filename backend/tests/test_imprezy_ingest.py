"""Ingest imprez z laptopa (sparsowane pola JSON) → upsert Impreza + przeliczenie wymagań.
VPS nie czyta NAS-a ani nie parsuje Excela — dostaje gotowe pola od przeglądarki.
"""

from datetime import time

import models
import factories

ZAKRES = {"start": "2026-06-01", "end": "2026-06-07"}


def _impreza(**nad):
    base = {
        "data": "2026-06-06", "klient": "Wesele Test", "godzina": "18:00",
        "sala": "R1", "liczba_osob": 30, "nazwa_pliku": "2026.06.06 - Wesele Test.xlsx",
    }
    base.update(nad)
    return base


def test_ingest_dodaje_imprezy(admin_client, db):
    r = admin_client.post("/api/imprezy/ingest", params=ZAKRES, json={"imprezy": [_impreza()]})
    assert r.status_code == 200
    assert r.json()["dodano"] == 1
    imp = db.query(models.Impreza).one()
    assert imp.klient == "Wesele Test"
    assert imp.liczba_osob == 30
    assert imp.sala == "R1"
    assert imp.godzina == "18:00"


def test_ingest_przelicza_wymagania_imprez(admin_client, db):
    factories.StanowiskoFactory(nazwa="Imprezy")
    admin_client.post("/api/imprezy/ingest", params=ZAKRES, json={"imprezy": [_impreza(liczba_osob=30, godzina="18:00", sala="R1")]})
    wym = db.query(models.WymaganiaDnia).filter_by(jest_impreza=True).all()
    assert len(wym) == 1
    # 30 osób / 15 = 2 prac.; start = 18:00 - 2h = 16:00
    assert wym[0].liczba_osob == 2
    assert wym[0].godz_od == time(16, 0)


def test_ingest_aktualizuje_istniejaca(admin_client, db):
    admin_client.post("/api/imprezy/ingest", params=ZAKRES, json={"imprezy": [_impreza()]})
    r = admin_client.post("/api/imprezy/ingest", params=ZAKRES, json={"imprezy": [_impreza(liczba_osob=60)]})
    assert r.json()["dodano"] == 0
    assert r.json()["zaktualizowano"] == 1
    assert db.query(models.Impreza).one().liczba_osob == 60


def test_ingest_braki_pol_nie_wywalaja(admin_client, db):
    # rekord bez wymaganej daty -> liczony jako błąd, nie crash
    r = admin_client.post("/api/imprezy/ingest", params=ZAKRES, json={"imprezy": [{"klient": "Bez daty"}]})
    assert r.status_code == 200
    assert r.json()["bledy"] == 1
    assert db.query(models.Impreza).count() == 0


def test_ingest_pusta_godzina_i_sala(admin_client, db):
    admin_client.post("/api/imprezy/ingest", params=ZAKRES, json={"imprezy": [_impreza(godzina=None, sala=None, liczba_osob=0)]})
    imp = db.query(models.Impreza).one()
    assert imp.godzina == "Brak"
    assert imp.sala == "Brak"


def test_ingest_godzina_ulamek_doby_na_hhmm(admin_client, db):
    # Excel zwraca godzinę jako ułamek doby: 0.6041666… = 14:30
    admin_client.post("/api/imprezy/ingest", params=ZAKRES, json={"imprezy": [_impreza(godzina="0.6041666666666666")]})
    assert db.query(models.Impreza).one().godzina == "14:30"


def test_ingest_godzina_hhmmss_zachowana(admin_client, db):
    admin_client.post("/api/imprezy/ingest", params=ZAKRES, json={"imprezy": [_impreza(godzina="14:30:00")]})
    assert db.query(models.Impreza).one().godzina == "14:30:00"


def test_ingest_wymaga_admina(make_employee_client):
    prac = factories.PracownikFactory()
    c, _ = make_employee_client(prac)
    r = c.post("/api/imprezy/ingest", params=ZAKRES, json={"imprezy": []})
    assert r.status_code == 403


def test_ingest_bez_tokenu_401(client):
    assert client.post("/api/imprezy/ingest", params=ZAKRES, json={"imprezy": []}).status_code == 401


# ── Naprawa: wymagania imprez celują w „Imprezy", nie w Bar; ostrzeżenia ──────────
def test_ingest_wymagania_celuja_w_imprezy_nie_bar(admin_client, db):
    """Wymagania imprez trafiają na stanowisko „Imprezy", nie na Bar (id 1) — fallback usunięty."""
    bar = factories.StanowiskoFactory(nazwa="Bar")             # tworzony pierwszy → niższe id
    imprezy_stan = factories.StanowiskoFactory(nazwa="Imprezy")
    admin_client.post("/api/imprezy/ingest", params=ZAKRES, json={"imprezy": [_impreza(liczba_osob=30)]})
    wym = db.query(models.WymaganiaDnia).filter_by(jest_impreza=True).all()
    assert len(wym) == 1
    assert wym[0].stanowisko_id == imprezy_stan.id
    assert wym[0].stanowisko_id != bar.id


def test_ingest_bez_stanowiska_imprezy_nie_uzywa_baru(admin_client, db):
    """Brak stanowiska „Imprezy" → ŻADNE wymagania imprez (nie lądują na Barze) + ostrzeżenie."""
    factories.StanowiskoFactory(nazwa="Bar")
    r = admin_client.post("/api/imprezy/ingest", params=ZAKRES, json={"imprezy": [_impreza()]})
    assert db.query(models.WymaganiaDnia).filter_by(jest_impreza=True).count() == 0
    assert "Imprezy" in (r.json().get("ostrzezenie") or "")


def test_ingest_ostrzega_o_braku_kwalifikacji(admin_client, db):
    """Jest stanowisko „Imprezy", ale nikt nie ma kwalifikacji → ostrzeżenie o kwalifikacji."""
    factories.StanowiskoFactory(nazwa="Imprezy")
    factories.PracownikFactory()  # aktywny, bez kwalifikacji „Imprezy"
    r = admin_client.post("/api/imprezy/ingest", params=ZAKRES, json={"imprezy": [_impreza()]})
    assert "kwalifikacj" in (r.json().get("ostrzezenie") or "").lower()


def test_ingest_brak_ostrzezenia_gdy_ktos_ma_kwalifikacje(admin_client, db):
    """Stanowisko „Imprezy" + aktywny pracownik z tą kwalifikacją → brak ostrzeżenia."""
    imprezy_stan = factories.StanowiskoFactory(nazwa="Imprezy")
    admin_client.post("/api/pracownicy", json={
        "imie": "Imprez", "nazwisko": "Owy", "aktywny": True, "kwalifikacje_ids": [imprezy_stan.id],
    })
    r = admin_client.post("/api/imprezy/ingest", params=ZAKRES, json={"imprezy": [_impreza()]})
    assert r.json().get("ostrzezenie") is None
