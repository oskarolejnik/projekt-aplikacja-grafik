"""CEL 4 (część A) — ograniczenia faktycznie egzekwowane przez algorytm `auto_assign`
oraz logika wymiany danych z systemem zewnętrznym (imprezy -> wymagania).

Algorytm egzekwuje: kwalifikacje, dyspozycyjność (dostępność + 'dostępny od' <= start),
JEDNĄ zmianę na pracownika dziennie, stanowiska weekend-only, sprawiedliwy podział oraz
raport niedoborów. Tego właśnie tu dowodzimy. Ograniczenia, których aplikacja NIE ma
(min. odpoczynek, limit godzin, urlopy), są w test_constraint_gaps.py.
"""

from datetime import time

import pytest

import models
import factories
from algorithm import auto_assign, przelicz_imprezy_na_wymagania

pytestmark = pytest.mark.algorithm

PON = factories.dzien(0)   # poniedziałek (dzień roboczy)
WT = factories.dzien(1)
SR = factories.dzien(2)
SOB = factories.dzien(5)   # weekend


def pracownik_zdolny(stany, data, dostepnosc=True, godz_od=None):
    """Pracownik z kwalifikacjami (lista stanowisk) i dyspozycją na dany dzień."""
    p = factories.PracownikFactory()
    p.kwalifikacje = list(stany)
    factories.Session.commit()
    factories.DyspozycjaFactory(pracownik=p, data=data, dostepnosc=dostepnosc, godz_od=godz_od)
    return p


# ── Kwalifikacje ──────────────────────────────────────────────────────────────
def test_przydziela_tylko_wykwalifikowanych(db):
    sala = factories.StanowiskoFactory(nazwa="Sala")
    inne = factories.StanowiskoFactory(nazwa="Kuchnia")
    zdolny1 = pracownik_zdolny([sala], PON)
    zdolny2 = pracownik_zdolny([sala], PON)
    niezdolny = pracownik_zdolny([inne], PON)  # dostępny, ale bez kwalifikacji 'Sala'
    factories.WymaganieFactory(stanowisko=sala, data=PON, liczba_osob=1)

    wynik = auto_assign(db, PON, PON)

    assert wynik["przydzielone"] == 1
    przydzial = db.query(models.PrzydzialZmiany).one()
    assert przydzial.pracownik_id in {zdolny1.id, zdolny2.id}
    assert przydzial.pracownik_id != niezdolny.id


# ── Dyspozycyjność ────────────────────────────────────────────────────────────
def test_pomija_niedostepnych(db):
    sala = factories.StanowiskoFactory(nazwa="Sala")
    pracownik_zdolny([sala], PON, dostepnosc=False)  # zaznaczył: niedostępny
    factories.WymaganieFactory(stanowisko=sala, data=PON, liczba_osob=1)

    wynik = auto_assign(db, PON, PON)

    assert wynik["przydzielone"] == 0
    assert len(wynik["niedobory"]) == 1


def test_brak_rekordu_dyspozycji_oznacza_niedostepny(db):
    """Pracownik bez żadnej dyspozycji na dany dzień NIE jest brany pod uwagę."""
    sala = factories.StanowiskoFactory(nazwa="Sala")
    p = factories.PracownikFactory()
    p.kwalifikacje = [sala]
    factories.Session.commit()  # brak Dyspozycji!
    factories.WymaganieFactory(stanowisko=sala, data=PON, liczba_osob=1)

    wynik = auto_assign(db, PON, PON)
    assert wynik["przydzielone"] == 0


def test_dostepny_od_pozniej_niz_start_zmiany_odrzucony(db):
    """'Dostępny od 16:00' nie obsadzi zmiany startującej o 10:00."""
    sala = factories.StanowiskoFactory(nazwa="Sala")
    pracownik_zdolny([sala], PON, godz_od=time(16, 0))
    factories.WymaganieFactory(stanowisko=sala, data=PON, liczba_osob=1, godz_od=time(10, 0))

    wynik = auto_assign(db, PON, PON)
    assert wynik["przydzielone"] == 0
    assert len(wynik["niedobory"]) == 1


def test_dostepny_od_wczesniej_niz_start_zaakceptowany(db):
    sala = factories.StanowiskoFactory(nazwa="Sala")
    p = pracownik_zdolny([sala], PON, godz_od=time(8, 0))
    factories.WymaganieFactory(stanowisko=sala, data=PON, liczba_osob=1, godz_od=time(10, 0))

    wynik = auto_assign(db, PON, PON)
    assert wynik["przydzielone"] == 1
    assert db.query(models.PrzydzialZmiany).one().pracownik_id == p.id


