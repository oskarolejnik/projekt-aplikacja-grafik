"""Router: portal klienta imprezy (roadmapa v2, TOP 2 — oś weselna).

Publiczna, tokenowa strona dla pary młodej / organizatora (`/?impreza=TOKEN`).
Publiczne endpointy pod /api/online/ (allowlista role_guard — jak widget rezerwacji):
podgląd karty imprezy, aktualizacja liczby gości (trafia do karty i — dla terminów
sparowanych z Imprezą — do wymagań obsady), wątek ustaleń z pisemnym śladem oraz
harmonogram wpłat (odczyt zadatków). Koniec telefonów „to ile w końcu osób?".

Bezpieczeństwo: token = secrets.token_urlsafe(24) na Terminie (regeneracja unieważnia
stary link), publiczne POST-y objęte dziennym limitem per IP (ratelimit.zuzyj_kwote),
treści przycinane, zero PII ponad to, co klient i tak zna (własna impreza).
"""

import logging
import secrets
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
import ratelimit
from auth import require_admin
from database import get_db
from deps import utcnow_naive

router = APIRouter()
logger = logging.getLogger(__name__)

PORTAL_LIMIT_IP_DZIENNY = 120     # publiczne POST-y (wiadomości/goście) per IP na dobę
MAKS_TRESC = 2000
MAKS_GOSCIE = 2000
STATUSY_AKTYWNE = ("rezerwacja", "potwierdzona")


class WiadomoscIn(BaseModel):
    tresc: str


class GoscieIn(BaseModel):
    liczba_osob: int


def _termin_po_tokenie(token: str, db: Session) -> models.Termin:
    t = db.query(models.Termin).filter(models.Termin.portal_token == token).first() if token else None
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nieprawidłowy lub nieaktualny link portalu.")
    return t


def _limit_ip(request: Request) -> None:
    ip = (request.client.host if request.client else "?")
    if not ratelimit.zuzyj_kwote(f"portal-imprezy:{ip}", str(date.today()), PORTAL_LIMIT_IP_DZIENNY):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Za dużo operacji — spróbuj jutro.")


def _wiadomosc_out(w: models.WiadomoscImprezy) -> dict:
    return {"id": w.id, "autor": w.autor, "tresc": w.tresc,
            "utworzono_at": w.utworzono_at.isoformat() if w.utworzono_at else None}


def _dodaj_wiadomosc(db: Session, termin_id: int, autor: str, tresc: str) -> models.WiadomoscImprezy:
    w = models.WiadomoscImprezy(termin_id=termin_id, autor=autor, tresc=tresc[:MAKS_TRESC],
                                utworzono_at=utcnow_naive())
    db.add(w)
    return w


def _watek(db: Session, termin_id: int) -> list:
    rows = db.query(models.WiadomoscImprezy).filter(
        models.WiadomoscImprezy.termin_id == termin_id
    ).order_by(models.WiadomoscImprezy.utworzono_at.asc(), models.WiadomoscImprezy.id.asc()).all()
    return [_wiadomosc_out(w) for w in rows]


def _suma_zadatkow_kp(db: Session, termin_id: int) -> float:
    return sum((z.kwota or 0) for z in
               db.query(models.KpZadatek).filter(models.KpZadatek.termin_id == termin_id).all())


def _sync_impreza(db: Session, t: models.Termin) -> None:
    """Termin z iCloud ma sparowaną Imprezę (obsada) — replika logiki z PUT /api/terminy,
    żeby zmiana liczby gości z portalu też odświeżyła wymagania obsady."""
    if not t.ical_uid:
        return
    imp = db.query(models.Impreza).filter(models.Impreza.sciezka_pliku == f"ical:{t.ical_uid}").first()
    if imp is not None:
        imp.liczba_osob = (t.liczba_osob or 0)


