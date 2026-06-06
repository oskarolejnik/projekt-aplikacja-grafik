"""Fabryki danych testowych (factory_boy + Faker) dla aplikacji grafikowej.

Mapują się 1:1 na realne modele ORM (`models.py`). Sesję SQLAlchemy podpina
`conftest.py` (ten sam silnik in-memory co aplikacja testowa), dzięki czemu dane
utworzone fabrykami są widoczne dla endpointów FastAPI (po commit).

Profile pracowników (Cel 1) odwzorowują realne sytuacje kadrowe:
  - student   — 1-2 kwalifikacje, dostępność popołudniami (godz_od), część dni wolnych,
  - etat      — 2-3 kwalifikacje, pełna dostępność (cały dzień),
  - manager   — „Zarządzanie" + 2 inne, pełna dostępność.
"""

from datetime import date, time, timedelta

import factory
from factory.alchemy import SQLAlchemyModelFactory
from sqlalchemy.orm import scoped_session, sessionmaker

import models
from auth import hash_password

# Sesja współdzielona przez fabryki. `bind` ustawia conftest.configure_factories().
Session = scoped_session(sessionmaker(autoflush=False, expire_on_commit=False))

# Stała data odniesienia: 2026-06-01 to PONIEDZIAŁEK, 06-06 sobota, 06-07 niedziela.
PONIEDZIALEK = date(2026, 6, 1)


def dzien(offset: int) -> date:
    """Dzień względem poniedziałku odniesienia (0=pon, 5=sob, 6=niedz)."""
    return PONIEDZIALEK + timedelta(days=offset)


# ─────────────────────────────────────────────────────────────────────────────
# Fabryki bazowe
# ─────────────────────────────────────────────────────────────────────────────
class BaseFactory(SQLAlchemyModelFactory):
    class Meta:
        abstract = True
        sqlalchemy_session = Session
        sqlalchemy_session_persistence = "commit"


class StanowiskoFactory(BaseFactory):
    class Meta:
        model = models.Stanowisko

    nazwa = factory.Sequence(lambda n: f"Stanowisko {n}")
    tylko_weekend = False


class PracownikFactory(BaseFactory):
    class Meta:
        model = models.Pracownik

    imie = factory.Faker("first_name", locale="pl_PL")
    nazwisko = factory.Faker("last_name", locale="pl_PL")
    aktywny = True


class UserFactory(BaseFactory):
    class Meta:
        model = models.User

    class Params:
        # Domyślne, znane hasło (spełnia walidator: litera+cyfra+znak specjalny, >=8).
        haslo = "Haslo123!"

    login = factory.Sequence(lambda n: f"konto{n:04d}")
    haslo_hash = factory.LazyAttribute(lambda o: hash_password(o.haslo))
    rola = "employee"
    aktywny = True
    pracownik = factory.SubFactory(PracownikFactory)


class PodkategoriaFactory(BaseFactory):
    class Meta:
        model = models.Podkategoria

    stanowisko = factory.SubFactory(StanowiskoFactory)
    nazwa = factory.Sequence(lambda n: f"Rewir {n}")
    godz_od = None


class WymaganieFactory(BaseFactory):
    """WymaganiaDnia nie ma relacji ORM do Stanowiska — używamy exclude + SelfAttribute."""

    class Meta:
        model = models.WymaganiaDnia
        exclude = ("stanowisko",)

    stanowisko = factory.SubFactory(StanowiskoFactory)
    stanowisko_id = factory.SelfAttribute("stanowisko.id")
    data = PONIEDZIALEK
    liczba_osob = 1
    godz_od = None
    rewir = None
    jest_impreza = False


class DyspozycjaFactory(BaseFactory):
    class Meta:
        model = models.Dyspozycja

    pracownik = factory.SubFactory(PracownikFactory)
    data = PONIEDZIALEK
    dostepnosc = True
    godz_od = None


class PrzydzialFactory(BaseFactory):
    class Meta:
        model = models.PrzydzialZmiany

    data = PONIEDZIALEK
    stanowisko = factory.SubFactory(StanowiskoFactory)
    pracownik = factory.SubFactory(PracownikFactory)
    godz_od = None
    rewir = None


class ImprezaFactory(BaseFactory):
    class Meta:
        model = models.Impreza

    data = date(2026, 6, 6)  # sobota
    klient = factory.Faker("company", locale="pl_PL")
    liczba_osob = 30
    godzina = "18:00"
    sala = "R1"
    sciezka_pliku = factory.Sequence(lambda n: f"/pliki/impreza_{n}.xlsx")


