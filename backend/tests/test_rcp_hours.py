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
    assert moj["stanowiska"] == [{"stanowisko": "Sala", "godziny": 8.0, "stawka": 0.0, "kwota": 0.0}]
    assert moj["do_wyplaty"] == 0.0


def test_raport_liczy_wyplate_wg_stawki(db):
    sala = factories.StanowiskoFactory(nazwa="Sala")
    p = factories.PracownikFactory()
    factories.PrzydzialFactory(stanowisko=sala, pracownik=p, data=factories.dzien(0))
    _opublikuj(db, factories.dzien(0), factories.dzien(6))
    db.add(models.StawkaPracownika(pracownik_id=p.id, stanowisko_id=sala.id, stawka=30.0))
    db.commit()

    odbicia = [{"pracownik_id": p.id, "imie_nazwisko": "x", "data": factories.dzien(0),
                "godziny": 8.0, "wejscie": None}]
    raport = raporty.raport_godzin_miesiac(db, 2026, 6, odbicia=odbicia)
    moj = raport["pracownicy"][0]
    assert moj["stanowiska"][0]["stawka"] == 30.0
    assert moj["stanowiska"][0]["kwota"] == 240.0   # 8h * 30 zl
    assert moj["do_wyplaty"] == 240.0


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


def test_raport_noc_imprezowa_dolicza_do_poprzedniego_dnia(db):
    """Impreza ciągnie się po północy: odbicie z wejściem przed 9:00 następnego dnia
    dolicza się do imprezy z dnia poprzedniego (a nie ląduje „poza grafikiem")."""
    from datetime import time
    imprezy = factories.StanowiskoFactory(nazwa="Imprezy")
    p = factories.PracownikFactory()
    factories.PrzydzialFactory(stanowisko=imprezy, pracownik=p, data=factories.dzien(0), godz_od=time(15, 0))
    _opublikuj(db, factories.dzien(0), factories.dzien(6))

    # ogon imprezy odbity po północy: data = następny dzień, wejście 02:00
    odbicia = [{"pracownik_id": p.id, "imie_nazwisko": "x", "data": factories.dzien(1),
                "godziny": 3.3, "wejscie": datetime(2026, 6, 2, 2, 0)}]
    raport = raporty.raport_godzin_miesiac(db, 2026, 6, odbicia=odbicia)
    moj = raport["pracownicy"][0]
    assert moj["stanowiska"] == [{"stanowisko": "Imprezy", "godziny": 3.3, "stawka": 0.0, "kwota": 0.0}]


def test_raport_wejscie_po_9_rano_to_nowy_dzien(db):
    """Po 9:00 to już nowa zmiana — nie dolicza się do wczorajszej imprezy."""
    from datetime import time
    imprezy = factories.StanowiskoFactory(nazwa="Imprezy")
    p = factories.PracownikFactory()
    factories.PrzydzialFactory(stanowisko=imprezy, pracownik=p, data=factories.dzien(0), godz_od=time(15, 0))
    _opublikuj(db, factories.dzien(0), factories.dzien(6))

    # wejście 12:00 następnego dnia (po 9:00), brak przydziału tego dnia → poza grafikiem
    odbicia = [{"pracownik_id": p.id, "imie_nazwisko": "x", "data": factories.dzien(1),
                "godziny": 6.0, "wejscie": datetime(2026, 6, 2, 12, 0)}]
    raport = raporty.raport_godzin_miesiac(db, 2026, 6, odbicia=odbicia)
    assert raport["pracownicy"][0]["stanowiska"][0]["stanowisko"] == raporty.BUCKET_POZA_GRAFIKIEM


def test_raport_przycina_godziny_do_grafiku(db):
    """Pracownik odbija się wcześniej niż wpisany w grafiku → liczymy od zaplanowanej godziny."""
    from datetime import time
    sala = factories.StanowiskoFactory(nazwa="Sala")
    p = factories.PracownikFactory()
    factories.PrzydzialFactory(stanowisko=sala, pracownik=p, data=factories.dzien(0), godz_od=time(14, 0))
    _opublikuj(db, factories.dzien(0), factories.dzien(6))
    # odbił się 13:00, RCP liczy 9h — ale wpisany od 14:00 → liczymy 8h, 1h zaoszczędzone
    odbicia = [{"pracownik_id": p.id, "imie_nazwisko": "x", "data": factories.dzien(0),
                "godziny": 9.0, "wejscie": datetime(2026, 6, 1, 13, 0)}]
    raport = raporty.raport_godzin_miesiac(db, 2026, 6, odbicia=odbicia)
    moj = raport["pracownicy"][0]
    assert moj["suma_godzin"] == 8.0
    assert moj["zaoszczedzone_godziny"] == 1.0
    assert raport["zaoszczedzone"]["godziny"] == 1.0


