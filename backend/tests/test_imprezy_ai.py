"""Skrzynka zapytań o imprezy (roadmapa v2, TOP 1) — ekstrakcja, dostępność, szkic, karta.

Testy pokrywają ścieżkę regułową (bez ANTHROPIC_API_KEY — tak działa CI) oraz ścieżkę AI
z zamockowanym klientem (nadpisanie ekstrakcji + szkic z modelu, fallback przy błędzie API).
"""

from datetime import date, timedelta

import pytest

import factories
import models
from deps import utcnow_naive
from routers import imprezy_ai as mod

ROK = date.today().year + 1


# ── Ekstrakcja regułowa ──────────────────────────────────────────────────────

def test_ekstrakcja_pelne_zapytanie():
    p = mod.ekstrakcja_regulowa(
        f"Dzień dobry, szukamy sali na wesele dla ~120 osób w sierpniu {ROK}, "
        "budżet około 250 zł/os. Kontakt: 601 234 567.")
    assert p["typ"] == "wesele"
    assert p["liczba_osob"] == 120
    assert p["budzet_od_osoby"] == 250
    assert p["miesiac"] == 8 and p["rok"] == ROK
    assert p["telefon"] == "601234567"


def test_ekstrakcja_budzet_od_osoby():
    p = mod.ekstrakcja_regulowa("budżet ok. 250 zł od osoby, 100 gości")
    assert p["budzet_od_osoby"] == 250 and p["liczba_osob"] == 100


def test_szkic_dopelniacz_typu():
    szkic = mod.szkic_szablonowy({"typ": "wesele", "liczba_osob": 120, "miesiac": 8, "rok": 2027},
                                 [], "Testowy Lokal")
    assert "organizację wesela" in szkic and "organizację wesele" not in szkic


def test_ekstrakcja_data_dokladna_i_odmiany():
    p = mod.ekstrakcja_regulowa(f"Rezerwacja na komunie 17.05.{ROK} dla 45 gości")
    assert p["data"] == f"{ROK}-05-17"
    assert p["typ"] == "komunia"
    assert p["liczba_osob"] == 45


def test_ekstrakcja_rok_domyslny_gdy_brak():
    p = mod.ekstrakcja_regulowa("Impreza firmowa w grudniu, 80 osób")
    assert p["miesiac"] == 12
    assert p["rok"] in (date.today().year, date.today().year + 1)


def test_ekstrakcja_puste_pola_dla_luznego_tekstu():
    p = mod.ekstrakcja_regulowa("Dzień dobry, czy macie wolne terminy?")
    assert p["typ"] is None and p["liczba_osob"] is None and p["miesiac"] is None


# ── Dostępność ───────────────────────────────────────────────────────────────

def _termin(db, d, status="rezerwacja"):
    t = models.Termin(data=d, nazwisko="Kowalscy", status=status, zadatek=0.0,
                      utworzono_at=utcnow_naive())
    db.add(t); db.commit()
    return t


def test_wolne_terminy_miesiaca_omija_zajete(db):
    # pierwsza sobota sierpnia przyszłego roku — zajęta
    d = date(ROK, 8, 1)
    while d.weekday() != 5:
        d += timedelta(days=1)
    _termin(db, d)
    terminy = mod.wolne_terminy(db, {"miesiac": 8, "rok": ROK})
    assert all(t["dzien"] in ("pt", "sob") for t in terminy)
    stan = {t["data"]: t["wolny"] for t in terminy}
    assert stan[str(d)] is False
    assert any(w for w in stan.values())          # inne piątki/soboty wolne


def test_termin_odwolany_nie_blokuje(db):
    d = date(ROK, 8, 1)
    while d.weekday() != 5:
        d += timedelta(days=1)
    _termin(db, d, status="odwolana")
    terminy = mod.wolne_terminy(db, {"miesiac": 8, "rok": ROK})
    assert {t["data"]: t["wolny"] for t in terminy}[str(d)] is True


def test_konkretna_data(db):
    d = date(ROK, 6, 20)
    _termin(db, d)
    wynik = mod.wolne_terminy(db, {"data": str(d)})
    assert wynik == [{"data": str(d), "dzien": wynik[0]["dzien"], "wolny": False}]


# ── Endpoint (ścieżka regułowa, bez klucza AI) ───────────────────────────────

def test_endpoint_pelny_przeplyw(admin_client, db, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = admin_client.post("/api/imprezy/zapytanie", json={
        "tresc": f"Szukamy sali na wesele, ~120 osób, sierpień {ROK}, budżet 250 zł/os."})
    assert r.status_code == 200
    body = r.json()
    assert body["ai"] is False
    assert body["parametry"]["typ"] == "wesele"
    assert len(body["terminy"]) > 0
    assert "wesel" in body["szkic"] and "120" in body["szkic"]
    assert body["karta"]["liczba_osob"] == 120 and body["karta"]["status"] == "rezerwacja"
    assert body["karta"]["data"] in [t["data"] for t in body["terminy"]]


def test_endpoint_waliduje_dlugosc(admin_client):
    assert admin_client.post("/api/imprezy/zapytanie", json={"tresc": "krótko"}).status_code == 400


def test_endpoint_tylko_admin(client):
    r = client.post("/api/imprezy/zapytanie", json={"tresc": "wesele na 100 osób w maju"})
    assert r.status_code in (401, 403)


def test_status_ai_bez_klucza(admin_client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert admin_client.get("/api/imprezy/zapytanie/status").json() == {"ai": False}


# ── Ścieżka AI (mock klienta) ────────────────────────────────────────────────

def test_endpoint_z_ai_nadpisuje_i_generuje(admin_client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-klucz")
    monkeypatch.setattr(mod.ai, "zapytaj_claude_json",
                        lambda system, prompt, max_tokens=1024: {"nazwisko": "Nowakowie", "liczba_osob": 130})
    monkeypatch.setattr(mod.ai, "zapytaj_claude",
                        lambda system, prompt, max_tokens=1024: "Szanowni Państwo, mamy wolne terminy…")
    r = admin_client.post("/api/imprezy/zapytanie", json={
        "tresc": f"Wesele dla 120 osób w sierpniu {ROK}, rodzina Nowaków."})
    body = r.json()
    assert body["ai"] is True
    assert body["parametry"]["nazwisko"] == "Nowakowie"
    assert body["parametry"]["liczba_osob"] == 130          # AI nadpisało fallback
    assert body["parametry"]["miesiac"] == 8                # fallback uzupełnia brakujące
    assert body["szkic"].startswith("Szanowni Państwo")
    assert body["karta"]["nazwisko"] == "Nowakowie"


def test_blad_ai_wraca_do_fallbacku(admin_client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-klucz")
    def _wybuch(*a, **k):
        raise RuntimeError("Claude API: HTTP 529")
    monkeypatch.setattr(mod.ai, "zapytaj_claude_json", _wybuch)
    monkeypatch.setattr(mod.ai, "zapytaj_claude", _wybuch)
    r = admin_client.post("/api/imprezy/zapytanie", json={
        "tresc": f"Wesele dla 120 osób w sierpniu {ROK}."})
    body = r.json()
    assert r.status_code == 200
    assert body["ai"] is False                 # degradacja bez wybuchu
    assert body["parametry"]["liczba_osob"] == 120
    assert "wesel" in body["szkic"]
