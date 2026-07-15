"""Router: RODO/GDPR — prawa podmiotu danych (art. 15/17/20) + retencja PII gości (art. 5 ust.1 e).

Admin-only (role_guard chroni całe /api/*, dodatkowo require_admin). PII gości (telefon/e-mail)
szyfrowane niedeterministycznie (EncryptedString) → dopasowanie gościa po ODSZYFROWANIU w Pythonie,
tak jak crm.py (nie da się GROUP BY po szyfrogramie). Każda operacja zostawia ślad w AuditLog.

Anonimizacja czyści nazwisko/telefon/e-mail/notatkę rezerwacji, wątki portalu (treść bywa z PII)
oraz opisy/nazwiska zadatków KP (wolny tekst z nazwiskiem). Statystyki (daty/kwoty/statusy)
zostają, więc raporty i scoring nie kłamią po usunięciu danych osobowych.
"""

from datetime import datetime, timedelta
import hashlib
import hmac
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

import models
import reservation_audit
import reservation_service
from auth import SECRET_KEY, require_admin
from crm_identity import hash_key as _profile_hash_key
from crm_identity import identity_key as _profile_identity_key
from database import get_db
from deps import utcnow_naive
from sms import _normalizuj_numer

router = APIRouter()

_ANON = "[anonimizacja RODO]"
_ZAMKNIETE = ("odbyla", "no_show", "odwolana")
# ``oczekuje`` jest bezpieczne dopiero po przekroczeniu progu: wpis dotyczy wtedy
# historycznej daty, więc nie może już reprezentować aktywnego przyszłego oczekiwania.
_WAITLIST_RETENTION_STATUSES = ("zrealizowany", "odwolany", "oczekuje")
RETENTION_AUDIT_ACTION = "rodo_retencja_automatyczna"
_PUBLIC_HOLD_CLEANUP_GRACE = timedelta(days=1)


def _klucz(t) -> str:
    """Klucz gościa (jak w crm.py): znormalizowany telefon → e-mail → nazwisko (po odszyfrowaniu)."""
    email = getattr(t, "email", None) or ""
    return _normalizuj_numer(t.telefon or "") or email.strip().lower() or (t.nazwisko or "").strip().lower()


def _terminy_goscia(db, klucz: str):
    k = (klucz or "").strip().lower()
    if not k:
        return []
    return [t for t in db.query(models.Termin).all() if _klucz(t) == k]


def _waitlista_goscia(db, klucz: str):
    k = (klucz or "").strip().lower()
    if not k:
        return []
    return [
        wpis
        for wpis in db.query(models.ListaOczekujacych).all()
        if _klucz(wpis) == k
    ]


def _referencja_goscia(klucz: str) -> str:
    """Nieodwracalna, stabilna referencja do audytu dostępu — nigdy surowe PII."""
    normalized = (klucz or "").strip().lower().encode("utf-8")
    digest = hmac.new(SECRET_KEY.encode("utf-8"), normalized, hashlib.sha256).hexdigest()
    return f"guest_ref:{digest}"


def _audyt(db, admin, akcja, zasob, request):
    """Dodaje wpis do transakcji wywołującego; eksport bez audytu nie może się udać."""
    ip = request.client.host if (request and request.client) else None
    db.add(models.AuditLog(ts=utcnow_naive(), user_id=getattr(admin, "id", None),
                           login=getattr(admin, "login", None), akcja=akcja, zasob=zasob, ip=ip))


def _wpis(t) -> dict:
    return {"id": t.id, "data": str(t.data), "rodzaj": getattr(t, "rodzaj", None), "typ": t.typ,
            "status": t.status, "nazwisko": t.nazwisko, "telefon": t.telefon,
            "email": getattr(t, "email", None), "notatka": t.notatka,
            "liczba_osob": t.liczba_osob, "sala": t.sala, "zadatek": t.zadatek}


def _iso(value):
    return value.isoformat() if value is not None else None


