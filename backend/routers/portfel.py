"""Router: portfel pracownika (roadmapa v2, oś C — retencja załogi).

Pracownik widzi „zarobiłeś już X zł w tym miesiącu" (liczone z tych samych danych
RCP × stawki co raport wypłat — zero rozjazdów) i składa wniosek o zaliczkę do limitu
procentu bieżącego zarobku. Admin akceptuje/odrzuca jednym kliknięciem (celowany push
do pracownika), a zaakceptowane zaliczki miesiąca są potrącane w raporcie wypłat.

To workflow potrącenia, NIE kredytowanie (uwaga sędziów o EWA): lokal wypłaca z kasy
własne, już zarobione przez pracownika pieniądze — Lokalo tylko pilnuje limitu i śladu.
"""

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
import push
import raporty
from auth import get_current_user, require_admin
from database import get_db
from deps import utcnow_naive

router = APIRouter()
logger = logging.getLogger(__name__)

LIMIT_PROCENT = 50          # maks. suma zaliczek = tyle % bieżącego zarobku miesiąca
STATUSY_DECYZJI = ("zaakceptowana", "odrzucona")


class ZaliczkaIn(BaseModel):
    kwota: float


class DecyzjaIn(BaseModel):
    status: str


def _miesiac_str(rok: int, miesiac: int) -> str:
    return f"{rok}-{miesiac:02d}"


def _zaliczka_out(z: models.Zaliczka, pracownik: str = None) -> dict:
    d = {"id": z.id, "pracownik_id": z.pracownik_id, "miesiac": z.miesiac,
         "kwota": float(z.kwota or 0), "status": z.status,
         "wniosek_at": z.wniosek_at.isoformat() if z.wniosek_at else None,
         "decyzja_at": z.decyzja_at.isoformat() if z.decyzja_at else None}
    if pracownik is not None:
        d["pracownik"] = pracownik
    return d


def _zarobek_mtd(db: Session, pracownik_id: int, rok: int, miesiac: int) -> dict:
    """Zarobek narastająco (ta sama logika co raport wypłat — raporty.raport_godzin_miesiac)."""
    raport = raporty.raport_godzin_miesiac(db, rok, miesiac, tylko_pracownik_id=pracownik_id)
    moj = next((p for p in raport["pracownicy"] if p["pracownik_id"] == pracownik_id), None)
    return {"zarobek": float(moj["do_wyplaty"]) if moj else 0.0,
            "godziny": float(moj["suma_godzin"]) if moj else 0.0}


def _suma_zaliczek(db: Session, pracownik_id: int, mies: str, statusy) -> float:
    rows = db.query(models.Zaliczka).filter(
        models.Zaliczka.pracownik_id == pracownik_id,
        models.Zaliczka.miesiac == mies,
        models.Zaliczka.status.in_(statusy)).all()
    return sum(float(z.kwota or 0) for z in rows)


