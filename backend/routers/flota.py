"""Router: samoobsługowe zakładanie lokali + panel floty (instancja-matka).

Publiczny tor (za bramką PROVISIONING_ENABLED): kreator na landingu woła
POST /api/online/nowy-lokal → matka stawia nową instancję (provisioning.py)
i oddaje URL, pod którym świeży kreator zakłada konto właściciela.
GET /api/online/nowy-lokal/status mówi frontowi, czy samoobsługa jest dostępna.

Panel operatora: GET /api/flota (admin) — rejestr instancji ze stanem procesów
(zalążek „panelu super-admina nad flotą" z audytu CTO).
"""

import hashlib
import logging
import re
import secrets
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
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

class KartaIn(BaseModel):
    """Dane karty z kreatora (TRYB TESTOWY/sandbox). Matka liczy z nich odcisk (fingerprint) do
    dedup i ostatnie 4 cyfry, a numeru (PAN) NIE przechowuje. ⚠ PCI DSS: serwer NIE przyjmuje CVC
    (przechowywanie/logowanie CVC jest zabronione — Req. 3.2). Docelowo: tokenizacja po stronie
    klienta (Stripe Elements) — PAN nigdy nie dociera do serwera, fingerprint/token daje Stripe."""
    numer: str
    exp_miesiac: Optional[int] = None
    exp_rok: Optional[int] = None


class RejestracjaIn(BaseModel):
    """Kreator na matce: dane właściciela + wybór planu. DARMOWY → instancja od razu (bez karty).
    PŁATNY (basic/pro/premium) → wymaga `karta`: 14 dni za darmo, po nich AUTO-OBCIĄŻENIE planu;
    jedna karta = jeden trial (dedup). `trial=True` = stary tor operatorski (premium bez karty)."""
    email: str
    haslo: str
    nazwa_lokalu: str
    plan: Optional[str] = None
    trial: bool = False
    karta: Optional[KartaIn] = None
    typ_lokalu: Optional[str] = None
    moduly: Optional[dict] = None


def _przetworz_karte(karta: "KartaIn") -> tuple[str, str, str]:
    """SANDBOX: z danych karty testowej liczy (fingerprint, ostatnie4, token). Numer (PAN) NIE
    jest nigdzie zapisywany — tylko sha256 (dedup) + 4 cyfry + udawany token. Realny Stripe
    podmienia to na tokenizację po stronie klienta. Walidacja: długość, data ważności, CVC."""
    numer = re.sub(r"\D", "", karta.numer or "")
    if not (12 <= len(numer) <= 19):
        raise HTTPException(400, "Podaj prawidłowy numer karty.")
    m = int(karta.exp_miesiac or 0)
    r = int(karta.exp_rok or 0)
    if r < 100:
        r += 2000
    dzis = date.today()
    if not (1 <= m <= 12) or r < dzis.year or (r == dzis.year and m < dzis.month):
        raise HTTPException(400, "Sprawdź datę ważności karty.")
    fingerprint = hashlib.sha256(numer.encode()).hexdigest()
    return fingerprint, numer[-4:], "sandbox_" + secrets.token_hex(12)


