"""Prywatność: pracownik NIE widzi nazwy klienta/imprezy — tylko salę.

Dotyczy dwóch miejsc:
  • /api/me/imprezy  — pole `klient` nie jest w ogóle wysyłane (jest `sala`),
  • /api/me/grafik   — rewir imprezy „IMPREZA: {klient} ({sala})" -> „Impreza ({sala})".
"""

from datetime import datetime

import main
import models
import factories
from auth import create_access_token


def _h(user):
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def test_me_imprezy_bez_klienta_z_sala(client, db):
    prac = factories.PracownikFactory()
    emp = factories.UserFactory(login="empriv", rola="employee", pracownik=prac)
    db.add(models.Impreza(
        data=factories.dzien(0), klient="Wesele Kowalski", sala="R1",
        godzina="18:00", liczba_osob=50, sciezka_pliku="x.xlsx",
    ))
    db.commit()
    r = client.get("/api/me/imprezy", headers=_h(emp),
                   params={"start": str(factories.dzien(0)), "end": str(factories.dzien(6))})
    assert r.status_code == 200
    row = r.json()[0]
    assert "klient" not in row          # nazwa klienta NIE wychodzi do pracownika
    assert "sciezka_pliku" not in row
    assert row["sala"] == "R1"


def test_rewir_dla_pracownika_ukrywa_klienta():
    assert main._rewir_dla_pracownika("IMPREZA: Kowalski (R1)") == "Impreza (R1)"
    assert main._rewir_dla_pracownika("IMPREZA: Nowak Anna (R2Piw)") == "Impreza (R2Piw)"
    assert main._rewir_dla_pracownika("IMPREZA: X (Brak)") == "Impreza"
    assert main._rewir_dla_pracownika("R3") == "R3"        # zwykly rewir bez zmian
    assert main._rewir_dla_pracownika(None) is None


def test_me_grafik_rewir_imprezy_bez_klienta(client, db):
    stan = factories.StanowiskoFactory(nazwa="Imprezy")
    prac = factories.PracownikFactory()
    emp = factories.UserFactory(login="empg", rola="employee", pracownik=prac)
    d = factories.dzien(0)
    db.add(models.PrzydzialZmiany(
        data=d, stanowisko_id=stan.id, pracownik_id=prac.id,
        godz_od=None, rewir="IMPREZA: Wesele Kowalski (R1)",
    ))
    db.add(models.PublikacjaGrafiku(start=d, koniec=factories.dzien(6), opublikowano_at=datetime.utcnow()))
    db.commit()
    r = client.get("/api/me/grafik", headers=_h(emp),
                   params={"start": str(d), "end": str(factories.dzien(6))})
    z = r.json()["zmiany"][0]
    assert "Kowalski" not in z["rewir"]
    assert z["rewir"] == "Impreza (R1)"
