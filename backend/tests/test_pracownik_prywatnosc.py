"""Prywatność: pracownik NIE widzi nazwy klienta/imprezy — tylko salę.

Dotyczy dwóch miejsc:
  • /api/me/imprezy  — pole `klient` nie jest w ogóle wysyłane (jest `sala`),
  • /api/me/grafik   — rewir imprezy „IMPREZA: {klient} ({sala})" -> „Impreza ({sala})".
"""

from datetime import date, datetime, time

import main
import models
import factories
from auth import create_access_token


def _h(user):
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def test_rezerwacje_stolik_pii_niedostepne_dla_pracownika(make_employee_client, admin_client, db):
    """Regresja (kolizja prefiksów w role_guard): pracownik NIE może pobrać /api/rezerwacje-stolik
    (pełne PII gościa: nazwisko/telefon/email), mimo że whitelist ma prefiks „/api/rezerwacje"
    (zagregowany, bez PII). Wcześniej startswith przepuszczał „/api/rezerwacje-stolik" → wyciek RODO.
    Admin widzi PII (200), pracownik dostaje 403, a zagregowany „/api/rezerwacje" pozostaje dostępny."""
    prac = factories.PracownikFactory()
    ce, _ = make_employee_client(prac)
    db.add(models.Termin(rodzaj="stolik", kanal="reczna", nazwisko="Klient Tajny",
                         telefon="600100200", email="tajny@example.com",
                         data=date.today(), status="rezerwacja"))
    db.commit()
    okno = {"start": str(date.today()), "end": str(date.today())}

    ra = admin_client.get("/api/rezerwacje-stolik", params=okno)
    assert ra.status_code == 200
    assert any(x.get("telefon") == "600100200" for x in ra.json()["rezerwacje"])

    rr = ce.get("/api/rezerwacje-stolik", params=okno)
    assert rr.status_code == 403                              # PII gościa chronione przed pracownikiem
    assert ce.get("/api/rezerwacje").status_code == 200        # zagregowany (bez PII) nadal dostępny


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


def test_me_grafik_wspolpracownicy_po_rewirze(client, db):
    """Na tym samym stanowisku współpracownik = TEN SAM rewir (niezależnie od godziny).
    Inny rewir na tej samej Sali → niewidoczny. Inne stanowisko (bez powiązania) → niewidoczny."""
    sala = factories.StanowiskoFactory(nazwa="Sala")
    bar = factories.StanowiskoFactory(nazwa="Bar")
    ja = factories.PracownikFactory(imie="Ja", nazwisko="Parter")
    ten_sam = factories.PracownikFactory(imie="Kolega", nazwisko="Parter")
    inny = factories.PracownikFactory(imie="Ktos", nazwisko="Pietro")
    barman = factories.PracownikFactory(imie="Barman", nazwisko="X")
    emp = factories.UserFactory(login="emprew", rola="employee", pracownik=ja)
    d = factories.dzien(0)
    db.add(models.PrzydzialZmiany(data=d, stanowisko_id=sala.id, pracownik_id=ja.id, godz_od=time(10, 0), rewir="Parter"))
    db.add(models.PrzydzialZmiany(data=d, stanowisko_id=sala.id, pracownik_id=ten_sam.id, godz_od=time(16, 0), rewir="Parter"))  # ten sam rewir, INNA godzina
    db.add(models.PrzydzialZmiany(data=d, stanowisko_id=sala.id, pracownik_id=inny.id, godz_od=time(10, 0), rewir="Pietro"))     # INNY rewir
    db.add(models.PrzydzialZmiany(data=d, stanowisko_id=bar.id, pracownik_id=barman.id, godz_od=time(10, 0), rewir="Parter"))    # inne stanowisko
    db.add(models.PublikacjaGrafiku(start=d, koniec=factories.dzien(6), opublikowano_at=datetime.utcnow()))
    db.commit()
    r = client.get("/api/me/grafik", headers=_h(emp), params={"start": str(d), "end": str(factories.dzien(6))})
    wsp = r.json()["zmiany"][0]["wspolpracownicy"]
    imiona = {w["imie"] for w in wsp}
    assert "Kolega Parter" in imiona       # ten sam rewir, inna godzina → widoczny
    assert "Ktos Pietro" not in imiona     # inny rewir → niewidoczny
    assert "Barman X" not in imiona        # inne stanowisko → niewidoczny
    kolega_w = next(w for w in wsp if w["imie"] == "Kolega Parter")
    assert kolega_w["godz_od"] == "16:00"  # godzina współpracownika dołączona


