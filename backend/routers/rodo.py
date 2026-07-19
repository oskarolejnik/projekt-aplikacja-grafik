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
import unicodedata
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

import models
import reservation_audit
import reservation_communication
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
_WAITLIST_RETENTION_STATUSES = (
    "zaakceptowano", "wygasla", "anulowano", "oczekuje", "zaoferowano",
)
RETENTION_AUDIT_ACTION = "rodo_retencja_automatyczna"
_PUBLIC_HOLD_CLEANUP_GRACE = timedelta(days=1)


def _kanoniczny_tekst(value: str) -> str:
    return unicodedata.normalize("NFKC", value or "").strip().casefold()


def _klucz(t) -> str:
    """Preferowany klucz profilu: telefon → e-mail → nazwisko."""
    email = _kanoniczny_tekst(getattr(t, "email", None) or "")
    return (
        _normalizuj_numer(t.telefon or "")
        or email
        or _kanoniczny_tekst(t.nazwisko or "")
    )


def _pasuje_do_klucza(owner, klucz: str) -> bool:
    """Dopasowuje każdy kontakt ownera, bez fallbacku nazwiska dla kontaktowych.

    Telefon i e-mail są równorzędnymi identyfikatorami podmiotu. Nazwisko może
    służyć jako historyczny fallback wyłącznie wtedy, gdy rekord nie ma żadnego
    kontaktu — inaczej wspólne nazwisko mogłoby ujawnić dane obcej osoby.
    """
    raw = (klucz or "").strip()
    if not raw:
        return False
    lookup_phone = _normalizuj_numer(raw)
    lookup_email = _kanoniczny_tekst(raw)
    owner_phone = _normalizuj_numer(getattr(owner, "telefon", None) or "")
    owner_email = _kanoniczny_tekst(getattr(owner, "email", None) or "")
    if owner_phone or owner_email:
        return bool(
            (lookup_phone and owner_phone == lookup_phone)
            or (lookup_email and owner_email == lookup_email)
        )
    return _kanoniczny_tekst(getattr(owner, "nazwisko", None) or "") == lookup_email


def _terminy_goscia(db, klucz: str, *, refresh: bool = False):
    if not (klucz or "").strip():
        return []
    query = db.query(models.Termin)
    if refresh:
        query = query.populate_existing()
    return [t for t in query.all() if _pasuje_do_klucza(t, klucz)]


def _waitlista_goscia(db, klucz: str, *, refresh: bool = False):
    if not (klucz or "").strip():
        return []
    query = db.query(models.ListaOczekujacych)
    if refresh:
        query = query.populate_existing()
    return [
        wpis
        for wpis in query.all()
        if _pasuje_do_klucza(wpis, klucz)
    ]


class RodoOwnerLockScopeChanged(RuntimeError):
    """Maintenance musi rozpocząć transakcję od nowa z odświeżonym zakresem dni."""


def _dni_wlascicieli(terminy, waitlista) -> set:
    return {
        owner.data
        for owner in (*terminy, *waitlista)
        if getattr(owner, "data", None) is not None
    }


