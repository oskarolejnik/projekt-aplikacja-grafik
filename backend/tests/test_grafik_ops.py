"""Operacje na grafiku:
  • „Wyczyść tabelę" (DELETE /api/przydzialy) czyści TYLKO wskazany dział (obsługa/kuchnia),
    a nie oba grafiki naraz — wcześniej kasowało wszystko.
  • Auto-przydział TYLKO SZKICUJE: po ułożeniu cofa publikację tygodnia, więc zmiany nie idą
    od razu do obsługi (admin sprawdza i publikuje ręcznie).
"""

from datetime import datetime

import models
import factories

DZIEN = factories.dzien(0)
KONIEC = factories.dzien(6)


def _para_obsluga_kuchnia(db):
    sala = factories.StanowiskoFactory(nazwa="Sala")
    kuchnia = factories.StanowiskoFactory(nazwa="Kuchnia")
    obs = factories.PracownikFactory(dzial="obsluga")
    kuch = factories.PracownikFactory(dzial="kuchnia")
    factories.PrzydzialFactory(stanowisko=sala, pracownik=obs, data=DZIEN)
    factories.PrzydzialFactory(stanowisko=kuchnia, pracownik=kuch, data=DZIEN)
    return obs, kuch


def test_wyczysc_dzial_obsluga_nie_rusza_kuchni(admin_client, db):
    obs, kuch = _para_obsluga_kuchnia(db)
    r = admin_client.delete(f"/api/przydzialy?start={DZIEN}&end={KONIEC}&dzial=obsluga")
    assert r.status_code == 204
    pozostale = db.query(models.PrzydzialZmiany).all()
    assert len(pozostale) == 1
    assert pozostale[0].pracownik_id == kuch.id   # kuchnia ocalała


def test_wyczysc_dzial_kuchnia_nie_rusza_obslugi(admin_client, db):
    obs, kuch = _para_obsluga_kuchnia(db)
    admin_client.delete(f"/api/przydzialy?start={DZIEN}&end={KONIEC}&dzial=kuchnia")
    pozostale = db.query(models.PrzydzialZmiany).all()
    assert len(pozostale) == 1
    assert pozostale[0].pracownik_id == obs.id     # obsługa ocalała


def test_wyczysc_bez_dzialu_czysci_wszystko(admin_client, db):
    """Bez parametru dzial — czyści wszystko (zachowanie wsteczne / kompatybilność)."""
    _para_obsluga_kuchnia(db)
    admin_client.delete(f"/api/przydzialy?start={DZIEN}&end={KONIEC}")
    assert db.query(models.PrzydzialZmiany).count() == 0


def test_auto_przydzial_cofa_publikacje(admin_client, db):
    """Auto-przydział TYLKO szkicuje: cofa publikację tygodnia (zmiany nie idą do obsługi)."""
    db.add(models.PublikacjaGrafiku(start=DZIEN, koniec=KONIEC, opublikowano_at=datetime.utcnow()))
    db.commit()
    assert db.query(models.PublikacjaGrafiku).count() == 1
    r = admin_client.post(f"/api/auto-assign?start={DZIEN}&end={KONIEC}")
    assert r.status_code == 200
    assert db.query(models.PublikacjaGrafiku).count() == 0   # publikacja cofnięta


def test_auto_przydzial_priorytet_sali(admin_client, db):
    """Sala ma PRIORYTET: pracownik moze isc na Sale ALBO Bar (1 zmiana/dzien) — auto-przydzial
    wstawia go na Sale, nie na Bar."""
    sala = factories.StanowiskoFactory(nazwa="Sala")
    bar = factories.StanowiskoFactory(nazwa="Bar")
    p = factories.PracownikFactory(dzial="obsluga")
    pp = db.get(models.Pracownik, p.id)
    pp.kwalifikacje = [db.get(models.Stanowisko, sala.id), db.get(models.Stanowisko, bar.id)]
    db.add(models.Dyspozycja(pracownik_id=p.id, data=DZIEN, dostepnosc=True))      # caly dzien
    db.add(models.WymaganiaDnia(data=DZIEN, stanowisko_id=sala.id, liczba_osob=1))
    db.add(models.WymaganiaDnia(data=DZIEN, stanowisko_id=bar.id, liczba_osob=1))
    db.commit()
    admin_client.post(f"/api/auto-assign?start={DZIEN}&end={DZIEN}")
    przy = db.query(models.PrzydzialZmiany).filter_by(pracownik_id=p.id).all()
    assert len(przy) == 1
    assert przy[0].stanowisko_id == sala.id   # priorytet Sali
