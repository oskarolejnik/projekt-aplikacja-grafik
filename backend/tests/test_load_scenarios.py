"""Scenariusze pod dużym obciążeniem logicznym — realistyczna firma (15+ osób),
pełne tygodnie wymagań, przeciążenie i wydajność algorytmu. Sprawdzamy NIEZMIENNIKI
(invariants), które muszą zachodzić niezależnie od skali danych.
"""

import time as _time
from collections import Counter

import pytest

import models
import factories
from algorithm import auto_assign

pytestmark = pytest.mark.algorithm


def _niezmienniki(db):
    """Zwraca dane do asercji niezmienników grafiku."""
    przydzialy = db.query(models.PrzydzialZmiany).all()
    kwal = {p.id: {st.id for st in p.kwalifikacje} for p in db.query(models.Pracownik).all()}
    return przydzialy, kwal


def test_pelny_tydzien_realistyczna_firma(company, db):
    s = company["stanowiska"]
    tydzien = [factories.dzien(i) for i in range(7)]
    for w in company["pracownicy"]:
        factories.domyslna_dyspozycyjnosc_profilu(w, tydzien)

    for d in tydzien:
        factories.WymaganieFactory(stanowisko=s["sala"], data=d, liczba_osob=2)
        factories.WymaganieFactory(stanowisko=s["kuchnia"], data=d, liczba_osob=1)
        factories.WymaganieFactory(stanowisko=s["bar"], data=d, liczba_osob=1)
    for d in (factories.dzien(5), factories.dzien(6)):  # weekend: dodatkowe Eventy
        factories.WymaganieFactory(stanowisko=s["eventy"], data=d, liczba_osob=1)

    wynik = auto_assign(db, tydzien[0], tydzien[-1])
    przydzialy, kwal = _niezmienniki(db)

    assert wynik["przydzielone"] == len(przydzialy) > 0

    # NIEZMIENNIK 1: nikt nie ma dwóch zmian tego samego dnia
    per_day = Counter((a.pracownik_id, a.data) for a in przydzialy)
    assert all(v == 1 for v in per_day.values()), "Podwójne obsadzenie tego samego dnia!"

    # NIEZMIENNIK 2: każdy przydział zgodny z kwalifikacjami
    assert all(a.stanowisko_id in kwal[a.pracownik_id] for a in przydzialy)

    # NIEZMIENNIK 3: każdy przydzielony był tego dnia dostępny
    for a in przydzialy:
        dys = db.query(models.Dyspozycja).filter_by(pracownik_id=a.pracownik_id, data=a.data).first()
        assert dys is not None and dys.dostepnosc is True

    # NIEZMIENNIK 4: Eventy (weekend-only) obsadzane wyłącznie w sobotę/niedzielę
    for a in przydzialy:
        if a.stanowisko_id == s["eventy"].id:
            assert a.data.weekday() >= 5


def test_przeciazenie_generuje_niedobory_bez_bledu(company, db):
    """Ekstremalne zapotrzebowanie (50 osób) — algorytm obsadza ile może i raportuje resztę."""
    s = company["stanowiska"]
    d = factories.dzien(2)
    for w in company["pracownicy"]:
        factories.DyspozycjaFactory(pracownik=w["obj"], data=d, dostepnosc=True, godz_od=None)
    factories.WymaganieFactory(stanowisko=s["sala"], data=d, liczba_osob=50)

    wynik = auto_assign(db, d, d)

    zdolni = sum(1 for w in company["pracownicy"] if s["sala"] in w["obj"].kwalifikacje)
    assert wynik["przydzielone"] == zdolni, "Obsadza wszystkich zdolnych (1 zmiana/os./dzień)"
    assert len(wynik["niedobory"]) == 50 - zdolni


def test_idempotencja_ponownego_uruchomienia(company, db):
    """Drugie uruchomienie auto-assign na tym samym zakresie nie dubluje obsadzonych slotów."""
    s = company["stanowiska"]
    d = factories.dzien(3)
    for w in company["pracownicy"]:
        factories.DyspozycjaFactory(pracownik=w["obj"], data=d, dostepnosc=True, godz_od=None)
    factories.WymaganieFactory(stanowisko=s["sala"], data=d, liczba_osob=2)

    pierwszy = auto_assign(db, d, d)
    przed = db.query(models.PrzydzialZmiany).count()
    drugi = auto_assign(db, d, d)
    po = db.query(models.PrzydzialZmiany).count()

    assert pierwszy["przydzielone"] == 2
    assert drugi["przydzielone"] == 0, "Sloty już pokryte — brak nowych przydziałów"
    assert przed == po == 2


def test_wydajnosc_auto_assign_cztery_tygodnie(company, db):
    """Skala: 28 dni × 15+ osób × kilka stanowisk — kończy się w rozsądnym czasie."""
    s = company["stanowiska"]
    dni = [factories.dzien(i) for i in range(28)]
    for w in company["pracownicy"]:
        factories.ustaw_dyspozycyjnosc(w["obj"], dni, dostepnosc=True, godz_od=None)
    for d in dni:
        factories.WymaganieFactory(stanowisko=s["sala"], data=d, liczba_osob=2)
        factories.WymaganieFactory(stanowisko=s["kuchnia"], data=d, liczba_osob=1)
        factories.WymaganieFactory(stanowisko=s["bar"], data=d, liczba_osob=1)

    t0 = _time.perf_counter()
    wynik = auto_assign(db, dni[0], dni[-1])
    elapsed = _time.perf_counter() - t0

    assert wynik["przydzielone"] > 0
    assert elapsed < 5.0, f"auto_assign za wolny dla 4 tygodni: {elapsed:.2f}s"

    # Globalny niezmiennik na dużą skalę: brak podwójnych obsadzeń w żadnym dniu
    przydzialy = db.query(models.PrzydzialZmiany).all()
    per_day = Counter((a.pracownik_id, a.data) for a in przydzialy)
    assert all(v == 1 for v in per_day.values())
