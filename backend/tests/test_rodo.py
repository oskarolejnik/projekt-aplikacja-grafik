"""RODO/GDPR: eksport (art. 15/20), anonimizacja gościa (art. 17) i retencja (art. 5 ust.1 e).
Admin-only; dopasowanie gościa po odszyfrowanym telefonie (jak CRM)."""

from datetime import date, datetime, timedelta
import json

import models
import reservation_service
from sms import _normalizuj_numer

TEL = "600 100 200"
KLUCZ = _normalizuj_numer(TEL)


def _termin(db, *, data, nazwisko="Kowalski", telefon=TEL, status="rezerwacja", rodzaj="stolik", notatka="VIP"):
    t = models.Termin(data=data, nazwisko=nazwisko, telefon=telefon, status=status, rodzaj=rodzaj, notatka=notatka)
    db.add(t); db.commit(); db.refresh(t)
    return t


def test_eksport_gosc(admin_client, db):
    _termin(db, data=date.today())
    _termin(db, data=date.today() - timedelta(days=30), status="odbyla")
    r = admin_client.get("/api/rodo/eksport-gosc", params={"klucz": KLUCZ})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["liczba_rekordow"] == 2
    assert any(w["telefon"] == TEL for w in body["rezerwacje"])
    audit = db.query(models.AuditLog).filter_by(akcja="rodo_eksport_gosc").one()
    assert audit.zasob.startswith("guest_ref:")
    assert len(audit.zasob) == len("guest_ref:") + 64
    assert KLUCZ not in audit.zasob
    # Nieznany klucz → 404.
    assert admin_client.get("/api/rodo/eksport-gosc", params={"klucz": "nieistnieje"}).status_code == 404


def test_anonimizuj_gosc(admin_client, db):
    t1 = _termin(db, data=date.today())
    t2 = _termin(db, data=date.today() - timedelta(days=10), status="odbyla")
    teraz = datetime.now()
    payload = {"nazwisko": "Kowalski", "telefon": TEL, "notatka": "VIP"}
    idem = reservation_service.begin_idempotency(
        db,
        operation="reservation.create.manual:v1",
        raw_key="rodo-replay-key",
        payload=payload,
        secret="rodo-test-secret",
        now=teraz,
    )
    reservation_service.complete_idempotency(
        idem.record,
        response={"id": t1.id, **payload},
        http_status=201,
        termin_id=t1.id,
        now=teraz,
    )
    db.add(models.WiadomoscImprezy(termin_id=t1.id, autor="klient", tresc="mój numer 600100200",
                                   utworzono_at=datetime.now()))
    db.commit()
    db.expunge(idem.record)
    r = admin_client.post("/api/rodo/anonimizuj-gosc", json={"klucz": KLUCZ})
    assert r.status_code == 200 and r.json()["zanonimizowano"] == 2, r.text
    for tid in (t1.id, t2.id):
        t = db.get(models.Termin, tid)
        db.refresh(t)
        assert t.nazwisko == "[anonimizacja RODO]" and t.telefon is None and t.notatka is None
    # Wątek portalu (z PII) usunięty.
    assert db.query(models.WiadomoscImprezy).filter_by(termin_id=t1.id).count() == 0
    # Zaszyfrowany wynik idempotencji też zawierał PII; po anonimizacji nie wolno go odtworzyć.
    assert db.query(models.RezerwacjaIdempotencja).filter_by(termin_id=t1.id).count() == 0
    replay = reservation_service.begin_idempotency(
        db,
        operation="reservation.create.manual:v1",
        raw_key="rodo-replay-key",
        payload=payload,
        secret="rodo-test-secret",
        now=teraz,
    )
    assert replay.replayed is False
    assert replay.response is None
    db.rollback()
    audits = db.query(models.ReservationAudit).order_by(models.ReservationAudit.id).all()
    assert len(audits) == 2
    assert all(a.action == "edit" and a.reason == "guest_request" for a in audits)
    assert all(set(a.diff["pii_changed"]) == {"nazwisko", "notatka", "telefon"} for a in audits)
    encoded = json.dumps([a.diff for a in audits], ensure_ascii=False)
    assert "Kowalski" not in encoded and TEL not in encoded and "VIP" not in encoded
    access_audit = db.query(models.AuditLog).filter_by(akcja="rodo_anonimizuj_gosc").one()
    assert access_audit.zasob.startswith("guest_ref:")
    assert KLUCZ not in access_audit.zasob


def test_retencja_anonimizuje_stare_zamkniete(admin_client, db):
    stary = _termin(db, data=date.today() - timedelta(days=800), status="odbyla")   # ~2,2 roku
    swiezy = _termin(db, data=date.today() - timedelta(days=30), status="odbyla")
    r = admin_client.post("/api/rodo/retencja?miesiace=12")
    assert r.status_code == 200, r.text
    assert r.json()["zanonimizowano"] >= 1
    assert db.get(models.Termin, stary.id).nazwisko == "[anonimizacja RODO]"   # stary → anonim
    assert db.get(models.Termin, swiezy.id).nazwisko == "Kowalski"             # świeży → bez zmian
    audit = db.query(models.ReservationAudit).filter_by(termin_id=stary.id).one()
    assert audit.action == "edit" and audit.reason == "system_automation"


def test_rodo_wymaga_admina(client):
    """Bez tokenu admina RODO jest niedostępne (role_guard)."""
    assert client.get("/api/rodo/eksport-gosc", params={"klucz": KLUCZ}).status_code == 401
