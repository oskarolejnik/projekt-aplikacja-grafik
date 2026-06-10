"""AUTO „zamyka lokal": osoba z NAJPÓŹNIEJSZYM godz_od na PARKIECIE (stanowiska, których
nazwa zaczyna się od „Sala": Sala, Sala-ABC, Sala-RZP, Sala-Bar...) danego dnia zamyka lokal.

Flaga jest w pełni automatyczna (bez ręcznego ustawiania) i przeliczana po każdej zmianie
grafiku: POST/PUT/DELETE przydziału oraz publikacja tygodnia (backfill)."""

from datetime import time

import factories

DZIEN = factories.dzien(0)          # poniedziałek 2026-06-01
TYDZIEN_END = factories.dzien(6)


def _body(stan, prac, godz_od=None, zamyka=None):
    b = {"data": str(DZIEN), "stanowisko_id": stan.id, "pracownik_id": prac.id}
    if godz_od is not None:
        b["godz_od"] = godz_od.strftime("%H:%M")
    if zamyka is not None:
        b["zamyka"] = zamyka
    return b


def _zamyka_map(admin_client):
    """{pracownik_id: bool(zamyka)} z GET /api/przydzialy dla DZIEN (świeży odczyt z API)."""
    rows = admin_client.get(f"/api/przydzialy?start={DZIEN}&end={DZIEN}").json()
    return {r["pracownik_id"]: bool(r["zamyka"]) for r in rows}


def test_najpozniejszy_na_sali_zamyka(admin_client):
    sala = factories.StanowiskoFactory(nazwa="Sala")
    wczesny = factories.PracownikFactory(imie="Wczesny", nazwisko="A")
    pozny = factories.PracownikFactory(imie="Pozny", nazwisko="B")
    admin_client.post("/api/przydzialy", json=_body(sala, wczesny, time(10, 0)))
    admin_client.post("/api/przydzialy", json=_body(sala, pozny, time(16, 0)))
    z = _zamyka_map(admin_client)
    assert z[pozny.id] is True
    assert z[wczesny.id] is False


def test_parkiet_obejmuje_warianty_sala(admin_client):
    """Najpóźniejszy z CAŁEGO parkietu (Sala + Sala-*) zamyka, nawet z innej strefy."""
    sala = factories.StanowiskoFactory(nazwa="Sala")
    sala_abc = factories.StanowiskoFactory(nazwa="Sala-ABC")
    p_sala = factories.PracownikFactory(imie="Sala", nazwisko="A")
    p_abc = factories.PracownikFactory(imie="Abc", nazwisko="B")
    admin_client.post("/api/przydzialy", json=_body(sala, p_sala, time(12, 0)))
    admin_client.post("/api/przydzialy", json=_body(sala_abc, p_abc, time(18, 0)))
    z = _zamyka_map(admin_client)
    assert z[p_abc.id] is True
    assert z[p_sala.id] is False


def test_stanowisko_spoza_parkietu_nie_zamyka(admin_client):
    """Bar zaczyna najpóźniej, ale to NIE parkiet → zamyka osoba z Sali."""
    sala = factories.StanowiskoFactory(nazwa="Sala")
    bar = factories.StanowiskoFactory(nazwa="Bar")
    p_sala = factories.PracownikFactory(imie="Sala", nazwisko="A")
    p_bar = factories.PracownikFactory(imie="Bar", nazwisko="B")
    admin_client.post("/api/przydzialy", json=_body(sala, p_sala, time(15, 0)))
    admin_client.post("/api/przydzialy", json=_body(bar, p_bar, time(20, 0)))
    z = _zamyka_map(admin_client)
    assert z[p_sala.id] is True
    assert z[p_bar.id] is False


def test_bez_godziny_startu_nie_jest_kandydatem(admin_client):
    """Osoba na Sali bez godz_od (Dowolnie) nie może być „najpóźniejsza" → zamyka ten z godziną."""
    sala = factories.StanowiskoFactory(nazwa="Sala")
    bez = factories.PracownikFactory(imie="Bez", nazwisko="A")
    zgodz = factories.PracownikFactory(imie="Zgodz", nazwisko="B")
    admin_client.post("/api/przydzialy", json=_body(sala, bez, None))          # bez godz_od
    admin_client.post("/api/przydzialy", json=_body(sala, zgodz, time(11, 0)))
    z = _zamyka_map(admin_client)
    assert z[zgodz.id] is True
    assert z[bez.id] is False


def test_usuniecie_zamykajacego_przechodzi_na_kolejnego(admin_client):
    sala = factories.StanowiskoFactory(nazwa="Sala")
    wczesny = factories.PracownikFactory(imie="Wczesny", nazwisko="A")
    pozny = factories.PracownikFactory(imie="Pozny", nazwisko="B")
    admin_client.post("/api/przydzialy", json=_body(sala, wczesny, time(10, 0)))
    r2 = admin_client.post("/api/przydzialy", json=_body(sala, pozny, time(16, 0)))
    assert _zamyka_map(admin_client)[pozny.id] is True
    admin_client.delete(f"/api/przydzialy/{r2.json()['id']}")
    assert _zamyka_map(admin_client)[wczesny.id] is True   # teraz on jest najpóźniejszy


