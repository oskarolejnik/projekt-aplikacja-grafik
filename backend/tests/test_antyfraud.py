"""Antyfraud POS (roadmapa v2, TOP 3) — ingest storn od agenta + analiza per kelner."""

from datetime import date, timedelta

import factories
import models
from routers import antyfraud as mod

DZIS = date.today()
TOKEN = {"X-RCP-Token": "test-rcp-token"}


def _ingest(client, storna, headers=TOKEN):
    return client.post("/api/gastro/storna", json={"storna": storna}, headers=headers)


def _zdarzenie(i, nazwa="Jan Kowalski", typ="storno", kwota=25.0, dni_temu=3):
    return {"id": f"guid-{i}", "data": str(DZIS - timedelta(days=dni_temu)),
            "imie_nazwisko": nazwa, "typ": typ, "kwota": kwota}


# ── Ingest ───────────────────────────────────────────────────────────────────

def test_ingest_wymaga_tokena(client, monkeypatch):
    monkeypatch.setenv("RCP_INGEST_TOKEN", "test-rcp-token")
    monkeypatch.setattr(mod, "RCP_INGEST_TOKEN", "test-rcp-token")
    assert _ingest(client, [], headers={}).status_code == 401
    assert _ingest(client, [], headers={"X-RCP-Token": "zly"}).status_code == 401
    assert _ingest(client, []).status_code == 200


def test_ingest_upsert_i_mapowanie_pracownika(client, db, monkeypatch):
    monkeypatch.setattr(mod, "RCP_INGEST_TOKEN", "test-rcp-token")
    p = factories.PracownikFactory(imie="Jan", nazwisko="Kowalski")
    r = _ingest(client, [_zdarzenie(1), _zdarzenie(2, typ="rabat", kwota=15)])
    assert r.status_code == 200 and r.json()["przyjeto"] == 2
    rec = db.get(models.StornoGastro, "guid-1")
    assert rec.pracownik_id == p.id and rec.typ == "storno" and rec.kwota == 25.0
    # upsert: ta sama pozycja z poprawioną kwotą nie duplikuje
    _ingest(client, [dict(_zdarzenie(1), kwota=30)])
    db.expire_all()
    assert db.query(models.StornoGastro).count() == 2
    assert db.get(models.StornoGastro, "guid-1").kwota == 30.0


def test_ingest_kwota_zawsze_dodatnia_i_typ_walidowany(client, db, monkeypatch):
    monkeypatch.setattr(mod, "RCP_INGEST_TOKEN", "test-rcp-token")
    _ingest(client, [dict(_zdarzenie(7), kwota=-45.0, typ="dziwny")])
    rec = db.get(models.StornoGastro, "guid-7")
    assert rec.kwota == 45.0 and rec.typ == "storno"


# ── Analiza ──────────────────────────────────────────────────────────────────

def _seed_zespol(client, monkeypatch):
    """3 kelnerów „normalnych" (2 zdarzenia) + 1 odstający (12 zdarzeń po 40 zł)."""
    monkeypatch.setattr(mod, "RCP_INGEST_TOKEN", "test-rcp-token")
    storna, i = [], 0
    for nazwa in ("Anna Nowak", "Piotr Wiśniewski", "Ewa Szymańska"):
        for _ in range(2):
            i += 1
            storna.append(_zdarzenie(i, nazwa=nazwa, kwota=20))
    for _ in range(12):
        i += 1
        storna.append(_zdarzenie(i, nazwa="Marek Zieliński", kwota=40))
    assert _ingest(client, storna).json()["przyjeto"] == i


def test_podsumowanie_flaguje_odstajacego(admin_client, monkeypatch):
    _seed_zespol(admin_client, monkeypatch)
    w = admin_client.get("/api/antyfraud/podsumowanie").json()
    assert w["zespol"]["osob"] == 4 and w["zespol"]["zdarzen"] == 18
    marek = next(k for k in w["kelnerzy"] if k["nazwa"] == "Marek Zieliński")
    anna = next(k for k in w["kelnerzy"] if k["nazwa"] == "Anna Nowak")
    assert marek["flaga"] is True and "vs śr." in marek["powod"]
    assert anna["flaga"] is False and anna["powod"] is None
    assert w["kelnerzy"][0]["nazwa"] == "Marek Zieliński"   # flagi na górze


def test_malo_zdarzen_bez_flagi(admin_client, monkeypatch):
    """Nawet „odstający" z <5 zdarzeniami nie jest flagowany (szum małych liczb)."""
    monkeypatch.setattr(mod, "RCP_INGEST_TOKEN", "test-rcp-token")
    _ingest(admin_client, [_zdarzenie(1, nazwa="A B"), _zdarzenie(2, nazwa="C D"),
                           _zdarzenie(3, nazwa="E F", kwota=500)])
    w = admin_client.get("/api/antyfraud/podsumowanie").json()
    assert all(not k["flaga"] for k in w["kelnerzy"])


def test_puste_dane_nie_wybuchaja(admin_client):
    w = admin_client.get("/api/antyfraud/podsumowanie").json()
    assert w["kelnerzy"] == [] and w["zespol"]["osob"] == 0


def test_podsumowanie_tylko_admin(client):
    assert client.get("/api/antyfraud/podsumowanie").status_code in (401, 403)


def test_zakres_dat_filtruje(admin_client, monkeypatch):
    monkeypatch.setattr(mod, "RCP_INGEST_TOKEN", "test-rcp-token")
    _ingest(admin_client, [_zdarzenie(1, dni_temu=3), _zdarzenie(2, dni_temu=100)])
    w = admin_client.get("/api/antyfraud/podsumowanie").json()          # domyślnie 30 dni
    assert w["zespol"]["zdarzen"] == 1
    w2 = admin_client.get(f"/api/antyfraud/podsumowanie?start={DZIS - timedelta(days=200)}&end={DZIS}").json()
    assert w2["zespol"]["zdarzen"] == 2


# ── AI (mock) ────────────────────────────────────────────────────────────────

def test_podsumowanie_ai_mock(admin_client, monkeypatch):
    _seed_zespol(admin_client, monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(mod.ai, "zapytaj_claude",
                        lambda system, prompt, max_tokens=500: "Marek stornuje częściej niż zespół — porozmawiaj spokojnie.")
    w = admin_client.get("/api/antyfraud/podsumowanie?ai=1").json()
    assert w["ai"].startswith("Marek")
    assert w["ai_dostepne"] is True


def test_ai_opcjonalne_bez_klucza(admin_client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _seed_zespol(admin_client, monkeypatch)
    w = admin_client.get("/api/antyfraud/podsumowanie?ai=1").json()
    assert w["ai"] is None and w["ai_dostepne"] is False
