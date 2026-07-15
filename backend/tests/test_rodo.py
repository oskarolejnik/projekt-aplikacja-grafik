"""RODO/GDPR: eksport (art. 15/20), anonimizacja gościa (art. 17) i retencja (art. 5 ust.1 e).
Admin-only; dopasowanie gościa po odszyfrowanym telefonie (jak CRM)."""

from datetime import date, datetime, time, timedelta
import json
import threading
from time import monotonic

import maintenance
import main
import models
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
    _termin(db, data=date.today())
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
    assert body["lista_oczekujacych"][0]["status"] == "oczekuje"
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
    audit = db.query(models.ReservationAudit).filter_by(termin_id=stary.id).one()
    assert audit.action == "edit" and audit.reason == "system_automation"


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
        status="odwolany",
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
        status="zrealizowany",
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
        status="zrealizowany",
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
