"""CEL 4 (część B) — ograniczenia prawne/biznesowe: stan faktyczny vs oczekiwania.

RAPORT QA — czego aplikacja NIE egzekwuje (a wynika to z wymagań/Kodeksu pracy):
  1. Minimalny odpoczynek między zmianami (np. 11h)  — BRAK (zmiany nie mają godz. końca).
  2. Maksymalna liczba godzin/dni w tygodniu          — BRAK (brak modelu godzin).
  3. Maksymalna liczba godzin/dni w miesiącu          — BRAK.
  4. Urlopy jako encja/zakres                         — BRAK (obejście: niedostępność dzień po dniu).
  5. Detekcja nakładających się godzin                — BRAK (brak godz. końca).
  6. Ręczny przydział sprawdzający kwalifikacje       — BRAK (sprawdza tylko auto-assign).
  7. Ręczny przydział sprawdzający dyspozycyjność     — BRAK (sprawdza tylko auto-assign).

Testy oznaczone @gap + xfail(strict=False): kodują OCZEKIWANE zachowanie. Dopóki brak
implementacji — są 'xfail' (nie psują CI). Gdy ktoś doda funkcję, zrobią się 'XPASS',
co sygnalizuje, że trzeba odznaczyć xfail. Poniżej są też testy PRZECHODZĄCE, które
dowodzą działających obejść (np. urlop = niedostępność, twardy dzień wolny).
"""

import pytest

import models
import factories
from algorithm import auto_assign

PON = factories.dzien(0)

pytestmark = pytest.mark.gap


def _p(stan, prac, data, godz="10:00"):
    return {
        "data": str(data),
        "stanowisko_id": stan.id,
        "pracownik_id": prac.id,
        "godz_od": godz,
        "rewir": None,
    }


def _zdolny(stan, data, dostepnosc=True, godz_od=None):
    p = factories.PracownikFactory()
    p.kwalifikacje = [stan]
    factories.Session.commit()
    factories.DyspozycjaFactory(pracownik=p, data=data, dostepnosc=dostepnosc, godz_od=godz_od)
    return p


# ── 1. Minimalny odpoczynek między zmianami ──────────────────────────────────
@pytest.mark.xfail(reason="Brak walidacji min. odpoczynku (np. 11h) między zmianami z różnych dni.", strict=False)
def test_minimalny_odpoczynek_miedzy_zmianami(admin_client):
    stan = factories.StanowiskoFactory()
    prac = factories.PracownikFactory()
    admin_client.post("/api/przydzialy", json=_p(stan, prac, factories.dzien(0), "22:00"))  # nocna
    r = admin_client.post("/api/przydzialy", json=_p(stan, prac, factories.dzien(1), "06:00"))  # rano
    assert r.status_code == 400, "OCZEKIWANE: za krótki odpoczynek (8h) powinien być odrzucony"


# ── 2. Limit w tygodniu ──────────────────────────────────────────────────────
@pytest.mark.xfail(reason="Brak limitu dni/godzin pracy w tygodniu — można obsadzić wszystkie 7 dni.", strict=False)
def test_limit_dni_pracy_w_tygodniu(admin_client):
    stan = factories.StanowiskoFactory()
    prac = factories.PracownikFactory()
    statusy = [
        admin_client.post("/api/przydzialy", json=_p(stan, prac, factories.dzien(i), "10:00")).status_code
        for i in range(7)
    ]
    assert any(s == 400 for s in statusy), "OCZEKIWANE: po przekroczeniu limitu kolejne zmiany odrzucone"


# ── 3. Limit w miesiącu ──────────────────────────────────────────────────────
@pytest.mark.xfail(reason="Brak limitu godzin w miesiącu.", strict=False)
def test_limit_godzin_w_miesiacu(admin_client):
    stan = factories.StanowiskoFactory()
    prac = factories.PracownikFactory()
    statusy = [
        admin_client.post("/api/przydzialy", json=_p(stan, prac, factories.dzien(i), "10:00")).status_code
        for i in range(28)
    ]
    assert any(s == 400 for s in statusy), "OCZEKIWANE: przekroczenie miesięcznego limitu = odrzucenie"