def _zablokuj_i_odswiez_wlascicieli(
    db,
    loader,
    *,
    lock_scope_loader=None,
    current_transaction: bool = False,
):
    """Serializuje producentów snapshotów, a potem ponownie wyznacza ownerów.

    Producenci rezerwacji i waitlisty blokują anchory dnia przed zmianą danych i
    utworzeniem outboxa. RODO przejmuje te same anchory w porządku rosnącym, a
    następnie wymusza ``populate_existing``. Jeśli właściciel zmienił dzień w
    czasie oczekiwania, zwykłe żądanie restartuje transakcję i przejmuje sumę dni
    od początku. Maintenance sygnalizuje restart do swojej zewnętrznej pętli, aby
    nie utracić ochrony pojedynczego przebiegu.
    """
    terminy, waitlista = loader(False)
    lock_terminy, lock_waitlista = (
        lock_scope_loader(False) if lock_scope_loader is not None else ([], [])
    )
    required_dates = _dni_wlascicieli(
        [*terminy, *lock_terminy],
        [*waitlista, *lock_waitlista],
    )
    if not required_dates:
        return terminy, waitlista, ()

    for _attempt in range(8):
        ordered_dates = tuple(sorted(required_dates))
        if current_transaction:
            guards = reservation_service.lock_days_in_current_transaction(
                db, ordered_dates,
            )
        else:
            guards = reservation_service.begin_locked_write(db, ordered_dates)

        terminy, waitlista = loader(True)
        lock_terminy, lock_waitlista = (
            lock_scope_loader(True)
            if lock_scope_loader is not None else ([], [])
        )
        refreshed_dates = _dni_wlascicieli(
            [*terminy, *lock_terminy],
            [*waitlista, *lock_waitlista],
        )
        if refreshed_dates.issubset(required_dates):
            return terminy, waitlista, guards
        if current_transaction:
            raise RodoOwnerLockScopeChanged()
        required_dates.update(refreshed_dates)

    raise reservation_service.ReservationError(
        503,
        "RESERVATION_BUSY",
        "Zakres danych rezerwacji zmieniał się w trakcie operacji. Spróbuj ponownie.",
        rule="transaction",
    )


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
            "kanal_komunikacji": getattr(t, "kanal_komunikacji", None),
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
        "kanal_komunikacji": wpis.kanal_komunikacji,
        "notatka": wpis.notatka,
        "notatka_nadpisania_oferty": wpis.offer_override_note,
        "status": wpis.status,
        "priorytet": int(wpis.priorytet or 0),
        "offer_auto_przydzielony": wpis.offer_auto_przydzielony,
        "offer_override_authorized": wpis.offer_override_authorized,
        "kanal": wpis.kanal,
        "demand_reason_code": wpis.demand_reason_code,
        "demand_resource_kind": wpis.demand_resource_kind,
        "utworzono_at": _iso(wpis.utworzono_at),
        "zrealizowano_at": _iso(wpis.zrealizowano_at),
        "zaoferowano_at": _iso(wpis.zaoferowano_at),
        "oferta_wygasa_at": _iso(wpis.oferta_wygasa_at),
        "zaakceptowano_at": _iso(wpis.zaakceptowano_at),
        "attended_at": _iso(wpis.attended_at),
        "wygasla_at": _iso(wpis.wygasla_at),
        "anulowano_at": _iso(wpis.anulowano_at),
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


def _refy_komunikacji_podmiotu(klucz: str):
    phone_ref, email_ref = reservation_communication.subject_refs_for_key(klucz)
    conditions = []
    if phone_ref:
        conditions.append(
            models.RezerwacjaWiadomoscOutbox.subject_phone_ref == phone_ref,
        )
    if email_ref:
        conditions.append(
            models.RezerwacjaWiadomoscOutbox.subject_email_ref == email_ref,
        )
    return phone_ref, email_ref, conditions


def _wiadomosci_podmiotu(db, klucz: str):
    _phone_ref, _email_ref, conditions = _refy_komunikacji_podmiotu(klucz)
    if not conditions:
        return []
    return db.query(models.RezerwacjaWiadomoscOutbox).filter(
        or_(*conditions),
    ).order_by(models.RezerwacjaWiadomoscOutbox.id).all()


def _wlasciciele_wiadomosci_podmiotu(db, klucz: str, *, refresh: bool = False):
    _phone_ref, _email_ref, conditions = _refy_komunikacji_podmiotu(klucz)
    owner_rows = (
        db.query(
            models.RezerwacjaWiadomoscOutbox.termin_id,
            models.RezerwacjaWiadomoscOutbox.waitlist_id,
        ).filter(or_(*conditions)).all()
        if conditions else []
    )
    termin_ids = {row[0] for row in owner_rows if row[0] is not None}
    waitlist_ids = {row[1] for row in owner_rows if row[1] is not None}
    terminy_query = db.query(models.Termin).filter(models.Termin.id.in_(termin_ids))
    waitlist_query = db.query(models.ListaOczekujacych).filter(
        models.ListaOczekujacych.id.in_(waitlist_ids),
    )
    if refresh:
        terminy_query = terminy_query.populate_existing()
        waitlist_query = waitlist_query.populate_existing()
    return terminy_query.all(), waitlist_query.all()


