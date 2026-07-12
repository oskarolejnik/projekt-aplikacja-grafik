"""CRM gości: historia wizyt, scoring no-show i trwały profil.

Publiczny kontrakt panelu nigdy nie używa telefonu, e-maila ani ich hasha jako
identyfikatora. Nawigacja z rezerwacji rozwiązuje gościa po ``reservation_id``
po stronie serwera. Stare trasy z kluczem pozostają przejściowo admin-only dla
kompatybilności, ale nie są już zasilane przez listę CRM ani zwracane w JSON.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import models
import schemas
import uprawnienia
from auth import get_current_user, require_admin
from crm_identity import hash_key as _hash_klucz
from crm_identity import identity_key as _klucz_crm
from crm_identity import identity_parts as _identity_parts
from database import get_db
from deps import modul_aktywny

router = APIRouter()

_AKTYWNE = ("rezerwacja", "potwierdzona")
_RODZAJE_CRM = ("stolik", "sala")
_CRM_HISTORY_LIMIT = 50


def _sort_key(t):
    return t.data, t.godz_od or time.min, t.id or 0


def _ma(user, permission: str) -> bool:
    # ``None`` występuje wyłącznie w starych trasach chronionych require_admin.
    return user is None or uprawnienia.ma_user(user, permission)


def _ukryte_pola(user) -> list[str]:
    hidden = []
    if not _ma(user, "rezerwacje.dane_wrazliwe"):
        hidden.extend(("profil.tagi", "profil.alergie", "profil.dieta"))
    if not _ma(user, "rezerwacje.notatki_wewnetrzne"):
        hidden.append("profil.notatka")
    return hidden


def _capabilities(user) -> dict:
    return {
        "can_edit": getattr(user, "rola", None) == "admin",
        "can_view_sensitive": _ma(user, "rezerwacje.dane_wrazliwe"),
        "can_view_internal_notes": _ma(user, "rezerwacje.notatki_wewnetrzne"),
    }


def _profil_out(p, user=None) -> dict | None:
    if not p:
        return None
    wrazliwe = _ma(user, "rezerwacje.dane_wrazliwe")
    notatki = _ma(user, "rezerwacje.notatki_wewnetrzne")
    return {
        "nazwisko": p.nazwisko,
        "tagi": (p.tagi or []) if wrazliwe else [],
        "vip": bool(p.vip),
        "alergie": p.alergie if wrazliwe else None,
        "dieta": p.dieta if wrazliwe else None,
        "preferowana_strefa": p.preferowana_strefa,
        "notatka": p.notatka if notatki else None,
        "okazja_typ": p.okazja_typ,
        "okazja_data": p.okazja_data,
        "marketing_zgoda": bool(p.marketing_zgoda),
    }


def _wymagaj_modul_rezerwacje(db: Session = Depends(get_db)):
    if not modul_aktywny(db, "modul_rezerwacje"):
        raise HTTPException(
            403,
            "Moduł rezerwacji jest niedostępny w tym planie — odblokujesz go w pakiecie Pro.",
        )


def _termin_rezerwacji(db: Session, reservation_id: int, user=None) -> models.Termin:
    termin = db.get(models.Termin, reservation_id)
    if not termin or termin.rodzaj not in _RODZAJE_CRM:
        # Jeden komunikat dla braku rekordu i innego typu ogranicza enumerację domeny.
        raise HTTPException(404, "Brak rezerwacji.")
    # Historyczny CRM administratora obejmuje również rezerwacje sali. Granularne
    # konto operacyjne otrzymuje handoff wyłącznie z kanonicznych rezerwacji stolika.
    if termin.rodzaj != "stolik" and getattr(user, "rola", None) != "admin":
        raise HTTPException(404, "Brak rezerwacji.")
    return termin


def _terminy_dla_klucza(db: Session, klucz: str) -> list[models.Termin]:
    if not klucz:
        return []
    rows = db.query(models.Termin).filter(models.Termin.rodzaj.in_(_RODZAJE_CRM)).all()
    return sorted((t for t in rows if _klucz_crm(t) == klucz), key=_sort_key, reverse=True)


def _statystyki(lista: list[models.Termin]) -> dict:
    odbyte = sum(1 for t in lista if t.status == "odbyla")
    no_show = sum(1 for t in lista if t.status == "no_show")
    odwolane = sum(1 for t in lista if t.status == "odwolana")
    zamkniete = odbyte + no_show + odwolane
    return {
        "wizyt": len(lista),
        "odbyte": odbyte,
        "no_show": no_show,
        "odwolane": odwolane,
        "no_show_proc": round(no_show / zamkniete * 100) if zamkniete else 0,
        "vip_auto": odbyte >= 5,
    }


def _historia_out(lista: list[models.Termin]) -> list[dict]:
    return [
        {
            "reservation_id": t.id,
            "data": str(t.data),
            "godz_od": t.godz_od.strftime("%H:%M") if t.godz_od else None,
            "liczba_osob": t.liczba_osob,
            "status": t.status,
            "stolik_id": t.stolik_id,
            "kanal": t.kanal,
        }
        for t in lista[:_CRM_HISTORY_LIMIT]
    ]


def _profil_rezerwacji_out(db: Session, termin: models.Termin, user) -> dict:
    klucz, identity = _identity_parts(termin)
    lista = _terminy_dla_klucza(db, klucz)
    profil = db.query(models.ProfilGoscia).filter_by(klucz_hash=_hash_klucz(klucz)).first()
    najnowsza = lista[0] if lista else termin
    return {
        "reservation_id": termin.id,
        "profil_ref": termin.id,
        "nazwisko": profil.nazwisko if profil and profil.nazwisko else najnowsza.nazwisko,
        "identity": identity,
        "profil": _profil_out(profil, user),
        "statystyki": _statystyki(lista),
        "historia": _historia_out(lista),
        "historia_total": len(lista),
        "historia_limit": _CRM_HISTORY_LIMIT,
        "ukryte_pola": _ukryte_pola(user),
        "capabilities": _capabilities(user),
    }


def _upsert_profil(db: Session, klucz: str, dane: schemas.ProfilGosciaIn) -> models.ProfilGoscia:
    if not (klucz or "").strip():
        raise HTTPException(400, "Pusty klucz gościa.")
    kh = _hash_klucz(klucz)
    p = db.query(models.ProfilGoscia).filter_by(klucz_hash=kh).first()
    teraz = datetime.utcnow()
    if not p:
        p = models.ProfilGoscia(klucz_hash=kh, utworzono_at=teraz)
        db.add(p)
    p.nazwisko = dane.nazwisko
    p.tagi = dane.tagi or None
    p.vip = bool(dane.vip)
    p.alergie = dane.alergie or None
    p.dieta = dane.dieta or None
    p.preferowana_strefa = dane.preferowana_strefa or None
    p.notatka = dane.notatka or None
    p.okazja_typ = dane.okazja_typ or None
    p.okazja_data = dane.okazja_data or None
    p.marketing_zgoda = bool(dane.marketing_zgoda)
    p.zaktualizowano_at = teraz
    db.commit()
    db.refresh(p)
    return p


@router.get(
    "/api/crm/goscie",
    dependencies=[Depends(_wymagaj_modul_rezerwacje)],
)
def crm_goscie(
    min_wizyt: int = Query(1),
    limit: int = Query(500),
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
):
    """Adminowa lista CRM bez klucza kontaktowego w kontrakcie nawigacji."""
    rezerwacje = db.query(models.Termin).filter(models.Termin.rodzaj.in_(_RODZAJE_CRM)).all()

    grupy = defaultdict(list)
    for t in rezerwacje:
        klucz = _klucz_crm(t)
        if klucz:
            grupy[klucz].append(t)

    goscie = []
    profile_hash_by_ref = {}
    for klucz, lista in grupy.items():
        lista.sort(key=_sort_key, reverse=True)
        wizyt = len(lista)
        if wizyt < max(1, int(min_wizyt)):
            continue
        stats = _statystyki(lista)
        aktywne = sum(1 for t in lista if t.status in _AKTYWNE)
        ryzyko = (
            "wysokie"
            if stats["odbyte"] + stats["no_show"] + stats["odwolane"] >= 3
            and stats["no_show_proc"] >= 30
            else ("srednie" if stats["no_show_proc"] > 0 else "niskie")
        )
        najnowsza = lista[0]
        profil_ref = najnowsza.id
        profile_hash_by_ref[profil_ref] = _hash_klucz(klucz)
        daty = [t.data for t in lista]
        goscie.append(
            {
                "profil_ref": profil_ref,
                "identity": _identity_parts(najnowsza)[1],
                "nazwisko": najnowsza.nazwisko,
                "telefon": najnowsza.telefon,
                "email": najnowsza.email,
                "wizyt": wizyt,
                "odbyte": stats["odbyte"],
                "no_show": stats["no_show"],
                "odwolane": stats["odwolane"],
                "aktywne": aktywne,
                "no_show_proc": stats["no_show_proc"],
                "ryzyko": ryzyko,
                "vip": stats["vip_auto"],
                "ostatnia_data": str(max(daty)),
                "pierwsza_data": str(min(daty)),
            }
        )

    goscie.sort(key=lambda g: (g["wizyt"], g["odbyte"], g["profil_ref"]), reverse=True)
    goscie = goscie[:max(1, min(int(limit), 5000))]

    hashe = {profile_hash_by_ref[g["profil_ref"]] for g in goscie}
    if hashe:
        profile = {
            p.klucz_hash: p
            for p in db.query(models.ProfilGoscia)
            .filter(models.ProfilGoscia.klucz_hash.in_(hashe))
            .all()
        }
        for g in goscie:
            p = profile.get(profile_hash_by_ref[g["profil_ref"]])
            g["tagi"] = (p.tagi if p else None) or []
            g["ma_alergie"] = bool(p and p.alergie)
            g["ma_profil"] = p is not None
            g["vip"] = g["vip"] or bool(p and p.vip)
    return goscie


@router.get(
    "/api/crm/rezerwacje/{reservation_id}/profil",
    dependencies=[Depends(_wymagaj_modul_rezerwacje)],
)
def crm_profil_z_rezerwacji(
    reservation_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Bezpieczny handoff rezerwacja → profil bez kontaktowego klucza w URL/JSON."""
    if not (
        uprawnienia.ma_user(user, "rezerwacje.operacje")
        and uprawnienia.ma_user(user, "rezerwacje.dane_kontaktowe")
    ):
        raise HTTPException(403, "Brak uprawnień do profilu gościa.")
    termin = _termin_rezerwacji(db, reservation_id, user)
    return _profil_rezerwacji_out(db, termin, user)


