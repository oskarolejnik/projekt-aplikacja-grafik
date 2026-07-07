"""Router: CRM gości — historia rezerwacji, scoring no-show, VIP (roadmapa v1.5).

Dane gościa (PII) → tylko admin (wymusza role_guard). Agregacja PO STRONIE PYTHONA, bo
telefon/email są szyfrowane niedeterministycznie (EncryptedString) i nie da się ich GROUP BY
w SQL — pobieramy rezerwacje-gości i grupujemy po odszyfrowanym telefonie (fallback e-mail/nazwisko).
Bez nowych tabel/migracji (wzór jak /api/pulpit).
"""

import hashlib
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import models
import schemas
from database import get_db
from sms import _normalizuj_numer

router = APIRouter()

_AKTYWNE = ("rezerwacja", "potwierdzona")


def _klucz_crm(t) -> str:
    """Klucz grupujący gościa: znormalizowany telefon → e-mail → nazwisko (jak w crm_goscie)."""
    return _normalizuj_numer(t.telefon or "") or (t.email or "").strip().lower() or (t.nazwisko or "").strip().lower()


def _hash_klucz(klucz: str) -> str:
    """sha256 klucza CRM — indeks profilu bez plaintextu PII (telefonu) w bazie."""
    return hashlib.sha256((klucz or "").strip().encode("utf-8")).hexdigest()


def _profil_out(p) -> dict:
    if not p:
        return None
    return {"nazwisko": p.nazwisko, "tagi": p.tagi or [], "vip": p.vip, "alergie": p.alergie,
            "dieta": p.dieta, "preferowana_strefa": p.preferowana_strefa, "notatka": p.notatka,
            "okazja_typ": p.okazja_typ, "okazja_data": p.okazja_data, "marketing_zgoda": p.marketing_zgoda}


@router.get("/api/crm/goscie")
def crm_goscie(min_wizyt: int = Query(1), limit: int = Query(500), db: Session = Depends(get_db)):
    """Lista gości z historią rezerwacji i scoringiem no-show. Sortowana malejąco po liczbie wizyt."""
    rezerwacje = db.query(models.Termin).filter(models.Termin.rodzaj.in_(("stolik", "sala"))).all()

    grupy = defaultdict(list)
    for t in rezerwacje:
        klucz = _klucz_crm(t)
        if klucz:
            grupy[klucz].append(t)

    goscie = []
    for klucz, lista in grupy.items():
        wizyt = len(lista)
        if wizyt < max(1, int(min_wizyt)):
            continue
        odbyte = sum(1 for t in lista if t.status == "odbyla")
        no_show = sum(1 for t in lista if t.status == "no_show")
        odwolane = sum(1 for t in lista if t.status == "odwolana")
        aktywne = sum(1 for t in lista if t.status in _AKTYWNE)
        # Współczynnik no-show liczymy TYLKO po wizytach zamkniętych (odbyte/no_show/odwołane) —
        # rezerwacje przyszłe/oczekujące (aktywne) nie są dowodem zachowania i rozwadniałyby ryzyko
        # (im więcej gość ma nadchodzących rezerwacji, tym niżej wychodziłby scoring — błąd).
        zamkniete = odbyte + no_show + odwolane
        no_show_proc = round(no_show / zamkniete * 100) if zamkniete else 0
        ryzyko = "wysokie" if (zamkniete >= 3 and no_show_proc >= 30) else ("srednie" if no_show_proc > 0 else "niskie")
        najnowsza = max(lista, key=lambda t: t.data)
        daty = [t.data for t in lista]
        goscie.append({
            "klucz": klucz,
            "nazwisko": najnowsza.nazwisko, "telefon": najnowsza.telefon, "email": najnowsza.email,
            "wizyt": wizyt, "odbyte": odbyte, "no_show": no_show, "odwolane": odwolane, "aktywne": aktywne,
            "no_show_proc": no_show_proc, "ryzyko": ryzyko, "vip": odbyte >= 5,
            "ostatnia_data": str(max(daty)), "pierwsza_data": str(min(daty)),
        })

    goscie.sort(key=lambda g: (g["wizyt"], g["odbyte"]), reverse=True)
    goscie = goscie[:max(1, min(int(limit), 5000))]

    # Wzbogacenie o trwały profil (tagi/VIP/alergie) — jedno zapytanie po zahaszowanych kluczach.
    hashe = {g["klucz"]: _hash_klucz(g["klucz"]) for g in goscie}
    if hashe:
        profile = {p.klucz_hash: p for p in db.query(models.ProfilGoscia)
                   .filter(models.ProfilGoscia.klucz_hash.in_(set(hashe.values()))).all()}
        for g in goscie:
            p = profile.get(hashe[g["klucz"]])
            g["tagi"] = (p.tagi if p else None) or []
            g["ma_alergie"] = bool(p and p.alergie)
            g["ma_profil"] = p is not None
            g["vip"] = g["vip"] or bool(p and p.vip)     # VIP = auto (odbyte≥5) LUB ręczny z profilu
    return goscie


@router.get("/api/crm/goscie/{klucz}")
def crm_gosc_profil(klucz: str, db: Session = Depends(get_db)):
    """Profil gościa 360: trwały profil (tagi/alergie/preferencje/okazje) + policzona w locie
    historia wizyt (rezerwacje o tym samym kluczu). Tylko admin (role_guard)."""
    profil = db.query(models.ProfilGoscia).filter_by(klucz_hash=_hash_klucz(klucz)).first()
    lista = [t for t in db.query(models.Termin).filter(models.Termin.rodzaj.in_(("stolik", "sala"))).all()
             if _klucz_crm(t) == klucz]
    lista.sort(key=lambda t: t.data, reverse=True)
    odbyte = sum(1 for t in lista if t.status == "odbyla")
    no_show = sum(1 for t in lista if t.status == "no_show")
    odwolane = sum(1 for t in lista if t.status == "odwolana")
    zamkniete = odbyte + no_show + odwolane
    historia = [{"data": str(t.data), "godz_od": t.godz_od.strftime("%H:%M") if t.godz_od else None,
                 "liczba_osob": t.liczba_osob, "status": t.status, "stolik_id": t.stolik_id,
                 "kanal": t.kanal} for t in lista]
    return {
        "klucz": klucz, "profil": _profil_out(profil),
        "nazwisko": (profil.nazwisko if profil and profil.nazwisko else (lista[0].nazwisko if lista else None)),
        "statystyki": {"wizyt": len(lista), "odbyte": odbyte, "no_show": no_show, "odwolane": odwolane,
                       "no_show_proc": round(no_show / zamkniete * 100) if zamkniete else 0,
                       "vip_auto": odbyte >= 5},
        "historia": historia,
    }


@router.put("/api/crm/goscie/{klucz}/profil")
def crm_gosc_profil_zapisz(klucz: str, dane: schemas.ProfilGosciaIn, db: Session = Depends(get_db)):
    """Upsert profilu gościa. Alergie/notatka szyfrowane at-rest (RODO). Tylko admin."""
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
    p.alergie = (dane.alergie or None)
    p.dieta = (dane.dieta or None)
    p.preferowana_strefa = (dane.preferowana_strefa or None)
    p.notatka = (dane.notatka or None)
    p.okazja_typ = (dane.okazja_typ or None)
    p.okazja_data = (dane.okazja_data or None)
    p.marketing_zgoda = bool(dane.marketing_zgoda)
    p.zaktualizowano_at = teraz
    db.commit(); db.refresh(p)
    return _profil_out(p)
