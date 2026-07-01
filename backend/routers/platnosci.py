"""Router: płatności zadatków online (Rec#7 audytu). Admin (wymusza role_guard).

Tworzenie płatności (link do zapłaty), lista/status per rezerwacja, ręczne oznaczenie opłacenia.
Webhook realnej bramki (Stripe/P24) dopina się osobno (publiczny + weryfikacja podpisu).
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import models
import platnosci
import schemas
from database import get_db
from deps import utcnow_naive

router = APIRouter()


def _out(p: models.Platnosc) -> dict:
    return {"id": p.id, "termin_id": p.termin_id, "kwota": p.kwota, "status": p.status,
            "provider": p.provider, "external_id": p.external_id, "link": p.link,
            "utworzono_at": p.utworzono_at.isoformat() if p.utworzono_at else None,
            "oplacono_at": p.oplacono_at.isoformat() if p.oplacono_at else None}


@router.post("/api/platnosci", status_code=201)
def platnosc_utworz(dane: schemas.PlatnoscIn, db: Session = Depends(get_db)):
    """Tworzy płatność zadatku i zwraca link do zapłaty (sandbox albo realna bramka)."""
    if (dane.kwota or 0) <= 0:
        raise HTTPException(400, "Kwota zadatku musi być dodatnia.")
    return _out(platnosci.utworz_platnosc(db, dane.termin_id, dane.kwota))


@router.get("/api/platnosci")
def platnosc_lista(termin_id: int = Query(None), db: Session = Depends(get_db)):
    """Lista płatności (opcjonalnie filtr po rezerwacji). Najnowsze najpierw."""
    q = db.query(models.Platnosc)
    if termin_id:
        q = q.filter(models.Platnosc.termin_id == termin_id)
    return [_out(p) for p in q.order_by(models.Platnosc.id.desc()).all()]


@router.post("/api/platnosci/{pid}/oplacona")
def platnosc_oplac(pid: int, db: Session = Depends(get_db)):
    """Ręczne oznaczenie płatności jako opłaconej (admin). Idempotentne."""
    p = db.get(models.Platnosc, pid)
    if p is None:
        raise HTTPException(404, "Płatność nie istnieje.")
    if p.status != "oplacona":
        p.status = "oplacona"
        p.oplacono_at = utcnow_naive()
        db.commit(); db.refresh(p)
    return _out(p)