def test_raport_zaoszczedzone_przelicza_kwote(db):
    from datetime import time
    sala = factories.StanowiskoFactory(nazwa="Sala")
    p = factories.PracownikFactory()
    factories.PrzydzialFactory(stanowisko=sala, pracownik=p, data=factories.dzien(0), godz_od=time(14, 0))
    _opublikuj(db, factories.dzien(0), factories.dzien(6))
    db.add(models.StawkaPracownika(pracownik_id=p.id, stanowisko_id=sala.id, stawka=30.0))
    db.commit()
    odbicia = [{"pracownik_id": p.id, "imie_nazwisko": "x", "data": factories.dzien(0),
                "godziny": 9.0, "wejscie": datetime(2026, 6, 1, 13, 30)}]  # 0.5h za wcześnie
    moj = raporty.raport_godzin_miesiac(db, 2026, 6, odbicia=odbicia)["pracownicy"][0]
    assert moj["suma_godzin"] == 8.5
    assert moj["zaoszczedzone_godziny"] == 0.5
    assert moj["zaoszczedzone_kwota"] == 15.0   # 0.5h * 30 zł


def test_raport_pozne_wejscie_bez_oszczednosci(db):
    from datetime import time
    sala = factories.StanowiskoFactory(nazwa="Sala")
    p = factories.PracownikFactory()
    factories.PrzydzialFactory(stanowisko=sala, pracownik=p, data=factories.dzien(0), godz_od=time(14, 0))
    _opublikuj(db, factories.dzien(0), factories.dzien(6))
    odbicia = [{"pracownik_id": p.id, "imie_nazwisko": "x", "data": factories.dzien(0),
                "godziny": 7.0, "wejscie": datetime(2026, 6, 1, 14, 10)}]  # po grafiku
    moj = raporty.raport_godzin_miesiac(db, 2026, 6, odbicia=odbicia)["pracownicy"][0]
    assert moj["suma_godzin"] == 7.0
    assert moj["zaoszczedzone_godziny"] == 0.0


def test_raport_wyroznia_duze_ciecie(db):
    """Ucięcie > 1h trafia do `duze_ciecia` (kto, kiedy, ile, wejście vs plan)."""
    from datetime import time
    sala = factories.StanowiskoFactory(nazwa="Sala")
    p = factories.PracownikFactory(imie="Jan", nazwisko="Wczesniak")
    factories.PrzydzialFactory(stanowisko=sala, pracownik=p, data=factories.dzien(0), godz_od=time(14, 0))
    _opublikuj(db, factories.dzien(0), factories.dzien(6))
    odbicia = [{"pracownik_id": p.id, "imie_nazwisko": "x", "data": factories.dzien(0),
                "godziny": 10.0, "wejscie": datetime(2026, 6, 1, 12, 0)}]  # 2h za wcześnie
    raport = raporty.raport_godzin_miesiac(db, 2026, 6, odbicia=odbicia)
    assert len(raport["duze_ciecia"]) == 1
    c = raport["duze_ciecia"][0]
    assert c["pracownik"] == "Jan Wczesniak"
    assert c["godziny_uciete"] == 2.0
    assert c["wejscie"] == "12:00" and c["planowane"] == "14:00"