# ─────────────────────────────────────────────────────────────────────────────
# Admin: generowanie linku + wątek od strony lokalu
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/api/terminy/{termin_id}/portal")
def generuj_portal(termin_id: int, _admin: models.User = Depends(require_admin),
                   db: Session = Depends(get_db)):
    """Generuje (lub REGENERUJE — stary link przestaje działać) token portalu klienta."""
    t = db.get(models.Termin, termin_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Termin nie istnieje.")
    t.portal_token = secrets.token_urlsafe(24)
    db.commit(); db.refresh(t)
    return {"token": t.portal_token, "url": f"/?impreza={t.portal_token}"}


@router.delete("/api/terminy/{termin_id}/portal", status_code=204)
def wylacz_portal(termin_id: int, _admin: models.User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    t = db.get(models.Termin, termin_id)
    if t is not None and t.portal_token:
        t.portal_token = None
        db.commit()


@router.get("/api/terminy/{termin_id}/wiadomosci")
def watek_admin(termin_id: int, _admin: models.User = Depends(require_admin),
                db: Session = Depends(get_db)):
    if db.get(models.Termin, termin_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Termin nie istnieje.")
    return _watek(db, termin_id)


@router.post("/api/terminy/{termin_id}/wiadomosci", status_code=201)
def odpowiedz_lokalu(termin_id: int, dane: WiadomoscIn,
                     _admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.get(models.Termin, termin_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Termin nie istnieje.")
    if not dane.tresc.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pusta wiadomość.")
    w = _dodaj_wiadomosc(db, termin_id, "lokal", dane.tresc.strip())
    db.commit(); db.refresh(w)
    return _wiadomosc_out(w)


# ─────────────────────────────────────────────────────────────────────────────
# Publiczne (token) — strona klienta imprezy
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/api/online/imprezy/{token}")
def portal_dane(token: str, db: Session = Depends(get_db)):
    t = _termin_po_tokenie(token, db)
    cfg = db.query(models.LokalConfig).first()
    return {
        "lokal": (cfg.nazwa_lokalu if cfg else None) or "Lokal",
        "termin": {
            "data": str(t.data), "typ": t.typ, "sala": t.sala,
            "nazwisko": t.nazwisko, "liczba_osob": t.liczba_osob,
            "status": t.status,
            "zadatek": float(t.zadatek or 0),
            "zadatek_kp": _suma_zadatkow_kp(db, t.id),
            "edycja_gosci": t.status in STATUSY_AKTYWNE,
        },
        "wiadomosci": _watek(db, t.id),
    }


@router.put("/api/online/imprezy/{token}/goscie")
def portal_goscie(token: str, dane: GoscieIn, request: Request, db: Session = Depends(get_db)):
    _limit_ip(request)
    t = _termin_po_tokenie(token, db)
    if t.status not in STATUSY_AKTYWNE:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Impreza nie jest już aktywna — skontaktuj się z lokalem.")
    if not (1 <= dane.liczba_osob <= MAKS_GOSCIE):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Liczba gości: 1–{MAKS_GOSCIE}.")
    poprzednio = t.liczba_osob
    t.liczba_osob = dane.liczba_osob
    _sync_impreza(db, t)
    _dodaj_wiadomosc(db, t.id, "system",
                     f"Klient zaktualizował liczbę gości: {poprzednio or '—'} → {dane.liczba_osob}.")
    db.commit()
    if t.ical_uid:
        # Odśwież wymagania obsady dla terminów sparowanych z Imprezą (import leniwy —
        # helper żyje w main.py, a main importuje ten router; w runtime main jest już załadowany).
        from main import _odswiez_wymagania_imprez
        _odswiez_wymagania_imprez(db, t.data, t.data)
    return {"liczba_osob": t.liczba_osob}


@router.post("/api/online/imprezy/{token}/wiadomosci", status_code=201)
def portal_wiadomosc(token: str, dane: WiadomoscIn, request: Request, db: Session = Depends(get_db)):
    _limit_ip(request)
    t = _termin_po_tokenie(token, db)
    tresc = dane.tresc.strip()
    if not tresc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pusta wiadomość.")
    w = _dodaj_wiadomosc(db, t.id, "klient", tresc)
    db.commit(); db.refresh(w)
    return _wiadomosc_out(w)
