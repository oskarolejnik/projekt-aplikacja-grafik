"""Zgodność lokalu (roadmapa v2, oś B) — dokumenty załogi + terminy lokalu.

Pokrywa: CRUD (admin-only), statusy z dni do wygaśnięcia (przeterminowane/pilne/wkrótce/ok),
alerty, blokady grafiku (endpoint) oraz hak w auto-przydziale: przeterminowany dokument
z blokuje_grafik=True wyklucza pracownika od dnia PO dacie ważności.
"""

from datetime import date, timedelta

import factories
import models
from algorithm import auto_assign
from deps import utcnow_naive

DZIS = date.today()


def _dok(admin_client, **over):
    dane = {
        "pracownik_id": None,
        "typ": "koncesja",
        "nazwa": "Koncesja alkoholowa — rata",
        "data_waznosci": str(DZIS + timedelta(days=90)),
        "blokuje_grafik": False,
    }
    dane.update(over)
    return admin_client.post("/api/zgodnosc", json=dane)


# ── CRUD + walidacja ─────────────────────────────────────────────────────────

def test_dodanie_terminu_lokalu(admin_client):
    r = _dok(admin_client)
    assert r.status_code == 201
    body = r.json()
    assert body["pracownik"] is None and body["typ"] == "koncesja"
    assert body["status"] == "ok" and body["dni"] == 90


def test_dodanie_dokumentu_pracownika(admin_client):
    p = factories.PracownikFactory()
    r = _dok(admin_client, pracownik_id=p.id, typ="badania_sanepid",
             nazwa="Orzeczenie sanepid", blokuje_grafik=True)
    assert r.status_code == 201
    body = r.json()
    assert body["pracownik_id"] == p.id and body["pracownik"] == f"{p.imie} {p.nazwisko}"
    assert body["blokuje_grafik"] is True


def test_walidacja_typu_i_nazwy_i_pracownika(admin_client):
    assert _dok(admin_client, typ="nieznany").status_code == 400
    assert _dok(admin_client, nazwa="   ").status_code == 400
    assert _dok(admin_client, pracownik_id=99999).status_code == 404


def test_edycja_i_usuniecie(admin_client):
    did = _dok(admin_client).json()["id"]
    r = admin_client.put(f"/api/zgodnosc/{did}", json={
        "pracownik_id": None, "typ": "przeglad", "nazwa": "Przegląd gaśnic",
        "data_waznosci": str(DZIS + timedelta(days=5)), "blokuje_grafik": False})
    assert r.status_code == 200
    assert r.json()["typ"] == "przeglad" and r.json()["status"] == "pilne"
    assert admin_client.delete(f"/api/zgodnosc/{did}").status_code == 204
    assert all(d["id"] != did for d in admin_client.get("/api/zgodnosc").json())


def test_zgodnosc_tylko_dla_admina(client):
    assert client.get("/api/zgodnosc").status_code in (401, 403)


# ── Statusy i alerty ─────────────────────────────────────────────────────────

def test_statusy_progow(admin_client):
    for dni, oczekiwany in [(-1, "przeterminowane"), (0, "pilne"), (14, "pilne"),
                            (15, "wkrotce"), (30, "wkrotce"), (31, "ok")]:
        r = _dok(admin_client, nazwa=f"Termin {dni}", data_waznosci=str(DZIS + timedelta(days=dni)))
        assert r.json()["status"] == oczekiwany, f"dni={dni}"


def test_alerty_liczniki_i_pozycje(admin_client):
    _dok(admin_client, nazwa="Przeterminowany", data_waznosci=str(DZIS - timedelta(days=3)))
    _dok(admin_client, nazwa="Pilny", data_waznosci=str(DZIS + timedelta(days=7)))
    _dok(admin_client, nazwa="Wkrótce", data_waznosci=str(DZIS + timedelta(days=20)))
    _dok(admin_client, nazwa="Spokojny", data_waznosci=str(DZIS + timedelta(days=200)))
    a = admin_client.get("/api/zgodnosc/alerty").json()
    assert a["przeterminowane"] == 1 and a["pilne"] == 1 and a["wkrotce"] == 1
    nazwy = [p["nazwa"] for p in a["pozycje"]]
    assert "Spokojny" not in nazwy and len(nazwy) == 3
    assert nazwy[0] == "Przeterminowany"   # sortowanie: najbliższe/przeterminowane pierwsze


