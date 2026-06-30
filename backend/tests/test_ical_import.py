# -*- coding: utf-8 -*-
"""Testy importu imprez z iCloud: parser (.ics, jednostkowe) + endpoint (integracyjne)."""
from datetime import date

import ical_import
import models
import factories


# .ics zbudowany na realnych przykładach z kalendarza imprez.
# Uwaga: w wartości ICS znak nowej linii to '\n' (backslash+n) -> w źródle Pythona '\\n'.
# Foldowanie linii: fizyczne złamanie + wiodąca spacja (CRLF + ' ').
_LINIE = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Apple Inc.//iOS 18//EN",
    # VTIMEZONE ma własny DTSTART — musi zostać zignorowany (nie jest wydarzeniem):
    "BEGIN:VTIMEZONE",
    "TZID:Europe/Warsaw",
    "BEGIN:STANDARD",
    "DTSTART:19701025T030000",
    "TZOFFSETFROM:+0200",
    "TZOFFSETTO:+0100",
    "END:STANDARD",
    "END:VTIMEZONE",
    # A) Komunia, bez lokalizacji, opis z telefonem/zadatkiem/e-mailem (wielolinijkowy):
    "BEGIN:VEVENT",
    "UID:event-A@icloud",
    "SUMMARY:P. Jarkowski",
    "DTSTART;TZID=Europe/Warsaw:20270501T170000",
    "DTEND;TZID=Europe/Warsaw:20270501T180000",
    "DESCRIPTION:Komunia\\, 15 osób\\, 609 228 774\\n500 zł\\njarkowska.magdalena@gmai",
    " l.com",  # <- kontynuacja zwiniętej linii (folding)
    "END:VEVENT",
    # B) Wesele, para bez „P." w tytule, lokalizacja z adresem, dwa telefony:
    "BEGIN:VEVENT",
    "UID:event-B@icloud",
    "SUMMARY:Mateusz Przybyła Czerwonka Weronika",
    "DTSTART;TZID=Europe/Warsaw:20260627T150000",
    "LOCATION:R2Piw\\nMikołowska\\n44-177 Gierałtowice\\nPolska",
    "DESCRIPTION:Wesele\\, 80 os\\, 514 379 113\\, 797 362 678\\n2000 zł",
    "END:VEVENT",
    # C) Bez typu i bez zadatku, z VALARM (musi być pominięty), lokalizacja R2P:
    "BEGIN:VEVENT",
    "UID:event-C@icloud",
    "SUMMARY:P. Kuczera Janusz",
    "DTSTART;TZID=Europe/Warsaw:20260620T120000",
    "LOCATION:R2P\\nMikołowska\\n44-177 Gierałtowice\\nPolska",
    "DESCRIPTION:30 osób\\, 607 865 326",
    "BEGIN:VALARM",
    "ACTION:DISPLAY",
    "TRIGGER:-PT30M",
    "DESCRIPTION:Przypomnienie",  # NIE może nadpisać opisu wydarzenia
    "END:VALARM",
    "END:VEVENT",
    # D) Całodniowe (VALUE=DATE) — bierzemy samą datę:
    "BEGIN:VEVENT",
    "UID:event-D@icloud",
    "SUMMARY:P. Nowak",
    "DTSTART;VALUE=DATE:20260815",
    "DESCRIPTION:Chrzciny\\, 25 osób\\, 600 100 200\\n300 zł",
    "END:VEVENT",
    "END:VCALENDAR",
]
SAMPLE_ICS = "\r\n".join(_LINIE) + "\r\n"


def test_parsuj_ics_liczba_eventow():
    ev = ical_import.parsuj_ics(SAMPLE_ICS)
    assert len(ev) == 4  # VTIMEZONE zignorowany


def test_folding_i_pola_event_a():
    rec = {r["uid"]: r for r in ical_import.wczytaj_imprezy_z_ics(SAMPLE_ICS)}["event-A@icloud"]
    assert rec["data"] == date(2027, 5, 1)
    assert rec["nazwisko"] == "Jarkowski"
    assert rec["typ"] == "komunia"
    assert rec["liczba_osob"] == 15
    assert rec["telefon"] == "609 228 774"
    assert rec["zadatek"] == 500.0
    assert rec["sala"] is None
    # zwinięta linia złożona w całość: e-mail jest kompletny w notatce
    assert "jarkowska.magdalena@gmail.com" in rec["notatka"]


