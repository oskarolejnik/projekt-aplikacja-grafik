"""Router: samoobsługowe zakładanie lokali + panel floty (instancja-matka).

Publiczny tor (za bramką PROVISIONING_ENABLED): kreator na landingu woła
POST /api/online/nowy-lokal → matka stawia nową instancję (provisioning.py)
i oddaje URL, pod którym świeży kreator zakłada konto właściciela.
GET /api/online/nowy-lokal/status mówi frontowi, czy samoobsługa jest dostępna.

Panel operatora: GET /api/flota (admin) — rejestr instancji ze stanem procesów
(zalążek „panelu super-admina nad flotą" z audytu CTO).
"""

import logging
import secrets
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

import cennik
import integracje
import models
import provisioning
from auth import hash_password, require_admin
from database import get_db
from deps import utcnow_naive
from ratelimit import zuzyj_kwote
from validators import sprawdz_email, sprawdz_haslo

router = APIRouter()
logger = logging.getLogger(__name__)

NOWY_LOKAL_LIMIT_IP_DZIENNY = 3

# Pakiet z cennika (?plan=pro) → tier subskrypcji świeżej instancji.
PLAN_NA_TIER = {"darmowy": "free", "basic": "basic", "pro": "pro", "premium": "premium"}


class NowyLokalIn(BaseModel):
    nazwa_lokalu: str
    email: Optional[str] = None
    plan: Optional[str] = None


@router.get("/api/online/nowy-lokal/status")
def status_samoobslugi():
    """Publiczne: czy ta instalacja przyjmuje samoobsługowe zakładanie lokali."""
    if not provisioning.wlaczony():
        return {"enabled": False}
    zajete = len(provisioning.wczytaj_rejestr())
    return {"enabled": True, "wolne_miejsca": max(0, provisioning.LIMIT_FLOTY - zajete)}


@router.post("/api/online/nowy-lokal", status_code=201)
def nowy_lokal(dane: NowyLokalIn, request: Request):
    """Publiczne: stawia nową instancję lokalu i zwraca jej adres (pełna samoobsługa)."""
    if not provisioning.wlaczony():
        raise HTTPException(503, "Samoobsługowe zakładanie lokali jest wyłączone na tej instalacji.")
    nazwa = (dane.nazwa_lokalu or "").strip()
    if len(nazwa) < 3:
        raise HTTPException(400, "Podaj nazwę lokalu (min. 3 znaki).")
    ip = request.client.host if request.client else "?"
    if not zuzyj_kwote(f"nowy-lokal:{ip}", str(date.today()), NOWY_LOKAL_LIMIT_IP_DZIENNY):
        raise HTTPException(429, "Zbyt wiele lokali z tego adresu dzisiaj — spróbuj jutro.")
    tier = PLAN_NA_TIER.get((dane.plan or "").strip().lower())
    try:
        wpis = provisioning.utworz_instancje(nazwa, dane.email, host=request.url.hostname or "127.0.0.1", tier=tier)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    return {"slug": wpis["slug"], "url": wpis["url"], "nazwa": wpis["nazwa"]}


# ── Tor z płatnością: kreator → checkout → auto-provision konta + instancji ──────

class RejestracjaIn(BaseModel):
    """Kreator na matce: dane właściciela + wybrany plan. Konto + instancja powstają
    DOPIERO po opłaceniu (rejestracja czeka ze statusem 'oczekuje')."""
    email: str
    haslo: str
    nazwa_lokalu: str
    plan: str
    typ_lokalu: Optional[str] = None
    moduly: Optional[dict] = None