def test_raport_male_ciecie_w_osobnej_liscie(db):
    """Cięcie 10 min–1h trafia do `male_ciecia` (nie do `duze_ciecia`)."""
    from datetime import time
    sala = factories.StanowiskoFactory(nazwa="Sala")
    p = factories.PracownikFactory()
    factories.PrzydzialFactory(stanowisko=sala, pracownik=p, data=factories.dzien(0), godz_od=time(14, 0))
    _opublikuj(db, factories.dzien(0), factories.dzien(6))
    odbicia = [{"pracownik_id": p.id, "imie_nazwisko": "x", "data": factories.dzien(0),
                "godziny": 8.0, "wejscie": datetime(2026, 6, 1, 13, 30)}]  # 30 min za wcześnie
    raport = raporty.raport_godzin_miesiac(db, 2026, 6, odbicia=odbicia)
    assert raport["duze_ciecia"] == []
    assert len(raport["male_ciecia"]) == 1
    assert raport["male_ciecia"][0]["godziny_uciete"] == 0.5


def test_raport_ponizej_10min_pomijane(db):
    """Cięcie ≤10 min nie pojawia się ani w dużych, ani w małych."""
    from datetime import time
    sala = factories.StanowiskoFactory(nazwa="Sala")
    p = factories.PracownikFactory()
    factories.PrzydzialFactory(stanowisko=sala, pracownik=p, data=factories.dzien(0), godz_od=time(14, 0))
    _opublikuj(db, factories.dzien(0), factories.dzien(6))
    odbicia = [{"pracownik_id": p.id, "imie_nazwisko": "x", "data": factories.dzien(0),
                "godziny": 8.0, "wejscie": datetime(2026, 6, 1, 13, 53)}]  # 7 min — poniżej progu
    raport = raporty.raport_godzin_miesiac(db, 2026, 6, odbicia=odbicia)
    assert raport["duze_ciecia"] == [] and raport["male_ciecia"] == []


def test_raport_techniczny_pelne_godziny_bez_grafiku(db):
    """Pracownik techniczny: pełne godziny RCP × stawka, bez grafiku i bez publikacji."""
    tech = factories.StanowiskoFactory(nazwa="Techniczny")
    p = factories.PracownikFactory(imie="Tech", nazwisko="Nik", dzial="techniczny")
    db.add(models.StawkaPracownika(pracownik_id=p.id, stanowisko_id=tech.id, stawka=40.0))
    db.commit()
    # BRAK przydziału i BRAK publikacji — techniczny i tak liczy pełne godziny
    odbicia = [{"pracownik_id": p.id, "imie_nazwisko": "x", "data": factories.dzien(0),
                "godziny": 6.0, "wejscie": datetime(2026, 6, 1, 8, 0)}]
    moj = raporty.raport_godzin_miesiac(db, 2026, 6, odbicia=odbicia)["pracownicy"][0]
    assert moj["dzial"] == "techniczny"
    assert moj["stanowiska"] == [{"stanowisko": "Techniczny", "godziny": 6.0, "stawka": 40.0, "kwota": 240.0}]
    assert moj["do_wyplaty"] == 240.0


def test_raport_sortuje_malejaco_wg_wyplaty(db):
    sala = factories.StanowiskoFactory(nazwa="Sala")
    p1 = factories.PracownikFactory(imie="Maly", nazwisko="A")
    p2 = factories.PracownikFactory(imie="Duzy", nazwisko="B")
    factories.PrzydzialFactory(stanowisko=sala, pracownik=p1, data=factories.dzien(0))
    factories.PrzydzialFactory(stanowisko=sala, pracownik=p2, data=factories.dzien(0))
    _opublikuj(db, factories.dzien(0), factories.dzien(6))
    db.add(models.StawkaPracownika(pracownik_id=p1.id, stanowisko_id=sala.id, stawka=10.0))
    db.add(models.StawkaPracownika(pracownik_id=p2.id, stanowisko_id=sala.id, stawka=50.0))
    db.commit()
    odbicia = [
        {"pracownik_id": p1.id, "imie_nazwisko": "a", "data": factories.dzien(0), "godziny": 8.0, "wejscie": None},
        {"pracownik_id": p2.id, "imie_nazwisko": "b", "data": factories.dzien(0), "godziny": 8.0, "wejscie": None},
    ]
    raport = raporty.raport_godzin_miesiac(db, 2026, 6, odbicia=odbicia)
    assert [p["pracownik"] for p in raport["pracownicy"]] == ["Duzy B", "Maly A"]  # 400 zł przed 80 zł
    assert raport["pracownicy"][0]["do_wyplaty"] == 400.0


