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
from deps import utcnow_naive, modul_aktywny

router = APIRouter()


def _wymagaj_rezerwacje(db: Session = Depends(get_db)):
    """Zadatki są częścią modułu rezerwacji (Pro+) — spójne gating z resztą rezerwacji."""
    if not modul_aktywny(db, "modul_rezerwacje"):
        raise HTTPException(403, "Moduł rezerwacji jest niedostępny w tym planie — odblokujesz go w pakiecie Pro.")


def _out(p: models.Platnosc) -> dict:
    return {"id": p.id, "termin_id": p.termin_id, "kwota": p.kwota, "status": p.status,
            "provider": p.provider, "external_id": p.external_id, "link": p.link,
            "utworzono_at": p.utworzono_at.isoformat() if p.utworzono_at else None,
            "oplacono_at": p.oplacono_at.isoformat() if p.oplacono_at else None}


@router.post("/api/platnosci", status_code=201, dependencies=[Depends(_wymagaj_rezerwacje)])
def platnosc_utworz(dane: schemas.PlatnoscIn, db: Session = Depends(get_db)):
    """Tworzy płatność zadatku i zwraca link do zapłaty (sandbox albo realna bramka)."""
    if (dane.kwota or 0) <= 0:
        raise HTTPException(400, "Kwota zadatku musi być dodatnia.")
    return _out(platnosci.utworz_platnosc(db, dane.termin_id, dane.kwota))


@router.get("/api/platnosci", dependencies=[Depends(_wymagaj_rezerwacje)])
def platnosc_lista(termin_id: int = Query(None), db: Session = Depends(get_db)):
    """Lista płatności (opcjonalnie filtr po rezerwacji). Najnowsze najpierw."""
    q = db.query(models.Platnosc)
    if termin_id:
        q = q.filter(models.Platnosc.termin_id == termin_id)
    return [_out(p) for p in q.order_by(models.Platnosc.id.desc()).all()]


@router.post("/api/platnosci/{pid}/oplacona", dependencies=[Depends(_wymagaj_rezerwacje)])
def platnosc_oplac(pid: int, db: Session = Depends(get_db)):
    """Ręczne oznaczenie płatności jako opłaconej (admin). Idempotentne. Zapisuje kwotę na
    Termin.zadatek — jedno źródło prawdy dla UI rezerwacji."""
    p = db.get(models.Platnosc, pid)
    if p is None:
        raise HTTPException(404, "Płatność nie istnieje.")
    if p.status != "oplacona":
        p.status = "oplacona"
        p.oplacono_at = utcnow_naive()
        if p.termin_id:
            t = db.get(models.Termin, p.termin_id)
            if t is not None:
                t.zadatek = p.kwota
        db.commit(); db.refresh(p)
    return _out(p)