def _wpis_waitlisty(wpis) -> dict:
    """Dane podmiotu i metryki wpisu; bez tokenu ani wewnętrznych identyfikatorów stołów."""
    return {
        "id": wpis.id,
        "data": str(wpis.data),
        "godz_od": _iso(wpis.godz_od),
        "liczba_osob": wpis.liczba_osob,
        "nazwisko": wpis.nazwisko,
        "telefon": wpis.telefon,
        "email": wpis.email,
        "notatka": wpis.notatka,
        "status": wpis.status,
        "kanal": wpis.kanal,
        "utworzono_at": _iso(wpis.utworzono_at),
        "zrealizowano_at": _iso(wpis.zrealizowano_at),
        "powiadomiono_at": _iso(wpis.powiadomiono_at),
        "hold_wygasa_at": _iso(wpis.hold_do),
    }


def _zgoda_wpis(zgoda) -> dict:
    """Dowód wyboru gościa bez nieodwracalnego hasha IP."""
    owner_kind = "rezerwacja" if zgoda.termin_id is not None else "waitlista"
    owner_id = zgoda.termin_id if zgoda.termin_id is not None else zgoda.waitlist_id
    return {
        "wlasciciel_typ": owner_kind,
        "wlasciciel_id": owner_id,
        "notice_version": zgoda.notice_version,
        "notice_ack_at": _iso(zgoda.notice_ack_at),
        "marketing": bool(zgoda.marketing),
        "marketing_version": zgoda.marketing_version,
        "marketing_at": _iso(zgoda.marketing_at),
        "sensitive": bool(zgoda.sensitive),
        "sensitive_version": zgoda.sensitive_version,
        "sensitive_at": _iso(zgoda.sensitive_at),
        "sensitive_data": zgoda.sensitive_data if zgoda.sensitive else None,
        "retention_until": _iso(zgoda.retention_until),
        "created_at": _iso(zgoda.created_at),
    }


def _metadane_prywatnosci(db, termin_ids, waitlist_ids) -> dict:
    consents_query = db.query(models.RezerwacjaZgodaPubliczna)
    conditions = []
    if termin_ids:
        conditions.append(models.RezerwacjaZgodaPubliczna.termin_id.in_(termin_ids))
    if waitlist_ids:
        conditions.append(models.RezerwacjaZgodaPubliczna.waitlist_id.in_(waitlist_ids))
    consents = []
    if conditions:
        consents = consents_query.filter(or_(*conditions)).order_by(
            models.RezerwacjaZgodaPubliczna.created_at,
            models.RezerwacjaZgodaPubliczna.id,
        ).all()

    tokens = []
    if termin_ids:
        for token in db.query(models.RezerwacjaTokenZarzadzania).filter(
            models.RezerwacjaTokenZarzadzania.termin_id.in_(termin_ids)
        ).order_by(models.RezerwacjaTokenZarzadzania.created_at).all():
            scopes = token.scopes if isinstance(token.scopes, (list, tuple)) else []
            tokens.append({
                "rezerwacja_id": token.termin_id,
                "zakresy": list(scopes),
                "created_at": _iso(token.created_at),
                "expires_at": _iso(token.expires_at),
                "used_at": _iso(token.used_at),
                "revoked_at": _iso(token.revoked_at),
                "used_operation": token.used_operation,
            })

    holds = []
    if termin_ids:
        for hold in db.query(models.RezerwacjaPublicznyHold).filter(
            models.RezerwacjaPublicznyHold.termin_id.in_(termin_ids)
        ).order_by(models.RezerwacjaPublicznyHold.created_at).all():
            claim_count = db.query(models.RezerwacjaStolikClaim).filter_by(
                public_hold_id=hold.id,
            ).count()
            holds.append({
                "rezerwacja_id": hold.termin_id,
                "state": hold.state,
                "data": str(hold.data),
                "godz_od": _iso(hold.godz_od),
                "godz_do": _iso(hold.godz_do),
                "liczba_osob": hold.liczba_osob,
                "bufor_min": hold.bufor_min,
                "expires_at": _iso(hold.expires_at),
                "created_at": _iso(hold.created_at),
                "released_at": _iso(hold.released_at),
                "consumed_at": _iso(hold.consumed_at),
                "liczba_claimow": claim_count,
            })

    return {
        "zgody": [_zgoda_wpis(consent) for consent in consents],
        # Wyłącznie metadane cyklu życia. Hash i surowy capability token nigdy nie
        # opuszczają warstwy uwierzytelnienia.
        "dostepy_zarzadzania": tokens,
        "holdy_publiczne": holds,
    }