def test_duze_ciecia_widzi_admin_i_szef(admin_client, client, db):
    from datetime import time
    sala = factories.StanowiskoFactory(nazwa="Sala")
    p = factories.PracownikFactory(imie="Jan", nazwisko="Wcz")
    factories.PrzydzialFactory(stanowisko=sala, pracownik=p, data=factories.dzien(0), godz_od=time(14, 0))
    _opublikuj(db, factories.dzien(0), factories.dzien(6))
    db.add(models.OdbicieRcp(rcp_id="ciecie-1", imie_nazwisko="Jan Wcz", pracownik_id=p.id,
                             data=factories.dzien(0), wejscie=datetime(2026, 6, 1, 12, 0),
                             wyjscie=datetime(2026, 6, 1, 22, 0), godziny=10.0))
    db.commit()
    radm = admin_client.get("/api/raporty/godziny?rok=2026&miesiac=6").json()
    assert len(radm.get("duze_ciecia", [])) == 1
    szef = factories.UserFactory(login="szefciec", rola="szef")
    rszef = client.get("/api/raporty/godziny?rok=2026&miesiac=6",
                       headers={"Authorization": f"Bearer {create_access_token(szef)}"}).json()
    assert len(rszef.get("duze_ciecia", [])) == 1 and "male_ciecia" in rszef  # szef też widzi cięcia


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


def test_me_godziny_pokazuje_trwajaca_zmiane(client, db):
    import main
    from datetime import datetime
    p = factories.PracownikFactory(imie="Jan", nazwisko="Kowalski")
    emp = factories.UserFactory(login="janopen", rola="employee", pracownik=p)
    teraz = main._teraz_lokalnie() or datetime.now()
    db.add(models.OdbicieRcp(
        rcp_id="open1", imie_nazwisko="Jan Kowalski", pracownik_id=p.id,
        data=teraz.date(), wejscie=teraz.replace(microsecond=0), wyjscie=None,
    ))
    db.commit()
    r = client.get("/api/me/godziny", headers=_h(emp), params={"rok": teraz.year, "miesiac": teraz.month})
    assert r.status_code == 200
    akt = r.json()["aktywna_zmiana"]
    assert akt is not None
    assert akt["wejscie"].startswith(teraz.date().isoformat())


def test_me_godziny_stara_otwarta_zmiana_pominieta(client, db):
    import main
    from datetime import datetime, timedelta
    if main._teraz_lokalnie() is None:
        import pytest
        pytest.skip("brak strefy czasu (zoneinfo) — bramka swiezosci wylaczona")
    p = factories.PracownikFactory(imie="Anna", nazwisko="Stara")
    emp = factories.UserFactory(login="annastara", rola="employee", pracownik=p)
    stara = (main._teraz_lokalnie() - timedelta(days=3)).replace(microsecond=0)
    db.add(models.OdbicieRcp(
        rcp_id="open_old", imie_nazwisko="Anna Stara", pracownik_id=p.id,
        data=stara.date(), wejscie=stara, wyjscie=None,
    ))
    db.commit()
    r = client.get("/api/me/godziny", headers=_h(emp), params={"rok": stara.year, "miesiac": stara.month})
    assert r.json()["aktywna_zmiana"] is None


def test_me_godziny_podzial_na_dni(client, db):
    from datetime import datetime
    p = factories.PracownikFactory(imie="Jan", nazwisko="Dniowy")
    emp = factories.UserFactory(login="jandni", rola="employee", pracownik=p)
    db.add_all([  # dwie zmiany 01.06 + jedna 03.06
        models.OdbicieRcp(rcp_id="d1", imie_nazwisko="Jan Dniowy", pracownik_id=p.id, data=factories.dzien(0),
                          wejscie=datetime(2026, 6, 1, 8, 0), wyjscie=datetime(2026, 6, 1, 12, 0), godziny=4.0),
        models.OdbicieRcp(rcp_id="d2", imie_nazwisko="Jan Dniowy", pracownik_id=p.id, data=factories.dzien(0),
                          wejscie=datetime(2026, 6, 1, 18, 0), wyjscie=datetime(2026, 6, 1, 20, 30), godziny=2.5),
        models.OdbicieRcp(rcp_id="d3", imie_nazwisko="Jan Dniowy", pracownik_id=p.id, data=factories.dzien(2),
                          wejscie=datetime(2026, 6, 3, 10, 0), wyjscie=datetime(2026, 6, 3, 18, 0), godziny=8.0),
    ])
    db.commit()
    r = client.get("/api/me/godziny", headers=_h(emp), params={"rok": 2026, "miesiac": 6})
    d_map = {d["data"]: d["godziny"] for d in r.json()["dni"]}
    assert d_map[str(factories.dzien(0))] == 6.5  # 4.0 + 2.5 zsumowane w jednym dniu
    assert d_map[str(factories.dzien(2))] == 8.0


