"""Testy ingestu odbić RCP (od lokalnego agenta) i raportu godzin/stanowisko.

Push jest nieaktywny w testach (brak kluczy VAPID -> wysyłka zwraca 0), więc sprawdzamy
SAMĄ logikę: upsert po rcp_id, dopasowanie pracownika, liczenie godzin, flagi powiadomień,
oraz złączenie z OPUBLIKOWANYM grafikiem.
"""

from datetime import datetime

import models
import factories
import raporty
from auth import create_access_token

TOKEN = {"X-RCP-Token": "test-rcp-token"}


def _h(user):
    return {"Authorization": f"Bearer {create_access_token(user)}"}


# ── Ingest / autoryzacja ──────────────────────────────────────────────────────
def test_ingest_wymaga_tokenu(client):
    assert client.post("/api/rcp/ingest", json={"odbicia": []}).status_code == 401


def test_ingest_zly_token(client):
    r = client.post("/api/rcp/ingest", headers={"X-RCP-Token": "zly"}, json={"odbicia": []})
    assert r.status_code == 401


def test_ingest_tworzy_i_dopasowuje_po_nazwie(client, db):
    p = factories.PracownikFactory(imie="Jan", nazwisko="Kowalski")
    r = client.post(
        "/api/rcp/ingest", headers=TOKEN,
        json={"odbicia": [{"rcp_id": "1", "imie_nazwisko": "Jan Kowalski",
                            "data": "2026-06-01", "wejscie": "2026-06-01T10:00:00"}]},
    )
    assert r.status_code == 200 and r.json()["nowe"] == 1
    rec = db.query(models.OdbicieRcp).filter_by(rcp_id="1").one()
    assert rec.pracownik_id == p.id
    assert rec.godziny is None  # brak wyjścia
    assert rec.powiadomiono_wejscie is True  # flaga ustawiona (push 0 bez VAPID)
    assert rec.powiadomiono_wyjscie is False


def test_ingest_dopasowanie_ignoruje_ogonki_i_wielkosc(client, db):
    factories.PracownikFactory(imie="Łukasz", nazwisko="Żółć")
    client.post("/api/rcp/ingest", headers=TOKEN, json={"odbicia": [
        {"rcp_id": "9", "imie_nazwisko": "lukasz zolc", "data": "2026-06-01",
         "wejscie": "2026-06-01T08:00:00"}]})
    rec = db.query(models.OdbicieRcp).filter_by(rcp_id="9").one()
    assert rec.pracownik_id is not None


def test_ingest_nieznana_osoba_zostaje_niedopasowana(client, db):
    client.post("/api/rcp/ingest", headers=TOKEN, json={"odbicia": [
        {"rcp_id": "7", "imie_nazwisko": "Ktoś Spoza", "data": "2026-06-01",
         "wejscie": "2026-06-01T08:00:00"}]})
    rec = db.query(models.OdbicieRcp).filter_by(rcp_id="7").one()
    assert rec.pracownik_id is None


def test_ingest_zakonczenie_liczy_godziny_i_jest_idempotentny(client, db):
    factories.PracownikFactory(imie="Jan", nazwisko="Kowalski")
    o_in = {"rcp_id": "1", "imie_nazwisko": "Jan Kowalski", "data": "2026-06-01",
            "wejscie": "2026-06-01T10:00:00"}
    o_out = dict(o_in, wyjscie="2026-06-01T18:30:00")

    client.post("/api/rcp/ingest", headers=TOKEN, json={"odbicia": [o_in]})
    r2 = client.post("/api/rcp/ingest", headers=TOKEN, json={"odbicia": [o_out]})
    assert r2.json()["nowe"] == 0 and r2.json()["zakonczone"] == 1

    rec = db.query(models.OdbicieRcp).filter_by(rcp_id="1").one()
    assert rec.godziny == 8.5
    assert rec.powiadomiono_wyjscie is True

    # Powtórny ingest tego samego nie tworzy nowych ani nie zakańcza ponownie.
    r3 = client.post("/api/rcp/ingest", headers=TOKEN, json={"odbicia": [o_out]})
    assert r3.json()["nowe"] == 0 and r3.json()["zakonczone"] == 0
    assert db.query(models.OdbicieRcp).count() == 1


# ── Raport godzin/stanowisko (jednostkowo, wstrzyknięte odbicia) ──────────────
def _opublikuj(db, start, koniec):
    db.add(models.PublikacjaGrafiku(start=start, koniec=koniec, opublikowano_at=datetime.utcnow()))
    db.commit()


