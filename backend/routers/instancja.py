"""Router: operacje instancji SaaS — subskrypcja/licencja, dziennik audytu, status integracji.

Wydzielone z main.py (Rec#5 audytu — dekompozycja monolitu). Ścieżki URL bez zmian (1:1).
Autoryzacja (admin) i degradacja READ_ONLY są egzekwowane przez middleware role_guard w main.
"""

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

import integracje
import models
import schemas
from database import get_db
from deps import get_subskrypcja, subskrypcja_aktywna

router = APIRouter()


def _subskrypcja_out(s, db) -> dict:
    return {"tier": s.tier, "status": s.status,
            "data_od": s.data_od.isoformat() if s.data_od else None,
            "data_do": s.data_do.isoformat() if s.data_do else None,
            "uwagi": s.uwagi, "aktywna": subskrypcja_aktywna(db)}


def _audit_out(w: models.AuditLog) -> dict:
    return {"id": w.id, "ts": w.ts.isoformat() if w.ts else None, "login": w.login,
            "akcja": w.akcja, "zasob": w.zasob, "pracownik_id": w.pracownik_id,
            "ip": w.ip, "szczegoly": w.szczegoly}


@router.get("/api/subskrypcja")
def subskrypcja_get(db: Session = Depends(get_db)):
    """Status subskrypcji/licencji instancji (admin). `aktywna` = czy zapisy są dozwolone."""
    return _subskrypcja_out(get_subskrypcja(db), db)


@router.put("/api/subskrypcja")
def subskrypcja_update(data: schemas.SubskrypcjaIn, db: Session = Depends(get_db)):
    """Zmiana subskrypcji (admin) — status/tier/daty. Ustawienie statusu na aktywna odblokowuje zapisy."""
    s = get_subskrypcja(db)
    for pole, wartosc in data.model_dump(exclude_unset=True).items():
        setattr(s, pole, wartosc)
    db.commit(); db.refresh(s)
    return _subskrypcja_out(s, db)


@router.get("/api/integracje/status")
def integracje_status():
    """Status integracji instancji (które mają komplet sekretów) — bez wartości sekretów. Admin."""
    return {"integracje": integracje.status()}


@router.get("/api/audit-log")
def audit_log_list(od: date = Query(None), do: date = Query(None), login: str = Query(None),
                   akcja: str = Query(None), limit: int = Query(200), db: Session = Depends(get_db)):
    """Dziennik audytu dostępu do danych wrażliwych (RODO). Tylko admin (wymusza middleware).
    Filtry: zakres dat (od/do), login, akcja; najnowsze najpierw."""
    q = db.query(models.AuditLog)
    if od:
        q = q.filter(models.AuditLog.ts >= datetime(od.year, od.month, od.day))
    if do:
        q = q.filter(models.AuditLog.ts < datetime(do.year, do.month, do.day) + timedelta(days=1))
    if login:
        q = q.filter(models.AuditLog.login == login)
    if akcja:
        q = q.filter(models.AuditLog.akcja == akcja)
    q = q.order_by(models.AuditLog.id.desc()).limit(max(1, min(int(limit), 1000)))
    return [_audit_out(w) for w in q.all()]
