"""Router: uniwersalne API danych POS — tor A integracji (docs/POS-INTEGRACJA.md).

POST /api/pos/utarg-dnia  — dzienny utarg (wspólny mianownik: ręczny wpis, CSV,
                            agent z driverem, konektor chmurowy); upsert po (data, zrodlo);
                            liczba_rachunkow zasila stoliki_historia → prognozę ruchu/obsady.
POST /api/pos/heartbeat   — telemetria agenta (wersja, driver, capabilities, błędy).
GET  /api/pos/utarg-dnia  — odczyt utargów (admin przez role_guard).
GET  /api/pos/status      — zdrowie agentów + ostatnie utargi per źródło (admin).

Autoryzacja POST-ów (trasy publiczne w role_guard): stały token agenta
(X-RCP-Token lub Authorization: Bearer <token agenta>) ALBO JWT administratora —
dzięki temu formularz w panelu i agent piszą w ten sam endpoint.
"""

import hashlib
import logging
import secrets
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

import auth
import models
from database import get_db
from deps import get_lokal_config, token_agenta_ok, utcnow_naive

router = APIRouter()
logger = logging.getLogger(__name__)

ZNANE_ZRODLA_RECZNE = ("reczny", "csv")


class UtargDzienIn(BaseModel):
    data: date
    netto: float
    gotowka: Optional[float] = None
    karta: Optional[float] = None
    liczba_rachunkow: Optional[int] = None

    @field_validator("netto", "gotowka", "karta")
    @classmethod
    def _nieujemne(cls, v):
        if v is not None and v < 0:
            raise ValueError("Kwota nie może być ujemna.")
        return v

    @field_validator("liczba_rachunkow")
    @classmethod
    def _rachunki(cls, v):
        if v is not None and v < 0:
            raise ValueError("Liczba rachunków nie może być ujemna.")
        return v


class UtargPaczkaIn(BaseModel):
    zrodlo: str = "reczny"
    dni: List[UtargDzienIn]

    @field_validator("zrodlo")
    @classmethod
    def _zrodlo(cls, v):
        v = (v or "").strip().lower()
        if not v or len(v) > 32:
            raise ValueError("Nieprawidłowe źródło.")
        return v

    @field_validator("dni")
    @classmethod
    def _dni(cls, v):
        if not v:
            raise ValueError("Pusta paczka.")
        if len(v) > 400:
            raise ValueError("Maksymalnie 400 dni w jednej paczce.")
        return v


class HeartbeatIn(BaseModel):
    driver: str
    wersja: Optional[str] = None
    capabilities: Optional[List[str]] = None
    ostatni_sync: Optional[datetime] = None
    bledy: Optional[List[str]] = None

    @field_validator("driver")
    @classmethod
    def _driver(cls, v):
        v = (v or "").strip()
        if not v or len(v) > 48:
            raise ValueError("Nieprawidłowy driver.")
        return v