@router.post("/api/online/rejestracja", status_code=201)
def rejestracja(dane: RejestracjaIn, request: Request, db: Session = Depends(get_db)):
    """Publiczne: kreator zapisuje rejestrację oczekującą na płatność i zwraca link do checkoutu.
    Hasło hashowane TU (na matce, bcrypt) — plaintext nie opuszcza tego procesu."""
    if not provisioning.wlaczony():
        raise HTTPException(503, "Samoobsługowe zakładanie lokali jest wyłączone na tej instalacji.")
    # Walidacja PRZED limitem — literówka nie zużywa dziennego limitu zakładania lokali.
    email = sprawdz_email(dane.email)
    sprawdz_haslo(dane.haslo)
    nazwa = (dane.nazwa_lokalu or "").strip()
    if len(nazwa) < 3:
        raise HTTPException(400, "Podaj nazwę lokalu (min. 3 znaki).")
    tier = PLAN_NA_TIER.get((dane.plan or "").strip().lower())
    if not tier:
        raise HTTPException(400, "Wybierz pakiet (darmowy, basic, pro lub premium).")
    ip = request.client.host if request.client else "?"
    if not zuzyj_kwote(f"rejestracja:{ip}", str(date.today()), NOWY_LOKAL_LIMIT_IP_DZIENNY):
        raise HTTPException(429, "Zbyt wiele prób z tego adresu dzisiaj — spróbuj jutro.")
    netto = cennik.cena_netto(tier)
    external_id = secrets.token_urlsafe(24)
    rej = models.RejestracjaLokalu(
        email=email, haslo_hash=hash_password(dane.haslo), nazwa=nazwa,
        typ_lokalu=dane.typ_lokalu, moduly=dane.moduly, tier=tier, netto=netto,
        status="oczekuje", external_id=external_id, utworzono_at=utcnow_naive(),
    )
    db.add(rej)
    db.commit()
    # Link do checkoutu: sandbox (lokalny) teraz; realna bramka (Stripe/P24) później przez flagę.
    provider = "api" if integracje.skonfigurowane("platnosci") else "sandbox"
    return {"external_id": external_id, "plan": tier, "brutto": cennik.brutto(netto),
            "link": f"/?rejestracja-oplac={external_id}", "provider": provider}


@router.post("/api/online/rejestracja/{external_id}/oplac")
def rejestracja_oplac(external_id: str, request: Request, db: Session = Depends(get_db)):
    """Sandbox: potwierdzenie płatności → provisioning instancji z gotowym adminem i aktywną
    subskrypcją. IDEMPOTENTNE: podwójne wywołanie nie stawia drugiej instancji (klucz: status)."""
    rej = db.query(models.RejestracjaLokalu).filter_by(external_id=external_id).first()
    if rej is None:
        raise HTTPException(404, "Nie znaleziono rejestracji.")
    if rej.status == "zrealizowana":
        return {"status": "zrealizowana", "url": rej.url, "slug": rej.slug}
    # Atomowe „zajęcie": tylko jeden request przechodzi 'oczekuje' → 'przetwarzanie' (guard 2× klik).
    zajete = db.query(models.RejestracjaLokalu).filter(
        models.RejestracjaLokalu.external_id == external_id,
        models.RejestracjaLokalu.status == "oczekuje",
    ).update({"status": "przetwarzanie"})
    db.commit()
    if not zajete:
        db.refresh(rej)
        if rej.status == "zrealizowana":
            return {"status": "zrealizowana", "url": rej.url, "slug": rej.slug}
        raise HTTPException(409, "Rejestracja jest już przetwarzana — poczekaj chwilę.")
    konfiguracja = {"typ_lokalu": rej.typ_lokalu}
    if rej.moduly:
        konfiguracja.update(rej.moduly)
    try:
        wpis = provisioning.utworz_instancje(
            rej.nazwa, host=request.url.hostname or "127.0.0.1", tier=rej.tier,
            admin_email=rej.email, admin_haslo_hash=rej.haslo_hash, konfiguracja=konfiguracja)
    except RuntimeError as e:
        rej.status = "blad"
        db.commit()
        raise HTTPException(503, str(e))
    rej.status, rej.slug, rej.url = "zrealizowana", wpis["slug"], wpis["url"]
    rej.zrealizowano_at = utcnow_naive()
    db.commit()
    return {"status": "zrealizowana", "url": wpis["url"], "slug": wpis["slug"]}


@router.get("/api/online/rejestracja/{external_id}")
def rejestracja_status(external_id: str, db: Session = Depends(get_db)):
    """Polling po powrocie z checkoutu: status + URL gotowej instancji."""
    rej = db.query(models.RejestracjaLokalu).filter_by(external_id=external_id).first()
    if rej is None:
        raise HTTPException(404, "Nie znaleziono rejestracji.")
    return {"status": rej.status, "url": rej.url, "plan": rej.tier}


@router.get("/api/flota")
def flota(admin: models.User = Depends(require_admin)):
    """Panel operatora: instancje floty + żywy stan subskrypcji (pakiet/status/ważność)
    zaciągany z każdej instancji, z licznikami wg pakietu i statusu."""
    return provisioning.flota_z_pulsem()