def usun_powiazane_publiczne_sekrety(
    db,
    termin_ids,
    *,
    preserve_management_token_ids=(),
) -> None:
    if not termin_ids:
        return
    hold_ids = [
        row[0]
        for row in db.query(models.RezerwacjaPublicznyHold.id).filter(
            models.RezerwacjaPublicznyHold.termin_id.in_(termin_ids)
        ).all()
    ]
    if hold_ids:
        db.query(models.RezerwacjaStolikClaim).filter(
            models.RezerwacjaStolikClaim.public_hold_id.in_(hold_ids)
        ).delete(synchronize_session=False)
        db.query(models.RezerwacjaPublicznyHold).filter(
            models.RezerwacjaPublicznyHold.id.in_(hold_ids)
        ).delete(synchronize_session=False)
    db.query(models.RezerwacjaZgodaPubliczna).filter(
        models.RezerwacjaZgodaPubliczna.termin_id.in_(termin_ids)
    ).delete(synchronize_session=False)
    token_query = db.query(models.RezerwacjaTokenZarzadzania).filter(
        models.RezerwacjaTokenZarzadzania.termin_id.in_(termin_ids)
    )
    preserved = tuple(preserve_management_token_ids or ())
    if preserved:
        token_query = token_query.filter(
            ~models.RezerwacjaTokenZarzadzania.id.in_(preserved)
        )
    token_query.delete(synchronize_session=False)
    db.query(models.RezerwacjaIdempotencja).filter(
        models.RezerwacjaIdempotencja.termin_id.in_(termin_ids)
    ).delete(synchronize_session=False)


def usun_powiazane_pii_rezerwacji(db, terminy) -> None:
    """Usuwa PII poza samym ``Termin`` dla retencji i samoobsługi gościa.

    Profil CRM może być współdzielony przez kilka wizyt tego samego gościa, dlatego
    znika tylko wtedy, gdy po anonimizacji nie zostaje żaden inny właściciel tego
    klucza. Wątki oraz wolny tekst KP są przypisane bezpośrednio do rezerwacji.
    """
    termin_ids = {termin.id for termin in terminy if termin.id is not None}
    if not termin_ids:
        return

    def profile_hashes(termin):
        keys = {_profile_identity_key(termin), _klucz(termin)}
        return {_profile_hash_key(key) for key in keys if key}

    candidate_hashes = set().union(
        *(profile_hashes(termin) for termin in terminy)
    ) if terminy else set()
    if candidate_hashes:
        remaining_hashes = set()
        for other in db.query(models.Termin).all():
            if other.id not in termin_ids:
                remaining_hashes.update(profile_hashes(other))
        delete_hashes = candidate_hashes - remaining_hashes
        if delete_hashes:
            db.query(models.ProfilGoscia).filter(
                models.ProfilGoscia.klucz_hash.in_(delete_hashes)
            ).delete(synchronize_session=False)

    db.query(models.WiadomoscImprezy).filter(
        models.WiadomoscImprezy.termin_id.in_(termin_ids)
    ).delete(synchronize_session=False)
    for zadatek in db.query(models.KpZadatek).filter(
        models.KpZadatek.termin_id.in_(termin_ids)
    ).all():
        zadatek.nazwisko = None
        zadatek.opis = _ANON