def eksport_komunikacji_operacyjnej(
    db,
    *,
    subject_phone_refs=(),
    subject_email_refs=(),
    termin_ids=(),
    waitlist_ids=(),
    require_owner_scope: bool = False,
) -> list[dict]:
    """Returns a complete subject-facing delivery history without system secrets.

    Recipient and rendered content belong to the data subject and are therefore
    included.  Provider credentials, idempotency keys/headers, lease tokens and
    staff identifiers are operational secrets and intentionally stay internal.
    Provider/error values are stable codes only; no raw provider response or
    exception text can enter the export (or an audit log built from it).
    """
    subject_phone_refs = {str(value) for value in subject_phone_refs if value}
    subject_email_refs = {str(value) for value in subject_email_refs if value}
    termin_ids = {int(value) for value in termin_ids if value is not None}
    waitlist_ids = {int(value) for value in waitlist_ids if value is not None}
    subject_conditions = []
    owner_conditions = []
    if subject_phone_refs:
        subject_conditions.append(
            models.RezerwacjaWiadomoscOutbox.subject_phone_ref.in_(
                subject_phone_refs,
            ),
        )
    if subject_email_refs:
        subject_conditions.append(
            models.RezerwacjaWiadomoscOutbox.subject_email_ref.in_(
                subject_email_refs,
            ),
        )
    if termin_ids:
        owner_conditions.append(
            models.RezerwacjaWiadomoscOutbox.termin_id.in_(termin_ids),
        )
    if waitlist_ids:
        owner_conditions.append(
            models.RezerwacjaWiadomoscOutbox.waitlist_id.in_(waitlist_ids),
        )

    if require_owner_scope:
        # Capability samoobsługowa daje dostęp do jednego ownera, nie do całego
        # podmiotu. Oba warunki są obowiązkowe: rekord musi należeć do ownera z
        # tokena ORAZ przedstawiać snapshot jego bieżącego kontaktu.
        if not subject_conditions or not owner_conditions:
            return []
        message_filter = and_(
            or_(*owner_conditions),
            or_(*subject_conditions),
        )
    elif subject_conditions:
        # Tożsamość snapshotu ma pierwszeństwo przed bieżącym owner ID. Po
        # zmianie kontaktu A→B rekord Termin należy do B, ale historia A nie może
        # zostać ujawniona B ani stać się dla A nieosiągalna.
        message_filter = or_(*subject_conditions)
    else:
        if not owner_conditions:
            return []
        message_filter = or_(*owner_conditions)

    messages = db.query(models.RezerwacjaWiadomoscOutbox).filter(
        message_filter,
    ).order_by(
        models.RezerwacjaWiadomoscOutbox.created_at,
        models.RezerwacjaWiadomoscOutbox.id,
    ).all()
    attempts_by_message = {}
    if messages:
        attempts = db.query(models.RezerwacjaWiadomoscProba).filter(
            models.RezerwacjaWiadomoscProba.wiadomosc_id.in_(
                [message.id for message in messages],
            ),
        ).order_by(
            models.RezerwacjaWiadomoscProba.wiadomosc_id,
            models.RezerwacjaWiadomoscProba.numer,
        ).all()
        for attempt in attempts:
            attempts_by_message.setdefault(attempt.wiadomosc_id, []).append(attempt)

    result = []
    for message in messages:
        owner_is_reservation = message.termin_id is not None
        result.append({
            "wiadomosc_id": message.id,
            "wlasciciel_typ": "rezerwacja" if owner_is_reservation else "waitlista",
            "wlasciciel_id": message.termin_id if owner_is_reservation else message.waitlist_id,
            "typ": message.typ_zdarzenia,
            "kanal": message.kanal,
            "odbiorca": message.odbiorca,
            "temat": message.temat,
            "tresc": message.tresc,
            "szablon": message.template_key,
            "wersja_szablonu": message.template_version,
            "provider": message.provider,
            "stan": message.stan,
            "liczba_prob": message.liczba_prob,
            "maks_prob": message.maks_prob,
            "dostepna_od": _iso(message.available_at),
            "wygasa_at": _iso(message.expires_at),
            "ostatni_kod_bledu": message.last_error_code,
            "aktor_typ": message.actor_kind,
            "utworzono_at": _iso(message.created_at),
            "zaktualizowano_at": _iso(message.updated_at),
            "przyjeto_at": _iso(message.sent_at),
            "wynik_niepewny_at": _iso(message.uncertain_at),
            "uzgodniono_at": _iso(message.reconciled_at),
            "notatka_uzgodnienia": message.reconciliation_note,
            "proby": [
                {
                    "numer": attempt.numer,
                    "provider": attempt.provider,
                    "stan": attempt.wynik,
                    "zajeto_at": _iso(attempt.claimed_at),
                    "rozpoczeto_at": _iso(attempt.started_at),
                    "zakonczono_at": _iso(attempt.finished_at),
                    "ponowienie_at": _iso(attempt.retry_at),
                    "kod_bledu": attempt.error_code,
                    "status_http": attempt.status_code,
                }
                for attempt in attempts_by_message.get(message.id, ())
            ],
        })
    return result


