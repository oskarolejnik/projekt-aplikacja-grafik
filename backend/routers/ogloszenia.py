"""Router: ogłoszenia zespołowe — tablica komunikatów manager→pracownicy (roadmapa v1.5).

Manager (admin) tworzy/edytuje/usuwa ogłoszenia pod `/api/ogloszenia` (require_admin) i widzi
kto potwierdził przeczytanie. Pracownik czyta aktywne ogłoszenia pod `/api/me/ogloszenia`
(role_guard przepuszcza nie-admina tylko na /api/me/*) i potwierdza przeczytanie.

Na nowe ogłoszenie idzie best-effort push do wszystkich (reuse push.py, no-op bez VAPID).
"""

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import models
import schemas
import push
from auth import get_current_user, require_admin
from database import get_db
from deps import utcnow_naive

router = APIRouter()
logger = logging.getLogger(__name__)


def _wymagaj_pracownika(user: models.User) -> int:
    if not user.pracownik_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Konto nie jest powiązane z pracownikiem.")
    return user.pracownik_id


def _liczba_odbiorcow(db: Session) -> int:
    """Liczba aktywnych pracowników = audytorium ogłoszenia (mianownik „X z Y przeczytało")."""
    return db.query(models.Pracownik).filter(models.Pracownik.aktywny == True).count()  # noqa: E712


def _out(o: models.Ogloszenie, *, przeczytane=None, liczba_potwierdzen=None, liczba_odbiorcow=None) -> dict:
    d = {
        "id": o.id, "tytul": o.tytul, "tresc": o.tresc, "autor": o.autor_login,
        "przypiete": bool(o.przypiete),
        "wazne_do": str(o.wazne_do) if o.wazne_do else None,
        "utworzono_at": o.utworzono_at.isoformat() if o.utworzono_at else None,
    }
    if przeczytane is not None:
        d["przeczytane"] = przeczytane
    if liczba_potwierdzen is not None:
        d["liczba_potwierdzen"] = liczba_potwierdzen
    if liczba_odbiorcow is not None:
        d["liczba_odbiorcow"] = liczba_odbiorcow
    return d


# ─────────────────────────────────────────────────────────────────────────────
# Manager (admin): tworzenie / edycja / usuwanie / śledzenie odczytów
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/api/ogloszenia", status_code=201)
def utworz_ogloszenie(dane: schemas.OgloszenieIn, admin: models.User = Depends(require_admin),
                      db: Session = Depends(get_db)):
    if not dane.tytul.strip() or not dane.tresc.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Podaj tytuł i treść ogłoszenia.")
    o = models.Ogloszenie(
        tytul=dane.tytul.strip(), tresc=dane.tresc.strip(), autor_login=admin.login,
        przypiete=bool(dane.przypiete), wazne_do=dane.wazne_do, utworzono_at=utcnow_naive())
    db.add(o); db.commit(); db.refresh(o)
    try:
        push.wyslij_push(db, f"Ogłoszenie: {o.tytul}", o.tresc[:140], url="/")
    except Exception as e:  # noqa: BLE001
        logger.warning("Push ogłoszenia nie powiódł się: %s", e)
    return _out(o, liczba_potwierdzen=0, liczba_odbiorcow=_liczba_odbiorcow(db))


