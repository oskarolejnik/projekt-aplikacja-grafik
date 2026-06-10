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
