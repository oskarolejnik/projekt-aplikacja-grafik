"""Operacje na grafiku:
  • „Wyczyść tabelę" (DELETE /api/przydzialy) czyści TYLKO wskazany dział (obsługa/kuchnia),
    a nie oba grafiki naraz — wcześniej kasowało wszystko.
  • Auto-przydział TYLKO SZKICUJE: po ułożeniu cofa publikację tygodnia, więc zmiany nie idą
    od razu do obsługi (admin sprawdza i publikuje ręcznie).
"""

from datetime import datetime, date, timedelta

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


def _kwal(db, prac, *stanowiska):
    db.get(models.Pracownik, prac.id).kwalifikacje = [db.get(models.Stanowisko, s.id) for s in stanowiska]


def test_auto_przydzial_sala_nie_zabiera_jedynego_kandydata(admin_client, db):
    """Regresja #6: łatwy slot Sali NIE może zabrać jedynego kandydata trudniejszego slotu poza salą.
    W (Sala+Kuchnia), Z (tylko Sala); Sala=1, Kuchnia=1 → oba obsadzone (W→Kuchnia, Z→Sala), 0 niedoborów."""
    sala = factories.StanowiskoFactory(nazwa="Sala")
    kuchnia = factories.StanowiskoFactory(nazwa="Kuchnia")
    w = factories.PracownikFactory(dzial="obsluga")
    z = factories.PracownikFactory(dzial="obsluga")
    _kwal(db, w, sala, kuchnia)
    _kwal(db, z, sala)
    for pr in (w, z):
        db.add(models.Dyspozycja(pracownik_id=pr.id, data=DZIEN, dostepnosc=True))
    db.add(models.WymaganiaDnia(data=DZIEN, stanowisko_id=sala.id, liczba_osob=1))
    db.add(models.WymaganiaDnia(data=DZIEN, stanowisko_id=kuchnia.id, liczba_osob=1))
    db.commit()
    admin_client.post(f"/api/auto-assign?start={DZIEN}&end={DZIEN}")
    przy = {a.stanowisko_id: a.pracownik_id for a in db.query(models.PrzydzialZmiany).all()}
    assert przy.get(kuchnia.id) == w.id and przy.get(sala.id) == z.id   # oba obsadzone, bez niedoboru


def test_auto_przydzial_respektuje_limit_tygodnia(admin_client, db):
    """Regresja #7: auto-przydział nie łamie limitu dni/tydzień (domyślnie 6) — 7. dzień w tym samym
    tygodniu ISO zostaje nieobsadzony (jak odrzuciłby ręczny przydział)."""
    mon = date(2026, 7, 6)
    mon = mon - timedelta(days=mon.weekday())          # poniedziałek
    sala = factories.StanowiskoFactory(nazwa="Sala")
    p = factories.PracownikFactory(dzial="obsluga")
    _kwal(db, p, sala)
    for i in range(7):
        d = mon + timedelta(days=i)
        db.add(models.Dyspozycja(pracownik_id=p.id, data=d, dostepnosc=True))
        db.add(models.WymaganiaDnia(data=d, stanowisko_id=sala.id, liczba_osob=1))
    db.commit()
    admin_client.post(f"/api/auto-assign?start={mon}&end={mon + timedelta(days=6)}")
    assert db.query(models.PrzydzialZmiany).filter_by(pracownik_id=p.id).count() == 6   # nie 7


def test_auto_przydzial_duplikat_wymagania_pelna_obsada(admin_client, db):
    """Regresja #9: dwa wiersze WymaganiaDnia o TYM SAMYM kluczu nie odejmują wielokrotnie tego samego
    istniejącego przydziału. 2+2 wymagane, 1 ręczny → automat dodaje 3 (razem 4, nie 3)."""
    sala = factories.StanowiskoFactory(nazwa="Sala")
    prac = [factories.PracownikFactory(dzial="obsluga") for _ in range(4)]
    for pr in prac:
        _kwal(db, pr, sala)
        db.add(models.Dyspozycja(pracownik_id=pr.id, data=DZIEN, dostepnosc=True))
    db.add(models.PrzydzialZmiany(data=DZIEN, stanowisko_id=sala.id, pracownik_id=prac[0].id))   # 1 ręczny
    db.add(models.WymaganiaDnia(data=DZIEN, stanowisko_id=sala.id, liczba_osob=2))
    db.add(models.WymaganiaDnia(data=DZIEN, stanowisko_id=sala.id, liczba_osob=2))               # duplikat klucza
    db.commit()
    admin_client.post(f"/api/auto-assign?start={DZIEN}&end={DZIEN}")
    assert db.query(models.PrzydzialZmiany).filter_by(data=DZIEN, stanowisko_id=sala.id).count() == 4