def test_me_grafik_stanowisko_widoczne_dla_wszystkich(client, db):
    """Stanowisko z flagą `widoczny_dla_wszystkich` (np. Menadżer) jest widoczne dla KAŻDEGO
    pracownika danego dnia — z nazwą stanowiska."""
    sala = factories.StanowiskoFactory(nazwa="Sala")
    menadzer = factories.StanowiskoFactory(nazwa="Menadżer", widoczny_dla_wszystkich=True)
    ja = factories.PracownikFactory(imie="Kelner", nazwisko="X")
    szef = factories.PracownikFactory(imie="Pan", nazwisko="Szef")
    emp = factories.UserFactory(login="empmen", rola="employee", pracownik=ja)
    d = factories.dzien(0)
    db.add(models.PrzydzialZmiany(data=d, stanowisko_id=sala.id, pracownik_id=ja.id, godz_od=time(10, 0), rewir="Parter"))
    db.add(models.PrzydzialZmiany(data=d, stanowisko_id=menadzer.id, pracownik_id=szef.id, godz_od=time(8, 0)))
    db.add(models.PublikacjaGrafiku(start=d, koniec=factories.dzien(6), opublikowano_at=datetime.utcnow()))
    db.commit()
    r = client.get("/api/me/grafik", headers=_h(emp), params={"start": str(d), "end": str(factories.dzien(6))})
    wsp = r.json()["zmiany"][0]["wspolpracownicy"]
    men = [w for w in wsp if w["imie"] == "Pan Szef"]
    assert men and men[0]["stanowisko"] == "Menadżer"   # menadżer widoczny + z nazwą stanowiska


def test_me_grafik_grupa_widocznosci_wzajemnie(client, db):
    """KOMP i Wydawka w tej samej grupie widzą się WZAJEMNIE; ktoś spoza grupy (Sala) — nie."""
    komp = factories.StanowiskoFactory(nazwa="KOMP", grupa_widocznosci="kuchnia-komp")
    wydawka = factories.StanowiskoFactory(nazwa="Wydawka", grupa_widocznosci="kuchnia-komp")
    sala = factories.StanowiskoFactory(nazwa="Sala")
    p_komp = factories.PracownikFactory(imie="Komp", nazwisko="Owy")
    p_wyd = factories.PracownikFactory(imie="Wyda", nazwisko="Wka")
    p_sala = factories.PracownikFactory(imie="Sal", nazwisko="Owy")
    emp_komp = factories.UserFactory(login="empkomp", rola="employee", pracownik=p_komp)
    emp_wyd = factories.UserFactory(login="empwyd", rola="employee", pracownik=p_wyd)
    d = factories.dzien(0)
    db.add(models.PrzydzialZmiany(data=d, stanowisko_id=komp.id, pracownik_id=p_komp.id, godz_od=time(10, 0)))
    db.add(models.PrzydzialZmiany(data=d, stanowisko_id=wydawka.id, pracownik_id=p_wyd.id, godz_od=time(12, 0)))
    db.add(models.PrzydzialZmiany(data=d, stanowisko_id=sala.id, pracownik_id=p_sala.id, godz_od=time(10, 0)))
    db.add(models.PublikacjaGrafiku(start=d, koniec=factories.dzien(6), opublikowano_at=datetime.utcnow()))
    db.commit()
    r1 = client.get("/api/me/grafik", headers=_h(emp_komp), params={"start": str(d), "end": str(factories.dzien(6))})
    im1 = {w["imie"] for w in r1.json()["zmiany"][0]["wspolpracownicy"]}
    assert "Wyda Wka" in im1 and "Sal Owy" not in im1   # KOMP widzi Wydawkę, nie Salę
    r2 = client.get("/api/me/grafik", headers=_h(emp_wyd), params={"start": str(d), "end": str(factories.dzien(6))})
    im2 = {w["imie"] for w in r2.json()["zmiany"][0]["wspolpracownicy"]}
    assert "Komp Owy" in im2                              # Wydawka widzi KOMP (wzajemnie)