def test_raport_przypisuje_godziny_do_stanowiska_z_grafiku(db):
    sala = factories.StanowiskoFactory(nazwa="Sala")
    p = factories.PracownikFactory()
    factories.PrzydzialFactory(stanowisko=sala, pracownik=p, data=factories.dzien(0))
    _opublikuj(db, factories.dzien(0), factories.dzien(6))

    odbicia = [{"pracownik_id": p.id, "imie_nazwisko": "x", "data": factories.dzien(0),
                "godziny": 8.0, "wejscie": None}]
    raport = raporty.raport_godzin_miesiac(db, 2026, 6, odbicia=odbicia)

    moj = raport["pracownicy"][0]
    assert moj["pracownik_id"] == p.id
    assert moj["suma_godzin"] == 8.0
    assert moj["stanowiska"] == [{"stanowisko": "Sala", "godziny": 8.0}]


def test_raport_nieopublikowany_grafik_trafia_do_kubelka(db):
    sala = factories.StanowiskoFactory(nazwa="Sala")
    p = factories.PracownikFactory()
    factories.PrzydzialFactory(stanowisko=sala, pracownik=p, data=factories.dzien(0))
    # brak publikacji!
    odbicia = [{"pracownik_id": p.id, "imie_nazwisko": "x", "data": factories.dzien(0),
                "godziny": 5.0, "wejscie": None}]
    raport = raporty.raport_godzin_miesiac(db, 2026, 6, odbicia=odbicia)
    assert raport["pracownicy"][0]["stanowiska"][0]["stanowisko"] == raporty.BUCKET_NIEOPUBLIKOWANY


def test_raport_zmiana_dzielona_wybiera_wg_wejscia(db):
    sala = factories.StanowiskoFactory(nazwa="Sala")
    bar = factories.StanowiskoFactory(nazwa="Bar")
    p = factories.PracownikFactory()
    from datetime import time
    factories.PrzydzialFactory(stanowisko=sala, pracownik=p, data=factories.dzien(0), godz_od=time(10, 0))
    factories.PrzydzialFactory(stanowisko=bar, pracownik=p, data=factories.dzien(0), godz_od=time(18, 0))
    _opublikuj(db, factories.dzien(0), factories.dzien(6))

    odbicia = [{"pracownik_id": p.id, "imie_nazwisko": "x", "data": factories.dzien(0),
                "godziny": 4.0, "wejscie": datetime(2026, 6, 1, 18, 5)}]  # wszedł ~18:00 -> Bar
    raport = raporty.raport_godzin_miesiac(db, 2026, 6, odbicia=odbicia)
    assert raport["pracownicy"][0]["stanowiska"][0]["stanowisko"] == "Bar"


def test_raport_filtruje_po_pracowniku(db):
    sala = factories.StanowiskoFactory(nazwa="Sala")
    p1 = factories.PracownikFactory()
    p2 = factories.PracownikFactory()
    for p in (p1, p2):
        factories.PrzydzialFactory(stanowisko=sala, pracownik=p, data=factories.dzien(0))
    _opublikuj(db, factories.dzien(0), factories.dzien(6))
    odbicia = [
        {"pracownik_id": p1.id, "imie_nazwisko": "a", "data": factories.dzien(0), "godziny": 8.0, "wejscie": None},
        {"pracownik_id": p2.id, "imie_nazwisko": "b", "data": factories.dzien(0), "godziny": 6.0, "wejscie": None},
    ]
    raport = raporty.raport_godzin_miesiac(db, 2026, 6, odbicia=odbicia, tylko_pracownik_id=p1.id)
    assert len(raport["pracownicy"]) == 1
    assert raport["pracownicy"][0]["pracownik_id"] == p1.id


# ── Endpoint pracownika /api/me/godziny ───────────────────────────────────────
def test_me_godziny_pokazuje_miesieczne_podsumowanie(client, db):
    sala = factories.StanowiskoFactory(nazwa="Sala")
    p = factories.PracownikFactory(imie="Jan", nazwisko="Kowalski")
    emp = factories.UserFactory(login="jan1", rola="employee", pracownik=p)
    factories.PrzydzialFactory(stanowisko=sala, pracownik=p, data=factories.dzien(0))
    _opublikuj(db, factories.dzien(0), factories.dzien(6))
    db.add(models.OdbicieRcp(
        rcp_id="1", imie_nazwisko="Jan Kowalski", pracownik_id=p.id, data=factories.dzien(0),
        wejscie=datetime(2026, 6, 1, 10, 0), wyjscie=datetime(2026, 6, 1, 18, 0), godziny=8.0,
    ))
    db.commit()

    r = client.get("/api/me/godziny", headers=_h(emp), params={"rok": 2026, "miesiac": 6})
    assert r.status_code == 200
    body = r.json()
    assert body["suma_godzin"] == 8.0
    assert body["stanowiska"][0]["stanowisko"] == "Sala"


def test_me_godziny_wymaga_logowania(client):
    assert client.get("/api/me/godziny", params={"rok": 2026, "miesiac": 6}).status_code == 401


def test_raport_admin_dostepny_dla_admina(admin_client, db):
    r = admin_client.get("/api/raporty/godziny", params={"rok": 2026, "miesiac": 6})
    assert r.status_code == 200
    assert "pracownicy" in r.json()