def _metadane_prywatnosci(
    db,
    termin_ids,
    waitlist_ids,
    *,
    communication_subject_phone_refs=(),
    communication_subject_email_refs=(),
) -> dict:
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

    reservation_audits = []
    if termin_ids:
        audit_rows = db.query(models.ReservationAudit).filter(
            models.ReservationAudit.termin_id.in_(termin_ids),
        ).order_by(
            models.ReservationAudit.created_at,
            models.ReservationAudit.id,
        ).all()
        contexts = {
            row.audit_id: row
            for row in db.query(models.ReservationOverrideContext).filter(
                models.ReservationOverrideContext.audit_id.in_(
                    [audit.id for audit in audit_rows],
                ),
            ).all()
        } if audit_rows else {}
        for audit in audit_rows:
            context = contexts.get(audit.id)
            reservation_audits.append({
                "rezerwacja_id": audit.termin_id,
                "utworzono_at": _iso(audit.created_at),
                "akcja": audit.action,
                "powod": audit.reason,
                "zmiany": audit.diff,
                "kod_powodu_nadpisania": (
                    context.reason_code if context is not None else None
                ),
                "notatka_nadpisania": (
                    context.note if context is not None else None
                ),
            })

    waitlist_override_history = []
    if waitlist_ids:
        for context in db.query(
            models.WaitlistOfferOverrideContext,
        ).filter(
            models.WaitlistOfferOverrideContext.waitlist_id.in_(waitlist_ids),
        ).order_by(
            models.WaitlistOfferOverrideContext.created_at,
            models.WaitlistOfferOverrideContext.id,
        ).all():
            waitlist_override_history.append({
                "wpis_waitlisty_id": context.waitlist_id,
                "offer_version": context.offer_version,
                "kod_powodu": context.reason_code,
                "notatka": context.note,
                "utworzono_at": _iso(context.created_at),
            })

    return {
        "zgody": [_zgoda_wpis(consent) for consent in consents],
        # Wyłącznie metadane cyklu życia. Hash i surowy capability token nigdy nie
        # opuszczają warstwy uwierzytelnienia.
        "dostepy_zarzadzania": tokens,
        "holdy_publiczne": holds,
        "audyty_rezerwacji": reservation_audits,
        "historia_nadpisan_ofert_waitlisty": waitlist_override_history,
        "komunikacja_operacyjna": eksport_komunikacji_operacyjnej(
            db,
            subject_phone_refs=communication_subject_phone_refs,
            subject_email_refs=communication_subject_email_refs,
            termin_ids=termin_ids,
            waitlist_ids=waitlist_ids,
        ),
    }


