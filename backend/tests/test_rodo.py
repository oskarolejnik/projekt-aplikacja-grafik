"""RODO/GDPR: eksport (art. 15/20), anonimizacja gościa (art. 17) i retencja (art. 5 ust.1 e).
Admin-only; dopasowanie gościa po odszyfrowanym telefonie (jak CRM)."""

from datetime import date, datetime, time, timedelta
import hashlib
import hmac
import json
import os
import threading
from time import monotonic

import maintenance
import main
import models
import reservation_communication as communication
import reservation_audit
import reservation_service
from crm_identity import hash_key, reservation_fallback_hash
from deps import get_lokal_config, utcnow_naive
from sms import _normalizuj_numer

TEL = "600 100 200"
KLUCZ = _normalizuj_numer(TEL)


def _termin(db, *, data, nazwisko="Kowalski", telefon=TEL, status="rezerwacja", rodzaj="stolik", notatka="VIP"):
    t = models.Termin(data=data, nazwisko=nazwisko, telefon=telefon, status=status, rodzaj=rodzaj, notatka=notatka)
    db.add(t); db.commit(); db.refresh(t)
    return t


def _override_audit(db, termin, *, note="Poufna decyzja operatora"):
    audit = models.ReservationAudit(
        created_at=utcnow_naive(),
        reservation_ref=reservation_audit.reservation_reference(termin),
        termin_id=termin.id,
        actor_kind="system",
        actor_user_id=None,
        actor_login=None,
        action="override",
        reason="other",
        diff={
            "changes": {},
            "pii_changed": [],
            "override": {
                "violations": [{
                    "rule": "party_max",
                    "code": "PARTY_SIZE_ABOVE_MAX",
                    "scope": {"type": "global", "sala_id": None, "kanal": None},
                    "source": {"type": "override", "id": 1},
                    "observed": 6,
                    "limit": 4,
                    "projected": 6,
                }],
            },
        },
    )
    db.add(audit)
    db.flush()
    context = models.ReservationOverrideContext(
        audit_id=audit.id,
        reason_code="operational_decision",
        note=note,
    )
    db.add(context)
    db.commit()
    db.refresh(context)
    return audit, context


def _zgoda(
    db,
    *,
    now,
    termin_id=None,
    waitlist_id=None,
    sensitive=True,
    retention_until=None,
):
    zgoda = models.RezerwacjaZgodaPubliczna(
        termin_id=termin_id,
        waitlist_id=waitlist_id,
        notice_version="privacy-v1",
        notice_ack_at=now,
        marketing=False,
        marketing_version="marketing-v1",
        marketing_at=now,
        sensitive=sensitive,
        sensitive_version="sensitive-v1" if sensitive else None,
        sensitive_at=now if sensitive else None,
        sensitive_data="alergia na orzechy" if sensitive else None,
        retention_until=retention_until or now + timedelta(days=365),
        ip_hash="i" * 64,
        created_at=now,
    )
    db.add(zgoda)
    return zgoda


def test_eksport_gosc(admin_client, db):
    current = _termin(db, data=date.today())
    _override_audit(db, current, note="Gość poprosił o wyjątek")
    _termin(db, data=date.today() - timedelta(days=30), status="odbyla")
    r = admin_client.post("/api/rodo/eksport-gosc", json={"klucz": KLUCZ})
    assert r.headers["cache-control"] == "private, no-store"
    assert "authorization" in {
        part.strip().casefold() for part in r.headers["vary"].split(",")
    }
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["liczba_rekordow"] == 2
    assert any(w["telefon"] == TEL for w in body["rezerwacje"])
    exported_audit = body["prywatnosc"]["audyty_rezerwacji"][0]
    assert exported_audit["powod"] == "other"
    assert exported_audit["kod_powodu_nadpisania"] == "operational_decision"
    assert exported_audit["notatka_nadpisania"] == "Gość poprosił o wyjątek"
    assert admin_client.get(
        "/api/rodo/eksport-gosc", params={"klucz": KLUCZ},
    ).status_code == 404
    audit = db.query(models.AuditLog).filter_by(akcja="rodo_eksport_gosc").one()
    assert audit.zasob.startswith("guest_ref:")
    assert len(audit.zasob) == len("guest_ref:") + 64
    assert KLUCZ not in audit.zasob
    # Nieznany klucz → 404.
    assert admin_client.post(
        "/api/rodo/eksport-gosc", json={"klucz": "nieistnieje"},
    ).status_code == 404


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
    db.add(models.ProfilGoscia(
        klucz_hash=hash_key(KLUCZ),
        nazwisko="Kowalski",
        alergie="orzechy",
        notatka="Poufny profil gościa",
        utworzono_at=datetime.now(),
    ))
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
    assert db.query(models.ProfilGoscia).filter_by(klucz_hash=hash_key(KLUCZ)).count() == 0
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


def test_anonimizacja_usuwa_rezerwacyjny_fallback_profilu_crm(admin_client, db):
    termin = _termin(
        db,
        data=date.today(),
        nazwisko="Bez Kontaktu",
        telefon=None,
        notatka="Notatka rezerwacji",
    )
    db.add(models.ProfilGoscia(
        klucz_hash=reservation_fallback_hash(termin.id),
        nazwisko="Bez Kontaktu",
        alergie="orzechy",
        notatka="Poufna notatka profilu",
        vip=True,
        utworzono_at=datetime.now(),
    ))
    db.commit()

    response = admin_client.post(
        "/api/rodo/anonimizuj-gosc",
        json={"klucz": "bez kontaktu"},
    )

    assert response.status_code == 200, response.text
    db.expire_all()
    assert db.query(models.ProfilGoscia).count() == 0
    profile = admin_client.get(f"/api/crm/rezerwacje/{termin.id}/profil").json()
    assert profile["profil"] is None
    assert profile["nazwisko"] == "[anonimizacja RODO]"
    assert "orzechy" not in str(profile)
    assert "Poufna notatka profilu" not in str(profile)


