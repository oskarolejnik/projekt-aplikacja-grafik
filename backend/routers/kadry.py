"""Router: kadry i konta zespołu (dekompozycja main — audyt CTO).

Zarządzanie kontami użytkowników (/api/users) wraz z hurtowym provisioningiem,
kartoteka pracowników i ich stawek (/api/pracownicy), stanowiska-kwalifikacje
z podkategoriami (/api/stanowiska), dyspozycyjność (/api/dyspozycje) oraz
rozpatrywanie wniosków urlopowych przez admina (/api/urlopy).
Dostęp tylko admin — wymusza middleware autoryzacyjne w main.
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import models
import schemas
import uprawnienia
from auth import get_current_user, hash_password, require_admin
from database import get_db
from deps import (
    SPRZATACZKA_NAZWA, _przypisz_odbicia_do_pracownika, _urlop_out, _user_out, utcnow_naive,
    limit_pracownikow_stan,
)
import push

router = APIRouter()

# Wszystkie dozwolone wartości ról konta. „employee" = Pracownik obsługa (zachowana wartość
# z istniejących kont — bez migracji), „kuchnia" = Pracownik kuchnia, „szef_kuchni" = Szef kuchni.
ROLE_VALID = ("admin", "employee", "szef", "kuchnia", "szef_kuchni")


def _override_z_presetu(rola: str, preset: str) -> dict[str, bool]:
    try:
        return uprawnienia.override_dla_presetu(rola, preset)
    except ValueError as exc:
        raise HTTPException(400, "Nieprawidłowy preset uprawnień dla tej roli.") from exc


# --- Zarządzanie kontami (dostęp tylko admin — wymusza middleware) ---

@router.get("/api/users", response_model=List[schemas.UserOut])
def list_users(db: Session = Depends(get_db)):
    return [_user_out(u) for u in db.query(models.User).order_by(models.User.id).all()]

@router.post("/api/users", response_model=schemas.UserOut, status_code=201)
def create_user(dane: schemas.UserCreate, db: Session = Depends(get_db)):
    if dane.rola not in ROLE_VALID:
        raise HTTPException(400, "Nieprawidłowa rola.")
    override = (
        _override_z_presetu(dane.rola, dane.preset)
        if dane.preset is not None else None
    )
    if db.query(models.User).filter(models.User.login == dane.login).first():
        raise HTTPException(400, "Login jest już zajęty.")
    if dane.pracownik_id is not None:
        if not db.get(models.Pracownik, dane.pracownik_id):
            raise HTTPException(404, "Nie znaleziono pracownika.")
        if db.query(models.User).filter(models.User.pracownik_id == dane.pracownik_id).first():
            raise HTTPException(400, "Ten pracownik ma już konto.")
    u = models.User(
        login=dane.login, haslo_hash=hash_password(dane.haslo),
        rola=dane.rola, pracownik_id=dane.pracownik_id,
        uprawnienia_override=override or None,
    )
    db.add(u); db.commit(); db.refresh(u)
    return _user_out(u)

@router.put("/api/users/{uid}", response_model=schemas.UserOut)
def update_user(uid: int, dane: schemas.UserUpdate, db: Session = Depends(get_db)):
    u = db.get(models.User, uid)
    if not u:
        raise HTTPException(404, "Nie znaleziono konta.")
    if dane.rola is not None:
        if dane.rola not in ROLE_VALID:
            raise HTTPException(400, "Nieprawidłowa rola.")
        if dane.rola != u.rola:
            u.uprawnienia_override = None
        u.rola = dane.rola
    if dane.aktywny is not None:
        u.aktywny = dane.aktywny
    if dane.pracownik_id is not None:
        u.pracownik_id = dane.pracownik_id
    db.commit(); db.refresh(u)
    return _user_out(u)


@router.put("/api/users/{uid}/uprawnienia", response_model=schemas.UserOut)
def update_user_uprawnienia(
    uid: int,
    dane: schemas.UserUprawnieniaUpdate,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
):
    """Admin: zastępuje wyjątki uprawnień; w bazie zostają tylko różnice od roli."""
    u = db.get(models.User, uid)
    if not u:
        raise HTTPException(404, "Nie znaleziono konta.")
    if u.rola != "szef":
        raise HTTPException(400, "Uprawnienia per konto można zmieniać tylko dla roli szef.")
    if dane.preset is not None and dane.uprawnienia_override is not None:
        raise HTTPException(400, "Podaj preset albo mapę uprawnień, nie oba naraz.")
    if dane.preset is not None:
        override = _override_z_presetu(u.rola, dane.preset)
    elif dane.uprawnienia_override is not None:
        nieznane = sorted(
            set(dane.uprawnienia_override) - set(uprawnienia.EDYTOWALNE_ODCZYTY)
        )
        if nieznane:
            raise HTTPException(400, f"Nieznane uprawnienia: {', '.join(nieznane)}.")
        override = uprawnienia.znormalizuj_override(
            u.rola, dane.uprawnienia_override,
        )
    else:
        raise HTTPException(400, "Podaj preset albo mapę uprawnień.")
    u.uprawnienia_override = override or None
    db.commit(); db.refresh(u)
    return _user_out(u)

@router.post("/api/users/{uid}/reset-haslo", status_code=204)
def reset_haslo(uid: int, dane: schemas.ResetHasloIn, db: Session = Depends(get_db)):
    u = db.get(models.User, uid)
    if not u:
        raise HTTPException(404, "Nie znaleziono konta.")
    u.haslo_hash = hash_password(dane.haslo)
    db.commit()

@router.delete("/api/users/{uid}", status_code=204)
def delete_user(uid: int, db: Session = Depends(get_db)):
    u = db.get(models.User, uid)
    if not u:
        raise HTTPException(404, "Nie znaleziono konta.")
    db.delete(u); db.commit()

@router.post("/api/users/provision", status_code=200)
def provision_accounts(db: Session = Depends(get_db)):
    """Tworzy konta (login=imie.nazwisko, hasło tymczasowe) dla pracowników bez konta."""
    import unicodedata
    def slug(s: str) -> str:
        s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
        return "".join(c for c in s if c.isalnum())
    maja_konto = {u.pracownik_id for u in db.query(models.User).all() if u.pracownik_id}
    utworzone = []
    for p in db.query(models.Pracownik).all():
        if p.id in maja_konto:
            continue
        base = f"{slug(p.imie)}.{slug(p.nazwisko)}" or f"user{p.id}"
        login = base; i = 1
        while db.query(models.User).filter(models.User.login == login).first():
            i += 1; login = f"{base}{i}"
        haslo = (slug(p.nazwisko) or "haslo") + "123"
        db.add(models.User(login=login, haslo_hash=hash_password(haslo), rola="employee", pracownik_id=p.id))
        utworzone.append({"pracownik": f"{p.imie} {p.nazwisko}", "login": login, "haslo_tymczasowe": haslo})
    db.commit()
    return {"utworzone": utworzone}


# --- URLOPY (obsługa) ---


@router.get("/api/urlopy")
def lista_urlopow(db: Session = Depends(get_db)):
    """Wszystkie wnioski (admin) — oczekujące najpierw, potem wg daty startu malejąco."""
    rows = db.query(models.Urlop).all()
    prac_map = {p.id: f"{p.imie} {p.nazwisko}" for p in db.query(models.Pracownik).all()}
    rows.sort(key=lambda u: (u.status != "oczekuje", -u.start.toordinal()))
    return {"urlopy": [_urlop_out(u, prac_map) for u in rows]}


@router.put("/api/urlopy/{uid}/status", status_code=204)
def rozpatrz_urlop(uid: int, dane: schemas.UrlopStatusIn, db: Session = Depends(get_db)):
    """Admin: 'zaakceptowany' / 'odrzucony' → push do pracownika."""
    u = db.get(models.Urlop, uid)
    if not u:
        raise HTTPException(404, "Nie znaleziono wniosku.")
    if dane.status not in ("zaakceptowany", "odrzucony"):
        raise HTTPException(400, "Status musi być 'zaakceptowany' albo 'odrzucony'.")
    u.status = dane.status
    u.rozpatrzono_at = utcnow_naive()
    db.commit()
    slowo = "zaakceptowany" if dane.status == "zaakceptowany" else "odrzucony"
    push.wyslij_push_do_pracownika(db, u.pracownik_id, "Urlop",
                              f"Twój wniosek urlopowy ({u.start.strftime('%d.%m')}–{u.koniec.strftime('%d.%m')}) został {slowo}.", url="/")


# ═══════════════════════════════════════════════════════════════════════════
# STANOWISKA (kwalifikacje) + PRACOWNICY
# ═══════════════════════════════════════════════════════════════════════════

# Kwalifikacje działu technicznego (nadawane w Pracownikach jak zwykłe kwalifikacje = Stanowiska).
# „Sprzątaczka" daje dostęp do formularza zamówień (stała w deps.py); „Stróż" tylko jako oznaczenie.
STROZ_NAZWA = "Stróż"


def _ensure_kwalifikacje_techniczne(db):
    """Dba, by stanowiska-kwalifikacje Sprzątaczka/Stróż istniały (admin może je nadać w Pracownikach).
    Sprzątaczka dostaje flagę `daje_dostep_zamowien` (dawniej rozpoznawana po nazwie)."""
    zmiana = False
    for nazwa in (SPRZATACZKA_NAZWA, STROZ_NAZWA):
        existing = db.query(models.Stanowisko).filter_by(nazwa=nazwa).first()
        if not existing:
            db.add(models.Stanowisko(nazwa=nazwa,
                                     daje_dostep_zamowien=(nazwa == SPRZATACZKA_NAZWA)))
            zmiana = True
        elif nazwa == SPRZATACZKA_NAZWA and not existing.daje_dostep_zamowien:
            existing.daje_dostep_zamowien = True   # adopcja istniejącej Sprzątaczki na flagę
            zmiana = True
    if zmiana:
        db.commit()


@router.get("/api/stanowiska", response_model=List[schemas.StanowiskoOut])
def get_stanowiska(db: Session = Depends(get_db)):
    _ensure_kwalifikacje_techniczne(db)  # Sprzątaczka/Stróż dostępne do nadania w Pracownikach
    return db.query(models.Stanowisko).all()

@router.post("/api/stanowiska", response_model=schemas.StanowiskoOut, status_code=201)
def create_stanowisko(data: schemas.StanowiskoCreate, db: Session = Depends(get_db)):
    if db.query(models.Stanowisko).filter_by(nazwa=data.nazwa).first():
        raise HTTPException(400, "Stanowisko o tej nazwie już istnieje.")
    s = models.Stanowisko(**data.model_dump())
    s.grupa_widocznosci = (s.grupa_widocznosci or "").strip() or None  # pusty string -> brak grupy
    s.rola = (s.rola or "").strip() or None
    db.add(s); db.commit(); db.refresh(s)
    return s

@router.put("/api/stanowiska/{sid}", response_model=schemas.StanowiskoOut)
def update_stanowisko(sid: int, data: schemas.StanowiskoCreate, db: Session = Depends(get_db)):
    s = db.get(models.Stanowisko, sid)
    if not s:
        raise HTTPException(404, "Nie znaleziono.")
    s.nazwa = data.nazwa
    s.tylko_weekend = data.tylko_weekend
    s.widoczny_dla_wszystkich = data.widoczny_dla_wszystkich
    s.grupa_widocznosci = (data.grupa_widocznosci or "").strip() or None
    s.rola = (data.rola or "").strip() or None
    s.daje_dostep_zamowien = bool(data.daje_dostep_zamowien)
    db.commit(); db.refresh(s)
    return s

@router.delete("/api/stanowiska/{sid}", status_code=204)
def delete_stanowisko(sid: int, db: Session = Depends(get_db)):
    s = db.get(models.Stanowisko, sid)
    if not s:
        raise HTTPException(404, "Nie znaleziono.")
    # WymaganiaDnia mają FK do stanowiska BEZ kaskady ORM/ondelete → kasujemy ręcznie, inaczej na
    # PostgreSQL (produkcja) delete rzuca IntegrityError 500, a na SQLite zostają sieroty.
    db.query(models.WymaganiaDnia).filter(models.WymaganiaDnia.stanowisko_id == sid).delete(synchronize_session=False)
    db.delete(s); db.commit()

@router.post("/api/stanowiska/{sid}/podkategorie", response_model=schemas.PodkategoriaOut)
def create_podkategoria(sid: int, data: schemas.PodkategoriaCreate, db: Session = Depends(get_db)):
    p = models.Podkategoria(**data.model_dump(), stanowisko_id=sid)
    db.add(p); db.commit(); db.refresh(p)
    return p


@router.get("/api/pracownicy", response_model=List[schemas.PracownikOut])
def get_pracownicy(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    pracownicy = db.query(models.Pracownik).order_by(models.Pracownik.kolejnosc, models.Pracownik.id).all()
    if user.rola == "szef" and not uprawnienia.ma_user(user, "wyplaty.podglad"):
        wynik = []
        for pracownik in pracownicy:
            out = schemas.PracownikOut.model_validate(pracownik)
            out.stawki = []
            wynik.append(out)
        return wynik
    return pracownicy


def _ustaw_stawki(db, p, stawki):
    """Nadpisuje stawki godzinowe pracownika (per stanowisko). Zapisuje tylko dodatnie."""
    db.query(models.StawkaPracownika).filter_by(pracownik_id=p.id).delete()
    for s in (stawki or []):
        if s.stanowisko_id and s.stawka and s.stawka > 0:
            db.add(models.StawkaPracownika(
                pracownik_id=p.id, stanowisko_id=s.stanowisko_id, stawka=float(s.stawka)
            ))


@router.post("/api/pracownicy", response_model=schemas.PracownikOut, status_code=201)
def create_pracownik(data: schemas.PracownikCreate, db: Session = Depends(get_db)):
    # Limit planu Free na aktywnych pracowników (dźwignia upsellu; Basic+ = bez limitu, trial = Premium).
    lim = limit_pracownikow_stan(db)
    if data.aktywny and lim["przekroczony"]:
        raise HTTPException(402, f"Plan Free obejmuje do {lim['limit']} aktywnych pracowników "
                                 f"(masz {lim['aktywni']}). Podnieś pakiet do Basic, aby dodać więcej.")
    ostatni = db.query(models.Pracownik).order_by(models.Pracownik.kolejnosc.desc()).first()
    p = models.Pracownik(imie=data.imie, nazwisko=data.nazwisko, aktywny=data.aktywny,
                         kolor=data.kolor, dzial=(data.dzial or "obsluga"),
                         kolejnosc=(ostatni.kolejnosc + 1 if ostatni else 0))
    if data.kwalifikacje_ids:
        p.kwalifikacje = db.query(models.Stanowisko).filter(
            models.Stanowisko.id.in_(data.kwalifikacje_ids)
        ).all()
    db.add(p); db.commit(); db.refresh(p)
    _ustaw_stawki(db, p, data.stawki); db.commit(); db.refresh(p)
    _przypisz_odbicia_do_pracownika(db, p)  # podlinkuj zalegle odbicia RCP od razu
    return p

@router.put("/api/pracownicy/kolejnosc", status_code=200)
def ustaw_kolejnosc(data: schemas.KolejnoscIn, db: Session = Depends(get_db)):
    """Ręczna kolejność wyświetlania pracowników: kolejnosc = pozycja na liście ids."""
    for idx, pid in enumerate(data.ids):
        p = db.get(models.Pracownik, pid)
        if p:
            p.kolejnosc = idx
    db.commit()
    return {"ok": True}


@router.put("/api/pracownicy/{pid}", response_model=schemas.PracownikOut)
def update_pracownik(pid: int, data: schemas.PracownikCreate, db: Session = Depends(get_db)):
    p = db.get(models.Pracownik, pid)
    if not p:
        raise HTTPException(404, "Nie znaleziono.")
    p.imie = data.imie
    p.nazwisko = data.nazwisko
    p.aktywny = data.aktywny
    p.kolor = data.kolor
    p.dzial = data.dzial or "obsluga"
    p.kwalifikacje = db.query(models.Stanowisko).filter(
        models.Stanowisko.id.in_(data.kwalifikacje_ids)
    ).all()
    _ustaw_stawki(db, p, data.stawki)
    db.commit(); db.refresh(p)
    _przypisz_odbicia_do_pracownika(db, p)  # nazwisko moglo sie zmienic -> sprobuj podlinkowac
    return p

@router.delete("/api/pracownicy/{pid}", status_code=204)
def delete_pracownik(pid: int, db: Session = Depends(get_db)):
    p = db.get(models.Pracownik, pid)
    if not p:
        raise HTTPException(404, "Nie znaleziono.")
    # Rekordy zależne BEZ kaskady ORM/ondelete kasujemy jawnie (przez ORM — by odpaliły zagnieżdżone
    # kaskady, np. RozliczenieImprezy→pozycje). Inaczej na PostgreSQL FK RESTRICT rzuca 500, a na
    # SQLite zostają SIEROTY — m.in. wiersz RozliczenieKelner zawyżający utarg dnia bez atrybucji.
    # Twardy delete pracownika = pełne usunięcie jego danych (miękkie usunięcie = aktywny=False).
    for Model in (models.RozliczenieKelner, models.RozliczenieImprezy, models.RozliczenieGastro,
                  models.Urlop, models.ZamowienieSprzataczki, models.SprzatanieOdhaczenie):
        for row in db.query(Model).filter(Model.pracownik_id == pid).all():
            db.delete(row)
    db.delete(p); db.commit()


# ═══════════════════════════════════════════════════════════════════════════
# DYSPOZYCJE
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/api/dyspozycje", response_model=List[schemas.DyspozycjaOut])
def get_dyspozycje(
    start: Optional[date] = None,
    end: Optional[date] = None,
    db: Session = Depends(get_db)
):
    q = db.query(models.Dyspozycja)
    if start: q = q.filter(models.Dyspozycja.data >= start)
    if end:   q = q.filter(models.Dyspozycja.data <= end)
    return q.all()

@router.post("/api/dyspozycje", response_model=schemas.DyspozycjaOut, status_code=201)
def create_dyspozycja(data: schemas.DyspozycjaCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Dyspozycja).filter_by(
        pracownik_id=data.pracownik_id, data=data.data
    ).first()
    if existing:
        for k, v in data.model_dump().items():
            setattr(existing, k, v)
        db.commit(); db.refresh(existing)
        return existing
    d = models.Dyspozycja(**data.model_dump())
    db.add(d); db.commit(); db.refresh(d)
    return d

@router.delete("/api/dyspozycje/{did}", status_code=204)
def delete_dyspozycja(did: int, db: Session = Depends(get_db)):
    """Czyści dyspozycyjność (admin) — wraca do stanu „brak zgłoszenia"."""
    d = db.get(models.Dyspozycja, did)
    if not d:
        raise HTTPException(404, "Nie znaleziono.")
    db.delete(d); db.commit()
