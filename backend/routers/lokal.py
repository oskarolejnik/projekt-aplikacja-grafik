"""Router: konfiguracja lokalu — white-label / branding + flagi modułów + parametry.

Wydzielone z main.py (Rec#5 audytu — dekompozycja monolitu). Ścieżki URL bez zmian (1:1).
Autoryzacja: /api/lokal/branding jest publiczny (whitelist w role_guard), /api/lokal/config
tylko dla admina (egzekwuje middleware).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import schemas
import reservation_communication
from database import get_db
from deps import get_lokal_config

router = APIRouter()


@router.get("/api/lokal/branding", response_model=schemas.LokalBrandingOut)
def lokal_branding(db: Session = Depends(get_db)):
    """Publiczny branding (nazwa/logo/kolor) — do strony logowania / PWA. Bez logowania."""
    return get_lokal_config(db)


@router.get("/api/lokal/config", response_model=schemas.LokalConfigOut)
def lokal_config_get(db: Session = Depends(get_db)):
    """Pełna konfiguracja lokalu (tylko admin — wymusza middleware)."""
    return get_lokal_config(db)


@router.put("/api/lokal/config", response_model=schemas.LokalConfigOut)
def lokal_config_update(data: schemas.LokalConfigIn, db: Session = Depends(get_db)):
    """Częściowa aktualizacja konfiguracji lokalu (admin) — zmienia tylko podane pola."""
    updates = data.model_dump(exclude_unset=True)
    if "rezerwacje_przypomnienie_h" in updates:
        reservation_communication.acquire_planner_configuration_lock(db)
    cfg = get_lokal_config(db)
    reminder_before = int(cfg.rezerwacje_przypomnienie_h or 0)
    for pole, wartosc in updates.items():
        setattr(cfg, pole, wartosc)
    if (
        "rezerwacje_przypomnienie_h" in updates
        and int(cfg.rezerwacje_przypomnienie_h or 0) != reminder_before
    ):
        reservation_communication.reconfigure_reminders(db, cfg=cfg)
    db.commit(); db.refresh(cfg)
    return cfg