def test_raport_admin_dostepny_dla_admina(admin_client, db):
    r = admin_client.get("/api/raporty/godziny", params={"rok": 2026, "miesiac": 6})
    assert r.status_code == 200
    assert "pracownicy" in r.json()
    assert "na_zmianie" in r.json()


def test_raport_na_zmianie_pokazuje_trwajace(admin_client, db):
    import main
    from datetime import datetime
    p = factories.PracownikFactory(imie="Live", nazwisko="Osoba")
    teraz = main._teraz_lokalnie() or datetime.now()
    db.add(models.OdbicieRcp(
        rcp_id="live1", imie_nazwisko="Live Osoba", pracownik_id=p.id,
        data=teraz.date(), wejscie=teraz.replace(microsecond=0), wyjscie=None,
    ))
    db.commit()
    r = admin_client.get("/api/raporty/godziny", params={"rok": teraz.year, "miesiac": teraz.month})
    nz = r.json()["na_zmianie"]
    assert any(z["pracownik"] == "Live Osoba" and z["dopasowany"] for z in nz)


# ── Back-fill: nowy/edytowany pracownik podlinkowuje zalegle odbicia RCP ──────
def test_utworzenie_pracownika_podlinkowuje_zalegle_odbicia(client, admin_client, db):
    # odbicie przychodzi ZANIM pracownik istnieje -> niedopasowane (pid NULL)
    client.post("/api/rcp/ingest", headers=TOKEN, json={"odbicia": [
        {"rcp_id": "100", "imie_nazwisko": "NOWY PRACOWNIK", "data": "2026-06-01",
         "wejscie": "2026-06-01T10:00:00", "wyjscie": "2026-06-01T18:00:00"}]})
    assert db.query(models.OdbicieRcp).filter_by(rcp_id="100").one().pracownik_id is None

    # tworzymy pracownika o pasujacym (inna wielkosc liter) nazwisku -> podlinkowane od razu
    r = admin_client.post("/api/pracownicy", json={
        "imie": "Nowy", "nazwisko": "Pracownik", "aktywny": True, "kwalifikacje_ids": []})
    assert r.status_code == 201
    assert db.query(models.OdbicieRcp).filter_by(rcp_id="100").one().pracownik_id == r.json()["id"]


def test_edycja_nazwiska_podlinkowuje_odbicia(client, admin_client, db):
    p = factories.PracownikFactory(imie="Stare", nazwisko="Nazwisko")
    client.post("/api/rcp/ingest", headers=TOKEN, json={"odbicia": [
        {"rcp_id": "101", "imie_nazwisko": "Anna Nowak", "data": "2026-06-01",
         "wejscie": "2026-06-01T10:00:00"}]})
    assert db.query(models.OdbicieRcp).filter_by(rcp_id="101").one().pracownik_id is None

    admin_client.put(f"/api/pracownicy/{p.id}", json={
        "imie": "Anna", "nazwisko": "Nowak", "aktywny": True, "kwalifikacje_ids": []})
    assert db.query(models.OdbicieRcp).filter_by(rcp_id="101").one().pracownik_id == p.id


def test_rejestracja_konta_podlinkowuje_odbicia(client, db):
    client.post("/api/rcp/ingest", headers=TOKEN, json={"odbicia": [
        {"rcp_id": "102", "imie_nazwisko": "Piotr Zielinski", "data": "2026-06-01",
         "wejscie": "2026-06-01T10:00:00"}]})
    assert db.query(models.OdbicieRcp).filter_by(rcp_id="102").one().pracownik_id is None

    r = client.post("/api/auth/register", json={
        "login": "piotrz", "haslo": "Haslo123!", "imie": "Piotr", "nazwisko": "Zielinski"})
    assert r.status_code == 201
    assert db.query(models.OdbicieRcp).filter_by(rcp_id="102").one().pracownik_id is not None