# ── Jedna zmiana dziennie ─────────────────────────────────────────────────────
def test_jedna_zmiana_na_pracownika_dziennie(db):
    """Jedyny zdolny pracownik dostanie 1 zmianę, drugie wymaganie tego dnia = niedobór."""
    sala = factories.StanowiskoFactory(nazwa="Sala")
    bar = factories.StanowiskoFactory(nazwa="Bar")
    p = pracownik_zdolny([sala, bar], PON)
    factories.WymaganieFactory(stanowisko=sala, data=PON, liczba_osob=1)
    factories.WymaganieFactory(stanowisko=bar, data=PON, liczba_osob=1)

    wynik = auto_assign(db, PON, PON)

    assert wynik["przydzielone"] == 1, "auto_assign nie dubluje pracownika tego samego dnia"
    assert len(wynik["niedobory"]) == 1
    assert db.query(models.PrzydzialZmiany).filter_by(pracownik_id=p.id, data=PON).count() == 1


# ── Stanowiska weekend-only ───────────────────────────────────────────────────
def test_weekend_only_pomijane_w_dzien_roboczy(db):
    eventy = factories.StanowiskoFactory(nazwa="Eventy", tylko_weekend=True)
    pracownik_zdolny([eventy], PON)
    factories.WymaganieFactory(stanowisko=eventy, data=PON, liczba_osob=1)

    wynik = auto_assign(db, PON, PON)
    # Slot weekend-only w poniedziałek jest w ogóle pomijany: 0 przydziałów i 0 niedoborów.
    assert wynik["przydzielone"] == 0
    assert wynik["niedobory"] == []


def test_weekend_only_obsadzane_w_sobote(db):
    eventy = factories.StanowiskoFactory(nazwa="Eventy", tylko_weekend=True)
    pracownik_zdolny([eventy], SOB)
    factories.WymaganieFactory(stanowisko=eventy, data=SOB, liczba_osob=1)

    wynik = auto_assign(db, SOB, SOB)
    assert wynik["przydzielone"] == 1


# ── Sprawiedliwy podział ──────────────────────────────────────────────────────
def test_sprawiedliwy_podzial_zmian(db):
    """Dwóch zdolnych, cztery sloty (4 dni) -> po 2 zmiany każdy (balans)."""
    sala = factories.StanowiskoFactory(nazwa="Sala")
    dni = [factories.dzien(i) for i in range(4)]
    p1 = factories.PracownikFactory(); p1.kwalifikacje = [sala]
    p2 = factories.PracownikFactory(); p2.kwalifikacje = [sala]
    factories.Session.commit()
    for d in dni:
        factories.DyspozycjaFactory(pracownik=p1, data=d, dostepnosc=True)
        factories.DyspozycjaFactory(pracownik=p2, data=d, dostepnosc=True)
        factories.WymaganieFactory(stanowisko=sala, data=d, liczba_osob=1)

    auto_assign(db, dni[0], dni[-1])

    c1 = db.query(models.PrzydzialZmiany).filter_by(pracownik_id=p1.id).count()
    c2 = db.query(models.PrzydzialZmiany).filter_by(pracownik_id=p2.id).count()
    assert {c1, c2} == {2}, f"Oczekiwano 2+2, jest {c1}+{c2}"


# ── Niedobory personelu ───────────────────────────────────────────────────────
def test_niedobor_gdy_brak_personelu_na_wymaganie(db):
    """Wymaganie na 5 osób, tylko 2 zdolnych -> 2 przydziały + 3 niedobory."""
    sala = factories.StanowiskoFactory(nazwa="Sala")
    pracownik_zdolny([sala], PON)
    pracownik_zdolny([sala], PON)
    factories.WymaganieFactory(stanowisko=sala, data=PON, liczba_osob=5)

    wynik = auto_assign(db, PON, PON)

    assert wynik["przydzielone"] == 2
    assert len(wynik["niedobory"]) == 3
    assert all(n["powod"] == "Brak dostępnych pracowników" for n in wynik["niedobory"])
    assert wynik["niedobory"][0]["data"] == str(PON)


def test_niedobor_gdy_zero_wykwalifikowanych(db):
    sala = factories.StanowiskoFactory(nazwa="Sala")
    inne = factories.StanowiskoFactory(nazwa="Kuchnia")
    pracownik_zdolny([inne], PON)  # dostępny, ale do innego stanowiska
    factories.WymaganieFactory(stanowisko=sala, data=PON, liczba_osob=1)

    wynik = auto_assign(db, PON, PON)
    assert wynik["przydzielone"] == 0
    assert len(wynik["niedobory"]) == 1
    assert "Sala" in wynik["niedobory"][0]["stanowisko"]