def test_wesele_para_i_lokalizacja():
    rec = {r["uid"]: r for r in ical_import.wczytaj_imprezy_z_ics(SAMPLE_ICS)}["event-B@icloud"]
    assert rec["data"] == date(2026, 6, 27)
    assert rec["nazwisko"] == "Mateusz Przybyła Czerwonka Weronika"  # brak „P." -> bez zmian
    assert rec["typ"] == "wesele"
    assert rec["liczba_osob"] == 80
    assert rec["telefon"] == "514 379 113"   # pierwszy z dwóch numerów
    assert rec["zadatek"] == 2000.0
    assert rec["sala"] == "R2Piw"            # sam kod sali, bez adresu


def test_brak_typu_i_zadatku_plus_valarm():
    rec = {r["uid"]: r for r in ical_import.wczytaj_imprezy_z_ics(SAMPLE_ICS)}["event-C@icloud"]
    assert rec["nazwisko"] == "Kuczera Janusz"
    assert rec["typ"] is None
    assert rec["liczba_osob"] == 30
    assert rec["telefon"] == "607 865 326"
    assert rec["zadatek"] == 0.0
    assert rec["sala"] == "R2P"
    assert rec["notatka"] == "30 osób, 607 865 326"  # opis VALARM nie nadpisał opisu wydarzenia


def test_caly_dzien_value_date():
    rec = {r["uid"]: r for r in ical_import.wczytaj_imprezy_z_ics(SAMPLE_ICS)}["event-D@icloud"]
    assert rec["data"] == date(2026, 8, 15)
    assert rec["typ"] == "chrzciny"
    assert rec["liczba_osob"] == 25


def test_honoryfikatyw_nie_obcina_imienia():
    assert ical_import._wyczysc_nazwisko("Paweł Nowak") == "Paweł Nowak"
    assert ical_import._wyczysc_nazwisko("P.Golda") == "Golda"
    assert ical_import._wyczysc_nazwisko("P. Jarkowski") == "Jarkowski"
    assert ical_import._wyczysc_nazwisko("Państwo Młodzi") == "Młodzi"


def test_zadatek_ze_spacja_tysiecy():
    assert ical_import._wykryj_zadatek("zaliczka 1 500 zł") == 1500.0
    assert ical_import._wykryj_zadatek("brak kwoty") == 0.0


# ── CZĘŚĆ INTEGRACYJNA: endpoint POST /api/imprezy/import-ics ─────────────────

def test_import_ics_tworzy_termin_i_impreze(admin_client, db):
    factories.StanowiskoFactory(nazwa="Imprezy")
    r = admin_client.post("/api/imprezy/import-ics", json={"ics": SAMPLE_ICS})
    assert r.status_code == 200
    body = r.json()
    assert body["dodano_terminy"] == 4
    assert body["dodano_imprezy"] == 4
    assert body["pominieto"] == 0
    # Termin „Jarkowski" poprawnie zmapowany z notatek
    t = db.query(models.Termin).filter_by(ical_uid="event-A@icloud").one()
    assert t.nazwisko == "Jarkowski"
    assert t.typ == "komunia"
    assert t.liczba_osob == 15
    assert t.telefon == "609 228 774"
    assert t.zadatek == 500.0
    assert t.status == "rezerwacja"
    # Sparowana Impreza istnieje, godzina celowo „Brak"
    imp = db.query(models.Impreza).filter_by(sciezka_pliku="ical:event-A@icloud").one()
    assert imp.klient == "Jarkowski"
    assert imp.liczba_osob == 15
    assert imp.godzina == "Brak"


def test_import_ics_generuje_wymagania_obsady(admin_client, db):
    factories.StanowiskoFactory(nazwa="Imprezy")
    admin_client.post("/api/imprezy/import-ics", json={"ics": SAMPLE_ICS})
    wym = db.query(models.WymaganiaDnia).filter_by(jest_impreza=True).all()
    assert len(wym) >= 1
    # wesele 2026-06-27 (80 osób) ma policzone wymaganie obsady
    assert any(w.data == date(2026, 6, 27) for w in wym)


