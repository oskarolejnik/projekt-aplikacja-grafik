"""CEL 1 — Baza sztucznych użytkowników (Mock Data).

Co najmniej 15 pracowników o zróżnicowanych profilach: studenci (mniejsza
dyspozycyjność), etatowcy (pełna dostępność), managerowie. Sprawdzamy liczność,
rozkład profili, kwalifikacje oraz że dane są realnie zapisane i widoczne przez API.
"""

from collections import Counter

import models
import factories
from factories import PROFILE_STUDENT, PROFILE_ETAT, PROFILE_MANAGER


def test_co_najmniej_15_pracownikow(company, db):
    assert len(company["pracownicy"]) >= 15
    assert db.query(models.Pracownik).count() >= 15


def test_rozklad_profili(company):
    licznik = Counter(p["profile"] for p in company["pracownicy"])
    assert licznik[PROFILE_STUDENT] >= 5, "Powinno być kilku studentów"
    assert licznik[PROFILE_ETAT] >= 5, "Powinno być kilku etatowców"
    assert licznik[PROFILE_MANAGER] >= 2, "Powinno być kilku managerów"


def test_kazdy_pracownik_ma_kwalifikacje(company):
    for wpis in company["pracownicy"]:
        assert len(wpis["obj"].kwalifikacje) >= 1, "Każdy ma min. 1 kwalifikację"


def test_profile_roznia_sie_szerokoscia_kwalifikacji(company):
    """Studenci węziej (1-2), etatowcy/managerowie szerzej (>=2); manager zna Zarządzanie."""
    zarzadzanie = company["stanowiska"]["zarzadzanie"]
    for wpis in company["pracownicy"]:
        n = len(wpis["obj"].kwalifikacje)
        if wpis["profile"] == PROFILE_STUDENT:
            assert 1 <= n <= 2
        elif wpis["profile"] == PROFILE_ETAT:
            assert n >= 2
        elif wpis["profile"] == PROFILE_MANAGER:
            assert n >= 2
            assert zarzadzanie in wpis["obj"].kwalifikacje


def test_faker_generuje_zroznicowane_nazwiska(company):
    nazwiska = [w["obj"].nazwisko for w in company["pracownicy"]]
    # Faker pl_PL — oczekujemy realnej różnorodności (nie wszyscy tacy sami).
    assert len(set(nazwiska)) >= len(nazwiska) - 2


def test_pracownicy_widoczni_przez_api(company, admin_client):
    r = admin_client.get("/api/pracownicy")
    assert r.status_code == 200
    dane = r.json()
    assert len(dane) >= 15
    # API zwraca kwalifikacje jako obiekty stanowisk
    assert all("kwalifikacje" in p for p in dane)
    assert any(len(p["kwalifikacje"]) >= 2 for p in dane)


def test_dyspozycyjnosc_wg_profilu(company, db):
    """Student ma mniejszą dyspozycyjność (mniej dni + dostępny dopiero od 16:00),
    etatowiec/manager — pełną (cały dzień)."""
    tydzien = [factories.dzien(i) for i in range(7)]
    for wpis in company["pracownicy"]:
        factories.domyslna_dyspozycyjnosc_profilu(wpis, tydzien)

    student = next(w for w in company["pracownicy"] if w["profile"] == PROFILE_STUDENT)
    etatowiec = next(w for w in company["pracownicy"] if w["profile"] == PROFILE_ETAT)

    dys_student = db.query(models.Dyspozycja).filter_by(pracownik_id=student["obj"].id).all()
    dys_etat = db.query(models.Dyspozycja).filter_by(pracownik_id=etatowiec["obj"].id).all()

    dostepne_student = [d for d in dys_student if d.dostepnosc]
    dostepne_etat = [d for d in dys_etat if d.dostepnosc]

    assert len(dostepne_student) < len(dostepne_etat), "Student dostępny w mniej dni"
    assert all(d.godz_od is not None for d in dostepne_student), "Student dostępny od konkretnej godziny"
    assert all(d.godz_od is None for d in dostepne_etat), "Etatowiec dostępny cały dzień"