# ── Współpraca z ręcznymi przydziałami ────────────────────────────────────────
def test_uwzglednia_istniejace_reczne_przydzialy(db):
    """Ręcznie wpisana zmiana jest liczona: auto-assign nie dubluje i zajmuje dzień."""
    sala = factories.StanowiskoFactory(nazwa="Sala")
    p = pracownik_zdolny([sala], PON)
    factories.PrzydzialFactory(stanowisko=sala, pracownik=p, data=PON, godz_od=None)
    factories.WymaganieFactory(stanowisko=sala, data=PON, liczba_osob=1)

    wynik = auto_assign(db, PON, PON)
    # Wymaganie już pokryte ręcznym przydziałem -> 0 nowych.
    assert wynik["przydzielone"] == 0
    assert db.query(models.PrzydzialZmiany).filter_by(data=PON).count() == 1


def test_trudniejsze_sloty_obsadzane_priorytetowo(db):
    """De-facto 'priorytet': slot o mniejszej liczbie kandydatów jest obsadzany pierwszy.
    Specjalista zna tylko 'Kuchnia' (deficytowe); uniwersalny zna 'Kuchnia' i 'Sala'.
    Algorytm powinien posłać specjalistę do kuchni, a uniwersalnego zostawić na salę."""
    kuchnia = factories.StanowiskoFactory(nazwa="Kuchnia")
    sala = factories.StanowiskoFactory(nazwa="Sala")
    specjalista = pracownik_zdolny([kuchnia], PON)
    uniwersalny = pracownik_zdolny([kuchnia, sala], PON)
    factories.WymaganieFactory(stanowisko=kuchnia, data=PON, liczba_osob=1)
    factories.WymaganieFactory(stanowisko=sala, data=PON, liczba_osob=1)

    wynik = auto_assign(db, PON, PON)

    assert wynik["przydzielone"] == 2 and wynik["niedobory"] == []
    kto_kuchnia = db.query(models.PrzydzialZmiany).filter_by(stanowisko_id=kuchnia.id).one().pracownik_id
    kto_sala = db.query(models.PrzydzialZmiany).filter_by(stanowisko_id=sala.id).one().pracownik_id
    assert kto_kuchnia == specjalista.id
    assert kto_sala == uniwersalny.id


# ═══════════════════════════════════════════════════════════════════════════════
# Wymiana danych z systemem zewnętrznym: imprezy (Excel) -> wymagania dnia
# ═══════════════════════════════════════════════════════════════════════════════
def _impreza(godzina="18:00", osoby=30, sala="R1"):
    return factories.ImprezaFactory.build(godzina=godzina, liczba_osob=osoby, sala=sala)


def test_impreza_start_pracy_dwie_godziny_wczesniej():
    out = przelicz_imprezy_na_wymagania([_impreza(godzina="18:00")])
    assert out[0]["godz_od"] == time(16, 0)


def test_impreza_start_nie_wczesniej_niz_10():
    out = przelicz_imprezy_na_wymagania([_impreza(godzina="11:00")])  # 11-2=9 -> limit 10:00
    assert out[0]["godz_od"] == time(10, 0)


def test_impreza_bledna_godzina_default_10():
    out = przelicz_imprezy_na_wymagania([_impreza(godzina="brak")])
    assert out[0]["godz_od"] == time(10, 0)


@pytest.mark.parametrize(
    "osoby,oczek",
    [(1, 1), (15, 1), (16, 2), (30, 2), (31, 3), (45, 3)],
)
def test_impreza_liczba_pracownikow_1_na_15(osoby, oczek):
    out = przelicz_imprezy_na_wymagania([_impreza(osoby=osoby, sala="R1")])
    assert out[0]["liczba_osob"] == oczek


def test_impreza_sala_specjalna_minimum_2():
    out = przelicz_imprezy_na_wymagania([_impreza(osoby=5, sala="R2Piw")])
    assert out[0]["liczba_osob"] == 2  # mimo 5 os. minimum 2 dla R2Piw/R2G


def test_impreza_oznaczona_jako_impreza_i_ma_rewir():
    out = przelicz_imprezy_na_wymagania([_impreza(sala="R1")])
    assert out[0]["jest_impreza"] is True
    assert out[0]["rewir"].startswith("IMPREZA:")