def test_rodo_waitlista_eksportuje_wybory_i_czysci_pii(admin_client, db):
    now = datetime.now()
    attended_at = now + timedelta(hours=2)
    wpis = models.ListaOczekujacych(
        data=date.today(),
        godz_od=time(18, 0),
        liczba_osob=4,
        nazwisko="Kowalski",
        telefon=TEL,
        email="gosc@example.com",
        notatka="Stolik przy oknie",
        status="oczekuje",
        utworzono_at=now,
        kanal="online",
        token="surowy-token-waitlisty",
        create_key_hash="k" * 64,
        create_request_fingerprint="f" * 64,
        demand_reason_code="resource_occupied",
        demand_resource_kind="table_or_combination",
        attended_at=attended_at,
    )
    db.add(wpis)
    db.flush()
    _zgoda(db, now=now, waitlist_id=wpis.id)
    db.commit()

    response = admin_client.post(
        "/api/rodo/eksport-gosc", json={"klucz": KLUCZ},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["liczba_rezerwacji"] == 0
    assert body["liczba_wpisow_waitlisty"] == 1
    exported_waitlist = body["lista_oczekujacych"][0]
    assert exported_waitlist["status"] == "oczekuje"
    assert exported_waitlist["demand_reason_code"] == "resource_occupied"
    assert exported_waitlist["demand_resource_kind"] == "table_or_combination"
    assert exported_waitlist["attended_at"] == attended_at.isoformat()
    consent = body["prywatnosc"]["zgody"][0]
    assert consent["wlasciciel_typ"] == "waitlista"
    assert consent["marketing"] is False
    assert consent["sensitive"] is True
    assert consent["sensitive_data"] == "alergia na orzechy"
    encoded = response.text
    assert "surowy-token-waitlisty" not in encoded
    assert "i" * 64 not in encoded
    assert all(secret_name not in encoded for secret_name in (
        "ip_hash", "token_hash", "session_hash",
    ))
    assert "k" * 64 not in encoded
    assert "f" * 64 not in encoded

    response = admin_client.post(
        "/api/rodo/anonimizuj-gosc", json={"klucz": KLUCZ},
    )

    assert response.status_code == 200, response.text
    assert response.json()["zanonimizowano_waitlista"] == 1
    db.expire_all()
    stored = db.get(models.ListaOczekujacych, wpis.id)
    assert stored.data == date.today()
    assert stored.liczba_osob == 4
    assert stored.status == "oczekuje"
    assert stored.nazwisko == "[anonimizacja RODO]"
    assert stored.telefon is None
    assert stored.email is None
    assert stored.notatka is None
    assert stored.token is None
    assert stored.create_key_hash is None
    assert stored.create_request_fingerprint is None
    assert stored.demand_reason_code == "resource_occupied"
    assert stored.demand_resource_kind == "table_or_combination"
    assert stored.attended_at == attended_at
    assert db.query(models.RezerwacjaZgodaPubliczna).count() == 0


def test_rodo_rezerwacji_nie_ujawnia_hashy_i_usuwa_publiczne_sekrety(admin_client, db):
    now = datetime.now()
    termin = _termin(db, data=date.today())
    termin.token_potwierdzenia = "stary-surowy-token"
    stolik = models.Stolik(nazwa="R1", pojemnosc=4, aktywny=True, kolejnosc=0)
    db.add(stolik)
    db.flush()
    _zgoda(db, now=now, termin_id=termin.id)
    db.add(models.RezerwacjaTokenZarzadzania(
        termin_id=termin.id,
        token_hash="t" * 64,
        scopes=["view", "data:export"],
        expires_at=now + timedelta(days=1),
        created_at=now,
    ))
    hold = models.RezerwacjaPublicznyHold(
        token_hash="h" * 64,
        session_hash="s" * 64,
        ip_hash="p" * 64,
        state="consumed",
        data=date.today(),
        godz_od=time(18, 0),
        godz_do=time(20, 0),
        liczba_osob=4,
        stolik_id=stolik.id,
        stoliki_dodatkowe=[],
        allocation_snapshot={},
        bufor_min=15,
        expires_at=now + timedelta(minutes=15),
        created_at=now,
        consumed_at=now,
        termin_id=termin.id,
    )
    db.add(hold)
    db.flush()
    db.add(models.RezerwacjaStolikClaim(
        public_hold_id=hold.id,
        stolik_id=stolik.id,
        data=date.today(),
        minute=18 * 60,
        expires_at=now + timedelta(minutes=15),
        created_at=now,
    ))
    db.commit()

    exported = admin_client.post(
        "/api/rodo/eksport-gosc", json={"klucz": KLUCZ},
    )

    assert exported.status_code == 200, exported.text
    privacy = exported.json()["prywatnosc"]
    assert privacy["dostepy_zarzadzania"][0]["zakresy"] == ["view", "data:export"]
    assert privacy["holdy_publiczne"][0]["state"] == "consumed"
    assert privacy["holdy_publiczne"][0]["liczba_claimow"] == 1
    assert all(secret not in exported.text for secret in (
        "t" * 64, "h" * 64, "s" * 64, "p" * 64, "stary-surowy-token",
    ))

    anonymized = admin_client.post(
        "/api/rodo/anonimizuj-gosc", json={"klucz": KLUCZ},
    )

    assert anonymized.status_code == 200, anonymized.text
    db.expire_all()
    assert db.get(models.Termin, termin.id).token_potwierdzenia is None
    assert db.query(models.RezerwacjaZgodaPubliczna).count() == 0
    assert db.query(models.RezerwacjaTokenZarzadzania).count() == 0
    assert db.query(models.RezerwacjaPublicznyHold).count() == 0
    assert db.query(models.RezerwacjaStolikClaim).count() == 0


def test_retencja_anonimizuje_stare_zamkniete(admin_client, db):
    stary = _termin(db, data=date.today() - timedelta(days=800), status="odbyla")   # ~2,2 roku
    _old_override_audit, old_context = _override_audit(db, stary)
    swiezy = _termin(db, data=date.today() - timedelta(days=30), status="odbyla")
    db.add(models.ProfilGoscia(
        klucz_hash=hash_key(KLUCZ),
        nazwisko="Kowalski",
        alergie="orzechy",
        utworzono_at=datetime.now(),
    ))
    db.commit()
    r = admin_client.post("/api/rodo/retencja?miesiace=12")
    assert r.status_code == 200, r.text
    assert r.json()["zanonimizowano"] >= 1
    assert db.get(models.Termin, stary.id).nazwisko == "[anonimizacja RODO]"   # stary → anonim
    assert db.get(models.Termin, swiezy.id).nazwisko == "Kowalski"             # świeży → bez zmian
    assert db.query(models.ProfilGoscia).filter_by(
        klucz_hash=hash_key(KLUCZ),
    ).one().alergie == "orzechy"
    audit = db.query(models.ReservationAudit).filter_by(
        termin_id=stary.id, action="edit",
    ).one()
    assert audit.action == "edit" and audit.reason == "system_automation"
    db.refresh(old_context)
    assert old_context.note is None
    assert old_context.reason_code == "operational_decision"


def test_anonimization_and_hard_delete_erase_override_note_before_fk_detach(
    admin_client, db,
):
    anonymized = _termin(
        db,
        data=date.today(),
        nazwisko="Anon Override",
        telefon="700 800 901",
    )
    _audit, anon_context = _override_audit(
        db, anonymized, note="Anonimizowana poufna notatka",
    )
    response = admin_client.post(
        "/api/rodo/anonimizuj-gosc",
        json={"klucz": _normalizuj_numer("700 800 901")},
    )
    assert response.status_code == 200, response.text
    db.expire_all()
    assert db.get(models.ReservationOverrideContext, anon_context.id).note is None

    deleted = _termin(
        db,
        data=date.today() + timedelta(days=1),
        nazwisko="Delete Override",
        telefon="700 800 902",
        status="potwierdzona",
    )
    deleted_audit, deleted_context = _override_audit(
        db, deleted, note="Kasowana poufna notatka",
    )
    deleted_id = deleted.id
    response = admin_client.delete(f"/api/rezerwacje-stolik/{deleted_id}")
    assert response.status_code == 204, response.text
    db.expire_all()
    assert db.get(models.Termin, deleted_id) is None
    preserved_audit = db.get(models.ReservationAudit, deleted_audit.id)
    assert preserved_audit.termin_id is None
    preserved_context = db.get(
        models.ReservationOverrideContext, deleted_context.id,
    )
    assert preserved_context.note is None
    assert preserved_context.reason_code == "operational_decision"


def test_retencja_z_configu_czysci_stare_dane_i_zachowuje_aktywny_hold(admin_client, db):
    now = utcnow_naive()
    cfg = get_lokal_config(db)
    cfg.rezerwacje_retencja_dni = 60
    stary = _termin(db, data=date.today() - timedelta(days=90), status="odbyla")
    swiezy = _termin(db, data=date.today() - timedelta(days=40), status="odbyla")
    stara_waitlista = models.ListaOczekujacych(
        data=date.today() - timedelta(days=90),
        godz_od=time(18, 0),
        liczba_osob=2,
        nazwisko="Stara Waitlista",
        telefon="700100200",
        email="stara@example.com",
        notatka="dane wrazliwe",
        status="anulowano",
        utworzono_at=now - timedelta(days=90),
        kanal="online",
        token="stary-token-waitlisty",
    )
    swieza_waitlista = models.ListaOczekujacych(
        data=date.today() - timedelta(days=40),
        godz_od=time(19, 0),
        liczba_osob=3,
        nazwisko="Swieza Waitlista",
        telefon="700100201",
        status="zaakceptowano",
        utworzono_at=now - timedelta(days=40),
        kanal="reczna",
    )
    stolik = models.Stolik(nazwa="R-retencja", pojemnosc=6, aktywny=True, kolejnosc=0)
    db.add_all([stara_waitlista, swieza_waitlista, stolik])
    db.flush()
    _zgoda(db, now=now - timedelta(days=90), termin_id=stary.id)
    _zgoda(db, now=now - timedelta(days=90), waitlist_id=stara_waitlista.id)
    db.add(models.RezerwacjaTokenZarzadzania(
        termin_id=swiezy.id,
        token_hash="x" * 64,
        scopes=["view"],
        expires_at=now - timedelta(hours=1),
        created_at=now - timedelta(days=1),
    ))
    aktywny_hold = models.RezerwacjaPublicznyHold(
        token_hash="a" * 64,
        session_hash="b" * 64,
        ip_hash="c" * 64,
        state="active",
        data=date.today() + timedelta(days=1),
        godz_od=time(18, 0),
        godz_do=time(20, 0),
        liczba_osob=4,
        stolik_id=stolik.id,
        stoliki_dodatkowe=[],
        allocation_snapshot={},
        bufor_min=15,
        expires_at=now + timedelta(minutes=15),
        created_at=now,
    )
    stary_dt = now - timedelta(days=90)
    zwolniony_hold = models.RezerwacjaPublicznyHold(
        token_hash="d" * 64,
        session_hash="e" * 64,
        ip_hash="f" * 64,
        state="released",
        data=date.today() - timedelta(days=90),
        godz_od=time(18, 0),
        godz_do=time(20, 0),
        liczba_osob=2,
        stolik_id=stolik.id,
        stoliki_dodatkowe=[],
        allocation_snapshot={},
        bufor_min=0,
        expires_at=stary_dt + timedelta(minutes=15),
        created_at=stary_dt,
        released_at=stary_dt + timedelta(minutes=20),
    )
    db.add_all([aktywny_hold, zwolniony_hold])
    db.flush()
    aktywny_hold_id = aktywny_hold.id
    zwolniony_hold_id = zwolniony_hold.id
    db.add_all([
        models.RezerwacjaStolikClaim(
            public_hold_id=aktywny_hold.id,
            stolik_id=stolik.id,
            data=aktywny_hold.data,
            minute=18 * 60,
            expires_at=aktywny_hold.expires_at,
            created_at=now,
        ),
        models.RezerwacjaStolikClaim(
            public_hold_id=zwolniony_hold.id,
            stolik_id=stolik.id,
            data=zwolniony_hold.data,
            minute=18 * 60,
            expires_at=zwolniony_hold.expires_at,
            created_at=stary_dt,
        ),
        models.RezerwacjaPublicznaKwota(
            scope="availability",
            client_hash="q" * 64,
            window_start=now - timedelta(hours=2),
            expires_at=now - timedelta(hours=1),
            count=1,
            created_at=now - timedelta(hours=2),
            updated_at=now - timedelta(hours=2),
        ),
    ])
    db.commit()

    response = admin_client.post("/api/rodo/retencja")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["dni"] == 60
    assert body["miesiace"] is None
    assert body["zrodlo"] == "lokal_config"
    assert body["usunieto_holdy_publiczne"] == 1
    assert body["usunieto_tokeny_wygasle"] == 1
    assert body["usunieto_kwoty_wygasle"] == 1
    db.expire_all()
    assert db.get(models.Termin, stary.id).nazwisko == "[anonimizacja RODO]"
    assert db.get(models.Termin, swiezy.id).nazwisko == "Kowalski"
    assert db.get(models.ListaOczekujacych, stara_waitlista.id).nazwisko == "[anonimizacja RODO]"
    assert db.get(models.ListaOczekujacych, swieza_waitlista.id).nazwisko == "Swieza Waitlista"
    assert db.get(models.RezerwacjaPublicznyHold, aktywny_hold_id).state == "active"
    assert db.get(models.RezerwacjaPublicznyHold, zwolniony_hold_id) is None
    assert db.query(models.RezerwacjaStolikClaim).filter_by(
        public_hold_id=aktywny_hold_id,
    ).count() == 1
    assert db.query(models.RezerwacjaTokenZarzadzania).count() == 0
    assert db.query(models.RezerwacjaPublicznaKwota).count() == 0
    assert db.query(models.RezerwacjaZgodaPubliczna).count() == 0


def test_retencja_nie_wydluza_deadline_po_zmianie_polityki(admin_client, db):
    now = utcnow_naive()
    cfg = get_lokal_config(db)
    cfg.rezerwacje_retencja_dni = 30
    publiczny = _termin(
        db,
        data=now.date() - timedelta(days=45),
        nazwisko="Publiczny deadline",
        telefon="700300400",
        status="odbyla",
    )
    legacy = _termin(
        db,
        data=now.date() - timedelta(days=45),
        nazwisko="Legacy bez dowodu",
        telefon="700300401",
        status="odbyla",
    )
    _zgoda(
        db,
        now=now - timedelta(days=50),
        termin_id=publiczny.id,
        retention_until=now - timedelta(seconds=1),
    )
    db.commit()

    # Późniejsza polityka 365 dni nie może unieważnić deadline'u pokazanego
    # gościowi przy rezerwacji. Rekord legacy nadal podlega bieżącej polityce.
    cfg = get_lokal_config(db)
    cfg.rezerwacje_retencja_dni = 365
    db.commit()
    response = admin_client.post("/api/rodo/retencja")

    assert response.status_code == 200, response.text
    db.expire_all()
    assert db.get(models.Termin, publiczny.id).nazwisko == "[anonimizacja RODO]"
    assert db.get(models.Termin, legacy.id).nazwisko == "Legacy bez dowodu"
    assert db.query(models.RezerwacjaZgodaPubliczna).filter_by(
        termin_id=publiczny.id,
    ).count() == 0


def test_automatyczna_retencja_jest_dzienna_systemowa_i_nie_rusza_aktywnych(db):
    now = utcnow_naive()
    dzis = now.date()
    cfg = get_lokal_config(db)
    cfg.rezerwacje_retencja_dni = 60
    zamkniety = _termin(
        db,
        data=dzis - timedelta(days=90),
        nazwisko="Do usuniecia",
        telefon="700200300",
        status="odbyla",
    )
    stary_aktywny = _termin(
        db,
        data=dzis - timedelta(days=90),
        nazwisko="Aktywny stary",
        telefon="700200301",
        status="rezerwacja",
    )
    przyszly_aktywny = _termin(
        db,
        data=dzis + timedelta(days=30),
        nazwisko="Aktywny przyszly",
        telefon="700200302",
        status="potwierdzona",
    )
    zamknieta_waitlista = models.ListaOczekujacych(
        data=dzis - timedelta(days=90),
        liczba_osob=2,
        nazwisko="Waitlista zamknieta",
        telefon="700200303",
        status="zaakceptowano",
        utworzono_at=now - timedelta(days=90),
        zrealizowano_at=now - timedelta(days=89),
        kanal="online",
    )
    otwarta_waitlista = models.ListaOczekujacych(
        data=dzis - timedelta(days=90),
        liczba_osob=3,
        nazwisko="Waitlista aktywna",
        telefon="700200304",
        status="oczekuje",
        utworzono_at=now - timedelta(days=90),
        kanal="online",
    )
    przyszla_waitlista = models.ListaOczekujacych(
        data=dzis + timedelta(days=7),
        liczba_osob=4,
        nazwisko="Waitlista przyszla",
        telefon="700200305",
        status="oczekuje",
        utworzono_at=now,
        kanal="online",
    )
    stolik = models.Stolik(nazwa="Auto-retencja", pojemnosc=4, aktywny=True, kolejnosc=0)
    db.add_all([zamknieta_waitlista, otwarta_waitlista, przyszla_waitlista, stolik])
    db.flush()
    wygasly_hold = models.RezerwacjaPublicznyHold(
        token_hash="r" * 64,
        session_hash="s" * 64,
        ip_hash="t" * 64,
        state="expired",
        data=dzis - timedelta(days=2),
        godz_od=time(18, 0),
        godz_do=time(20, 0),
        liczba_osob=2,
        stolik_id=stolik.id,
        stoliki_dodatkowe=[],
        allocation_snapshot={},
        bufor_min=0,
        expires_at=now - timedelta(days=2),
        created_at=now - timedelta(days=2, minutes=10),
        released_at=now - timedelta(days=2),
    )
    aktywny_hold = models.RezerwacjaPublicznyHold(
        token_hash="u" * 64,
        session_hash="v" * 64,
        ip_hash="w" * 64,
        state="active",
        data=dzis + timedelta(days=1),
        godz_od=time(18, 0),
        godz_do=time(20, 0),
        liczba_osob=2,
        stolik_id=stolik.id,
        stoliki_dodatkowe=[],
        allocation_snapshot={},
        bufor_min=0,
        expires_at=now + timedelta(minutes=10),
        created_at=now,
    )
    db.add_all([wygasly_hold, aktywny_hold])
    db.flush()
    wygasly_nastepca = models.RezerwacjaTokenZarzadzania(
        termin_id=przyszly_aktywny.id,
        token_hash="y" * 64,
        scopes=["view"],
        expires_at=now - timedelta(minutes=1),
        created_at=now - timedelta(days=1),
    )
    db.add(wygasly_nastepca)
    db.flush()
    db.add_all([
        models.RezerwacjaTokenZarzadzania(
            termin_id=przyszly_aktywny.id,
            token_hash="z" * 64,
            scopes=["view"],
            expires_at=now - timedelta(minutes=1),
            created_at=now - timedelta(days=1),
        ),
        models.RezerwacjaTokenZarzadzania(
            termin_id=przyszly_aktywny.id,
            token_hash="x" * 64,
            scopes=["view"],
            expires_at=now - timedelta(minutes=1),
            created_at=now - timedelta(days=1),
            used_at=now - timedelta(hours=1),
            rotated_to_id=wygasly_nastepca.id,
            used_operation="view",
            used_request_fingerprint="f" * 64,
        ),
        models.RezerwacjaPublicznaKwota(
            scope="availability",
            client_hash="q" * 64,
            window_start=now - timedelta(hours=2),
            expires_at=now - timedelta(hours=1),
            count=1,
            created_at=now - timedelta(hours=2),
            updated_at=now - timedelta(hours=2),
        ),
        models.RezerwacjaIdempotencja(
            operation="reservation.create.online:v2",
            key_hash="k" * 64,
            request_fingerprint="f" * 64,
            status="succeeded",
            http_status=201,
            response_enc=json.dumps({"nazwisko": "PII w replay cache"}),
            termin_id=przyszly_aktywny.id,
            created_at=now - timedelta(days=8),
            completed_at=now - timedelta(days=8),
            expires_at=now - timedelta(days=1),
        ),
    ])
    aktywny_hold_id = aktywny_hold.id
    wygasly_hold_id = wygasly_hold.id
    db.commit()

    first = maintenance.run_retention_maintenance_once(now=now)

    assert first["status"] == "executed"
    assert first["dni"] == 60
    assert first["liczba_zmian"] > 0
    assert first["usunieto_idempotencje_wygasla"] == 1
    db.expire_all()
    assert db.get(models.Termin, zamkniety.id).nazwisko == "[anonimizacja RODO]"
    assert db.get(models.Termin, stary_aktywny.id).nazwisko == "Aktywny stary"
    assert db.get(models.Termin, przyszly_aktywny.id).nazwisko == "Aktywny przyszly"
    assert db.get(models.ListaOczekujacych, zamknieta_waitlista.id).nazwisko == "[anonimizacja RODO]"
    assert db.get(models.ListaOczekujacych, otwarta_waitlista.id).nazwisko == "[anonimizacja RODO]"
    assert db.get(models.ListaOczekujacych, przyszla_waitlista.id).nazwisko == "Waitlista przyszla"
    assert db.get(models.RezerwacjaPublicznyHold, wygasly_hold_id) is None
    assert db.get(models.RezerwacjaPublicznyHold, aktywny_hold_id).state == "active"
    assert db.query(models.RezerwacjaTokenZarzadzania).count() == 0
    assert db.query(models.RezerwacjaPublicznaKwota).count() == 0
    assert db.query(models.RezerwacjaIdempotencja).count() == 0

    audit = db.query(models.AuditLog).filter_by(
        akcja="rodo_retencja_automatyczna",
    ).one()
    assert audit.user_id is None
    assert audit.login == "system"
    assert audit.ip is None
    assert audit.zasob == f"policy_days=60;cutoff={dzis - timedelta(days=60)}"
    details = json.loads(audit.szczegoly)
    assert details["zanonimizowano_lacznie"] == 3
    assert "Do usuniecia" not in audit.szczegoly
    system_audit = db.query(models.ReservationAudit).filter_by(
        termin_id=zamkniety.id,
    ).one()
    assert system_audit.actor_kind == "system"
    assert system_audit.actor_user_id is None

    second = maintenance.run_retention_maintenance_once(now=now + timedelta(hours=1))

    assert second["status"] == "already_run"
    assert db.query(models.AuditLog).filter_by(
        akcja="rodo_retencja_automatyczna",
    ).count() == 1


def test_automatyczna_retencja_nie_zasmieca_audytu_pustym_przebiegiem(db):
    result = maintenance.run_retention_maintenance_once(now=utcnow_naive())

    assert result["status"] == "no_changes"
    assert result["liczba_zmian"] == 0
    assert db.query(models.AuditLog).filter_by(
        akcja="rodo_retencja_automatyczna",
    ).count() == 0


def test_admin_rodo_export_is_complete_but_erasure_conflicts_after_io_started(
    admin_client,
    db,
):
    now = utcnow_naive()
    termin = _termin(db, data=date.today(), status="rezerwacja")
    messages = communication.enqueue_reservation(
        db,
        termin,
        "confirmation",
        dedupe_key="rodo-admin-processing-export",
        available_at=now - timedelta(seconds=1),
        expires_at=now + timedelta(hours=1),
    )
    db.commit()
    message_id = messages[0].id
    provider_key = messages[0].provider_idempotency_key
    claim = communication.claim_next(now=now)
    assert claim.id == message_id
    assert communication.mark_claim_started(claim, now=now) is not None

    exported = admin_client.post(
        "/api/rodo/eksport-gosc",
        json={"klucz": KLUCZ},
    )

    assert exported.status_code == 200, exported.text
    body = exported.json()
    assert body["rezerwacje"][0]["kanal_komunikacji"] == "auto"
    history = body["prywatnosc"]["komunikacja_operacyjna"]
    assert len(history) == 1
    assert history[0]["odbiorca"] == TEL
    assert history[0]["stan"] == "processing"
    assert history[0]["proby"][0]["stan"] == "processing"
    assert history[0]["tresc"]
    assert provider_key not in exported.text
    assert all(secret_field not in exported.text for secret_field in (
        "provider_idempotency_key", "provider_idempotency_header",
        "lease_token", "actor_user_id", "reconciled_by_user_id",
        "subject_phone_ref", "subject_email_ref",
    ))

    erased = admin_client.post(
        "/api/rodo/anonimizuj-gosc",
        json={"klucz": KLUCZ},
    )

    assert erased.status_code == 409, erased.text
    assert erased.json()["code"] == "COMMUNICATION_DELIVERY_IN_PROGRESS"
    assert TEL not in erased.text
    hard_delete = admin_client.delete(f"/api/rezerwacje-stolik/{termin.id}")
    assert hard_delete.status_code == 409, hard_delete.text
    assert hard_delete.json()["code"] == "COMMUNICATION_DELIVERY_IN_PROGRESS"
    assert TEL not in hard_delete.text
    db.expire_all()
    assert db.get(models.Termin, termin.id).nazwisko == "Kowalski"
    assert db.get(models.RezerwacjaWiadomoscOutbox, message_id).stan == "processing"


def test_rodo_subject_refs_isolate_history_and_erasure_after_contact_change(
    admin_client,
    db,
):
    now = utcnow_naive()
    phone_a = "600100211"
    email_a = "subject-a@example.test"
    phone_b = "700200311"
    email_b = "subject-b@example.test"
    key_a = _normalizuj_numer(phone_a)
    key_b = _normalizuj_numer(phone_b)
    termin = _termin(db, data=date.today(), telefon=phone_a)
    termin.email = email_a
    termin.kanal_komunikacji = "oba"
    messages_a = communication.enqueue_reservation(
        db,
        termin,
        "confirmation",
        dedupe_key="rodo-subject-a-confirmation",
        available_at=now - timedelta(seconds=1),
        expires_at=now + timedelta(hours=1),
    )
    db.commit()
    ids_a = {message.id for message in messages_a}
    refs_a = {
        (message.subject_phone_ref, message.subject_email_ref)
        for message in messages_a
    }
    assert len(refs_a) == 1
    phone_ref_a, email_ref_a = refs_a.pop()
    assert len(phone_ref_a) == len(email_ref_a) == 64
    assert phone_a not in phone_ref_a and email_a not in email_ref_a
    assert phone_ref_a != hashlib.sha256(phone_a.encode("utf-8")).hexdigest()
    assert email_ref_a != hashlib.sha256(email_a.encode("utf-8")).hexdigest()
    encryption_key = os.environ["ENCRYPTION_KEY"].encode("utf-8")
    index_key = hmac.new(
        encryption_key,
        communication._SUBJECT_INDEX_KEY_DOMAIN,
        hashlib.sha256,
    ).digest()
    assert phone_ref_a == hmac.new(
        index_key,
        communication._SUBJECT_PHONE_DOMAIN + key_a.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    assert email_ref_a == hmac.new(
        index_key,
        communication._SUBJECT_EMAIL_DOMAIN + email_a.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    termin.telefon = phone_b
    termin.email = email_b
    messages_b = communication.enqueue_reservation(
        db,
        termin,
        "change",
        dedupe_key="rodo-subject-b-change",
        available_at=now - timedelta(seconds=1),
        expires_at=now + timedelta(hours=1),
    )
    db.commit()
    ids_b = {message.id for message in messages_b}

    export_b = admin_client.post(
        "/api/rodo/eksport-gosc",
        json={"klucz": key_b},
    )
    assert export_b.status_code == 200, export_b.text
    history_b = export_b.json()["prywatnosc"]["komunikacja_operacyjna"]
    assert {entry["wiadomosc_id"] for entry in history_b} == ids_b
    assert phone_a not in export_b.text and email_a not in export_b.text

    export_a = admin_client.post(
        "/api/rodo/eksport-gosc",
        json={"klucz": key_a},
    )
    assert export_a.status_code == 200, export_a.text
    assert export_a.json()["liczba_rekordow"] == 0
    history_a = export_a.json()["prywatnosc"]["komunikacja_operacyjna"]
    assert {entry["wiadomosc_id"] for entry in history_a} == ids_a
    assert {entry["odbiorca"] for entry in history_a} == {phone_a, email_a}
    export_a_by_email = admin_client.post(
        "/api/rodo/eksport-gosc",
        json={"klucz": email_a},
    )
    assert {
        entry["wiadomosc_id"]
        for entry in export_a_by_email.json()["prywatnosc"]["komunikacja_operacyjna"]
    } == ids_a

    erased_a = admin_client.post(
        "/api/rodo/anonimizuj-gosc",
        json={"klucz": key_a},
    )
    assert erased_a.status_code == 200, erased_a.text
    assert erased_a.json()["zanonimizowano_lacznie"] == 0
    assert erased_a.json()["usunieto_komunikacja"] == 2
    db.expire_all()
    current = db.get(models.Termin, termin.id)
    assert current.telefon == phone_b and current.email == email_b
    assert db.query(models.RezerwacjaWiadomoscOutbox).filter(
        models.RezerwacjaWiadomoscOutbox.id.in_(ids_a),
    ).count() == 0
    assert db.query(models.RezerwacjaWiadomoscOutbox).filter(
        models.RezerwacjaWiadomoscOutbox.id.in_(ids_b),
    ).count() == 2

    erased_b = admin_client.post(
        "/api/rodo/anonimizuj-gosc",
        json={"klucz": key_b},
    )
    assert erased_b.status_code == 200, erased_b.text
    assert erased_b.json()["zanonimizowano"] == 1
    db.expire_all()
    assert db.get(models.Termin, termin.id).nazwisko == "[anonimizacja RODO]"
    assert db.query(models.RezerwacjaWiadomoscOutbox).filter(
        models.RezerwacjaWiadomoscOutbox.id.in_(ids_b),
    ).count() == 0


def test_rodo_current_owner_with_phone_and_email_matches_by_email(admin_client, db):
    now = utcnow_naive()
    email = "  ＧＯＳＣ@Example.TEST  "
    canonical_email = "gosc@example.test"
    termin = _termin(db, data=date.today(), telefon="600100213")
    termin.email = email
    termin.kanal_komunikacji = "oba"
    messages = communication.enqueue_reservation(
        db,
        termin,
        "confirmation",
        dedupe_key="rodo-current-owner-email-lookup",
        available_at=now + timedelta(hours=1),
        expires_at=now + timedelta(hours=2),
    )
    db.commit()
    message_ids = {message.id for message in messages}

    exported = admin_client.post(
        "/api/rodo/eksport-gosc",
        json={"klucz": canonical_email.upper()},
    )

    assert exported.status_code == 200, exported.text
    assert exported.json()["liczba_rezerwacji"] == 1
    assert exported.json()["rezerwacje"][0]["id"] == termin.id
    assert {
        entry["wiadomosc_id"]
        for entry in exported.json()["prywatnosc"]["komunikacja_operacyjna"]
    } == message_ids

    erased = admin_client.post(
        "/api/rodo/anonimizuj-gosc",
        json={"klucz": canonical_email},
    )

    assert erased.status_code == 200, erased.text
    assert erased.json()["zanonimizowano"] == 1
    assert erased.json()["usunieto_komunikacja"] == len(message_ids)
    db.expire_all()
    assert db.get(models.Termin, termin.id).nazwisko == "[anonimizacja RODO]"
    assert db.query(models.RezerwacjaWiadomoscOutbox).filter(
        models.RezerwacjaWiadomoscOutbox.id.in_(message_ids),
    ).count() == 0


def test_subject_a_erasure_does_not_block_on_subject_b_processing_message(
    admin_client,
    db,
):
    now = utcnow_naive()
    phone_a = "600100212"
    phone_b = "700200312"
    termin = _termin(db, data=date.today(), telefon=phone_a)
    termin.kanal_komunikacji = "sms"
    message_a = communication.enqueue_reservation(
        db,
        termin,
        "confirmation",
        dedupe_key="rodo-processing-isolation-a",
        available_at=now + timedelta(hours=1),
        expires_at=now + timedelta(hours=2),
    )[0]
    termin.telefon = phone_b
    message_b = communication.enqueue_reservation(
        db,
        termin,
        "change",
        dedupe_key="rodo-processing-isolation-b",
        available_at=now - timedelta(seconds=1),
        expires_at=now + timedelta(hours=2),
    )[0]
    db.commit()
    message_a_id = message_a.id
    message_b_id = message_b.id
    claim = communication.claim_next(now=now)
    assert claim.id == message_b_id
    assert communication.mark_claim_started(claim, now=now) is not None

    erased_a = admin_client.post(
        "/api/rodo/anonimizuj-gosc",
        json={"klucz": _normalizuj_numer(phone_a)},
    )

    assert erased_a.status_code == 200, erased_a.text
    assert erased_a.json()["zanonimizowano_lacznie"] == 0
    db.expire_all()
    assert db.get(models.Termin, termin.id).telefon == phone_b
    assert db.get(models.RezerwacjaWiadomoscOutbox, message_a_id) is None
    assert db.get(models.RezerwacjaWiadomoscOutbox, message_b_id).stan == "processing"


def test_waitlist_claimed_before_io_is_erased_and_cannot_start(admin_client, db):
    now = utcnow_naive()
    deadline = now + timedelta(minutes=15)
    stolik = models.Stolik(
        nazwa="RODO-race", pojemnosc=2, aktywny=True, kolejnosc=0,
    )
    db.add(stolik)
    db.flush()
    offer_key_hash = hashlib.sha256(b"rodo-waitlist-claimed-offer").hexdigest()
    wpis = models.ListaOczekujacych(
        data=date.today(),
        godz_od=time(18, 0),
        liczba_osob=2,
        nazwisko="Kowalski",
        telefon=TEL,
        kanal_komunikacji="sms",
        status="zaoferowano",
        offer_version=1,
        offer_auto_przydzielony=True,
        offer_override_authorized=False,
        offer_key_hash=offer_key_hash,
        offer_request_fingerprint=hashlib.sha256(
            b"rodo-waitlist-claimed-payload"
        ).hexdigest(),
        zaoferowano_at=now,
        oferta_wygasa_at=deadline,
        utworzono_at=now,
        kanal="reczna",
        hold_stolik_id=stolik.id,
        hold_stoliki_dodatkowe=[],
        hold_godz_od=time(18, 0),
        hold_godz_do=time(18, 15),
        hold_bufor_min=0,
        hold_do=deadline,
    )
    db.add(wpis)
    db.flush()
    db.add_all([
        models.RezerwacjaStolikClaim(
            waitlist_id=wpis.id,
            stolik_id=stolik.id,
            data=wpis.data,
            minute=minute,
            expires_at=deadline,
            created_at=now,
        )
        for minute in range(18 * 60, 18 * 60 + 15)
    ])
    messages = communication.enqueue_table_ready(
        db,
        wpis,
        dedupe_key=f"waitlist:{wpis.id}:offer:1:{offer_key_hash}",
    )
    messages[0].available_at = now - timedelta(seconds=1)
    db.commit()
    message_id = messages[0].id
    claim = communication.claim_next(now=now)
    assert claim.id == message_id

    erased = admin_client.post(
        "/api/rodo/anonimizuj-gosc",
        json={"klucz": KLUCZ},
    )

    assert erased.status_code == 200, erased.text
    assert erased.json()["zanonimizowano_waitlista"] == 1
    assert communication.mark_claim_started(claim, now=now) is None
    db.expire_all()
    assert db.get(models.ListaOczekujacych, wpis.id).nazwisko == "[anonimizacja RODO]"
    assert db.get(models.RezerwacjaWiadomoscOutbox, message_id) is None


def test_admin_rodo_relocks_all_owner_days_after_concurrent_move(
    monkeypatch,
    admin_client,
    db,
):
    now = utcnow_naive()
    original_day = date.today()
    moved_day = original_day - timedelta(days=2)
    waitlist_day = original_day + timedelta(days=1)
    termin = _termin(db, data=original_day)
    wpis = models.ListaOczekujacych(
        data=waitlist_day,
        godz_od=time(18, 0),
        liczba_osob=2,
        nazwisko="Kowalski",
        telefon=TEL,
        kanal_komunikacji="sms",
        status="oczekuje",
        utworzono_at=now,
        kanal="reczna",
    )
    db.add(wpis)
    db.commit()
    termin_id = termin.id
    wpis_id = wpis.id
    real_begin = reservation_service.begin_locked_write
    real_planner_lock = communication.acquire_erasure_planner_lock
    lock_calls = []
    lock_events = []
    moved = False
    inserted_message_id = None

    def move_owner_before_first_lock(session, dates):
        nonlocal moved, inserted_message_id
        ordered = tuple(dates)
        assert ordered == tuple(sorted(ordered))
        lock_calls.append(ordered)
        lock_events.append(("days", ordered))
        if not moved:
            moved = True
            # Deterministyczna granica synchronizacji: producent kończy zmianę
            # po pierwszym skanie RODO, lecz przed przejęciem starego dnia.
            session.rollback()
            concurrent = communication.SessionLocal()
            try:
                owner = concurrent.get(models.Termin, termin_id)
                owner.data = moved_day
                messages = communication.enqueue_reservation(
                    concurrent,
                    owner,
                    "change",
                    dedupe_key="rodo-concurrent-owner-move",
                    available_at=now - timedelta(seconds=1),
                    expires_at=now + timedelta(hours=1),
                )
                concurrent.commit()
                inserted_message_id = messages[0].id
            finally:
                concurrent.close()
        return real_begin(session, ordered)

    def record_planner_after_days(session):
        lock_events.append(("planner", None))
        return real_planner_lock(session)

    monkeypatch.setattr(
        reservation_service,
        "begin_locked_write",
        move_owner_before_first_lock,
    )
    monkeypatch.setattr(
        communication,
        "acquire_erasure_planner_lock",
        record_planner_after_days,
    )

    response = admin_client.post(
        "/api/rodo/anonimizuj-gosc",
        json={"klucz": KLUCZ},
    )

    assert response.status_code == 200, response.text
    assert lock_calls == [
        (original_day, waitlist_day),
        (moved_day, original_day, waitlist_day),
    ]
    assert [event for event, _payload in lock_events] == [
        "days", "days", "planner", "planner",
    ]
    db.expire_all()
    assert db.get(models.Termin, termin_id).nazwisko == "[anonimizacja RODO]"
    assert db.get(models.ListaOczekujacych, wpis_id).nazwisko == "[anonimizacja RODO]"
    assert db.get(models.RezerwacjaWiadomoscOutbox, inserted_message_id) is None


def test_hard_waitlist_delete_fences_claimed_and_processing_delivery(admin_client, db):
    now = utcnow_naive()
    stolik = models.Stolik(
        nazwa="RODO-hard-delete", pojemnosc=2, aktywny=True, kolejnosc=0,
    )
    db.add(stolik)
    db.commit()

    def queued_waitlist(suffix):
        deadline = now + timedelta(minutes=15)
        offer_key_hash = hashlib.sha256(
            f"waitlist-hard-delete-offer-{suffix}".encode()
        ).hexdigest()
        wpis = models.ListaOczekujacych(
            data=date.today(),
            godz_od=time(18, 0),
            liczba_osob=2,
            nazwisko=f"Waitlist {suffix}",
            telefon=f"7005006{suffix}",
            kanal_komunikacji="sms",
            status="zaoferowano",
            offer_version=1,
            offer_auto_przydzielony=True,
            offer_override_authorized=False,
            offer_key_hash=offer_key_hash,
            offer_request_fingerprint=hashlib.sha256(
                f"waitlist-hard-delete-payload-{suffix}".encode()
            ).hexdigest(),
            zaoferowano_at=now,
            oferta_wygasa_at=deadline,
            utworzono_at=now,
            kanal="reczna",
            hold_stolik_id=stolik.id,
            hold_stoliki_dodatkowe=[],
            hold_godz_od=time(18, 0),
            hold_godz_do=time(18, 15),
            hold_bufor_min=0,
            hold_do=deadline,
        )
        db.add(wpis)
        db.flush()
        db.add_all([
            models.RezerwacjaStolikClaim(
                waitlist_id=wpis.id,
                stolik_id=stolik.id,
                data=wpis.data,
                minute=minute,
                expires_at=deadline,
                created_at=now,
            )
            for minute in range(18 * 60, 18 * 60 + 15)
        ])
        messages = communication.enqueue_table_ready(
            db,
            wpis,
            dedupe_key=f"waitlist:{wpis.id}:offer:1:{offer_key_hash}",
        )
        messages[0].available_at = now - timedelta(seconds=1)
        db.commit()
        return wpis.id, messages[0].id

    claimed_owner_id, claimed_message_id = queued_waitlist("11")
    claimed = communication.claim_next(now=now)
    assert claimed.id == claimed_message_id

    deleted = admin_client.delete(f"/api/lista-oczekujacych/{claimed_owner_id}")

    assert deleted.status_code == 204, deleted.text
    assert communication.mark_claim_started(claimed, now=now) is None
    db.expire_all()
    assert db.get(models.ListaOczekujacych, claimed_owner_id) is None
    assert db.get(models.RezerwacjaWiadomoscOutbox, claimed_message_id) is None

    processing_owner_id, processing_message_id = queued_waitlist("12")
    processing_claim = communication.claim_next(now=now)
    assert processing_claim.id == processing_message_id
    assert communication.mark_claim_started(processing_claim, now=now) is not None

    conflict = admin_client.delete(f"/api/lista-oczekujacych/{processing_owner_id}")

    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["code"] == "COMMUNICATION_DELIVERY_IN_PROGRESS"
    assert "Waitlist 12" not in conflict.text
    assert "700500612" not in conflict.text
    db.expire_all()
    assert db.get(models.ListaOczekujacych, processing_owner_id) is not None
    assert db.get(models.RezerwacjaWiadomoscOutbox, processing_message_id).stan == "processing"


def test_maintenance_defers_only_owner_with_processing_delivery(db):
    now = utcnow_naive()
    processing = _termin(
        db,
        data=now.date() + timedelta(days=1),
        nazwisko="Processing RODO",
        telefon="700500601",
        status="rezerwacja",
    )
    messages = communication.enqueue_reservation(
        db,
        processing,
        "confirmation",
        dedupe_key="rodo-maintenance-processing",
        available_at=now - timedelta(seconds=1),
        expires_at=now + timedelta(hours=1),
    )
    db.commit()
    message_id = messages[0].id
    claim = communication.claim_next(now=now)
    assert claim.id == message_id
    assert communication.mark_claim_started(claim, now=now) is not None
    db.expire_all()
    processing = db.get(models.Termin, processing.id)
    processing.data = now.date() - timedelta(days=800)
    processing.status = "odbyla"
    db.commit()
    safe = _termin(
        db,
        data=now.date() - timedelta(days=800),
        nazwisko="Safe RODO",
        telefon="700500602",
        status="odbyla",
    )

    result = maintenance.run_retention_maintenance_once(now=now)

    assert result["status"] == "executed"
    assert result["odroczono_komunikacja"] == 1
    assert result["odroczono_rezerwacje"] == 1
    db.expire_all()
    assert db.get(models.Termin, processing.id).nazwisko == "Processing RODO"
    assert db.get(models.Termin, safe.id).nazwisko == "[anonimizacja RODO]"
    assert db.get(models.RezerwacjaWiadomoscOutbox, message_id).stan == "processing"
    audit = db.query(models.AuditLog).filter_by(
        akcja="rodo_retencja_automatyczna",
    ).one()
    assert "Processing RODO" not in audit.szczegoly
    assert "700500601" not in audit.szczegoly


def test_maintenance_without_other_changes_defers_and_leaves_no_daily_marker(db):
    now = utcnow_naive()
    processing = _termin(
        db,
        data=now.date() + timedelta(days=1),
        nazwisko="Only Processing RODO",
        telefon="700500603",
        status="rezerwacja",
    )
    messages = communication.enqueue_reservation(
        db,
        processing,
        "confirmation",
        dedupe_key="rodo-maintenance-only-processing",
        available_at=now - timedelta(seconds=1),
        expires_at=now + timedelta(hours=1),
    )
    db.commit()
    message_id = messages[0].id
    claim = communication.claim_next(now=now)
    assert claim.id == message_id
    assert communication.mark_claim_started(claim, now=now) is not None
    db.expire_all()
    processing = db.get(models.Termin, processing.id)
    processing.data = now.date() - timedelta(days=800)
    processing.status = "odbyla"
    db.commit()

    result = maintenance.run_retention_maintenance_once(now=now)

    assert result["status"] == "deferred"
    assert result["liczba_zmian"] == 0
    assert result["odroczono_komunikacja"] == 1
    db.expire_all()
    assert db.get(models.Termin, processing.id).nazwisko == "Only Processing RODO"
    assert db.get(models.RezerwacjaWiadomoscOutbox, message_id).stan == "processing"
    assert db.query(models.AuditLog).filter_by(
        akcja="rodo_retencja_automatyczna",
    ).count() == 0


def test_startup_uruchamia_lekki_maintenance(monkeypatch):
    calls = []
    monkeypatch.setattr(main.app_settings, "validate_critical_secrets", lambda: calls.append("validate"))
    monkeypatch.setattr(main, "init_db", lambda: calls.append("init_db"))
    monkeypatch.setattr(main.maintenance, "start_maintenance", lambda: calls.append("maintenance"))
    monkeypatch.setattr(main.provisioning, "wlaczony", lambda: False)

    main.startup()

    assert calls == ["validate", "init_db", "maintenance"]


def test_maintenance_nie_blokuje_startupu_pelnym_skanem(monkeypatch):
    entered = threading.Event()
    release = threading.Event()

    def blocking_run():
        entered.set()
        release.wait(timeout=2)

    maintenance.stop_maintenance()
    monkeypatch.setattr(maintenance, "_uses_ephemeral_sqlite", lambda: False)
    monkeypatch.setattr(maintenance, "_run_safely", blocking_run)
    started_at = monotonic()
    maintenance.start_maintenance()
    elapsed = monotonic() - started_at
    try:
        assert elapsed < 0.3
        assert entered.wait(timeout=1)
    finally:
        release.set()
        maintenance.stop_maintenance()


def test_rodo_wymaga_admina(client):
    """Bez tokenu admina RODO jest niedostępne (role_guard)."""
    assert client.post(
        "/api/rodo/eksport-gosc", json={"klucz": KLUCZ},
    ).status_code == 401