def wyczysc_notatki_kontekstu_nadpisan(db, termin_ids) -> int:
    """Erase encrypted free text before audit FK is detached from Termin."""
    ids = {int(value) for value in termin_ids if value is not None}
    if not ids:
        return 0
    audit_ids = [
        row[0] for row in db.query(models.ReservationAudit.id).filter(
            models.ReservationAudit.termin_id.in_(ids),
        ).all()
    ]
    if not audit_ids:
        return 0
    return db.query(models.ReservationOverrideContext).filter(
        models.ReservationOverrideContext.audit_id.in_(audit_ids),
        models.ReservationOverrideContext.note.isnot(None),
    ).update(
        {models.ReservationOverrideContext.note: None},
        synchronize_session=False,
    )


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


def _usun_zablokowane_wiadomosci(db, message_ids) -> None:
    message_ids = tuple(message_ids or ())
    if not message_ids:
        return
    db.query(models.RezerwacjaWiadomoscProba).filter(
        models.RezerwacjaWiadomoscProba.wiadomosc_id.in_(message_ids),
    ).delete(synchronize_session=False)
    db.query(models.RezerwacjaWiadomoscOutbox).filter(
        models.RezerwacjaWiadomoscOutbox.id.in_(message_ids),
    ).delete(synchronize_session=False)


def usun_outbox_przed_usunieciem_pii(
    db,
    *,
    message_ids=(),
    reservation_ids=(),
    waitlist_ids=(),
    defer_in_flight: bool = False,
):
    """Fences the worker and explicitly removes safe encrypted snapshots."""
    preparation = reservation_communication.prepare_outboxes_for_pii_erasure(
        db,
        message_ids=message_ids,
        reservation_ids=reservation_ids,
        waitlist_ids=waitlist_ids,
        defer_started=defer_in_flight,
    )
    _usun_zablokowane_wiadomosci(db, preparation.message_ids)
    return preparation


def usun_powiazane_pii_rezerwacji(
    db,
    terminy,
    *,
    defer_in_flight: bool = False,
    outbox_prepared: bool = False,
) -> set[int]:
    """Usuwa PII poza samym ``Termin`` dla retencji i samoobsługi gościa.

    Profil CRM może być współdzielony przez kilka wizyt tego samego gościa, dlatego
    znika tylko wtedy, gdy po anonimizacji nie zostaje żaden inny właściciel tego
    klucza. Wątki oraz wolny tekst KP są przypisane bezpośrednio do rezerwacji.
    """
    terminy = list(terminy)
    termin_ids = {termin.id for termin in terminy if termin.id is not None}
    if not termin_ids:
        return set()

    # Snapshoty outboxa zawierają zaszyfrowany adres i pełną treść. Przy żądaniu
    # usunięcia/retencji kasujemy je razem z próbami, zanim owner zostanie
    # zanonimizowany. Worker nie może później wysłać wiadomości.
    # Próby usuwamy jawnie przed outboxem: prywatność nie może zależeć od
    # włączonego PRAGMA foreign_keys w konkretnej instalacji SQLite.
    if outbox_prepared:
        blocked_ids = set()
    else:
        preparation = usun_outbox_przed_usunieciem_pii(
            db,
            reservation_ids=termin_ids,
            defer_in_flight=defer_in_flight,
        )
        blocked_ids = set(preparation.deferred_reservation_ids)
    safe_terminy = [termin for termin in terminy if termin.id not in blocked_ids]
    safe_ids = {termin.id for termin in safe_terminy if termin.id is not None}
    if not safe_ids:
        return blocked_ids

    wyczysc_notatki_kontekstu_nadpisan(db, safe_ids)

    def profile_hashes(termin):
        keys = {_profile_identity_key(termin), _klucz(termin)}
        return {_profile_hash_key(key) for key in keys if key}

    candidate_hashes = set().union(
        *(profile_hashes(termin) for termin in safe_terminy)
    ) if safe_terminy else set()
    if candidate_hashes:
        remaining_hashes = set()
        for other in db.query(models.Termin).all():
            if other.id not in safe_ids:
                remaining_hashes.update(profile_hashes(other))
        delete_hashes = candidate_hashes - remaining_hashes
        if delete_hashes:
            db.query(models.ProfilGoscia).filter(
                models.ProfilGoscia.klucz_hash.in_(delete_hashes)
            ).delete(synchronize_session=False)

    db.query(models.WiadomoscImprezy).filter(
        models.WiadomoscImprezy.termin_id.in_(safe_ids)
    ).delete(synchronize_session=False)
    for zadatek in db.query(models.KpZadatek).filter(
        models.KpZadatek.termin_id.in_(safe_ids)
    ).all():
        zadatek.nazwisko = None
        zadatek.opis = _ANON
    return blocked_ids


