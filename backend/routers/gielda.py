"""Router: giełda wymiany zmian (roadmapa v1.5).

Pracownik wystawia SWÓJ przydział (PrzydzialZmiany) do przejęcia, inny wykwalifikowany
pracownik go przejmuje, a manager (admin) akceptuje → przydział zostaje przepięty na
przejmującego. Ścieżki pracownicze pod `/api/me/gielda/*` (role_guard przepuszcza
nie-admina tylko tam); decyzje managera pod `/api/gielda/*` (require_admin).

Cykl statusu: otwarta → zajeta → zaakceptowana | (anulowana z otwarta/zajeta).
Odrzucenie przejęcia przez managera cofa ofertę do „otwarta" (nie kasuje oferty).
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


def _opis_zmiany(o: "models.OfertaZmiany") -> str:
    """Krótki opis zmiany do treści powiadomienia (data · godz · stanowisko)."""
    p = o.przydzial
    if not p:
        return "zmiana"
    czesci = [str(p.data)]
    if p.godz_od:
        czesci.append(p.godz_od.strftime("%H:%M"))
    if p.stanowisko:
        czesci.append(p.stanowisko.nazwa)
    return " · ".join(czesci)


def _imie(prac: "models.Pracownik") -> str:
    return f"{prac.imie} {prac.nazwisko}" if prac else "Pracownik"

# Statusy, w których oferta jest wciąż „w grze" (blokują drugą ofertę na ten sam przydział).
_AKTYWNE = ("otwarta", "zajeta")


def _wymagaj_pracownika(user: models.User) -> int:
    """Zwraca pracownik_id zalogowanego lub 400, gdy konto nie jest powiązane z pracownikiem."""
    if not user.pracownik_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Konto nie jest powiązane z pracownikiem.")
    return user.pracownik_id


def _dwie_zmiany_koliduja(db: Session, pracownik_id: int, data, godz_od, pomin_przydzial_id=None) -> bool:
    """Czy pracownik ma już zmianę tego samego dnia o tej samej godzinie startu (podwójne obsadzenie)."""
    q = db.query(models.PrzydzialZmiany).filter(
        models.PrzydzialZmiany.pracownik_id == pracownik_id,
        models.PrzydzialZmiany.data == data,
        models.PrzydzialZmiany.godz_od == godz_od,
    )
    if pomin_przydzial_id is not None:
        q = q.filter(models.PrzydzialZmiany.id != pomin_przydzial_id)
    return db.query(q.exists()).scalar()


def _serializuj(o: models.OfertaZmiany) -> dict:
    p = o.przydzial
    return {
        "id": o.id,
        "status": o.status,
        "powod": o.powod,
        "utworzono_at": o.utworzono_at.isoformat() if o.utworzono_at else None,
        "zajeto_at": o.zajeto_at.isoformat() if o.zajeto_at else None,
        "rozpatrzono_at": o.rozpatrzono_at.isoformat() if o.rozpatrzono_at else None,
        "przydzial_id": o.przydzial_id,
        "data": str(p.data) if p else None,
        "godz_od": p.godz_od.strftime("%H:%M") if (p and p.godz_od) else None,
        "rewir": p.rewir if p else None,
        "stanowisko": (p.stanowisko.nazwa if (p and p.stanowisko) else None),
        "stanowisko_id": (p.stanowisko_id if p else None),
        "wystawiajacy_id": o.wystawiajacy_id,
        "wystawiajacy": (f"{o.wystawiajacy.imie} {o.wystawiajacy.nazwisko}" if o.wystawiajacy else None),
        "przejmujacy_id": o.przejmujacy_id,
        "przejmujacy": (f"{o.przejmujacy.imie} {o.przejmujacy.nazwisko}" if o.przejmujacy else None),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Pracownik: wystawianie / przeglądanie / przejmowanie / anulowanie
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/api/me/gielda/oferty", status_code=201)
def wystaw_oferte(dane: schemas.OfertaZmianyIn,
                  user: models.User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """Pracownik wystawia SWÓJ (przyszły) przydział na giełdę."""
    prac_id = _wymagaj_pracownika(user)
    p = db.get(models.PrzydzialZmiany, dane.przydzial_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Przydział nie istnieje.")
    if p.pracownik_id != prac_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "To nie jest Twoja zmiana.")
    if p.data < date.today():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nie można wystawić minionej zmiany.")
    istnieje = db.query(models.OfertaZmiany).filter(
        models.OfertaZmiany.przydzial_id == p.id,
        models.OfertaZmiany.status.in_(_AKTYWNE),
    ).first()
    if istnieje:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ta zmiana jest już wystawiona na giełdzie.")
    o = models.OfertaZmiany(
        przydzial_id=p.id, wystawiajacy_id=prac_id,
        powod=(dane.powod or None), status="otwarta", utworzono_at=utcnow_naive(),
    )
    db.add(o); db.commit(); db.refresh(o)
    # Best-effort push do wykwalifikowanych kolegów (poza wystawiającym) o nowej dostępnej zmianie.
    try:
        for prac in (p.stanowisko.uprawnieni if p.stanowisko else []):
            if prac.id != prac_id:
                push.wyslij_push_do_pracownika(db, prac.id, "Giełda: nowa zmiana do przejęcia", _opis_zmiany(o))
    except Exception as e:  # noqa: BLE001
        logger.warning("Push giełdy (wystaw) nie powiódł się: %s", e)
    return _serializuj(o)


@router.get("/api/me/gielda/przydzialy")
def moje_przydzialy_do_wystawienia(user: models.User = Depends(get_current_user),
                                   db: Session = Depends(get_db)):
    """Przyszłe zmiany zalogowanego — kandydaci do wystawienia na giełdę.
    `wystawiony`=True, gdy zmiana ma już aktywną ofertę (nie da się wystawić drugi raz)."""
    prac_id = _wymagaj_pracownika(user)
    przydzialy = db.query(models.PrzydzialZmiany).filter(
        models.PrzydzialZmiany.pracownik_id == prac_id,
        models.PrzydzialZmiany.data >= date.today(),
    ).order_by(models.PrzydzialZmiany.data.asc(), models.PrzydzialZmiany.godz_od.asc()).all()
    aktywne_przydzialy = {
        o.przydzial_id for o in db.query(models.OfertaZmiany).filter(
            models.OfertaZmiany.status.in_(_AKTYWNE)).all()
    }
    return [{
        "przydzial_id": p.id,
        "data": str(p.data),
        "godz_od": p.godz_od.strftime("%H:%M") if p.godz_od else None,
        "stanowisko": (p.stanowisko.nazwa if p.stanowisko else None),
        "rewir": p.rewir,
        "wystawiony": p.id in aktywne_przydzialy,
    } for p in przydzialy]


@router.get("/api/me/gielda/oferty")
def moje_oferty(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Widok pracownika: otwarte oferty, które mogę przejąć (mam kwalifikację, nie moje)
    + moje własne wystawione oferty. Zwraca {dostepne, moje}."""
    prac_id = _wymagaj_pracownika(user)
    prac = db.get(models.Pracownik, prac_id)
    moje_stanowiska = {s.id for s in (prac.kwalifikacje if prac else [])}

    oferty = db.query(models.OfertaZmiany).all()
    dostepne, moje = [], []
    for o in oferty:
        if o.wystawiajacy_id == prac_id:
            if o.status in _AKTYWNE or o.status == "zaakceptowana":
                moje.append(_serializuj(o))
            continue
        # Cudze: pokazuj otwarte, dla których mam kwalifikację na dane stanowisko.
        if o.status == "otwarta" and o.przydzial and o.przydzial.stanowisko_id in moje_stanowiska:
            dostepne.append(_serializuj(o))
    dostepne.sort(key=lambda x: (x["data"] or "", x["godz_od"] or ""))
    moje.sort(key=lambda x: (x["data"] or "", x["godz_od"] or ""))
    return {"dostepne": dostepne, "moje": moje}