def test_reczne_zamyka_jest_nadpisywane(admin_client):
    """Ręczne zamyka=true na wcześniejszej osobie jest nadpisywane automatem (jedno źródło prawdy)."""
    sala = factories.StanowiskoFactory(nazwa="Sala")
    wczesny = factories.PracownikFactory(imie="Wczesny", nazwisko="A")
    pozny = factories.PracownikFactory(imie="Pozny", nazwisko="B")
    admin_client.post("/api/przydzialy", json=_body(sala, wczesny, time(10, 0), zamyka=True))
    admin_client.post("/api/przydzialy", json=_body(sala, pozny, time(16, 0)))
    z = _zamyka_map(admin_client)
    assert z[wczesny.id] is False
    assert z[pozny.id] is True


def test_publikacja_backfill_zamykajacego(admin_client):
    """Przydziały wstawione z pominięciem automatu (stare dane) — publikacja przelicza zamykającego."""
    sala = factories.StanowiskoFactory(nazwa="Sala")
    wczesny = factories.PracownikFactory(imie="W", nazwisko="A")
    pozny = factories.PracownikFactory(imie="P", nazwisko="B")
    # Bezpośrednio przez factory — pomija przeliczanie z endpointu (symuluje dane sprzed automatu).
    factories.PrzydzialFactory(stanowisko=sala, pracownik=wczesny, data=DZIEN, godz_od=time(10, 0))
    factories.PrzydzialFactory(stanowisko=sala, pracownik=pozny, data=DZIEN, godz_od=time(16, 0))
    assert _zamyka_map(admin_client)[pozny.id] is False   # jeszcze nieprzeliczone
    admin_client.post(f"/api/grafik/publikuj?start={DZIEN}&end={TYDZIEN_END}")
    z = _zamyka_map(admin_client)
    assert z[pozny.id] is True
    assert z[wczesny.id] is False


def test_reczne_nadpisanie_trzyma_sie_mimo_automatu(admin_client):
    """Ręczne ustawienie zamykającego (PUT /{id}/zamyka {reczny:true}) NIE jest nadpisywane
    przez automat, nawet gdy dojdzie ktoś późniejszy z parkietu."""
    sala = factories.StanowiskoFactory(nazwa="Sala")
    wczesny = factories.PracownikFactory(imie="Wczesny", nazwisko="A")
    pozny = factories.PracownikFactory(imie="Pozny", nazwisko="B")
    r1 = admin_client.post("/api/przydzialy", json=_body(sala, wczesny, time(10, 0)))
    admin_client.put(f"/api/przydzialy/{r1.json()['id']}/zamyka", json={"reczny": True})
    assert _zamyka_map(admin_client)[wczesny.id] is True
    admin_client.post("/api/przydzialy", json=_body(sala, pozny, time(16, 0)))  # późniejszy
    z = _zamyka_map(admin_client)
    assert z[wczesny.id] is True     # ręczne trzyma
    assert z[pozny.id] is False


def test_powrot_do_automatu(admin_client):
    """Zdjęcie ręcznego (reczny:false) przywraca automat — najpóźniejszy z parkietu."""
    sala = factories.StanowiskoFactory(nazwa="Sala")
    wczesny = factories.PracownikFactory(imie="Wczesny", nazwisko="A")
    pozny = factories.PracownikFactory(imie="Pozny", nazwisko="B")
    r1 = admin_client.post("/api/przydzialy", json=_body(sala, wczesny, time(10, 0)))
    admin_client.post("/api/przydzialy", json=_body(sala, pozny, time(16, 0)))
    admin_client.put(f"/api/przydzialy/{r1.json()['id']}/zamyka", json={"reczny": True})
    assert _zamyka_map(admin_client)[wczesny.id] is True
    admin_client.put(f"/api/przydzialy/{r1.json()['id']}/zamyka", json={"reczny": False})
    z = _zamyka_map(admin_client)
    assert z[pozny.id] is True
    assert z[wczesny.id] is False


def test_pelna_edycja_godziny_i_stanowiska(admin_client):
    """PUT /api/przydzialy/{id} zmienia godzinę, stanowisko i rewir istniejącego przydziału."""
    sala = factories.StanowiskoFactory(nazwa="Sala")
    bar = factories.StanowiskoFactory(nazwa="Bar")
    p = factories.PracownikFactory(imie="X", nazwisko="Y")
    r = admin_client.post("/api/przydzialy", json=_body(sala, p, time(10, 0)))
    aid = r.json()["id"]
    upd = admin_client.put(f"/api/przydzialy/{aid}", json={
        "data": str(DZIEN), "stanowisko_id": bar.id, "pracownik_id": p.id,
        "godz_od": "18:30", "rewir": "Parter",
    })
    assert upd.status_code == 200, upd.text
    body = upd.json()
    assert body["stanowisko_id"] == bar.id
    assert body["godz_od"].startswith("18:30")
    assert body["rewir"] == "Parter"