def test_import_ics_tylko_dodaje_nie_nadpisuje(admin_client, db):
    factories.StanowiskoFactory(nazwa="Imprezy")
    admin_client.post("/api/imprezy/import-ics", json={"ics": SAMPLE_ICS})
    # Ręczna edycja w aplikacji
    t = db.query(models.Termin).filter_by(ical_uid="event-A@icloud").one()
    t.nazwisko = "ZMIENIONE RECZNIE"
    t.liczba_osob = 99
    db.commit()
    # Ponowny import tego samego pliku — istniejące pomijamy
    body = admin_client.post("/api/imprezy/import-ics", json={"ics": SAMPLE_ICS}).json()
    assert body["dodano_terminy"] == 0
    assert body["pominieto"] == 4
    assert db.query(models.Termin).filter_by(ical_uid="event-A@icloud").count() == 1  # brak duplikatu
    t2 = db.query(models.Termin).filter_by(ical_uid="event-A@icloud").one()
    assert t2.nazwisko == "ZMIENIONE RECZNIE"   # ręczna zmiana zachowana
    assert t2.liczba_osob == 99


def test_import_ics_dopina_zadatek_ze_skrzynki(admin_client, db):
    # KP w skrzynce: komunia p.Jarkowski na 2027-05-01 (data eventu A)
    db.add(models.KpZadatek(id="kp-1", kwota=500.0, opis="Zadatek komunia p.Jarkowski 01.05.2027",
                            data=date(2026, 6, 14), nazwisko="Jarkowski", data_imprezy=date(2027, 5, 1)))
    db.commit()
    admin_client.post("/api/imprezy/import-ics", json={"ics": SAMPLE_ICS})
    z = db.get(models.KpZadatek, "kp-1")
    t = db.query(models.Termin).filter_by(ical_uid="event-A@icloud").one()
    assert z.termin_id == t.id   # auto-dopięty do nowo zaimportowanego terminu


def test_import_ics_edycja_terminu_aktualizuje_obsade(admin_client, db):
    factories.StanowiskoFactory(nazwa="Imprezy")
    admin_client.post("/api/imprezy/import-ics", json={"ics": SAMPLE_ICS})
    t = db.query(models.Termin).filter_by(ical_uid="event-C@icloud").one()  # Kuczera, 30 osób
    admin_client.put(f"/api/terminy/{t.id}", json={
        "data": "2026-06-20", "nazwisko": t.nazwisko, "typ": t.typ,
        "liczba_osob": 60, "telefon": t.telefon, "sala": t.sala,
        "notatka": t.notatka, "status": "rezerwacja", "zadatek": 0,
    })
    imp = db.query(models.Impreza).filter_by(sciezka_pliku="ical:event-C@icloud").one()
    assert imp.liczba_osob == 60   # sparowana Impreza poszła za ręczną korektą


def test_import_ics_usuniecie_terminu_kasuje_impreze(admin_client, db):
    factories.StanowiskoFactory(nazwa="Imprezy")
    admin_client.post("/api/imprezy/import-ics", json={"ics": SAMPLE_ICS})
    t = db.query(models.Termin).filter_by(ical_uid="event-C@icloud").one()
    admin_client.delete(f"/api/terminy/{t.id}")
    assert db.query(models.Impreza).filter_by(sciezka_pliku="ical:event-C@icloud").count() == 0


def test_import_ics_pusty_400(admin_client):
    assert admin_client.post("/api/imprezy/import-ics", json={"ics": "   "}).status_code == 400


def test_import_ics_wymaga_admina(make_employee_client):
    prac = factories.PracownikFactory()
    c, _ = make_employee_client(prac)
    assert c.post("/api/imprezy/import-ics", json={"ics": SAMPLE_ICS}).status_code == 403


def test_import_ics_bez_tokenu_401(client):
    assert client.post("/api/imprezy/import-ics", json={"ics": SAMPLE_ICS}).status_code == 401
