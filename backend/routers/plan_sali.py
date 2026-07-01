"""Router: plan sali — wizualne rozmieszczenie stolików + status na wybrany dzień (roadmapa v1.5).

Łączy stoliki (moduł rezerwacji) z rezerwacjami dnia (Termin rodzaj=stolik) i zwraca
gotowy plan: pozycje + status każdego stolika (wolny/zarezerwowany/potwierdzony/nieaktywny)
z listą rezerwacji. Edycja układu (pozycje) i podgląd — tylko admin (wymusza role_guard).
"""

from collections import defaultdict
from datetime import date, time
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

import models
import schemas
from database import get_db

router = APIRouter()

_AKTYWNE = ("rezerwacja", "potwierdzona")


def _rez_out(t: models.Termin) -> dict:
    return {
        "id": t.id,
        "nazwisko": t.nazwisko,
        "godz_od": t.godz_od.strftime("%H:%M") if t.godz_od else None,
        "godz_do": t.godz_do.strftime("%H:%M") if t.godz_do else None,
        "liczba_osob": t.liczba_osob,
        "status": t.status,
        "kanal": t.kanal,
    }


@router.get("/api/plan-sali")
def plan_sali(data: date = Query(None), db: Session = Depends(get_db)):
    """Plan sali na dzień `data` (domyślnie dziś): stoliki + pozycje + status z rezerwacji."""
    dzien = data or date.today()
    stoliki = db.query(models.Stolik).order_by(models.Stolik.kolejnosc, models.Stolik.id).all()
    rezerwacje = db.query(models.Termin).filter(
        models.Termin.rodzaj == "stolik",
        models.Termin.data == dzien,
        models.Termin.status.in_(_AKTYWNE),
    ).all()

    per_stolik = defaultdict(list)
    for t in rezerwacje:
        if t.stolik_id:
            per_stolik[t.stolik_id].append(t)

    # Live obłożenie z POS (Gastro) — po numerze rewiru; podpięte tylko dla stolików z rewir_nr.
    stan = {s.rewir_nr: s for s in db.query(models.StanStolow).all()}

    out = []
    for s in stoliki:
        rez = sorted(per_stolik.get(s.id, []), key=lambda t: (t.godz_od or time.min))
        if not s.aktywny:
            status = "nieaktywny"
        elif any(t.status == "potwierdzona" for t in rez):
            status = "potwierdzony"
        elif rez:
            status = "zarezerwowany"
        else:
            status = "wolny"
        sn = stan.get(s.rewir_nr) if s.rewir_nr else None
        live = None if sn is None else {
            "otwarte": sn.otwarte or 0,
            "zajete": (sn.otwarte or 0) > 0,
            "aktualizacja": sn.zaktualizowano_at.isoformat() if sn.zaktualizowano_at else None,
        }
        out.append({
            "id": s.id, "nazwa": s.nazwa, "strefa": s.strefa, "pojemnosc": s.pojemnosc,
            "aktywny": s.aktywny, "plan_x": s.plan_x, "plan_y": s.plan_y, "rewir_nr": s.rewir_nr,
            "status": status, "rezerwacje": [_rez_out(t) for t in rez], "live": live,
        })

    strefy = sorted({s.strefa for s in stoliki if s.strefa})
    return {
        "data": str(dzien),
        "strefy": strefy,
        "stoliki": out,
        "podsumowanie": {
            "wolne": sum(1 for s in out if s["status"] == "wolny"),
            "zarezerwowane": sum(1 for s in out if s["status"] in ("zarezerwowany", "potwierdzony")),
            "nieaktywne": sum(1 for s in out if s["status"] == "nieaktywny"),
            "zajete_live": sum(1 for s in out if s["live"] and s["live"]["zajete"]),
        },
    }


@router.put("/api/plan-sali/pozycje", status_code=200)
def zapisz_pozycje(pozycje: List[schemas.PlanPozycjaIn], db: Session = Depends(get_db)):
    """Zapis układu (pozycji) stolików na planie — admin. Pozycja w % (0–100)."""
    by_id = {s.id: s for s in db.query(models.Stolik).all()}
    zapisane = 0
    for p in pozycje:
        s = by_id.get(p.id)
        if s is None:
            continue
        s.plan_x = max(0, min(100, int(p.plan_x)))
        s.plan_y = max(0, min(100, int(p.plan_y)))
        zapisane += 1
    db.commit()
    return {"zapisane": zapisane}
