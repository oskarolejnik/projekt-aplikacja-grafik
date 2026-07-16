"""Wpięcie SMS w transakcyjny outbox potwierdzeń rezerwacji."""

import datetime as dt

import models
import reservation_communication as communication


def _termin(**kw):
    baza = dict(data=dt.date(2026, 7, 1), nazwisko="Gość", rodzaj="stolik", kanal="online",
                status="rezerwacja", kanal_komunikacji="auto",
                utworzono_at=dt.datetime(2026, 7, 1))
    baza.update(kw)
    return models.Termin(**baza)


def test_potwierdzenie_kolejkuje_sms_gdy_wybrano_sms(db, monkeypatch):
    licznik = {"n": 0}
    monkeypatch.setattr(
        communication.sms,
        "dostarcz_sms",
        lambda *a, **k: licznik.__setitem__("n", licznik["n"] + 1),
    )
    t = _termin(
        godz_od=dt.time(18, 0),
        telefon="600100200",
        email="g@example.com",
        kanal_komunikacji="sms",
    )
    db.add(t); db.commit(); db.refresh(t)

    rows = communication.enqueue_reservation(db, t, "confirmation")
    assert len(rows) == 1
    assert rows[0].kanal == "sms"
    assert rows[0].odbiorca == "600100200"
    assert "2026-07-01 o 18:00" in rows[0].tresc
    assert licznik["n"] == 0


def test_potwierdzenie_bez_telefonu_nie_kolejkuje_sms(db):
    t = _termin(email="g@example.com", kanal_komunikacji="sms")
    db.add(t); db.commit(); db.refresh(t)

    assert communication.enqueue_reservation(db, t, "confirmation") == []


def test_awaria_sms_nie_jest_wykonywana_w_transakcji_rezerwacji(db, monkeypatch):
    def provider_failure(*args, **kwargs):
        raise OSError("provider offline")

    monkeypatch.setattr(communication.sms, "dostarcz_sms", provider_failure)
    t = _termin(
        godz_od=dt.time(12, 0),
        telefon="600100200",
        email="g@example.com",
        kanal_komunikacji="sms",
    )
    db.add(t); db.commit(); db.refresh(t)

    rows = communication.enqueue_reservation(db, t, "confirmation")
    db.commit()
    assert rows[0].stan == "queued"
