"""Slice 5c: prognoza obsady zasilana zabukowanymi rezerwacjami — floor przez max() (nie suma,
bo historia już zawiera zrealizowane rezerwacje = double counting). Domyka pętlę grafik↔rezerwacje."""

import datetime as dt

import models


def _rez(db, d, osoby, status="potwierdzona"):
    db.add(models.Termin(rodzaj="stolik", data=d, nazwisko="Gość", status=status, kanal="reczna",
                         zadatek=0.0, liczba_osob=osoby, utworzono_at=dt.datetime.utcnow(),
                         godz_od=dt.time(18, 0)))
    db.commit()


def test_prognoza_floor_rezerwacjami(admin_client, db):
    # brak historii → prognoza historyczna 0; 3 aktywne rezerwacje na pojutrze (10 osób)
    d = dt.date.today() + dt.timedelta(days=2)
    for osoby in (4, 4, 2):
        _rez(db, d, osoby)
    proj = admin_client.get("/api/prognoza-ruchu").json()["projekcja_7dni"]
    dzien = next(p for p in proj if p["data"] == str(d))
    assert dzien["rezerwacje_zabukowane"] == 3
    assert dzien["covery_zabukowane"] == 10
    assert dzien["zrodlo"] == "rezerwacje"           # 3 > prognoza 0 → floor z rezerwacji
    assert dzien["sugerowana_obsada"] >= 1


def test_odwolane_i_poza_oknem_nie_licza(admin_client, db):
    d = dt.date.today() + dt.timedelta(days=1)
    _rez(db, d, 4, status="odwolana")                # anulowana — nie liczona
    _rez(db, dt.date.today() + dt.timedelta(days=20), 6)   # poza oknem 7 dni
    proj = admin_client.get("/api/prognoza-ruchu").json()["projekcja_7dni"]
    dzien = next(p for p in proj if p["data"] == str(d))
    assert dzien["rezerwacje_zabukowane"] == 0 and dzien["covery_zabukowane"] == 0
    assert dzien["zrodlo"] == "historia"


def test_bez_rezerwacji_zachowuje_historie(admin_client):
    # regresja: bez rezerwacji projekcja ma nowe pola wyzerowane, źródło = historia
    proj = admin_client.get("/api/prognoza-ruchu").json()["projekcja_7dni"]
    assert all(p["rezerwacje_zabukowane"] == 0 and p["zrodlo"] == "historia" for p in proj)
    assert all("sugerowana_obsada" in p for p in proj)