def _anonimizuj(db, terminy, *, actor, reason: str) -> int:
    termin_ids = [t.id for t in terminy if t.id is not None]
    # Zgody, capability tokeny, zużyte holdy oraz zaszyfrowany wynik idempotencji
    # mogą odtwarzać historię publicznego przepływu. Usuwamy je atomowo z PII.
    usun_powiazane_publiczne_sekrety(db, termin_ids)
    usun_powiazane_pii_rezerwacji(db, terminy)
    n = 0
    for t in terminy:
        audit_before = (
            reservation_audit.reservation_snapshot(t)
            if t.rodzaj == "stolik" else None
        )
        pii_changed = {
            field
            for field, target in {
                "nazwisko": _ANON,
                "telefon": None,
                "email": None,
                "notatka": None,
                "token_potwierdzenia": None,
            }.items()
            if getattr(t, field, None) != target
        }
        t.nazwisko = _ANON
        t.telefon = None
        t.notatka = None
        t.token_potwierdzenia = None
        if hasattr(t, "email"):
            t.email = None
        if audit_before is not None:
            reservation_audit.add_reservation_audit(
                db,
                termin=t,
                action="edit",
                actor=actor,
                actor_kind="system" if actor is None else "user",
                reason=reason,
                before=audit_before,
                after=t,
                pii_changed=pii_changed,
            )
        n += 1
    return n


def _anonimizuj_waitliste(db, wpisy) -> int:
    waitlist_ids = [wpis.id for wpis in wpisy if wpis.id is not None]
    if waitlist_ids:
        db.query(models.RezerwacjaZgodaPubliczna).filter(
            models.RezerwacjaZgodaPubliczna.waitlist_id.in_(waitlist_ids)
        ).delete(synchronize_session=False)
    for wpis in wpisy:
        wpis.nazwisko = _ANON
        wpis.telefon = None
        wpis.email = None
        wpis.notatka = None
        wpis.token = None
    return len(wpisy)


def _wyczysc_wygasle_publiczne_rekordy(db, *, now: datetime) -> dict:
    # Wspólny cleanup zwalnia zarówno publiczne holdy, jak i starsze holdy waitlisty.
    # Aktywny hold z przyszłym TTL nie spełnia żadnego z poniższych warunków.
    waitlist_holds = db.query(models.ListaOczekujacych.id).filter(
        models.ListaOczekujacych.hold_do.isnot(None),
        models.ListaOczekujacych.hold_do <= now,
    ).count()
    wygaszone_holdy = reservation_service.cleanup_expired_holds(db, now)
    cleanup_before = now - _PUBLIC_HOLD_CLEANUP_GRACE
    inactive_hold_ids = [
        row[0]
        for row in db.query(models.RezerwacjaPublicznyHold.id).filter(
            models.RezerwacjaPublicznyHold.state.in_(("released", "expired")),
            or_(
                models.RezerwacjaPublicznyHold.released_at <= cleanup_before,
                and_(
                    models.RezerwacjaPublicznyHold.released_at.is_(None),
                    models.RezerwacjaPublicznyHold.expires_at <= cleanup_before,
                ),
            ),
        ).all()
    ]
    if inactive_hold_ids:
        db.query(models.RezerwacjaStolikClaim).filter(
            models.RezerwacjaStolikClaim.public_hold_id.in_(inactive_hold_ids)
        ).delete(synchronize_session=False)
        usuniete_holdy = db.query(models.RezerwacjaPublicznyHold).filter(
            models.RezerwacjaPublicznyHold.id.in_(inactive_hold_ids)
        ).delete(synchronize_session=False)
    else:
        usuniete_holdy = 0
    usuniete_tokeny = db.query(models.RezerwacjaTokenZarzadzania).filter(
        models.RezerwacjaTokenZarzadzania.expires_at <= now,
    ).delete(synchronize_session=False)
    usuniete_idempotencje = db.query(models.RezerwacjaIdempotencja).filter(
        models.RezerwacjaIdempotencja.expires_at <= now,
    ).delete(synchronize_session=False)
    usuniete_kwoty = reservation_service.cleanup_expired_public_quotas(db, now)
    return {
        "wygaszono_holdy_i_claimy": int(wygaszone_holdy or 0),
        "wyczyszczono_holdy_waitlisty": int(waitlist_holds or 0),
        "usunieto_holdy_publiczne": int(usuniete_holdy or 0),
        "usunieto_tokeny_wygasle": int(usuniete_tokeny or 0),
        "usunieto_idempotencje_wygasla": int(usuniete_idempotencje or 0),
        "usunieto_kwoty_wygasle": int(usuniete_kwoty or 0),
    }


