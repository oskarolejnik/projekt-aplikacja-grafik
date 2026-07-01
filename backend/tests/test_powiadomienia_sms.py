"""Wpięcie SMS w potwierdzenie rezerwacji (Rec#7 krok 3) — best-effort, dodatkowy kanał."""

import datetime as dt

import main
import models


def _termin(**kw):
    baza = dict(data=dt.date(2026, 7, 1), nazwisko="Gość", rodzaj="stolik", kanal="online",
                status="rezerwacja", utworzono_at=dt.datetime(2026, 7, 1))
    baza.update(kw)
    return models.Termin(**baza)


def test_potwierdzenie_wysyla_sms_gdy_jest_telefon(db, monkeypatch):
    wyslane = {}
    monkeypatch.setattr(main.sms, "wyslij_sms", lambda numer, tresc: wyslane.update(sms=(numer, tresc)) or True)
    monkeypatch.setattr(main.mailer, "wyslij_email", lambda *a, **k: True)
    t = _termin(godz_od=dt.time(18, 0), telefon="600100200", email="g@example.com")
    db.add(t); db.commit(); db.refresh(t)

    main._wyslij_potwierdzenie_rezerwacji(db, t)
    assert "sms" in wyslane
    assert wyslane["sms"][0] == "600100200"
    assert "2026-07-01 18:00" in wyslane["sms"][1]


def test_potwierdzenie_bez_telefonu_nie_wola_sms(db, monkeypatch):
    licznik = {"n": 0}
    monkeypatch.setattr(main.sms, "wyslij_sms", lambda *a, **k: licznik.__setitem__("n", licznik["n"] + 1))
    monkeypatch.setattr(main.mailer, "wyslij_email", lambda *a, **k: True)
    t = _termin(email="g@example.com")   # bez telefonu
    db.add(t); db.commit(); db.refresh(t)

    main._wyslij_potwierdzenie_rezerwacji(db, t)
    assert licznik["n"] == 0             # brak telefonu → SMS nie jest wołany


def test_potwierdzenie_sms_nie_wywraca_gdy_blad(db, monkeypatch):
    # SMS jest best-effort — nawet gdy provider zawiedzie, potwierdzenie nie rzuca.
    monkeypatch.setattr(main.sms, "wyslij_sms", lambda *a, **k: False)
    monkeypatch.setattr(main.mailer, "wyslij_email", lambda *a, **k: True)
    t = _termin(godz_od=dt.time(12, 0), telefon="600100200", email="g@example.com")
    db.add(t); db.commit(); db.refresh(t)
    assert main._wyslij_potwierdzenie_rezerwacji(db, t) is True   # zwraca status maila, SMS best-effort
