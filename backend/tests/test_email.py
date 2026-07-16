"""Wysyłka e-mail (mailer) + potwierdzenia rezerwacji — best-effort."""

from datetime import datetime

import mailer
import models


def _stolik(admin_client):
    return admin_client.post("/api/stoliki", json={"nazwa": "S1", "pojemnosc": 4}).json()


def test_email_niesk_noop():
    # Bez SMTP_* w env (conftest ich nie ustawia) → integracja off → no-op (False, bez wyjątku).
    assert mailer.wyslij_email("gosc@example.pl", "Temat", "Treść") is False


def test_email_bez_adresu_noop():
    assert mailer.wyslij_email("", "Temat", "Treść") is False


def test_resend_kolejkuje_bez_synchronicznej_wysylki(admin_client, db):
    st = _stolik(admin_client)
    rid = admin_client.post("/api/rezerwacje-stolik", json={"data": "2026-07-01", "godz_od": "18:00",
                            "stolik_id": st["id"], "liczba_osob": 2, "nazwisko": "A",
                            "email": "gosc@example.pl"}).json()["id"]
    now = datetime.utcnow()
    for row in db.query(models.RezerwacjaWiadomoscOutbox).filter_by(
        termin_id=rid,
        typ_zdarzenia="confirmation",
    ).all():
        row.stan = "sent"
        row.sent_at = now
        row.updated_at = now
    db.commit()
    r = admin_client.post(
        f"/api/rezerwacje-stolik/{rid}/wyslij-potwierdzenie",
        headers={
            "Idempotency-Key": "test-resend-email",
            "X-Confirm-Resend": "true",
        },
    )
    assert r.status_code == 200
    assert r.json()["queued"] == 1
    assert r.json()["messages"][0]["state"] == "queued"
    assert r.json()["messages"][0]["channel"] == "email"


def test_resend_bez_email_400(admin_client):
    st = _stolik(admin_client)
    rid = admin_client.post("/api/rezerwacje-stolik", json={"data": "2026-07-01", "godz_od": "12:00",
                            "stolik_id": st["id"], "liczba_osob": 2, "nazwisko": "B"}).json()["id"]
    assert admin_client.post(
        f"/api/rezerwacje-stolik/{rid}/wyslij-potwierdzenie",
        headers={"Idempotency-Key": "test-resend-without-contact"},
    ).status_code == 400


def test_email_wysylka_gdy_skonfigurowana(monkeypatch):
    # Ustaw komplet SMTP → integracja aktywna; zamockuj smtplib.SMTP, by nie wychodzić do sieci.
    monkeypatch.setenv("SMTP_HOST", "smtp.test")
    monkeypatch.setenv("SMTP_USER", "u@test")
    monkeypatch.setenv("SMTP_PASSWORD", "haslo")
    wyslane = {}

    class FakeSMTP:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self, *a, **k): pass
        def login(self, *a, **k): pass
        def send_message(self, msg): wyslane["to"] = msg["To"]; wyslane["subj"] = msg["Subject"]

    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    assert mailer.wyslij_email("gosc@example.pl", "Temat", "Treść") is True
    assert wyslane["to"] == "gosc@example.pl"