# ── Blokady grafiku ──────────────────────────────────────────────────────────

def test_blokady_endpoint(admin_client):
    p = factories.PracownikFactory()
    _dok(admin_client, pracownik_id=p.id, typ="badania_sanepid", nazwa="Sanepid",
         data_waznosci=str(DZIS - timedelta(days=1)), blokuje_grafik=True)
    # nieblokujący przeterminowany — nie wchodzi do blokad
    _dok(admin_client, pracownik_id=p.id, typ="szkolenie_bhp", nazwa="BHP",
         data_waznosci=str(DZIS - timedelta(days=1)), blokuje_grafik=False)
    b = admin_client.get("/api/zgodnosc/blokady").json()
    assert b == {str(p.id): ["Sanepid"]} or b == {p.id: ["Sanepid"]}  # klucze JSON są stringami


def test_wazny_dokument_nie_blokuje(admin_client):
    p = factories.PracownikFactory()
    _dok(admin_client, pracownik_id=p.id, typ="badania_sanepid", nazwa="Sanepid OK",
         data_waznosci=str(DZIS + timedelta(days=10)), blokuje_grafik=True)
    assert admin_client.get("/api/zgodnosc/blokady").json() == {}


# ── Hak w auto-przydziale ────────────────────────────────────────────────────

def _pracownik_gotowy(stan, dzien_pracy):
    p = factories.PracownikFactory()
    p.kwalifikacje = [stan]
    factories.Session.commit()
    factories.DyspozycjaFactory(pracownik=p, data=dzien_pracy, dostepnosc=True, godz_od=None)
    return p


def test_auto_assign_pomija_przeterminowane_badania(db):
    stan = factories.StanowiskoFactory()
    dzien_pracy = factories.dzien(7)
    p = _pracownik_gotowy(stan, dzien_pracy)
    factories.WymaganieFactory(stanowisko_id=stan.id, data=dzien_pracy, liczba_osob=1, godz_od=None)
    db.add(models.DokumentZgodnosci(
        pracownik_id=p.id, typ="badania_sanepid", nazwa="Sanepid",
        data_waznosci=dzien_pracy - timedelta(days=2), blokuje_grafik=True,
        utworzono_at=utcnow_naive()))
    db.commit()

    wynik = auto_assign(db, dzien_pracy, dzien_pracy)
    assert wynik["przydzielone"] == 0
    assert len(wynik["niedobory"]) == 1   # jedyny kandydat wykluczony → niedobór


def test_auto_assign_przydziela_do_daty_waznosci(db):
    """Dokument wygasa w trakcie tygodnia: dzień PRZED datą ważności wolno, dzień PO — nie."""
    stan = factories.StanowiskoFactory()
    d_ok = factories.dzien(7)          # dokument ważny jeszcze tego dnia
    d_blok = factories.dzien(8)        # dzień po dacie ważności
    p = _pracownik_gotowy(stan, d_ok)
    factories.DyspozycjaFactory(pracownik=p, data=d_blok, dostepnosc=True, godz_od=None)
    factories.WymaganieFactory(stanowisko_id=stan.id, data=d_ok, liczba_osob=1, godz_od=None)
    factories.WymaganieFactory(stanowisko_id=stan.id, data=d_blok, liczba_osob=1, godz_od=None)
    db.add(models.DokumentZgodnosci(
        pracownik_id=p.id, typ="medycyna_pracy", nazwa="Medycyna pracy",
        data_waznosci=d_ok, blokuje_grafik=True,
        utworzono_at=utcnow_naive()))
    db.commit()

    wynik = auto_assign(db, d_ok, d_blok)
    assert wynik["przydzielone"] == 1
    przydzialy = db.query(models.PrzydzialZmiany).all()
    assert [a.data for a in przydzialy] == [d_ok]
    assert len(wynik["niedobory"]) == 1


def test_auto_assign_bez_blokady_dziala_normalnie(db):
    stan = factories.StanowiskoFactory()
    dzien_pracy = factories.dzien(7)
    _pracownik_gotowy(stan, dzien_pracy)
    factories.WymaganieFactory(stanowisko_id=stan.id, data=dzien_pracy, liczba_osob=1, godz_od=None)
    wynik = auto_assign(db, dzien_pracy, dzien_pracy)
    assert wynik["przydzielone"] == 1 and wynik["niedobory"] == []
