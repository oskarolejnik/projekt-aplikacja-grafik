"""Router: RODO/GDPR — prawa podmiotu danych (art. 15/17/20) + retencja PII gości (art. 5 ust.1 e).

Admin-only (role_guard chroni całe /api/*, dodatkowo require_admin). PII gości (telefon/e-mail)
szyfrowane niedeterministycznie (EncryptedString) → dopasowanie gościa po ODSZYFROWANIU w Pythonie,
tak jak crm.py (nie da się GROUP BY po szyfrogramie). Każda operacja zostawia ślad w AuditLog.

Anonimizacja czyści nazwisko/telefon/e-mail/notatkę rezerwacji, wątki portalu (treść bywa z PII)
oraz opisy/nazwiska zadatków KP (wolny tekst z nazwiskiem). Statystyki (daty/kwoty/statusy)
zostają, więc raporty i scoring nie kłamią po usunięciu danych osobowych.
"""

from datetime import date, timedelta
import hashlib
import hmac

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
import reservation_audit
from auth import SECRET_KEY, require_admin
from crm_identity import hash_key as _profile_hash_key
from crm_identity import identity_key as _profile_identity_key
from database import get_db
from deps import utcnow_naive
from sms import _normalizuj_numer

router = APIRouter()

_ANON = "[anonimizacja RODO]"
_ZAMKNIETE = ("odbyla", "no_show", "odwolana")


def _klucz(t) -> str:
    """Klucz gościa (jak w crm.py): znormalizowany telefon → e-mail → nazwisko (po odszyfrowaniu)."""
    email = getattr(t, "email", None) or ""
    return _normalizuj_numer(t.telefon or "") or email.strip().lower() or (t.nazwisko or "").strip().lower()


def _terminy_goscia(db, klucz: str):
    k = (klucz or "").strip().lower()
    if not k:
        return []
    return [t for t in db.query(models.Termin).all() if _klucz(t) == k]


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


def _anonimizuj(db, terminy, *, actor, reason: str) -> int:
    termin_ids = [t.id for t in terminy if t.id is not None]
    if termin_ids:
        # Zaszyfrowany wynik idempotencji nadal jest odtwarzalnym PII. Usuń jego kopię
        # razem z anonimizacją rekordu źródłowego, w tym samym commicie.
        db.query(models.RezerwacjaIdempotencja).filter(
            models.RezerwacjaIdempotencja.termin_id.in_(termin_ids)
        ).delete(synchronize_session=False)

    # Profil CRM przechowuje osobne PII (m.in. alergie i notatkę). Usuwamy profile
    # należące wyłącznie do anonimizowanych rekordów, zanim wyczyścimy klucz
    # kontaktowy. Profil kontaktu zostaje przy retencji starej wizyty, jeśli ten sam
    # gość ma nowszą, nieanonimizowaną rezerwację.
    selected_ids = set(termin_ids)

    def profile_hashes(termin):
        keys = {_profile_identity_key(termin), _klucz(termin)}
        return {_profile_hash_key(key) for key in keys if key}

    candidate_hashes = set().union(*(profile_hashes(t) for t in terminy)) if terminy else set()
    if candidate_hashes:
        remaining_hashes = set()
        for other in db.query(models.Termin).all():
            if other.id not in selected_ids:
                remaining_hashes.update(profile_hashes(other))
        delete_hashes = candidate_hashes - remaining_hashes
        if delete_hashes:
            db.query(models.ProfilGoscia).filter(
                models.ProfilGoscia.klucz_hash.in_(delete_hashes)
            ).delete(synchronize_session=False)
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
            }.items()
            if getattr(t, field, None) != target
        }
        t.nazwisko = _ANON
        t.telefon = None
        t.notatka = None
        if hasattr(t, "email"):
            t.email = None
        for w in db.query(models.WiadomoscImprezy).filter_by(termin_id=t.id).all():
            db.delete(w)                 # wątek ustaleń portalu — treść bywa z PII
        for z in db.query(models.KpZadatek).filter_by(termin_id=t.id).all():
            z.nazwisko = None
            z.opis = _ANON               # wolny tekst z nazwiskiem gościa
        if audit_before is not None:
            reservation_audit.add_reservation_audit(
                db,
                termin=t,
                action="edit",
                actor=actor,
                reason=reason,
                before=audit_before,
                after=t,
                pii_changed=pii_changed,
            )
        n += 1
    return n


class KluczIn(BaseModel):
    klucz: str


@router.get("/api/rodo/eksport-gosc")
def eksport_gosc(request: Request, klucz: str = Query(...), db: Session = Depends(get_db),
                 admin: models.User = Depends(require_admin)):
    """Art. 15/20: eksport wszystkich rezerwacji/imprez gościa (JSON) po kluczu z listy CRM."""
    terminy = _terminy_goscia(db, klucz)
    if not terminy:
        raise HTTPException(404, "Nie znaleziono danych dla podanego klucza.")
    _audyt(db, admin, "rodo_eksport_gosc", _referencja_goscia(klucz), request)
    db.commit()
    return {"klucz": klucz, "liczba_rekordow": len(terminy),
            "rezerwacje": [_wpis(t) for t in sorted(terminy, key=lambda x: x.data)]}


@router.post("/api/rodo/anonimizuj-gosc")
def anonimizuj_gosc(dane: KluczIn, request: Request, db: Session = Depends(get_db),
                    admin: models.User = Depends(require_admin)):
    """Art. 17 (prawo do bycia zapomnianym): anonimizacja PII gościa we wszystkich rekordach."""
    terminy = _terminy_goscia(db, dane.klucz)
    if not terminy:
        raise HTTPException(404, "Nie znaleziono danych dla podanego klucza.")
    n = _anonimizuj(db, terminy, actor=admin, reason="guest_request")
    _audyt(
        db, admin, "rodo_anonimizuj_gosc", _referencja_goscia(dane.klucz), request,
    )
    db.commit()
    return {"zanonimizowano": n}


@router.post("/api/rodo/retencja")
def retencja(request: Request, miesiace: int = Query(24, ge=1), db: Session = Depends(get_db),
             admin: models.User = Depends(require_admin)):
    """Art. 5 ust.1 lit.e (ograniczenie przechowywania): anonimizacja PII rezerwacji ZAMKNIĘTYCH
    starszych niż `miesiace`. Data/status/kwoty (nie-PII) zostają do statystyk. Idempotentne."""
    prog = date.today() - timedelta(days=30 * int(miesiace))
    terminy = db.query(models.Termin).filter(
        models.Termin.data < prog, models.Termin.status.in_(_ZAMKNIETE)).all()
    terminy = [t for t in terminy if t.nazwisko != _ANON]   # pomiń już zanonimizowane
    n = _anonimizuj(db, terminy, actor=admin, reason="system_automation")
    _audyt(db, admin, "rodo_retencja", f"starsze niż {prog}", request)
    db.commit()
    return {"zanonimizowano": n, "prog": str(prog), "miesiace": int(miesiace)}
