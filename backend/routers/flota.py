"""Router: samoobsługowe zakładanie lokali + panel floty (instancja-matka).

Publiczny tor (za bramką PROVISIONING_ENABLED): kreator na landingu woła
POST /api/online/nowy-lokal → matka stawia nową instancję (provisioning.py)
i oddaje URL, pod którym świeży kreator zakłada konto właściciela.
GET /api/online/nowy-lokal/status mówi frontowi, czy samoobsługa jest dostępna.

Panel operatora: GET /api/flota (admin) — rejestr instancji ze stanem procesów
(zalążek „panelu super-admina nad flotą" z audytu CTO).
"""

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

import models
import provisioning
from auth import require_admin
from ratelimit import zuzyj_kwote

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


@router.get("/api/flota")
def flota(admin: models.User = Depends(require_admin)):
    """Panel operatora: instancje floty + żywy stan subskrypcji (pakiet/status/ważność)
    zaciągany z każdej instancji, z licznikami wg pakietu i statusu."""
    return provisioning.flota_z_pulsem()
