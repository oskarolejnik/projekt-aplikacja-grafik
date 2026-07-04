"""Router: zaproszenia pracowników do kont (jedyna ścieżka rejestracji przy
wyłączonej otwartej rejestracji — feedback UX: „pracownik rejestruje się dopiero
po wejściu w link wygenerowany przez właściciela").

Przepływ:
  1. Manager (admin) tworzy zaproszenie: dla ISTNIEJĄCEGO pracownika (pracownik_id)
     albo podaje imię+nazwisko — wtedy pracownik jest zakładany (lub podpinany po
     znormalizowanym nazwisku, jeśli istnieje bez konta — spójnie z dawnym register).
  2. Link `/?zaproszenie=TOKEN` trafia do pracownika dowolnym kanałem (SMS/komunikator).
  3. Publiczny ekran czyta GET /api/online/zaproszenie/{token} (kogo zapraszamy, dokąd),
     a POST .../rejestracja zakłada konto PRZYPIĘTE do pracownika i od razu loguje.

Token jednorazowy (secrets.token_urlsafe), ważny WAZNOSC_DNI, ponowne zaproszenie
tego samego pracownika unieważnia poprzednie (naturalne „wyślij nowy link").
Ścieżki publiczne pod /api/online/* (allowlista role_guard) + dzienny limit prób
per IP (anty-DoS, jak rezerwacje online).
"""

import logging
import secrets
from datetime import timedelta
from typing import List, Optional

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

import models
import schemas
from auth import create_access_token, hash_password, require_admin
from database import get_db
from deps import _norm_nazwa, _user_out, get_lokal_config, utcnow_naive
from ratelimit import zuzyj_kwote
from validators import sprawdz_haslo, sprawdz_login

router = APIRouter()
logger = logging.getLogger(__name__)

WAZNOSC_DNI = 7
ROLE_ZAPROSZENIA = ("employee", "kuchnia", "szef", "szef_kuchni")   # admin tylko ręcznie w Kontach
REJESTRACJA_LIMIT_IP_DZIENNY = 15


def _status_zaproszenia(z: models.Zaproszenie) -> str:
    if z.uzyte_at is not None:
        return "uzyte"
    if z.wygasa_at < utcnow_naive():
        return "wygasle"
    return "aktywne"


def _zaproszenie_out(z: models.Zaproszenie) -> dict:
    return {
        "id": z.id,
        "token": z.token,
        "link": f"/?zaproszenie={z.token}",
        "pracownik_id": z.pracownik_id,
        "pracownik": f"{z.pracownik.imie} {z.pracownik.nazwisko}" if z.pracownik else None,
        "rola": z.rola,
        "status": _status_zaproszenia(z),
        "utworzono_at": z.utworzono_at.isoformat(),
        "wygasa_at": z.wygasa_at.isoformat(),
        "uzyte_at": z.uzyte_at.isoformat() if z.uzyte_at else None,
    }


# ── Panel managera (admin — wymusza role_guard) ───────────────────────────────

@router.post("/api/zaproszenia", status_code=201)
def utworz_zaproszenie(dane: schemas.ZaproszenieIn, db: Session = Depends(get_db),
                       admin: models.User = Depends(require_admin)):
    if dane.rola not in ROLE_ZAPROSZENIA:
        raise HTTPException(400, "Nieprawidłowa rola zaproszenia.")

    # 1) Ustal pracownika: wskazany id ALBO imię+nazwisko (reuse istniejącego bez konta / nowy).
    if dane.pracownik_id is not None:
        prac = db.get(models.Pracownik, dane.pracownik_id)
        if not prac:
            raise HTTPException(404, "Nie znaleziono pracownika.")
    else:
        imie = (dane.imie or "").strip()
        nazwisko = (dane.nazwisko or "").strip()
        if not imie or not nazwisko:
            raise HTTPException(400, "Podaj imię i nazwisko albo wybierz pracownika.")
        norm = _norm_nazwa(f"{imie} {nazwisko}")
        zajete = {u.pracownik_id for u in db.query(models.User).all() if u.pracownik_id}
        prac = next(
            (p for p in db.query(models.Pracownik).all()
             if p.id not in zajete and _norm_nazwa(f"{p.imie} {p.nazwisko}") == norm),
            None,
        )
        if prac is None:
            prac = models.Pracownik(imie=imie, nazwisko=nazwisko, aktywny=True,
                                    dzial="kuchnia" if dane.rola == "kuchnia" else "obsluga")
            db.add(prac)
            db.flush()

    # 2) Pracownik z kontem nie potrzebuje zaproszenia.
    if db.query(models.User).filter(models.User.pracownik_id == prac.id).first():
        raise HTTPException(400, "Ten pracownik ma już konto.")

    # 3) Nowe zaproszenie unieważnia poprzednie nieużyte (naturalny „wyślij ponownie").
    for stare in db.query(models.Zaproszenie).filter(
            models.Zaproszenie.pracownik_id == prac.id,
            models.Zaproszenie.uzyte_at.is_(None)).all():
        db.delete(stare)

    teraz = utcnow_naive()
    z = models.Zaproszenie(
        token=secrets.token_urlsafe(24),
        pracownik_id=prac.id,
        rola=dane.rola,
        utworzono_at=teraz,
        wygasa_at=teraz + timedelta(days=WAZNOSC_DNI),
        utworzyl_login=admin.login,
    )
    db.add(z)
    db.commit()
    db.refresh(z)
    return _zaproszenie_out(z)


