"""Napiwki — pula dnia dzielona między obsługę sali (/api/napiwki + /api/me/napiwki)."""

from datetime import date

import factories
import models

D = date(2026, 7, 10)


def _sala_z_godzinami(db, godziny):
    """Stanowisko Sala + pracownicy z przydziałem D i odbiciem RCP na podane godziny.
    godziny: {imie: godziny|None}. Zwraca listę pracowników w kolejności."""
    sala = factories.StanowiskoFactory(nazwa="Sala")
    prac = []
    for i, (imie, godz) in enumerate(godziny.items()):
        p = factories.PracownikFactory(imie=imie, nazwisko="X")
        factories.PrzydzialFactory(pracownik=p, stanowisko=sala, data=D)
        if godz is not None:
            db.add(models.OdbicieRcp(rcp_id=f"r{i}", imie_nazwisko=f"{imie} X", pracownik_id=p.id,
                                     data=D, godziny=godz))
        prac.append(p)
    db.commit()
    return prac


def test_podzial_wg_godzin(admin_client, db):
    _sala_z_godzinami(db, {"Ala": 6.0, "Bartek": 2.0})
    r = admin_client.put(f"/api/napiwki?data={D}", json={"kwota": 100, "sposob": "godziny"}).json()
    kwoty = {x["pracownik"]: x["kwota"] for x in r["podzial"]}
    assert kwoty["Ala X"] == 75.0 and kwoty["Bartek X"] == 25.0
    assert round(sum(x["kwota"] for x in r["podzial"]), 2) == 100.0
    assert r["suma_godzin"] == 8.0


def test_podzial_rowno(admin_client, db):
    _sala_z_godzinami(db, {"Ala": 6.0, "Bartek": 2.0})
    r = admin_client.put(f"/api/napiwki?data={D}", json={"kwota": 100, "sposob": "rowno"}).json()
    assert all(x["kwota"] == 50.0 for x in r["podzial"])


def test_brak_godzin_fallback_rowno(admin_client, db):
    _sala_z_godzinami(db, {"Ala": None, "Bartek": None})   # przydział bez odbicia RCP
    r = admin_client.put(f"/api/napiwki?data={D}", json={"kwota": 100, "sposob": "godziny"}).json()
    assert all(x["kwota"] == 50.0 for x in r["podzial"])   # brak godzin → po równo


def test_podzial_grosze_dokladnie(admin_client, db):
    _sala_z_godzinami(db, {"Ala": 1.0, "Bartek": 1.0, "Celina": 1.0})
    r = admin_client.put(f"/api/napiwki?data={D}", json={"kwota": 100, "sposob": "rowno"}).json()
    assert round(sum(x["kwota"] for x in r["podzial"]), 2) == 100.0   # 33.34 + 33.33 + 33.33


def test_pracownik_widzi_swoje_napiwki(admin_client, make_employee_client, db):
    a, _b = _sala_z_godzinami(db, {"Ala": 6.0, "Bartek": 2.0})
    admin_client.put(f"/api/napiwki?data={D}", json={"kwota": 100, "sposob": "godziny"})
    ca, _ = make_employee_client(a)
    r = ca.get(f"/api/me/napiwki?start={D}&end={D}").json()
    assert r["suma"] == 75.0 and len(r["dni"]) == 1 and r["dni"][0]["kwota"] == 75.0


def test_pracownik_nie_ma_dostepu_do_zapisu(make_employee_client, db):
    p = factories.PracownikFactory()
    ce, _ = make_employee_client(p)
    assert ce.put(f"/api/napiwki?data={D}", json={"kwota": 50}).status_code == 403
    assert ce.get(f"/api/napiwki?data={D}").status_code == 403