@router.post("/api/online/rejestracja", status_code=201)
def rejestracja(dane: RejestracjaIn, request: Request, db: Session = Depends(get_db)):
    """Publiczne: stawia instancję OD RAZU. DARMOWY → aktywny plan Free (bez karty). PŁATNY →
    wymaga karty: 14-dniowy trial, po którym instancja sama się obciąża i przechodzi na plan.
    Jedna karta = jeden trial (dedup po odcisku). Hasło i token karty poza plaintextem/argv."""
    if not provisioning.wlaczony():
        raise HTTPException(503, "Samoobsługowe zakładanie lokali jest wyłączone na tej instalacji.")
    # Walidacja PRZED limitem — literówka nie zużywa dziennego limitu zakładania lokali.
    email = sprawdz_email(dane.email)
    sprawdz_haslo(dane.haslo)
    nazwa = (dane.nazwa_lokalu or "").strip()
    if len(nazwa) < 3:
        raise HTTPException(400, "Podaj nazwę lokalu (min. 3 znaki).")
    plan = (dane.plan or "").strip().lower()
    if not dane.trial:
        tier = PLAN_NA_TIER.get(plan)
        if not tier:
            raise HTTPException(400, "Wybierz pakiet (darmowy, basic, pro lub premium).")
    ip = request.client.host if request.client else "?"
    if not zuzyj_kwote(f"rejestracja:{ip}", str(date.today()), NOWY_LOKAL_LIMIT_IP_DZIENNY):
        raise HTTPException(429, "Zbyt wiele prób z tego adresu dzisiaj — spróbuj jutro.")
    haslo_hash = hash_password(dane.haslo)
    host = request.url.hostname or "127.0.0.1"
    konfiguracja = {"typ_lokalu": dane.typ_lokalu}
    if dane.moduly:
        konfiguracja.update(dane.moduly)

    def _postaw(rej: models.RejestracjaLokalu, **prov) -> dict:
        """Zapis rejestracji + provisioning instancji; ustawia zrealizowana/blad. Wspólne dla
        wszystkich torów, żeby uniknąć powtórzeń i rozjazdu obsługi błędu."""
        db.add(rej); db.commit()
        try:
            wpis = provisioning.utworz_instancje(
                nazwa, host=host, admin_email=email, admin_haslo_hash=haslo_hash,
                konfiguracja=konfiguracja, **prov)
        except RuntimeError as e:
            rej.status = "blad"; db.commit()
            raise HTTPException(503, str(e))
        rej.status, rej.slug, rej.url = "zrealizowana", wpis["slug"], wpis["url"]
        rej.zrealizowano_at = utcnow_naive()
        db.commit()
        return wpis

    external_id = secrets.token_urlsafe(24)

    # 1) Stary tor operatorski: trial pełnego Premium bez karty (CLI/enterprise); po nim → Free.
    if dane.trial:
        rej = models.RejestracjaLokalu(
            email=email, haslo_hash=haslo_hash, nazwa=nazwa, typ_lokalu=dane.typ_lokalu,
            moduly=dane.moduly, tier="premium", netto=0.0, status="przetwarzanie",
            external_id=external_id, utworzono_at=utcnow_naive())
        wpis = _postaw(rej, tier="premium", trial=True)
        return {"tryb": "trial", "status": "zrealizowana", "url": wpis["url"], "slug": wpis["slug"]}

    # 2) Plan DARMOWY: instancja od razu, aktywny Free, bez karty i bez triala.
    if tier == "free":
        rej = models.RejestracjaLokalu(
            email=email, haslo_hash=haslo_hash, nazwa=nazwa, typ_lokalu=dane.typ_lokalu,
            moduly=dane.moduly, tier="free", netto=0.0, status="przetwarzanie",
            external_id=external_id, utworzono_at=utcnow_naive())
        wpis = _postaw(rej, tier="free")
        return {"tryb": "darmowy", "status": "zrealizowana", "url": wpis["url"], "slug": wpis["slug"], "plan": "free"}

    # 3) Plan PŁATNY: karta wymagana → 14 dni za darmo → auto-obciążenie po trialu. Dedup po karcie.
    if dane.karta is None:
        raise HTTPException(400, "Podaj dane karty — plan płatny zaczyna się od 14 dni za darmo, "
                                 "obciążymy ją dopiero po 14 dniach (możesz anulować wcześniej).")
    fingerprint, ostatnie4, token = _przetworz_karte(dane.karta)
    uzyta = db.query(models.RejestracjaLokalu).filter(
        models.RejestracjaLokalu.karta_fingerprint == fingerprint,
        models.RejestracjaLokalu.status.in_(("przetwarzanie", "zrealizowana")),
    ).first()
    if uzyta is not None:
        raise HTTPException(409, "Ta karta była już użyta do rozpoczęcia okresu próbnego.")
    rej = models.RejestracjaLokalu(
        email=email, haslo_hash=haslo_hash, nazwa=nazwa, typ_lokalu=dane.typ_lokalu,
        moduly=dane.moduly, tier=tier, netto=cennik.cena_netto(tier), status="przetwarzanie",
        external_id=external_id, karta_token=token, karta_ostatnie4=ostatnie4,
        karta_fingerprint=fingerprint, utworzono_at=utcnow_naive())
    try:
        wpis = _postaw(rej, tier=tier, trial=True, karta_token=token, karta_ostatnie4=ostatnie4)
    except IntegrityError:
        # Wyścig: druga równoległa rejestracja z tą samą kartą — częściowy UNIQUE odrzucił zapis.
        db.rollback()
        raise HTTPException(409, "Ta karta była już użyta do rozpoczęcia okresu próbnego.")
    return {"tryb": "trial-karta", "status": "zrealizowana", "url": wpis["url"], "slug": wpis["slug"],
            "plan": tier, "karta_ostatnie4": ostatnie4}


@router.post("/api/online/rejestracja/{external_id}/oplac")
def rejestracja_oplac(external_id: str, request: Request, db: Session = Depends(get_db)):
    """Sandbox: potwierdzenie płatności → provisioning instancji z gotowym adminem i aktywną
    subskrypcją. IDEMPOTENTNE: podwójne wywołanie nie stawia drugiej instancji (klucz: status)."""
    # Z podłączoną bramką „opłacenie" musi potwierdzać podpisany webhook, nie to ręczne wywołanie.
    if integracje.skonfigurowane("platnosci"):
        raise HTTPException(403, "Potwierdzenie płatności następuje przez webhook bramki, nie ręcznie.")
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