def _anonimizuj(
    db,
    terminy,
    *,
    actor,
    reason: str,
    defer_in_flight: bool = False,
    outbox_prepared: bool = False,
) -> tuple[int, int]:
    terminy = list(terminy)
    blocked_ids = usun_powiazane_pii_rezerwacji(
        db,
        terminy,
        defer_in_flight=defer_in_flight,
        outbox_prepared=outbox_prepared,
    )
    safe_terminy = [termin for termin in terminy if termin.id not in blocked_ids]
    termin_ids = [termin.id for termin in safe_terminy if termin.id is not None]
    # Zgody, capability tokeny, zużyte holdy oraz zaszyfrowany wynik idempotencji
    # mogą odtwarzać historię publicznego przepływu. Usuwamy je atomowo z PII.
    usun_powiazane_publiczne_sekrety(db, termin_ids)
    n = 0
    for t in safe_terminy:
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
    return n, len(blocked_ids)


def _anonimizuj_waitliste(
    db,
    wpisy,
    *,
    defer_in_flight: bool = False,
    outbox_prepared: bool = False,
) -> tuple[int, int]:
    wpisy = list(wpisy)
    waitlist_ids = {wpis.id for wpis in wpisy if wpis.id is not None}
    blocked_ids = set()
    if waitlist_ids and not outbox_prepared:
        preparation = usun_outbox_przed_usunieciem_pii(
            db,
            waitlist_ids=waitlist_ids,
            defer_in_flight=defer_in_flight,
        )
        blocked_ids = set(preparation.deferred_waitlist_ids)
    if waitlist_ids:
        safe_ids = waitlist_ids - blocked_ids
        db.query(models.RezerwacjaZgodaPubliczna).filter(
            models.RezerwacjaZgodaPubliczna.waitlist_id.in_(safe_ids)
        ).delete(synchronize_session=False)
        db.query(models.WaitlistOfferOverrideContext).filter(
            models.WaitlistOfferOverrideContext.waitlist_id.in_(safe_ids),
            models.WaitlistOfferOverrideContext.note.isnot(None),
        ).update(
            {models.WaitlistOfferOverrideContext.note: None},
            synchronize_session=False,
        )
    safe_wpisy = [wpis for wpis in wpisy if wpis.id not in blocked_ids]
    for wpis in safe_wpisy:
        wpis.nazwisko = _ANON
        wpis.telefon = None
        wpis.email = None
        wpis.notatka = None
        wpis.offer_override_note = None
        wpis.token = None
        wpis.create_key_hash = None
        wpis.create_request_fingerprint = None
    return len(safe_wpisy), len(blocked_ids)