def wykonaj_retencje_rodo(
    db,
    *,
    now: Optional[datetime] = None,
    dni: Optional[int] = None,
    actor=None,
    request: Optional[Request] = None,
    zrodlo: str = "lokal_config",
    audit_action: str = "rodo_retencja",
    audituj_pusty: bool = True,
) -> dict:
    """Wykonuje jeden atomowy przebieg retencji bez zarządzania transakcją.

    Funkcja jest wspólna dla ręcznego endpointu i zadania maintenance. Anonimizuje
    wyłącznie zamknięte rezerwacje starsze od polityki. Stary wpis waitlisty
    ``oczekuje`` również podlega retencji, bo jego data jest już przed progiem;
    świeże i przyszłe oczekiwania pozostają nietknięte.
    """
    effective_now = now or utcnow_naive()
    if dni is None:
        cfg = db.get(models.LokalConfig, 1)
        configured_days = getattr(cfg, "rezerwacje_retencja_dni", 365) if cfg else 365
        retention_days = max(30, min(int(configured_days or 365), 3650))
    else:
        retention_days = max(1, int(dni))
    prog = effective_now.date() - timedelta(days=retention_days)

    # Dla publicznego przepływu zapisany dowód jest wiążącym, nieprzedłużalnym
    # terminem. Bieżąca polityka może okres skrócić, lecz późniejsza zmiana z 30
    # na 365 dni nie może retroaktywnie zatrzymać danych przez kolejny rok.
    expired_termin_ids = [
        row[0] for row in db.query(models.RezerwacjaZgodaPubliczna.termin_id).filter(
            models.RezerwacjaZgodaPubliczna.termin_id.isnot(None),
            models.RezerwacjaZgodaPubliczna.retention_until <= effective_now,
        ).all()
    ]
    expired_waitlist_ids = [
        row[0] for row in db.query(models.RezerwacjaZgodaPubliczna.waitlist_id).filter(
            models.RezerwacjaZgodaPubliczna.waitlist_id.isnot(None),
            models.RezerwacjaZgodaPubliczna.retention_until <= effective_now,
        ).all()
    ]
    termin_deadline = models.Termin.data < prog
    if expired_termin_ids:
        termin_deadline = or_(
            termin_deadline,
            models.Termin.id.in_(expired_termin_ids),
        )
    terminy = db.query(models.Termin).filter(
        termin_deadline,
        models.Termin.status.in_(_ZAMKNIETE),
    ).all()
    terminy = [termin for termin in terminy if termin.nazwisko != _ANON]
    waitlist_deadline = models.ListaOczekujacych.data < prog
    if expired_waitlist_ids:
        waitlist_deadline = or_(
            waitlist_deadline,
            models.ListaOczekujacych.id.in_(expired_waitlist_ids),
        )
    waitlista = db.query(models.ListaOczekujacych).filter(
        waitlist_deadline,
        models.ListaOczekujacych.status.in_(_WAITLIST_RETENTION_STATUSES),
    ).all()
    waitlista = [wpis for wpis in waitlista if wpis.nazwisko != _ANON]

    n = _anonimizuj(db, terminy, actor=actor, reason="system_automation")
    n_waitlist = _anonimizuj_waitliste(db, waitlista)
    cleanup = _wyczysc_wygasle_publiczne_rekordy(db, now=effective_now)
    liczba_zmian = n + n_waitlist + sum(int(value or 0) for value in cleanup.values())
    wynik = {
        "zanonimizowano": n,
        "zanonimizowano_waitlista": n_waitlist,
        "zanonimizowano_lacznie": n + n_waitlist,
        "prog": str(prog),
        "dni": retention_days,
        "zrodlo": zrodlo,
        "liczba_zmian": liczba_zmian,
        **cleanup,
    }

    if audituj_pusty or liczba_zmian:
        ip = request.client.host if (request is not None and request.client) else None
        szczegoly = json.dumps(wynik, ensure_ascii=False, sort_keys=True)
        db.add(models.AuditLog(
            ts=effective_now,
            user_id=getattr(actor, "id", None),
            login=getattr(actor, "login", None) if actor is not None else "system",
            akcja=audit_action,
            zasob=f"policy_days={retention_days};cutoff={prog}",
            ip=ip,
            szczegoly=szczegoly,
        ))
    return wynik