# ── 4. Urlopy ────────────────────────────────────────────────────────────────
@pytest.mark.xfail(reason="Brak pierwszoklasowej encji/endpointu urlopów (/api/urlopy).", strict=False)
def test_endpoint_urlopow_istnieje(admin_client):
    r = admin_client.get("/api/urlopy")
    assert r.status_code == 200, "OCZEKIWANE: dedykowany zasób urlopów"


def test_urlop_jako_zakres_niedostepnosci_dziala(db):
    """OBEJŚCIE (działa): urlop = niedostępność dzień po dniu — algorytm to respektuje."""
    sala = factories.StanowiskoFactory()
    p = factories.PracownikFactory()
    p.kwalifikacje = [sala]
    factories.Session.commit()
    tydzien = [factories.dzien(i) for i in range(5)]
    factories.ustaw_dyspozycyjnosc(p, tydzien, dostepnosc=False)  # "urlop"
    for d in tydzien:
        factories.WymaganieFactory(stanowisko=sala, data=d, liczba_osob=1)

    wynik = auto_assign(db, tydzien[0], tydzien[-1])
    assert db.query(models.PrzydzialZmiany).filter_by(pracownik_id=p.id).count() == 0
    assert len(wynik["niedobory"]) == 5


# ── 5. Preferowane dni wolne (twarda niedostępność) ──────────────────────────
def test_dzien_wolny_jest_twardy_nawet_przy_niedoborze(db):
    """Działa: zaznaczony dzień wolny jest twardy — algorytm woli niedobór niż go złamać.
    (Uwaga: brak rozróżnienia 'preferowany/miękki' vs 'twardy' — wszystko jest twarde.)"""
    sala = factories.StanowiskoFactory()
    p = factories.PracownikFactory()
    p.kwalifikacje = [sala]
    factories.Session.commit()
    factories.DyspozycjaFactory(pracownik=p, data=PON, dostepnosc=False)
    factories.WymaganieFactory(stanowisko=sala, data=PON, liczba_osob=1)

    wynik = auto_assign(db, PON, PON)
    assert wynik["przydzielone"] == 0
    assert len(wynik["niedobory"]) == 1


# ── 6. Detekcja nakładania (po godzinach) ────────────────────────────────────
@pytest.mark.xfail(reason="Brak detekcji nakładania — zmiany nie mają godziny końca.", strict=False)
def test_nakladajace_sie_zmiany_powinny_byc_odrzucone(admin_client):
    stan = factories.StanowiskoFactory()
    prac = factories.PracownikFactory()
    admin_client.post("/api/przydzialy", json=_p(stan, prac, PON, "10:00"))
    r = admin_client.post("/api/przydzialy", json=_p(stan, prac, PON, "11:00"))
    assert r.status_code == 400, "OCZEKIWANE: 11:00 nakłada się na trwającą zmianę od 10:00"


# ── 7. Ręczny przydział a kwalifikacje/dyspozycyjność ────────────────────────
@pytest.mark.xfail(reason="POST /api/przydzialy nie sprawdza kwalifikacji (tylko auto-assign).", strict=False)
def test_reczny_przydzial_wymaga_kwalifikacji(admin_client):
    stan = factories.StanowiskoFactory(nazwa="Kuchnia")
    prac = factories.PracownikFactory()  # BEZ kwalifikacji 'Kuchnia'
    r = admin_client.post("/api/przydzialy", json=_p(stan, prac, PON, "10:00"))
    assert r.status_code == 400, "OCZEKIWANE: brak kwalifikacji powinien blokować przydział"


@pytest.mark.xfail(reason="POST /api/przydzialy nie sprawdza dyspozycyjności (można obsadzić niedostępnego).", strict=False)
def test_reczny_przydzial_sprawdza_dyspozycyjnosc(admin_client):
    stan = factories.StanowiskoFactory()
    prac = factories.PracownikFactory()
    prac.kwalifikacje = [stan]
    factories.Session.commit()
    factories.DyspozycjaFactory(pracownik=prac, data=PON, dostepnosc=False)  # niedostępny
    r = admin_client.post("/api/przydzialy", json=_p(stan, prac, PON, "10:00"))
    assert r.status_code == 400, "OCZEKIWANE: niedostępny pracownik nie powinien być obsadzony ręcznie"
