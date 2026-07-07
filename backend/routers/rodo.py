"""Router: RODO/GDPR — prawa podmiotu danych (art. 15/17/20) + retencja PII gości (art. 5 ust.1 e).

Admin-only (role_guard chroni całe /api/*, dodatkowo require_admin). PII gości (telefon/e-mail)
szyfrowane niedeterministycznie (EncryptedString) → dopasowanie gościa po ODSZYFROWANIU w Pythonie,
tak jak crm.py (nie da się GROUP BY po szyfrogramie). Każda operacja zostawia ślad w AuditLog.

Anonimizacja czyści nazwisko/telefon/e-mail/notatkę rezerwacji, wątki portalu (treść bywa z PII)
oraz opisy/nazwiska zadatków KP (wolny tekst z nazwiskiem). Statystyki (daty/kwoty/statusy)
zostają, więc raporty i scoring nie kłamią po usunięciu danych osobowych.
"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
from auth import require_admin
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


def _audyt(db, admin, akcja, zasob, request):
    try:
        ip = request.client.host if (request and request.client) else None
        db.add(models.AuditLog(ts=utcnow_naive(), user_id=getattr(admin, "id", None),
                               login=getattr(admin, "login", None), akcja=akcja, zasob=zasob, ip=ip))
        db.commit()
    except Exception:
        db.rollback()


def _wpis(t) -> dict:
    return {"id": t.id, "data": str(t.data), "rodzaj": getattr(t, "rodzaj", None), "typ": t.typ,
            "status": t.status, "nazwisko": t.nazwisko, "telefon": t.telefon,
            "email": getattr(t, "email", None), "notatka": t.notatka,
            "liczba_osob": t.liczba_osob, "sala": t.sala, "zadatek": t.zadatek}


def _anonimizuj(db, terminy) -> int:
    n = 0
    for t in terminy:
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
        n += 1
    db.commit()
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
    _audyt(db, admin, "rodo_eksport_gosc", klucz, request)
    return {"klucz": klucz, "liczba_rekordow": len(terminy),
            "rezerwacje": [_wpis(t) for t in sorted(terminy, key=lambda x: x.data)]}


@router.post("/api/rodo/anonimizuj-gosc")
def anonimizuj_gosc(dane: KluczIn, request: Request, db: Session = Depends(get_db),
                    admin: models.User = Depends(require_admin)):
    """Art. 17 (prawo do bycia zapomnianym): anonimizacja PII gościa we wszystkich rekordach."""
    terminy = _terminy_goscia(db, dane.klucz)
    if not terminy:
        raise HTTPException(404, "Nie znaleziono danych dla podanego klucza.")
    n = _anonimizuj(db, terminy)
    _audyt(db, admin, "rodo_anonimizuj_gosc", dane.klucz, request)
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
    n = _anonimizuj(db, terminy)
    _audyt(db, admin, "rodo_retencja", f"starsze niż {prog}", request)
    return {"zanonimizowano": n, "prog": str(prog), "miesiace": int(miesiace)}