def test_rejestracja_nie_duplikuje_istniejacego_pracownika(client, db):
    """Rejestracja na nazwisko istniejacego pracownika BEZ konta podpina sie pod niego
    (zamiast tworzyc duplikat) — dzieki czemu konto od razu ma jego godziny z RCP."""
    from datetime import datetime
    p = factories.PracownikFactory(imie="Mateusz", nazwisko="Kajda")
    db.add(models.OdbicieRcp(
        rcp_id="kajda1", imie_nazwisko="MATEUSZ KAJDA", pracownik_id=p.id,
        data=factories.dzien(0), wejscie=datetime(2026, 6, 1, 10, 0),
        wyjscie=datetime(2026, 6, 1, 18, 0), godziny=8.0,
    ))
    db.commit()
    r = client.post("/api/auth/register", json={
        "login": "mkajda", "haslo": "Haslo123!", "imie": "Mateusz", "nazwisko": "Kajda"})
    assert r.status_code == 201
    # nie powstal duplikat
    assert db.query(models.Pracownik).filter_by(nazwisko="Kajda").count() == 1
    # konto wskazuje na istniejacego pracownika (z jego godzinami)
    u = db.get(models.User, r.json()["user"]["id"])
    assert u.pracownik_id == p.id


def test_powiadomienie_tylko_dla_swiezych_zdarzen(client, db, monkeypatch):
    """Push leci tylko dla zdarzen w oknie RCP_POWIADOM_OKNO; stare (np. z pierwszego
    ingestu/restartu agenta) sa pomijane, ale rekord i tak sie zapisuje."""
    import main
    from datetime import timedelta as _td
    teraz = main._teraz_lokalnie()
    if teraz is None:
        import pytest
        pytest.skip("brak strefy czasu (zoneinfo) — bramka swiezosci wylaczona")

    wyslane = []
    monkeypatch.setattr(main, "wyslij_push_do_pracownika",
                        lambda db, pid, tytul, tresc, url="/": (wyslane.append(tytul) or 1))
    factories.PracownikFactory(imie="Jan", nazwisko="Kowalski")

    swieze = teraz.replace(microsecond=0)
    stare = swieze - _td(hours=5)
    client.post("/api/rcp/ingest", headers=TOKEN, json={"odbicia": [
        {"rcp_id": "200", "imie_nazwisko": "Jan Kowalski", "data": stare.date().isoformat(),
         "wejscie": stare.isoformat()},
        {"rcp_id": "201", "imie_nazwisko": "Jan Kowalski", "data": swieze.date().isoformat(),
         "wejscie": swieze.isoformat()},
    ]})
    assert wyslane == ["Rozpoczęto zmianę"]  # tylko swieze; stare pominiete
    # ale OBA rekordy zapisane i dopasowane
    assert db.query(models.OdbicieRcp).filter(models.OdbicieRcp.rcp_id.in_(["200", "201"])).count() == 2


def test_backfill_nie_dotyka_juz_dopasowanych(client, admin_client, db):
    # istniejacy pracownik + odbicie do niego; nowy pracownik o INNYM nazwisku nie przejmuje
    p1 = factories.PracownikFactory(imie="Jan", nazwisko="Kowalski")
    client.post("/api/rcp/ingest", headers=TOKEN, json={"odbicia": [
        {"rcp_id": "103", "imie_nazwisko": "Jan Kowalski", "data": "2026-06-01",
         "wejscie": "2026-06-01T10:00:00"}]})
    assert db.query(models.OdbicieRcp).filter_by(rcp_id="103").one().pracownik_id == p1.id

    admin_client.post("/api/pracownicy", json={
        "imie": "Ewa", "nazwisko": "Inna", "aktywny": True, "kwalifikacje_ids": []})
    # nadal przypisane do p1, nie podmienione
    assert db.query(models.OdbicieRcp).filter_by(rcp_id="103").one().pracownik_id == p1.id