def _wyczysc_wygasle_publiczne_rekordy(
    db, *, now: datetime, locked_dates=(),
) -> dict:
    # Wspólny cleanup zwalnia zarówno publiczne holdy, jak i starsze holdy waitlisty.
    # Aktywny hold z przyszłym TTL nie spełnia żadnego z poniższych warunków.
    waitlist_holds = db.query(models.ListaOczekujacych.id).filter(
        models.ListaOczekujacych.hold_do.isnot(None),
        models.ListaOczekujacych.hold_do <= now,
    ).count()
    wygaszone_holdy = reservation_service.cleanup_expired_holds(
        db, now, dates=locked_dates,
    )
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


def _wlasciciele_cleanup_holdow(db, *, now: datetime, refresh: bool = False):
    cleanup_before = now - _PUBLIC_HOLD_CLEANUP_GRACE
    public_query = db.query(models.RezerwacjaPublicznyHold).filter(
        or_(
            and_(
                models.RezerwacjaPublicznyHold.state == "active",
                models.RezerwacjaPublicznyHold.expires_at <= now,
            ),
            and_(
                models.RezerwacjaPublicznyHold.state.in_(("released", "expired")),
                or_(
                    models.RezerwacjaPublicznyHold.released_at <= cleanup_before,
                    and_(
                        models.RezerwacjaPublicznyHold.released_at.is_(None),
                        models.RezerwacjaPublicznyHold.expires_at <= cleanup_before,
                    ),
                ),
            ),
        ),
    )
    waitlist_query = db.query(models.ListaOczekujacych).filter(
        models.ListaOczekujacych.hold_do.isnot(None),
        models.ListaOczekujacych.hold_do <= now,
    )
    if refresh:
        public_query = public_query.populate_existing()
        waitlist_query = waitlist_query.populate_existing()
    return public_query.all(), waitlist_query.all()