# ─────────────────────────────────────────────────────────────────────────────
# Pracownik: portfel + wnioski
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/api/me/portfel")
def moj_portfel(rok: int = Query(None), miesiac: int = Query(None),
                user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.pracownik_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Konto nie jest powiązane z pracownikiem.")
    dzis = date.today()
    rok = rok or dzis.year
    miesiac = miesiac or dzis.month
    mies = _miesiac_str(rok, miesiac)
    dane = _zarobek_mtd(db, user.pracownik_id, rok, miesiac)
    zajete = _suma_zaliczek(db, user.pracownik_id, mies, ("oczekuje", "zaakceptowana"))
    limit = dane["zarobek"] * LIMIT_PROCENT / 100.0
    moje = db.query(models.Zaliczka).filter(
        models.Zaliczka.pracownik_id == user.pracownik_id,
        models.Zaliczka.miesiac == mies,
    ).order_by(models.Zaliczka.wniosek_at.desc()).all()
    return {
        "miesiac": mies,
        "zarobek": round(dane["zarobek"], 2),
        "godziny": round(dane["godziny"], 2),
        "limit_procent": LIMIT_PROCENT,
        "dostepna_zaliczka": round(max(0.0, limit - zajete), 2),
        "zaliczki": [_zaliczka_out(z) for z in moje],
    }


@router.post("/api/me/portfel/zaliczki", status_code=201)
def wniosek_o_zaliczke(dane: ZaliczkaIn, user: models.User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    if not user.pracownik_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Konto nie jest powiązane z pracownikiem.")
    kwota = round(float(dane.kwota or 0), 2)
    if kwota <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Kwota zaliczki musi być dodatnia.")
    dzis = date.today()
    mies = _miesiac_str(dzis.year, dzis.month)
    zarobek = _zarobek_mtd(db, user.pracownik_id, dzis.year, dzis.month)["zarobek"]
    zajete = _suma_zaliczek(db, user.pracownik_id, mies, ("oczekuje", "zaakceptowana"))
    dostepne = max(0.0, zarobek * LIMIT_PROCENT / 100.0 - zajete)
    if kwota > dostepne + 0.005:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Kwota przekracza dostępny limit ({dostepne:.2f} zł = "
                            f"{LIMIT_PROCENT}% dotychczasowego zarobku minus wcześniejsze wnioski).")
    z = models.Zaliczka(pracownik_id=user.pracownik_id, miesiac=mies, kwota=kwota,
                        status="oczekuje", wniosek_at=utcnow_naive())
    db.add(z); db.commit(); db.refresh(z)
    try:
        prac = db.get(models.Pracownik, user.pracownik_id)
        push.wyslij_push_do_adminow(db, "Wniosek o zaliczkę",
                                    f"{prac.imie} {prac.nazwisko}: {kwota:.0f} zł ({mies})", url="/")
    except Exception as e:  # noqa: BLE001
        logger.warning("Push wniosku o zaliczkę nie powiódł się: %s", e)
    return _zaliczka_out(z)


@router.delete("/api/me/portfel/zaliczki/{zid}", status_code=204)
def wycofaj_zaliczke(zid: int, user: models.User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    z = db.get(models.Zaliczka, zid)
    if z is None or z.pracownik_id != user.pracownik_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Wniosek nie istnieje.")
    if z.status != "oczekuje":
        raise HTTPException(status.HTTP_409_CONFLICT, "Rozpatrzonego wniosku nie można wycofać.")
    db.delete(z); db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Admin: przegląd i decyzje
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/api/zaliczki")
def zaliczki_admin(rok: int = Query(None), miesiac: int = Query(None),
                   _admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    dzis = date.today()
    mies = _miesiac_str(rok or dzis.year, miesiac or dzis.month)
    prac = {p.id: f"{p.imie} {p.nazwisko}" for p in db.query(models.Pracownik).all()}
    rows = db.query(models.Zaliczka).filter(models.Zaliczka.miesiac == mies) \
        .order_by(models.Zaliczka.status.desc(), models.Zaliczka.wniosek_at.asc()).all()
    return [_zaliczka_out(z, prac.get(z.pracownik_id, "?")) for z in rows]


@router.put("/api/zaliczki/{zid}")
def decyzja_zaliczki(zid: int, dane: DecyzjaIn, admin: models.User = Depends(require_admin),
                     db: Session = Depends(get_db)):
    z = db.get(models.Zaliczka, zid)
    if z is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Wniosek nie istnieje.")
    if dane.status not in STATUSY_DECYZJI:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Dozwolone decyzje: zaakceptowana / odrzucona.")
    if z.status != "oczekuje":
        raise HTTPException(status.HTTP_409_CONFLICT, "Wniosek został już rozpatrzony.")
    z.status = dane.status
    z.decyzja_at = utcnow_naive()
    z.decyzja_login = admin.login
    db.commit(); db.refresh(z)
    try:
        tytul = "Zaliczka zaakceptowana" if z.status == "zaakceptowana" else "Zaliczka odrzucona"
        push.wyslij_push_do_pracownika(db, z.pracownik_id, tytul,
                                       f"{z.kwota:.0f} zł ({z.miesiac}) — decyzja: {admin.login}.", url="/")
    except Exception as e:  # noqa: BLE001
        logger.warning("Push decyzji o zaliczce nie powiódł się: %s", e)
    return _zaliczka_out(z)