def _wymagaj_agenta_lub_admina(request: Request, db: Session) -> str:
    """Zwraca 'agent' albo login admina; 401/403 gdy żadna ścieżka nie pasuje."""
    if token_agenta_ok(request, db):
        return "agent"
    naglowek = request.headers.get("authorization") or ""
    if naglowek.startswith("Bearer "):
        try:
            import jwt as _jwt
            payload = _jwt.decode(naglowek[7:], auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
            user = db.get(models.User, int(payload["sub"]))
            if user and user.aktywny and user.rola == "admin":
                return user.login
        except Exception:  # noqa: BLE001 — każdy zepsuty token = brak autoryzacji
            pass
    raise HTTPException(401, "Wymagany token agenta POS albo konto administratora.")


@router.post("/api/pos/utarg-dnia")
def utarg_dnia_ingest(dane: UtargPaczkaIn, request: Request, db: Session = Depends(get_db)):
    """Upsert dziennych utargów po (data, zrodlo). Idempotentne — agent może słać
    ten sam zakres wielokrotnie. liczba_rachunkow dodatkowo zasila stoliki_historia
    (prognoza ruchu/obsady), o ile dnia nie wypełnił już bogatszy strumień POS."""
    kto = _wymagaj_agenta_lub_admina(request, db)
    zapisane = 0
    for dz in dane.dni:
        wiersz = (db.query(models.UtargDnia)
                  .filter_by(data=dz.data, zrodlo=dane.zrodlo).first())
        if wiersz is None:
            wiersz = models.UtargDnia(data=dz.data, zrodlo=dane.zrodlo)
            db.add(wiersz)
        wiersz.netto = round(float(dz.netto), 2)
        wiersz.gotowka = None if dz.gotowka is None else round(float(dz.gotowka), 2)
        wiersz.karta = None if dz.karta is None else round(float(dz.karta), 2)
        wiersz.liczba_rachunkow = dz.liczba_rachunkow
        wiersz.aktualizacja_at = utcnow_naive()
        zapisane += 1

        # Ruch dzienny do prognozy: uzupełniamy TYLKO brakujące dni — agent Gastro
        # pisze stoliki_historia bezpośrednio i jego dane są bogatsze (nie nadpisujemy).
        if dz.liczba_rachunkow is not None:
            hist = db.get(models.StolikiHistoria, dz.data)
            if hist is None:
                db.add(models.StolikiHistoria(data=dz.data, liczba=dz.liczba_rachunkow))
            elif dane.zrodlo in ZNANE_ZRODLA_RECZNE and (hist.liczba or 0) == 0:
                hist.liczba = dz.liczba_rachunkow
    db.commit()
    logger.info("POS utarg-dnia: %s dni ze źródła '%s' (%s).", zapisane, dane.zrodlo, kto)
    return {"zapisane": zapisane, "zrodlo": dane.zrodlo}


@router.post("/api/pos/heartbeat")
def heartbeat(dane: HeartbeatIn, request: Request, db: Session = Depends(get_db)):
    """Telemetria agenta — upsert po driverze. Panel pokazuje zdrowie integracji."""
    _wymagaj_agenta_lub_admina(request, db)
    wiersz = db.query(models.AgentStatus).filter_by(driver=dane.driver).first()
    if wiersz is None:
        wiersz = models.AgentStatus(driver=dane.driver)
        db.add(wiersz)
    wiersz.wersja = dane.wersja
    wiersz.capabilities = dane.capabilities
    wiersz.ostatni_sync = dane.ostatni_sync or utcnow_naive()
    wiersz.bledy = (dane.bledy or [])[:20] or None
    wiersz.aktualizacja_at = utcnow_naive()
    db.commit()
    return {"ok": True, "driver": dane.driver}


@router.get("/api/pos/utarg-dnia")
def utarg_dnia_lista(start: date = Query(...), end: date = Query(...),
                     db: Session = Depends(get_db),
                     admin: models.User = Depends(auth.require_admin)):
    rows = (db.query(models.UtargDnia)
            .filter(models.UtargDnia.data >= start, models.UtargDnia.data <= end)
            .order_by(models.UtargDnia.data.desc(), models.UtargDnia.zrodlo.asc()).all())
    return {"dni": [{
        "data": str(r.data), "zrodlo": r.zrodlo, "netto": r.netto, "gotowka": r.gotowka,
        "karta": r.karta, "liczba_rachunkow": r.liczba_rachunkow,
        "aktualizacja_at": r.aktualizacja_at.isoformat() if r.aktualizacja_at else None,
    } for r in rows]}


@router.get("/api/pos/status")
def pos_status(db: Session = Depends(get_db), admin: models.User = Depends(auth.require_admin)):
    """Zdrowie integracji POS: agenty (heartbeat) + świeżość utargu per źródło + token."""
    agenty = [{
        "driver": a.driver, "wersja": a.wersja, "capabilities": a.capabilities,
        "ostatni_sync": a.ostatni_sync.isoformat() if a.ostatni_sync else None,
        "bledy": a.bledy or [],
    } for a in db.query(models.AgentStatus).order_by(models.AgentStatus.driver).all()]
    ostatnie = {}
    for r in db.query(models.UtargDnia).order_by(models.UtargDnia.data.desc()).limit(200).all():
        ostatnie.setdefault(r.zrodlo, str(r.data))
    cfg = get_lokal_config(db)
    return {"agenty": agenty, "ostatni_utarg": ostatnie,
            "token_aktywny": bool(cfg.pos_token_hash),
            "token_od": cfg.pos_token_od.isoformat() if cfg.pos_token_od else None}


@router.post("/api/pos/token", status_code=201)
def wygeneruj_token_agenta(db: Session = Depends(get_db),
                           admin: models.User = Depends(auth.require_admin)):
    """Generuje token agenta POS (kreator „Podłącz POS"). Plaintext zwracany JEDEN raz —
    w bazie zostaje wyłącznie hash SHA-256. Nowy token unieważnia poprzedni."""
    token = secrets.token_urlsafe(32)
    cfg = get_lokal_config(db)
    cfg.pos_token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    cfg.pos_token_od = utcnow_naive()
    db.commit()
    logger.info("Wygenerowano token agenta POS (admin: %s).", admin.login)
    return {"token": token, "utworzono": cfg.pos_token_od.isoformat()}


@router.delete("/api/pos/token", status_code=204)
def uniewaznij_token_agenta(db: Session = Depends(get_db),
                            admin: models.User = Depends(auth.require_admin)):
    """Unieważnia token agenta — agent traci dostęp od następnego żądania.
    (Env RCP_INGEST_TOKEN, jeśli ustawiony, pozostaje w mocy — to osobny, stały kanał.)"""
    cfg = get_lokal_config(db)
    cfg.pos_token_hash = None
    cfg.pos_token_od = None
    db.commit()
    logger.info("Unieważniono token agenta POS (admin: %s).", admin.login)