# ─────────────────────────────────────────────────────────────────────────────
# Typowe zmiany (Cel 3) — aplikacja modeluje zmianę przez godzinę startu (godz_od);
# nie ma osobnego typu/końca zmiany, więc „typ" oddajemy godziną rozpoczęcia.
# ─────────────────────────────────────────────────────────────────────────────
ZMIANA_PORANNA = time(6, 0)
ZMIANA_DZIENNA = time(10, 0)
ZMIANA_POPOLUDNIOWA = time(14, 0)
ZMIANA_WIECZORNA = time(18, 0)
ZMIANA_NOCNA = time(22, 0)


PROFILE_STUDENT = "student"
PROFILE_ETAT = "etat"
PROFILE_MANAGER = "manager"


def _emp(profile, kwalifikacje):
    p = PracownikFactory()
    p.kwalifikacje = list(kwalifikacje)
    Session.commit()
    return {"obj": p, "profile": profile, "kwalifikacje": list(kwalifikacje)}


def build_company():
    """Cel 1 + 2: stanowiska + >=15 pracowników o zróżnicowanych profilach i kwalifikacjach.

    Zwraca: {"stanowiska": {...}, "pracownicy": [ {obj, profile, kwalifikacje}, ... ]}
    """
    s = {
        "sala": StanowiskoFactory(nazwa="Obsługa sali"),
        "kuchnia": StanowiskoFactory(nazwa="Kuchnia"),
        "bar": StanowiskoFactory(nazwa="Bar"),
        "kasa": StanowiskoFactory(nazwa="Kasa"),
        "zarzadzanie": StanowiskoFactory(nazwa="Zarządzanie"),
        # Stanowisko aktywne wyłącznie w weekend (realny priorytet/ograniczenie w apce).
        "eventy": StanowiskoFactory(nazwa="Eventy", tylko_weekend=True),
    }

    pracownicy = []
    # 6 studentów — wąskie kwalifikacje (1-2), słabsza dyspozycyjność (dodawana osobno).
    student_kwal = [
        [s["sala"]],
        [s["bar"]],
        [s["kasa"]],
        [s["sala"], s["bar"]],
        [s["sala"], s["kasa"]],
        [s["bar"], s["kasa"]],
    ]
    for kw in student_kwal:
        pracownicy.append(_emp(PROFILE_STUDENT, kw))

    # 6 etatowców — szersze kwalifikacje (2-3).
    etat_kwal = [
        [s["sala"], s["kuchnia"]],
        [s["sala"], s["bar"], s["kasa"]],
        [s["kuchnia"], s["bar"]],
        [s["sala"], s["kuchnia"], s["bar"]],
        [s["kasa"], s["sala"]],
        [s["kuchnia"], s["kasa"], s["eventy"]],
    ]
    for kw in etat_kwal:
        pracownicy.append(_emp(PROFILE_ETAT, kw))

    # 3 managerów — „Zarządzanie" + dwa inne stanowiska.
    manager_kwal = [
        [s["zarzadzanie"], s["sala"], s["bar"]],
        [s["zarzadzanie"], s["kuchnia"], s["kasa"]],
        [s["zarzadzanie"], s["sala"], s["eventy"]],
    ]
    for kw in manager_kwal:
        pracownicy.append(_emp(PROFILE_MANAGER, kw))

    return {"stanowiska": s, "pracownicy": pracownicy}


def ustaw_dyspozycyjnosc(pracownik, dni, dostepnosc=True, godz_od=None):
    """Tworzy/aktualizuje Dyspozycję pracownika dla listy dni (lista `date`)."""
    out = []
    for d in dni:
        rec = (
            Session.query(models.Dyspozycja)
            .filter_by(pracownik_id=pracownik.id, data=d)
            .first()
        )
        if rec:
            rec.dostepnosc = dostepnosc
            rec.godz_od = godz_od
        else:
            rec = models.Dyspozycja(
                pracownik_id=pracownik.id, data=d, dostepnosc=dostepnosc, godz_od=godz_od
            )
            Session.add(rec)
        out.append(rec)
    Session.commit()
    return out


def domyslna_dyspozycyjnosc_profilu(wpis, tydzien):
    """Nadaje dyspozycyjność wg profilu na podany tydzień (lista 7 dat).

    - etat/manager: cały tydzień, cały dzień (godz_od=None),
    - student: tylko 3 wybrane dni, dostępny dopiero od 16:00 (mniejsza dyspozycyjność).
    """
    p = wpis["obj"]
    if wpis["profile"] in (PROFILE_ETAT, PROFILE_MANAGER):
        ustaw_dyspozycyjnosc(p, tydzien, dostepnosc=True, godz_od=None)
    else:  # student
        # dostępny w 3 dni od 16:00, w pozostałe niedostępny
        dostepne = tydzien[2:5]
        niedostepne = [d for d in tydzien if d not in dostepne]
        ustaw_dyspozycyjnosc(p, dostepne, dostepnosc=True, godz_od=time(16, 0))
        ustaw_dyspozycyjnosc(p, niedostepne, dostepnosc=False, godz_od=None)