@router.get("/api/zaproszenia")
def lista_zaproszen(db: Session = Depends(get_db)):
    rows = db.query(models.Zaproszenie).order_by(models.Zaproszenie.id.desc()).all()
    return {"zaproszenia": [_zaproszenie_out(z) for z in rows]}


@router.delete("/api/zaproszenia/{zid}", status_code=204)
def uniewaznij_zaproszenie(zid: int, db: Session = Depends(get_db)):
    z = db.get(models.Zaproszenie, zid)
    if not z:
        raise HTTPException(404, "Nie znaleziono zaproszenia.")
    if z.uzyte_at is not None:
        raise HTTPException(400, "Zaproszenie zostało już użyte — konto istnieje.")
    db.delete(z)
    db.commit()


# ── Publiczne (widget rejestracji z linku) ────────────────────────────────────

def _zaproszenie_wazne(db, token: str) -> models.Zaproszenie:
    z = db.query(models.Zaproszenie).filter(models.Zaproszenie.token == token).first()
    if not z:
        raise HTTPException(404, "Zaproszenie nie istnieje albo zostało unieważnione.")
    if z.uzyte_at is not None:
        raise HTTPException(400, "To zaproszenie zostało już użyte.")
    if z.wygasa_at < utcnow_naive():
        raise HTTPException(400, "Zaproszenie wygasło — poproś managera o nowy link.")
    return z


@router.get("/api/online/zaproszenie/{token}")
def podglad_zaproszenia(token: str, db: Session = Depends(get_db)):
    """Publiczny ekran powitania: kogo zapraszamy i do jakiego lokalu."""
    z = _zaproszenie_wazne(db, token)
    cfg = get_lokal_config(db)
    return {
        "imie": z.pracownik.imie,
        "nazwisko": z.pracownik.nazwisko,
        "rola": z.rola,
        "nazwa_lokalu": cfg.nazwa_lokalu,
        "wygasa_at": z.wygasa_at.isoformat(),
    }


@router.post("/api/online/zaproszenie/{token}/rejestracja",
             response_model=schemas.TokenOut, status_code=201)
def rejestracja_z_zaproszenia(token: str, dane: schemas.ZaproszenieRejestracjaIn,
                              request: Request, db: Session = Depends(get_db)):
    """Zakłada konto przypięte do pracownika z zaproszenia i od razu loguje."""
    ip = request.client.host if request.client else "?"
    if not zuzyj_kwote(f"zaproszenie:{ip}", str(date.today()), REJESTRACJA_LIMIT_IP_DZIENNY):
        raise HTTPException(429, "Zbyt wiele prób z tego adresu — spróbuj jutro.")

    z = _zaproszenie_wazne(db, token)
    login = sprawdz_login(dane.login)
    sprawdz_haslo(dane.haslo)
    if db.query(models.User).filter(models.User.login == login).first():
        raise HTTPException(400, "Ten login jest już zajęty.")
    if db.query(models.User).filter(models.User.pracownik_id == z.pracownik_id).first():
        raise HTTPException(400, "Ten pracownik ma już konto.")

    user = models.User(
        login=login, haslo_hash=hash_password(dane.haslo),
        rola=z.rola, pracownik_id=z.pracownik_id,
    )
    db.add(user)
    z.uzyte_at = utcnow_naive()
    db.commit()
    db.refresh(user)
    logger.info("Zaproszenie %s użyte: pracownik %s → konto %s (%s)",
                z.id, z.pracownik_id, user.login, user.rola)
    return schemas.TokenOut(access_token=create_access_token(user), user=_user_out(user))