def _wlasciciele_retencji(
    db,
    *,
    effective_now: datetime,
    prog,
    refresh: bool = False,
):
    """Ponownie wyznacza cały zakres retencji po przejęciu blokad dni."""
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
    terminy_query = db.query(models.Termin).filter(
        termin_deadline,
        models.Termin.status.in_(_ZAMKNIETE),
    )
    if refresh:
        terminy_query = terminy_query.populate_existing()
    terminy = [
        termin for termin in terminy_query.all()
        if termin.nazwisko != _ANON
    ]

    waitlist_deadline = models.ListaOczekujacych.data < prog
    if expired_waitlist_ids:
        waitlist_deadline = or_(
            waitlist_deadline,
            models.ListaOczekujacych.id.in_(expired_waitlist_ids),
        )
    waitlista_query = db.query(models.ListaOczekujacych).filter(
        waitlist_deadline,
        models.ListaOczekujacych.status.in_(_WAITLIST_RETENTION_STATUSES),
    )
    if refresh:
        waitlista_query = waitlista_query.populate_existing()
    waitlista = [
        wpis for wpis in waitlista_query.all()
        if wpis.nazwisko != _ANON
    ]
    return terminy, waitlista


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
    defer_in_flight: bool = False,
    owner_lock_in_current_transaction: bool = False,
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
    terminy, waitlista, owner_guards = _zablokuj_i_odswiez_wlascicieli(
        db,
        lambda refresh: _wlasciciele_retencji(
            db,
            effective_now=effective_now,
            prog=prog,
            refresh=refresh,
        ),
        lock_scope_loader=lambda refresh: _wlasciciele_cleanup_holdow(
            db, now=effective_now, refresh=refresh,
        ),
        current_transaction=owner_lock_in_current_transaction,
    )

    n, deferred_reservations = _anonimizuj(
        db,
        terminy,
        actor=actor,
        reason="system_automation",
        defer_in_flight=defer_in_flight,
    )
    n_waitlist, deferred_waitlists = _anonimizuj_waitliste(
        db,
        waitlista,
        defer_in_flight=defer_in_flight,
    )
    cleanup = _wyczysc_wygasle_publiczne_rekordy(
        db,
        now=effective_now,
        locked_dates=tuple(guard.data for guard in owner_guards),
    )
    if n or n_waitlist or cleanup.get("wygaszono_holdy_i_claimy"):
        reservation_service.touch_days(owner_guards)
    liczba_zmian = n + n_waitlist + sum(int(value or 0) for value in cleanup.values())
    wynik = {
        "zanonimizowano": n,
        "zanonimizowano_waitlista": n_waitlist,
        "zanonimizowano_lacznie": n + n_waitlist,
        "odroczono_komunikacja": deferred_reservations + deferred_waitlists,
        "odroczono_rezerwacje": deferred_reservations,
        "odroczono_waitlista": deferred_waitlists,
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
    messages = _wiadomosci_podmiotu(db, klucz)
    if not terminy and not waitlista and not messages:
        raise HTTPException(404, "Nie znaleziono danych dla podanego klucza.")
    termin_ids = [t.id for t in terminy if t.id is not None]
    waitlist_ids = [wpis.id for wpis in waitlista if wpis.id is not None]
    phone_ref, email_ref, _conditions = _refy_komunikacji_podmiotu(klucz)
    privacy = _metadane_prywatnosci(
        db,
        termin_ids,
        waitlist_ids,
        communication_subject_phone_refs=[phone_ref] if phone_ref else (),
        communication_subject_email_refs=[email_ref] if email_ref else (),
    )
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
    terminy, waitlista, guards = _zablokuj_i_odswiez_wlascicieli(
        db,
        lambda refresh: (
            _terminy_goscia(db, dane.klucz, refresh=refresh),
            _waitlista_goscia(db, dane.klucz, refresh=refresh),
        ),
        lock_scope_loader=lambda refresh: _wlasciciele_wiadomosci_podmiotu(
            db, dane.klucz, refresh=refresh,
        ),
    )
    # Day -> planner -> exact subject message rows. Scheduler nie może dopisać
    # snapshotu pomiędzy wyborem refów a fence/delete.
    reservation_communication.acquire_erasure_planner_lock(db)
    messages = _wiadomosci_podmiotu(db, dane.klucz)
    if not terminy and not waitlista and not messages:
        raise HTTPException(404, "Nie znaleziono danych dla podanego klucza.")
    current_termin_ids = {termin.id for termin in terminy if termin.id is not None}
    current_waitlist_ids = {wpis.id for wpis in waitlista if wpis.id is not None}
    historical_message_ids = {
        message.id
        for message in messages
        if message.termin_id not in current_termin_ids
        and message.waitlist_id not in current_waitlist_ids
    }
    current_message_query = db.query(models.RezerwacjaWiadomoscOutbox.id)
    current_conditions = []
    if current_termin_ids:
        current_conditions.append(
            models.RezerwacjaWiadomoscOutbox.termin_id.in_(current_termin_ids),
        )
    if current_waitlist_ids:
        current_conditions.append(
            models.RezerwacjaWiadomoscOutbox.waitlist_id.in_(current_waitlist_ids),
        )
    current_message_ids = {
        row[0] for row in (
            current_message_query.filter(or_(*current_conditions)).all()
            if current_conditions else []
        )
    }
    selected_message_ids = historical_message_ids | current_message_ids
    usun_outbox_przed_usunieciem_pii(
        db,
        message_ids=historical_message_ids,
        reservation_ids=current_termin_ids,
        waitlist_ids=current_waitlist_ids,
    )
    n, _ = _anonimizuj(
        db,
        terminy,
        actor=admin,
        reason="guest_request",
        outbox_prepared=True,
    )
    n_waitlist, _ = _anonimizuj_waitliste(
        db,
        waitlista,
        outbox_prepared=True,
    )
    reservation_service.touch_days(guards)
    _audyt(
        db, admin, "rodo_anonimizuj_gosc", _referencja_goscia(dane.klucz), request,
    )
    db.commit()
    return {
        "zanonimizowano": n,
        "zanonimizowano_waitlista": n_waitlist,
        "zanonimizowano_lacznie": n + n_waitlist,
        "usunieto_komunikacja": len(selected_message_ids),
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