@router.get("/api/ogloszenia")
def lista_ogloszen(_admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    """Widok managera: wszystkie ogłoszenia (przypięte i najnowsze na górze) + licznik odczytów."""
    odbiorcy = _liczba_odbiorcow(db)
    oglosz = db.query(models.Ogloszenie).order_by(
        models.Ogloszenie.przypiete.desc(), models.Ogloszenie.utworzono_at.desc()).all()
    return [_out(o, liczba_potwierdzen=len(o.potwierdzenia), liczba_odbiorcow=odbiorcy) for o in oglosz]


@router.get("/api/ogloszenia/{oid}/potwierdzenia")
def kto_potwierdzil(oid: int, _admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    """Manager: kto (i kiedy) potwierdził przeczytanie danego ogłoszenia."""
    o = db.get(models.Ogloszenie, oid)
    if o is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ogłoszenie nie istnieje.")
    out = []
    for p in sorted(o.potwierdzenia, key=lambda x: x.potwierdzono_at or utcnow_naive()):
        prac = db.get(models.Pracownik, p.pracownik_id)
        out.append({"pracownik": (f"{prac.imie} {prac.nazwisko}" if prac else "—"),
                    "potwierdzono_at": p.potwierdzono_at.isoformat() if p.potwierdzono_at else None})
    return out


@router.put("/api/ogloszenia/{oid}", status_code=200)
def edytuj_ogloszenie(oid: int, dane: schemas.OgloszenieIn, _admin: models.User = Depends(require_admin),
                      db: Session = Depends(get_db)):
    o = db.get(models.Ogloszenie, oid)
    if o is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ogłoszenie nie istnieje.")
    if not dane.tytul.strip() or not dane.tresc.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Podaj tytuł i treść ogłoszenia.")
    o.tytul = dane.tytul.strip(); o.tresc = dane.tresc.strip()
    o.przypiete = bool(dane.przypiete); o.wazne_do = dane.wazne_do
    db.commit(); db.refresh(o)
    return _out(o, liczba_potwierdzen=len(o.potwierdzenia), liczba_odbiorcow=_liczba_odbiorcow(db))


@router.delete("/api/ogloszenia/{oid}", status_code=204)
def usun_ogloszenie(oid: int, _admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    o = db.get(models.Ogloszenie, oid)
    if o is not None:
        db.delete(o); db.commit()   # kaskada ORM usuwa potwierdzenia (cascade='all, delete-orphan')


# ─────────────────────────────────────────────────────────────────────────────
# Pracownik: odczyt aktywnych ogłoszeń + potwierdzenie przeczytania
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/api/me/ogloszenia")
def moje_ogloszenia(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Pracownik: aktywne ogłoszenia (nie po dacie ważności), przypięte na górze, z flagą
    `przeczytane` dla mnie. Zwraca też `nieprzeczytane` (do odznaki na zakładce)."""
    prac_id = _wymagaj_pracownika(user)
    dzis = date.today()
    oglosz = db.query(models.Ogloszenie).filter(
        (models.Ogloszenie.wazne_do.is_(None)) | (models.Ogloszenie.wazne_do >= dzis)
    ).order_by(models.Ogloszenie.przypiete.desc(), models.Ogloszenie.utworzono_at.desc()).all()
    moje = {p.ogloszenie_id for p in db.query(models.OgloszeniePotwierdzenie).filter(
        models.OgloszeniePotwierdzenie.pracownik_id == prac_id).all()}
    lista = [_out(o, przeczytane=(o.id in moje)) for o in oglosz]
    return {"ogloszenia": lista, "nieprzeczytane": sum(1 for x in lista if not x["przeczytane"])}


@router.post("/api/me/ogloszenia/{oid}/potwierdz", status_code=204)
def potwierdz_przeczytanie(oid: int, user: models.User = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    """Pracownik potwierdza przeczytanie (idempotentnie — ponowne wywołanie nic nie zmienia)."""
    prac_id = _wymagaj_pracownika(user)
    if db.get(models.Ogloszenie, oid) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ogłoszenie nie istnieje.")
    istnieje = db.query(models.OgloszeniePotwierdzenie).filter_by(
        ogloszenie_id=oid, pracownik_id=prac_id).first()
    if istnieje:
        return
    db.add(models.OgloszeniePotwierdzenie(
        ogloszenie_id=oid, pracownik_id=prac_id, potwierdzono_at=utcnow_naive()))
    try:
        db.commit()
    except Exception:
        db.rollback()   # wyścig (unique) — ktoś już potwierdził; idempotentnie OK