@router.post("/api/me/gielda/oferty/{oid}/przejmij", status_code=200)
def przejmij_oferte(oid: int, user: models.User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """Wykwalifikowany pracownik zgłasza chęć przejęcia otwartej oferty (→ status zajeta)."""
    prac_id = _wymagaj_pracownika(user)
    o = db.get(models.OfertaZmiany, oid)
    if o is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Oferta nie istnieje.")
    if o.status != "otwarta":
        raise HTTPException(status.HTTP_409_CONFLICT, "Oferta nie jest już otwarta.")
    if o.wystawiajacy_id == prac_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nie możesz przejąć własnej zmiany.")
    prac = db.get(models.Pracownik, prac_id)
    stan_id = o.przydzial.stanowisko_id if o.przydzial else None
    if stan_id not in {s.id for s in (prac.kwalifikacje if prac else [])}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Brak kwalifikacji na to stanowisko.")
    if _dwie_zmiany_koliduja(db, prac_id, o.przydzial.data, o.przydzial.godz_od):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Masz już zmianę tego dnia o tej godzinie.")
    o.status = "zajeta"; o.przejmujacy_id = prac_id; o.zajeto_at = utcnow_naive()
    db.commit(); db.refresh(o)
    try:
        opis = _opis_zmiany(o)
        push.wyslij_push_do_adminow(db, "Giełda: oferta do akceptacji", f"{_imie(prac)} chce przejąć: {opis}")
        push.wyslij_push_do_pracownika(db, o.wystawiajacy_id, "Giełda: ktoś chce przejąć Twoją zmianę", opis)
    except Exception as e:  # noqa: BLE001
        logger.warning("Push giełdy (przejmij) nie powiódł się: %s", e)
    return _serializuj(o)


@router.post("/api/me/gielda/oferty/{oid}/anuluj", status_code=200)
def anuluj_oferte(oid: int, user: models.User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """Wystawiający wycofuje swoją ofertę (z otwarta/zajeta → anulowana)."""
    prac_id = _wymagaj_pracownika(user)
    o = db.get(models.OfertaZmiany, oid)
    if o is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Oferta nie istnieje.")
    if o.wystawiajacy_id != prac_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "To nie jest Twoja oferta.")
    if o.status not in _AKTYWNE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Oferty nie można już anulować.")
    o.status = "anulowana"; o.rozpatrzono_at = utcnow_naive()
    db.commit(); db.refresh(o)
    return _serializuj(o)


# ─────────────────────────────────────────────────────────────────────────────
# Manager (admin): przegląd wszystkich + decyzja
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/api/gielda/oferty")
def wszystkie_oferty(status_filtr: str = None, _admin: models.User = Depends(require_admin),
                     db: Session = Depends(get_db)):
    """Widok managera: wszystkie oferty (opcjonalny filtr statusu), najnowsze na górze."""
    q = db.query(models.OfertaZmiany)
    if status_filtr:
        q = q.filter(models.OfertaZmiany.status == status_filtr)
    oferty = q.order_by(models.OfertaZmiany.utworzono_at.desc()).all()
    return [_serializuj(o) for o in oferty]


@router.post("/api/gielda/oferty/{oid}/akceptuj", status_code=200)
def akceptuj_oferte(oid: int, _admin: models.User = Depends(require_admin),
                    db: Session = Depends(get_db)):
    """Manager akceptuje przejęcie → przydział zostaje przepięty na przejmującego."""
    o = db.get(models.OfertaZmiany, oid)
    if o is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Oferta nie istnieje.")
    if o.status != "zajeta":
        raise HTTPException(status.HTTP_409_CONFLICT, "Oferta nie czeka na akceptację.")
    p = o.przydzial
    if p is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Przydział już nie istnieje.")
    if _dwie_zmiany_koliduja(db, o.przejmujacy_id, p.data, p.godz_od, pomin_przydzial_id=p.id):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Przejmujący ma już zmianę tego dnia o tej godzinie.")
    p.pracownik_id = o.przejmujacy_id
    o.status = "zaakceptowana"; o.rozpatrzono_at = utcnow_naive()
    db.commit(); db.refresh(o)
    try:
        opis = _opis_zmiany(o)
        przej = db.get(models.Pracownik, o.przejmujacy_id)
        push.wyslij_push_do_pracownika(db, o.przejmujacy_id, "Giełda: przejęcie zaakceptowane", opis)
        push.wyslij_push_do_pracownika(db, o.wystawiajacy_id, "Giełda: Twoja zmiana przejęta", f"{_imie(przej)} przejmuje: {opis}")
    except Exception as e:  # noqa: BLE001
        logger.warning("Push giełdy (akceptuj) nie powiódł się: %s", e)
    return _serializuj(o)


@router.post("/api/gielda/oferty/{oid}/odrzuc", status_code=200)
def odrzuc_oferte(oid: int, _admin: models.User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    """Manager odrzuca konkretne przejęcie → oferta wraca na giełdę (status otwarta)."""
    o = db.get(models.OfertaZmiany, oid)
    if o is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Oferta nie istnieje.")
    if o.status != "zajeta":
        raise HTTPException(status.HTTP_409_CONFLICT, "Oferta nie czeka na decyzję.")
    bylo_przejmujacy = o.przejmujacy_id
    o.status = "otwarta"; o.przejmujacy_id = None; o.zajeto_at = None
    db.commit(); db.refresh(o)
    try:
        push.wyslij_push_do_pracownika(db, bylo_przejmujacy, "Giełda: przejęcie odrzucone",
                                       f"Oferta wróciła na giełdę: {_opis_zmiany(o)}")
    except Exception as e:  # noqa: BLE001
        logger.warning("Push giełdy (odrzuc) nie powiódł się: %s", e)
    return _serializuj(o)