@router.put(
    "/api/crm/rezerwacje/{reservation_id}/profil",
    dependencies=[Depends(_wymagaj_modul_rezerwacje)],
)
def crm_profil_z_rezerwacji_zapisz(
    reservation_id: int,
    dane: schemas.ProfilGosciaIn,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    """Admin-only zapis profilu bez przyjmowania surowego klucza gościa."""
    termin = _termin_rezerwacji(db, reservation_id, admin)
    _upsert_profil(db, _klucz_crm(termin), dane)
    return _profil_rezerwacji_out(db, termin, admin)


# Trasy kompatybilnościowe: admin-only, nieużywane przez nowe linki ani listę CRM.
@router.get(
    "/api/crm/goscie/{klucz}",
    dependencies=[Depends(_wymagaj_modul_rezerwacje)],
)
def crm_gosc_profil(
    klucz: str,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
):
    profil = db.query(models.ProfilGoscia).filter_by(klucz_hash=_hash_klucz(klucz)).first()
    lista = _terminy_dla_klucza(db, klucz)
    najnowsza = lista[0] if lista else None
    return {
        "profil_ref": najnowsza.id if najnowsza else None,
        "identity": _identity_parts(najnowsza)[1] if najnowsza else {"source": "legacy", "confident": False},
        "profil": _profil_out(profil),
        "nazwisko": profil.nazwisko if profil and profil.nazwisko else (najnowsza.nazwisko if najnowsza else None),
        "statystyki": _statystyki(lista),
        "historia": _historia_out(lista),
        "historia_total": len(lista),
        "historia_limit": _CRM_HISTORY_LIMIT,
    }


@router.put(
    "/api/crm/goscie/{klucz}/profil",
    dependencies=[Depends(_wymagaj_modul_rezerwacje)],
)
def crm_gosc_profil_zapisz(
    klucz: str,
    dane: schemas.ProfilGosciaIn,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
):
    """Przejściowy admin-only upsert; nowe UI zapisuje wyłącznie przez reservation_id."""
    return _profil_out(_upsert_profil(db, klucz, dane))