class KluczIn(BaseModel):
    klucz: str


@router.post("/api/rodo/eksport-gosc")
def eksport_gosc(dane: KluczIn, request: Request, db: Session = Depends(get_db),
                 admin: models.User = Depends(require_admin)):
    """Art. 15/20: eksport rezerwacji, waitlisty i dowodów prywatności gościa."""
    klucz = dane.klucz
    terminy = _terminy_goscia(db, klucz)
    waitlista = _waitlista_goscia(db, klucz)
    if not terminy and not waitlista:
        raise HTTPException(404, "Nie znaleziono danych dla podanego klucza.")
    termin_ids = [t.id for t in terminy if t.id is not None]
    waitlist_ids = [wpis.id for wpis in waitlista if wpis.id is not None]
    privacy = _metadane_prywatnosci(db, termin_ids, waitlist_ids)
    _audyt(db, admin, "rodo_eksport_gosc", _referencja_goscia(klucz), request)
    db.commit()
    return {
        "klucz": klucz,
        "liczba_rekordow": len(terminy) + len(waitlista),
        "liczba_rezerwacji": len(terminy),
        "liczba_wpisow_waitlisty": len(waitlista),
        "rezerwacje": [_wpis(t) for t in sorted(terminy, key=lambda x: x.data)],
        "lista_oczekujacych": [
            _wpis_waitlisty(wpis) for wpis in sorted(waitlista, key=lambda x: x.data)
        ],
        "prywatnosc": privacy,
    }


@router.post("/api/rodo/anonimizuj-gosc")
def anonimizuj_gosc(dane: KluczIn, request: Request, db: Session = Depends(get_db),
                    admin: models.User = Depends(require_admin)):
    """Art. 17: anonimizacja PII rezerwacji i waitlisty wraz z sekretami/zgodami."""
    terminy = _terminy_goscia(db, dane.klucz)
    waitlista = _waitlista_goscia(db, dane.klucz)
    if not terminy and not waitlista:
        raise HTTPException(404, "Nie znaleziono danych dla podanego klucza.")
    n = _anonimizuj(db, terminy, actor=admin, reason="guest_request")
    n_waitlist = _anonimizuj_waitliste(db, waitlista)
    _audyt(
        db, admin, "rodo_anonimizuj_gosc", _referencja_goscia(dane.klucz), request,
    )
    db.commit()
    return {
        "zanonimizowano": n,
        "zanonimizowano_waitlista": n_waitlist,
        "zanonimizowano_lacznie": n + n_waitlist,
    }


@router.post("/api/rodo/retencja")
def retencja(request: Request, miesiace: Optional[int] = Query(None, ge=1), db: Session = Depends(get_db),
             admin: models.User = Depends(require_admin)):
    """Art. 5 ust.1 lit.e (ograniczenie przechowywania): anonimizacja PII rezerwacji ZAMKNIĘTYCH
    i waitlisty. Bez jawnego parametru używa polityki skonfigurowanej dla lokalu."""
    if miesiace is None:
        dni = None
        zrodlo = "lokal_config"
    else:
        # Wsteczna zgodność ręcznego wywołania administracyjnego.
        dni = 30 * int(miesiace)
        zrodlo = "miesiace"
    wynik = wykonaj_retencje_rodo(
        db,
        now=utcnow_naive(),
        dni=dni,
        actor=admin,
        request=request,
        zrodlo=zrodlo,
    )
    db.commit()
    return {**wynik, "miesiace": int(miesiace) if miesiace is not None else None}
