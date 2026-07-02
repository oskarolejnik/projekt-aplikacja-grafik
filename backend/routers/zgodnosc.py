"""Router: zgodność lokalu — badania załogi + terminy lokalu (roadmapa v2, oś B).

Jedna tabela `dokumenty_zgodnosci` na dwa byty:
  • dokument PRACOWNIKA (badania sanitarno-epidemiologiczne, medycyna pracy, BHP) — pracownik_id ustawione,
  • termin LOKALU (koncesja alkoholowa + raty 31.01/31.05/30.09, przeglądy gaśnic/wentylacji) — pracownik_id NULL.

Statusy liczone z dni do wygaśnięcia: przeterminowane (<0) / pilne (≤14) / wkrótce (≤30) / ok.
`blokuje_grafik=True` ⇒ po dacie ważności auto-przydział pomija pracownika (hak w algorithm.py),
a GET /api/zgodnosc/blokady zasila ostrzeżenia w UI grafiku. Wszystko admin-only.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import models
import schemas
from auth import require_admin
from database import get_db
from deps import utcnow_naive

router = APIRouter()

DOZWOLONE_TYPY = {"badania_sanepid", "medycyna_pracy", "szkolenie_bhp", "koncesja", "przeglad", "inne"}

# Progi alertów (dni do wygaśnięcia) — spójne z opisem w ROADMAP.md (30/14/przeterminowane).
PROG_WKROTCE = 30
PROG_PILNE = 14


def _status(dni: int) -> str:
    if dni < 0:
        return "przeterminowane"
    if dni <= PROG_PILNE:
        return "pilne"
    if dni <= PROG_WKROTCE:
        return "wkrotce"
    return "ok"


def _out(d: models.DokumentZgodnosci, dzis: date) -> dict:
    dni = (d.data_waznosci - dzis).days
    prac = d.pracownik
    return {
        "id": d.id,
        "pracownik_id": d.pracownik_id,
        "pracownik": f"{prac.imie} {prac.nazwisko}" if prac else None,
        "typ": d.typ,
        "nazwa": d.nazwa,
        "data_waznosci": str(d.data_waznosci),
        "notatka": d.notatka,
        "blokuje_grafik": bool(d.blokuje_grafik),
        "dni": dni,
        "status": _status(dni),
    }


def _waliduj(dane: schemas.DokumentZgodnosciIn, db: Session) -> None:
    if not dane.nazwa.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Podaj nazwę dokumentu/terminu.")
    if dane.typ not in DOZWOLONE_TYPY:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Nieznany typ — dozwolone: {', '.join(sorted(DOZWOLONE_TYPY))}.")
    if dane.pracownik_id is not None and db.get(models.Pracownik, dane.pracownik_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pracownik nie istnieje.")


@router.post("/api/zgodnosc", status_code=201)
def dodaj_dokument(dane: schemas.DokumentZgodnosciIn, _admin: models.User = Depends(require_admin),
                   db: Session = Depends(get_db)):
    _waliduj(dane, db)
    d = models.DokumentZgodnosci(
        pracownik_id=dane.pracownik_id, typ=dane.typ, nazwa=dane.nazwa.strip(),
        data_waznosci=dane.data_waznosci, notatka=(dane.notatka or None),
        blokuje_grafik=bool(dane.blokuje_grafik), utworzono_at=utcnow_naive())
    db.add(d); db.commit(); db.refresh(d)
    return _out(d, date.today())


@router.get("/api/zgodnosc")
def lista_dokumentow(_admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    """Wszystkie dokumenty/terminy, najbliższe wygaśnięcia na górze (przeterminowane pierwsze)."""
    dzis = date.today()
    dok = db.query(models.DokumentZgodnosci).order_by(models.DokumentZgodnosci.data_waznosci.asc()).all()
    return [_out(d, dzis) for d in dok]


@router.get("/api/zgodnosc/alerty")
def alerty(_admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    """Skrót do Pulpitu/odznaki: liczba pozycji per status + pozycje wymagające uwagi (dni ≤ 30)."""
    dzis = date.today()
    dok = db.query(models.DokumentZgodnosci).all()
    pozycje = sorted((_out(d, dzis) for d in dok), key=lambda x: x["dni"])
    wymagajace = [p for p in pozycje if p["dni"] <= PROG_WKROTCE]
    return {
        "przeterminowane": sum(1 for p in pozycje if p["status"] == "przeterminowane"),
        "pilne": sum(1 for p in pozycje if p["status"] == "pilne"),
        "wkrotce": sum(1 for p in pozycje if p["status"] == "wkrotce"),
        "pozycje": wymagajace,
    }


@router.get("/api/zgodnosc/blokady")
def blokady_grafiku(_admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    """Pracownicy z przeterminowanym dokumentem blokującym grafik (na DZIŚ) — do ostrzeżeń w UI.
    Zwraca {pracownik_id: [nazwy dokumentów]}."""
    dzis = date.today()
    dok = db.query(models.DokumentZgodnosci).filter(
        models.DokumentZgodnosci.pracownik_id.isnot(None),
        models.DokumentZgodnosci.blokuje_grafik == True,  # noqa: E712
        models.DokumentZgodnosci.data_waznosci < dzis,
    ).all()
    out: dict[int, list[str]] = {}
    for d in dok:
        out.setdefault(d.pracownik_id, []).append(d.nazwa)
    return out


@router.put("/api/zgodnosc/{did}")
def edytuj_dokument(did: int, dane: schemas.DokumentZgodnosciIn,
                    _admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    d = db.get(models.DokumentZgodnosci, did)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dokument nie istnieje.")
    _waliduj(dane, db)
    d.pracownik_id = dane.pracownik_id
    d.typ = dane.typ
    d.nazwa = dane.nazwa.strip()
    d.data_waznosci = dane.data_waznosci
    d.notatka = dane.notatka or None
    d.blokuje_grafik = bool(dane.blokuje_grafik)
    db.commit(); db.refresh(d)
    return _out(d, date.today())


@router.delete("/api/zgodnosc/{did}", status_code=204)
def usun_dokument(did: int, _admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    d = db.get(models.DokumentZgodnosci, did)
    if d is not None:
        db.delete(d); db.commit()
