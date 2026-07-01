import csv
import io
import re
import os
import logging
import secrets
from datetime import date, time, timedelta, datetime, timezone
from typing import Optional, List
from collections import defaultdict

from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

import models, schemas, raporty, rezerwacje, sprzatanie, rozliczenia, ical_import, integracje, mailer, uprawnienia, ratelimit
from database import get_db, init_db, SessionLocal
from algorithm import auto_assign as _auto_assign, przelicz_imprezy_na_wymagania

import jwt
from auth import (
    get_current_user, hash_password, verify_password,
    create_access_token, SECRET_KEY, ALGORITHM,
)
from validators import sprawdz_login, sprawdz_haslo
from push import wyslij_push, wyslij_push_do_pracownika, wyslij_push_do_adminow, VAPID_PUBLIC_KEY

import openpyxl

import settings as app_settings
from deps import get_subskrypcja, subskrypcja_aktywna, utcnow_naive, get_lokal_config
from routers.instancja import router as instancja_router
from routers.lokal import router as lokal_router
from routers.platnosci import router as platnosci_router

logger = logging.getLogger(__name__)
app = FastAPI(title="Scheduler API")
app.include_router(instancja_router)   # subskrypcja/licencja, audyt, status integracji (Rec#5: dekompozycja main)
app.include_router(lokal_router)       # konfiguracja lokalu / branding (Rec#5: dekompozycja main)
app.include_router(platnosci_router)   # płatności zadatków online (Rec#7)

# CORS „secure by default": w produkcji domyślnie tylko same-origin (backend serwuje
# frontend z tego samego adresu), w dev lokalne origins. Pełna logika w settings.cors_origins().
ALLOWED_ORIGINS = app_settings.cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Wszystkie dozwolone wartości ról konta. „employee" = Pracownik obsługa (zachowana wartość
# z istniejących kont — bez migracji), „kuchnia" = Pracownik kuchnia, „szef_kuchni" = Szef kuchni.
ROLE_VALID = ("admin", "employee", "szef", "kuchnia", "szef_kuchni")

# Role nadzorcze i ich dozwolone ścieżki GET (poza /api/me/* dostępnym dla każdego zalogowanego).
# Wszystko spoza tych prefiksów = 403. Zapisy (POST/PUT/DELETE) zarezerwowane dla admina.
OVERSIGHT_GET = {
    "szef": (
        "/api/raporty/godziny", "/api/przydzialy", "/api/grafik/publikacja",
        "/api/imprezy", "/api/pracownicy", "/api/stanowiska", "/api/gastro/stoly",
        "/api/rezerwacje", "/api/szef/rozliczenie", "/api/szef/zeszyt", "/api/pulpit", "/api/alerty-kasowe",
    ),
    # Szef kuchni: godziny kuchni (bez wypłat), podgląd stołów na żywo, rezerwacje.
    "szef_kuchni": (
        "/api/szefkuchni/", "/api/gastro/stoly", "/api/rezerwacje",
    ),
    # Pracownik kuchni: podgląd rezerwacji (zagregowane liczby + rozbicie godzinowe,
    # bez danych klienta) do planowania pracy kuchni. Imprezy widzi przez
    # /api/me/imprezy (bez nazwy klienta — patrz preferencja prywatności).
    "kuchnia": (
        "/api/rezerwacje",
    ),
    # Pracownik obsługi (employee): jak kuchnia — rezerwacje (liczby + rozbicie godzinowe,
    # bez danych klienta) do planowania pracy na sali. Imprezy przez /api/me/imprezy (bez klienta).
    # Reszta panelu admina dalej 403 (poza /api/me/* dostępnym dla każdego zalogowanego).
    "employee": (
        "/api/rezerwacje",
    ),
}


# Centralna ochrona API: /api/auth/* publiczne, /api/me/* dla każdego zalogowanego,
# pozostałe /api/* tylko dla administratora (role nadzorcze: wybrane GET — patrz OVERSIGHT_GET).
# Statyczny frontend jest publiczny.
@app.middleware("http")
async def role_guard(request: Request, call_next):
    path = request.url.path
    # Degradacja READ_ONLY: nieaktywna subskrypcja → tylko odczyt. Zapisy (POST/PUT/DELETE/PATCH)
    # zwracają 402, POZA: logowaniem (/api/auth/*), zarządzaniem subskrypcją i /api/health.
    if (request.method in ("POST", "PUT", "DELETE", "PATCH") and path.startswith("/api/")
            and not path.startswith("/api/auth/") and not path.startswith("/api/onboarding/")
            and path != "/api/subskrypcja" and path != "/api/health"):
        _db = SessionLocal()
        try:
            if not subskrypcja_aktywna(_db):
                return JSONResponse(
                    {"detail": "Subskrypcja nieaktywna — instancja działa w trybie tylko do odczytu. "
                               "Przedłuż subskrypcję, aby zapisywać zmiany."},
                    status_code=402)
        finally:
            _db.close()
    # /api/rcp/ingest — wyjątek: autoryzacja stałym tokenem agenta (X-RCP-Token), nie JWT.
    if request.method != "OPTIONS" and path.startswith("/api/") and not path.startswith("/api/auth/") and path != "/api/health" and path != "/api/lokal/branding" and not path.startswith("/api/online/") and not path.startswith("/api/onboarding/") and path != "/api/rcp/ingest" and not (path.startswith("/api/gastro/stoly") and request.method == "POST") and not (path == "/api/gastro/rozliczenia" and request.method == "POST") and not (path == "/api/gastro/zadatki" and request.method == "POST"):
        header = request.headers.get("authorization", "")
        token = header[7:] if header.lower().startswith("bearer ") else ""
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        except jwt.PyJWTError:
            return JSONResponse({"detail": "Wymagane logowanie."}, status_code=401)
        rola = payload.get("rola")
        if not path.startswith("/api/me/") and rola != "admin":
            # Szef kuchni ma PEŁNY dostęp do swojej przestrzeni /api/szefkuchni/ (też zapisy:
            # korekty grafiku kuchni). Każdy taki endpoint sam pilnuje, że dotyczy tylko kuchni.
            if rola == "szef_kuchni" and path.startswith("/api/szefkuchni/"):
                pass
            else:
                # Pozostałe role nadzorcze (szef, szef_kuchni poza swoją przestrzenią) — tylko GET z whitelisty.
                dozwolone = OVERSIGHT_GET.get(rola, ())
                if not (request.method == "GET" and any(path.startswith(p) for p in dozwolone)):
                    return JSONResponse({"detail": "Brak uprawnień."}, status_code=403)
    return await call_next(request)


# Nazwa „ukrytego" stanowiska, na które trafiają zmiany z grafiku KUCHNI. Pracownik kuchni
# nie wybiera stanowiska — wszystkie jego zmiany idą na to jedno stanowisko, a stawkę ustawia
# się per osoba (StawkaPracownika na tym stanowisku). Dzięki temu reszta logiki (RCP×grafik,
# wypłaty) działa bez zmian i bez ryzykownej migracji „stanowisko_id NULL".
KUCHNIA_STANOWISKO = "Kuchnia"
# Stanowisko dla pracowników technicznych — pełne godziny RCP × stawka (bez grafiku). Jak kuchnia.
TECHNICZNY_STANOWISKO = "Techniczny"


def _stanowisko_wg_roli(db, rola: str, nazwa_legacy: str, utworz: bool = True):
    """Znajduje (lub tworzy) ukryte stanowisko po ROLI. Niezależne od nazwy — nowy klient może
    nazwać je dowolnie, byle miało właściwą rolę. Fallback + samo-naprawa: jeśli istnieje
    stanowisko o nazwie legacy bez ustawionej roli, dostaje rolę (adopcja istniejących danych)."""
    s = db.query(models.Stanowisko).filter_by(rola=rola).first()
    if s:
        return s
    s = db.query(models.Stanowisko).filter_by(nazwa=nazwa_legacy).first()
    if s:
        if s.rola != rola:
            s.rola = rola; db.commit(); db.refresh(s)
        return s
    if not utworz:
        return None
    s = models.Stanowisko(nazwa=nazwa_legacy, rola=rola)
    db.add(s); db.commit(); db.refresh(s)
    return s


def _kuchnia_stanowisko(db) -> models.Stanowisko:
    return _stanowisko_wg_roli(db, "kuchnia", KUCHNIA_STANOWISKO)


def _techniczny_stanowisko(db) -> models.Stanowisko:
    return _stanowisko_wg_roli(db, "techniczny", TECHNICZNY_STANOWISKO)


def zapisz_audyt(db, user, akcja, *, zasob=None, pracownik_id=None, request=None, szczegoly=None):
    """Zapisuje wpis dziennika audytu dostępu do danych wrażliwych (RODO). Best-effort —
    błąd audytu NIGDY nie przerywa właściwej operacji. `login` denormalizowany (rozliczalność).
    Znacznik czasu jako naiwny UTC (spójność SQLite/Postgres)."""
    try:
        ip = request.client.host if (request is not None and request.client) else None
        db.add(models.AuditLog(
            ts=datetime.now(timezone.utc).replace(tzinfo=None),
            user_id=getattr(user, "id", None),
            login=getattr(user, "login", None),
            akcja=akcja, zasob=zasob, pracownik_id=pracownik_id, ip=ip, szczegoly=szczegoly,
        ))
        db.commit()
    except Exception:
        db.rollback()


# Kwalifikacje działu technicznego (nadawane w Pracownikach jak zwykłe kwalifikacje = Stanowiska).
# „Sprzątaczka" daje dostęp do formularza zamówień; „Stróż" na razie tylko jako oznaczenie.
SPRZATACZKA_NAZWA = "Sprzątaczka"
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


def _jest_sprzataczka(prac: models.Pracownik) -> bool:
    """Dostęp do formularza zamówień: dział techniczny + kwalifikacja z flagą `daje_dostep_zamowien`
    (fallback po nazwie „Sprzątaczka" dla danych sprzed migracji)."""
    return bool(prac and prac.dzial == "techniczny"
                and any(getattr(s, "daje_dostep_zamowien", False) or (s.nazwa or "") == SPRZATACZKA_NAZWA
                        for s in prac.kwalifikacje))


# „Parkiet": stanowiska, których nazwa zaczyna się od „Sala" (Sala, Sala-ABC, Sala-RZP,
# Sala-Bar...). Spośród nich wybieramy osobę ZAMYKAJĄCĄ lokal — patrz _przelicz_zamykajacego.
SALA_PREFIX = "sala"


def _data_env(nazwa: str, domyslnie: str):
    """Czyta datę (RRRR-MM-DD) ze zmiennej środowiskowej; puste/niepoprawne -> None."""
    s = (os.environ.get(nazwa, domyslnie) or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


# Rozliczenia sali liczymy DOPIERO od dnia startu systemu — inaczej kelnerom wyskakują
# „zaległe" rozliczenia ze zmian Gastro sprzed wdrożenia (które nigdy nie były potwierdzane
# w aplikacji). Sterowane env ROZLICZENIA_START=RRRR-MM-DD (ustawiane na serwerze na dzień
# uruchomienia; puste/brak = bez cięcia). Po ~21 dniach naturalne okno (dziś−21) i tak wyprzedza
# tę datę, więc cięcie samo przestaje cokolwiek zmieniać.
ROZLICZENIA_START = _data_env("ROZLICZENIA_START", "")


def _sala_stanowisko_ids(db) -> set:
    """Stanowiska parkietu (kelnerzy). Rola 'sala' albo — fallback — nazwa zaczyna się od „Sala"."""
    return {s.id for s in db.query(models.Stanowisko).all()
            if s.rola == "sala" or (s.nazwa or "").strip().lower().startswith(SALA_PREFIX)}


def _przelicz_zamykajacego(db, dzien: date):
    """„zamyka lokal" dla danego dnia. RĘCZNE NADPISANIE ma pierwszeństwo: jeśli ktoś tego dnia
    ma zamyka_reczny=True, to ON zamyka i automat go nie zmienia. W innym wypadku AUTO wybiera
    osobę z NAJPÓŹNIEJSZYM godz_od na parkiecie (Sala*) — kandydaci muszą mieć godz_od. Reszta
    dnia ma zamyka=False. Commit tylko gdy coś realnie się zmienia. Zwraca zamykającego/None."""
    rows = db.query(models.PrzydzialZmiany).filter(models.PrzydzialZmiany.data == dzien).all()
    reczny = next((a for a in rows if a.zamyka_reczny), None)
    if reczny is not None:
        zamykajacy = reczny                      # ręczne nadpisanie — automat nie rusza
    else:
        sala_ids = _sala_stanowisko_ids(db)
        kandydaci = [a for a in rows if a.stanowisko_id in sala_ids]
        # Najpóźniejszy start zamyka. Brak godziny = traktujemy jak najwcześniejszą (00:00),
        # więc osoba z wpisaną godziną wygrywa; gdy NIKT na Sali nie ma godziny — i tak wybieramy
        # ostatnio dodanego (najwyższe id), żeby ZAWSZE ktoś był oznaczony jako zamykający.
        zamykajacy = max(kandydaci, key=lambda a: (a.godz_od or time.min, a.id)) if kandydaci else None
    zmienione = False
    for a in rows:
        powinien = zamykajacy is not None and a.id == zamykajacy.id
        if bool(a.zamyka) != powinien:
            a.zamyka = powinien
            zmienione = True
    if zmienione:
        db.commit()
    return zamykajacy


@app.on_event("startup")
def startup():
    # Fail-fast: w produkcji odmawiamy startu przy niebezpiecznych sekretach domyślnych.
    app_settings.validate_critical_secrets()
    init_db()
    # Stanowisko kuchni tworzymy LENIWIE (endpoint /api/grafik/kuchnia-stanowisko), nie na starcie —
    # żeby nie zaśmiecać bazy/testów dodatkowym stanowiskiem, gdy grafik kuchni nie jest używany.
    # Uwaga: konto administratora NIE jest już tworzone z pliku konfiguracyjnego (.env).
    # Admina zakłada się wyłącznie w bazie skryptem: python create_admin.py


@app.get("/api/health")
def health():
    """Publiczny status backendu (m.in. Electron sprawdza tu gotowość serwera)."""
    return {"status": "ok"}


# ... [Funkcja parse_date pozostaje bez zmian] ...
def parse_date(s: str) -> date:
    s = s.strip()
    if re.match(r"\d{4}-\d{2}-\d{2}", s): return date.fromisoformat(s)
    if re.match(r"\d{2}\.\d{2}\.\d{4}", s):
        d, m, y = s.split(".")
        return date(int(y), int(m), int(d))
    raise ValueError(f"Nieznany format daty: {s}")


# ═══════════════════════════════════════════════════════════════════════════
# AUTORYZACJA / UŻYTKOWNICY
# ═══════════════════════════════════════════════════════════════════════════

def _user_out(u: models.User) -> schemas.UserOut:
    return schemas.UserOut(
        id=u.id, login=u.login, rola=u.rola, aktywny=bool(u.aktywny),
        pracownik_id=u.pracownik_id,
        dzial=u.pracownik.dzial if u.pracownik else None,
        sprzataczka=_jest_sprzataczka(u.pracownik) if u.pracownik else False,
        imie=u.pracownik.imie if u.pracownik else None,
        nazwisko=u.pracownik.nazwisko if u.pracownik else None,
    )

@app.post("/api/auth/login", response_model=schemas.TokenOut)
def login(dane: schemas.LoginIn, request: Request, db: Session = Depends(get_db)):
    # Ochrona przed brute-force: limit prób + czasowy lockout (per login+IP oraz per IP).
    ip = request.client.host if request.client else "?"
    klucze = [f"login:{dane.login}|ip:{ip}", f"ip:{ip}"]
    for k in klucze:
        blok = ratelimit.pozostala_blokada(k)
        if blok:
            raise HTTPException(429, f"Za dużo prób logowania. Spróbuj ponownie za {blok} s.",
                                headers={"Retry-After": str(blok)})
    user = db.query(models.User).filter(models.User.login == dane.login).first()
    if not user or not user.aktywny or not verify_password(dane.haslo, user.haslo_hash):
        for k in klucze:
            ratelimit.zarejestruj_porazke(k)
        raise HTTPException(401, "Nieprawidłowy login lub hasło.")
    for k in klucze:
        ratelimit.zarejestruj_sukces(k)
    return schemas.TokenOut(access_token=create_access_token(user), user=_user_out(user))

@app.post("/api/auth/register", response_model=schemas.TokenOut, status_code=201)
def register(dane: schemas.RegisterIn, db: Session = Depends(get_db)):
    """Samodzielna rejestracja pracownika. Tworzy Pracownika + konto (rola employee)
    i od razu loguje (zwraca token). Wszystkie zapytania przez ORM = parametryzowane
    (brak ryzyka SQL Injection)."""
    login = sprawdz_login(dane.login)        # min 5, tylko [A-Za-z0-9]
    sprawdz_haslo(dane.haslo)                 # min 8, litera+cyfra+znak specjalny, ASCII
    imie = (dane.imie or "").strip()
    nazwisko = (dane.nazwisko or "").strip()
    if not imie or not nazwisko:
        raise HTTPException(400, "Podaj imię i nazwisko.")
    if db.query(models.User).filter(models.User.login == login).first():
        raise HTTPException(400, "Ten login jest już zajęty.")

    # Nie duplikuj pracownika: jesli istnieje juz ktos o tym samym (znormalizowanym) imieniu
    # i nazwisku BEZ konta (np. zalozony wczesniej albo dopasowany przez RCP) — podepnij konto
    # pod niego, zeby od razu mialo jego godziny. Inaczej tworzymy nowego pracownika.
    norm = _norm_nazwa(f"{imie} {nazwisko}")
    zajete = {u.pracownik_id for u in db.query(models.User).all() if u.pracownik_id}
    prac = next(
        (p for p in db.query(models.Pracownik).all()
         if p.id not in zajete and _norm_nazwa(f"{p.imie} {p.nazwisko}") == norm),
        None,
    )
    if prac is None:
        prac = models.Pracownik(imie=imie, nazwisko=nazwisko, aktywny=True)
        db.add(prac)
        db.flush()  # nadaje prac.id bez commita
    user = models.User(
        login=login, haslo_hash=hash_password(dane.haslo),
        rola="employee", pracownik_id=prac.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _przypisz_odbicia_do_pracownika(db, prac)  # podlinkuj zalegle odbicia RCP do nowego konta
    return schemas.TokenOut(access_token=create_access_token(user), user=_user_out(user))


# ── ONBOARDING (samoobsługowa pierwsza konfiguracja instancji) ────────────────

@app.get("/api/onboarding/status")
def onboarding_status(db: Session = Depends(get_db)):
    """Publiczny: czy instancja wymaga pierwszej konfiguracji (brak jakiegokolwiek użytkownika)."""
    potrzebny = db.query(models.User).first() is None
    return {"potrzebny": potrzebny, "nazwa_lokalu": get_lokal_config(db).nazwa_lokalu}


@app.post("/api/onboarding/bootstrap", response_model=schemas.TokenOut, status_code=201)
def onboarding_bootstrap(dane: schemas.OnboardingIn, db: Session = Depends(get_db)):
    """Publiczny, JEDNORAZOWY: na świeżej instancji (0 użytkowników) tworzy pierwszego
    administratora i ustawia nazwę lokalu, po czym od razu loguje (zwraca token). Jeśli
    jakikolwiek użytkownik już istnieje → 409 (ochrona przed przejęciem działającej instancji)."""
    if db.query(models.User).first() is not None:
        raise HTTPException(409, "Onboarding już wykonany — instancja ma administratora.")
    login = sprawdz_login(dane.login)
    sprawdz_haslo(dane.haslo)
    admin = models.User(login=login, haslo_hash=hash_password(dane.haslo), rola="admin")
    db.add(admin)
    cfg = get_lokal_config(db)
    if dane.nazwa_lokalu and dane.nazwa_lokalu.strip():
        cfg.nazwa_lokalu = dane.nazwa_lokalu.strip()
    db.commit(); db.refresh(admin)
    return schemas.TokenOut(access_token=create_access_token(admin), user=_user_out(admin))


@app.get("/api/auth/me", response_model=schemas.UserOut)
def auth_me(user: models.User = Depends(get_current_user)):
    return _user_out(user)


@app.get("/api/me/uprawnienia")
def me_uprawnienia(user: models.User = Depends(get_current_user)):
    """Granularne uprawnienia zalogowanego użytkownika (RBAC) — do sterowania UI.
    Krytyczny enforcement po stronie API dalej robi middleware role_guard."""
    return {"rola": user.rola, "uprawnienia": uprawnienia.uprawnienia(user.rola)}

# --- Zarządzanie kontami (dostęp tylko admin — wymusza middleware) ---

@app.get("/api/users", response_model=List[schemas.UserOut])
def list_users(db: Session = Depends(get_db)):
    return [_user_out(u) for u in db.query(models.User).order_by(models.User.id).all()]

@app.post("/api/users", response_model=schemas.UserOut, status_code=201)
def create_user(dane: schemas.UserCreate, db: Session = Depends(get_db)):
    if dane.rola not in ROLE_VALID:
        raise HTTPException(400, "Nieprawidłowa rola.")
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
    )
    db.add(u); db.commit(); db.refresh(u)
    return _user_out(u)

@app.put("/api/users/{uid}", response_model=schemas.UserOut)
def update_user(uid: int, dane: schemas.UserUpdate, db: Session = Depends(get_db)):
    u = db.get(models.User, uid)
    if not u:
        raise HTTPException(404, "Nie znaleziono konta.")
    if dane.rola is not None:
        if dane.rola not in ROLE_VALID:
            raise HTTPException(400, "Nieprawidłowa rola.")
        u.rola = dane.rola
    if dane.aktywny is not None:
        u.aktywny = dane.aktywny
    if dane.pracownik_id is not None:
        u.pracownik_id = dane.pracownik_id
    db.commit(); db.refresh(u)
    return _user_out(u)

@app.post("/api/users/{uid}/reset-haslo", status_code=204)
def reset_haslo(uid: int, dane: schemas.ResetHasloIn, db: Session = Depends(get_db)):
    u = db.get(models.User, uid)
    if not u:
        raise HTTPException(404, "Nie znaleziono konta.")
    u.haslo_hash = hash_password(dane.haslo)
    db.commit()

@app.delete("/api/users/{uid}", status_code=204)
def delete_user(uid: int, db: Session = Depends(get_db)):
    u = db.get(models.User, uid)
    if not u:
        raise HTTPException(404, "Nie znaleziono konta.")
    db.delete(u); db.commit()

@app.post("/api/users/provision", status_code=200)
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

# --- Samoobsługa: dyspozycyjność zalogowanego pracownika ---

@app.get("/api/me/dyspozycje", response_model=List[schemas.DyspozycjaOut])
def moje_dyspozycje(
    start: Optional[date] = None, end: Optional[date] = None,
    user: models.User = Depends(get_current_user), db: Session = Depends(get_db),
):
    if not user.pracownik_id:
        raise HTTPException(400, "Konto nie jest powiązane z pracownikiem.")
    q = db.query(models.Dyspozycja).filter(models.Dyspozycja.pracownik_id == user.pracownik_id)
    if start: q = q.filter(models.Dyspozycja.data >= start)
    if end:   q = q.filter(models.Dyspozycja.data <= end)
    return q.all()

@app.get("/api/me/imprezy")
def moje_imprezy(
    start: date = Query(...), end: date = Query(...),
    user: models.User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Imprezy w zakresie — podgląd dla pracownika przy składaniu dyspozycji.
    PRYWATNOŚĆ: pracownik NIE dostaje nazwy klienta/imprezy — tylko salę, godzinę, liczbę osób."""
    imprezy = (
        db.query(models.Impreza)
        .filter(models.Impreza.data >= start, models.Impreza.data <= end)
        .order_by(models.Impreza.data.asc(), models.Impreza.godzina.asc())
        .all()
    )
    return [
        {"id": i.id, "data": str(i.data), "godzina": i.godzina, "sala": i.sala, "liczba_osob": i.liczba_osob}
        for i in imprezy
    ]

@app.put("/api/me/dyspozycje", status_code=200)
def zapisz_moje_dyspozycje(
    batch: schemas.MojeDyspozycjeBatch,
    user: models.User = Depends(get_current_user), db: Session = Depends(get_db),
):
    if not user.pracownik_id:
        raise HTTPException(400, "Konto nie jest powiązane z pracownikiem.")
    # Edycja dyspozycji możliwa tylko DO publikacji grafiku danego tygodnia.
    daty = [d.data for d in batch.dyspozycje]
    if daty:
        opub = db.query(models.PublikacjaGrafiku).filter(
            models.PublikacjaGrafiku.start <= min(daty),
            models.PublikacjaGrafiku.koniec >= max(daty),
        ).first()
        if opub:
            raise HTTPException(409, "Grafik na ten tydzień jest już opublikowany — dyspozycji nie można już zmieniać.")
    zapisano = 0
    for d in batch.dyspozycje:
        existing = db.query(models.Dyspozycja).filter_by(
            pracownik_id=user.pracownik_id, data=d.data
        ).first()
        if existing:
            existing.dostepnosc = d.dostepnosc
            existing.godz_od = d.godz_od
            existing.godz_do = d.godz_do
        else:
            db.add(models.Dyspozycja(
                pracownik_id=user.pracownik_id, data=d.data,
                dostepnosc=d.dostepnosc, godz_od=d.godz_od, godz_do=d.godz_do,
            ))
        zapisano += 1
    db.commit()
    return {"zapisano": zapisano}


def _rewir_dla_pracownika(rewir):
    """Ukrywa nazwę klienta/imprezy przed pracownikiem. Rewir imprezy ma postać
    „IMPREZA: {klient} ({sala})" — zwracamy tylko „Impreza ({sala})". Zwykłe rewiry bez zmian."""
    if rewir and rewir.startswith("IMPREZA:"):
        sala = rewir[rewir.rfind("(") + 1 : -1].strip() if rewir.endswith(")") and "(" in rewir else ""
        return f"Impreza ({sala})" if sala and sala.lower() not in ("brak", "none") else "Impreza"
    return rewir


@app.get("/api/me/grafik", status_code=200)
def moj_grafik(
    start: date = Query(...), end: date = Query(...),
    user: models.User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Grafik zalogowanego pracownika — TYLKO jeśli tydzień został udostępniony przez
    admina. Zwraca zmiany z rewirem oraz współpracownikami dzielącymi ten rewir."""
    if not user.pracownik_id:
        raise HTTPException(400, "Konto nie jest powiązane z pracownikiem.")
    prac = db.get(models.Pracownik, user.pracownik_id)
    jest_kuchnia = bool(prac and prac.dzial == "kuchnia")
    pub = db.query(models.PublikacjaGrafiku).filter_by(start=start, koniec=end).first()
    # „Rozlicz się" jest globalne (ostatnie 21 dni z Gastro), niezależne od oglądanego tygodnia.
    oczekujace = _rozliczenia_oczekujace(db, user.pracownik_id)
    # Kuchnia: grafik „żywy" — kucharz widzi swoje zmiany od razu (bez czekania na publikację).
    if not pub and not jest_kuchnia:
        return {"opublikowany": False, "opublikowano_at": None, "zmiany": [],
                "rozliczenia_oczekujace": oczekujace}

    moje = (
        db.query(models.PrzydzialZmiany)
        .filter(
            models.PrzydzialZmiany.pracownik_id == user.pracownik_id,
            models.PrzydzialZmiany.data >= start,
            models.PrzydzialZmiany.data <= end,
        )
        .order_by(models.PrzydzialZmiany.data.asc(), models.PrzydzialZmiany.godz_od.asc())
        .all()
    )
    stan_objs = db.query(models.Stanowisko).all()
    stan_map = {s.id: s.nazwa for s in stan_objs}
    stan_grupa = {s.id: (s.grupa_widocznosci or "").strip().lower() for s in stan_objs}
    stan_wszyscy = {s.id: bool(s.widoczny_dla_wszystkich) for s in stan_objs}
    prac_map = {p.id: f"{p.imie} {p.nazwisko}" for p in db.query(models.Pracownik).all()}

    def _norm_rewir(r):
        return (r or "").strip()

    sala_ids = _sala_stanowisko_ids(db)
    _status_cache = {}
    def _status_sala(d):
        if d not in _status_cache:
            _status_cache[d] = _rozlicz_sala_status(db, user.pracownik_id, d, sala_ids)
        return _status_cache[d]

    zmiany = []
    for a in moje:
        # Z kim pracuję danego dnia — niezależnie od godziny przyjścia. Widzę:
        #  • ten sam REWIR na MOIM stanowisku (np. Sala/Parter — nie całą Salę),
        #  • stanowiska „widoczne dla wszystkich" (np. Menadżer),
        #  • stanowiska z mojej „grupy widoczności" (np. KOMP↔Wydawka).
        sv, rv = a.stanowisko_id, _norm_rewir(a.rewir)
        grupa_v = stan_grupa.get(sv, "")
        kandydaci = (
            db.query(models.PrzydzialZmiany)
            .filter(
                models.PrzydzialZmiany.data == a.data,
                models.PrzydzialZmiany.pracownik_id != user.pracownik_id,
            )
            .all()
        )
        wspol = []
        for w in kandydaci:
            ten_sam_rewir = w.stanowisko_id == sv and _norm_rewir(w.rewir) == rv
            dla_wszystkich = stan_wszyscy.get(w.stanowisko_id, False)
            ta_sama_grupa = bool(grupa_v) and stan_grupa.get(w.stanowisko_id, "") == grupa_v and w.stanowisko_id != sv
            if ten_sam_rewir or dla_wszystkich or ta_sama_grupa:
                wspol.append(w)
        wspol.sort(key=lambda w: (w.godz_od or time.min, w.id))
        zmiany.append({
            "data": str(a.data),
            "godz_od": a.godz_od.strftime("%H:%M") if a.godz_od else None,
            "stanowisko": stan_map.get(a.stanowisko_id, ""),
            "rewir": _rewir_dla_pracownika(a.rewir),
            "zamyka": bool(a.zamyka),
            "zamyka_rewir": bool(a.zamyka_rewir),
            "rozlicza_imprize": bool(a.rozlicza_imprize),
            "rozlicz_sala": _status_sala(a.data),   # None | 'oczekuje' | 'wyslane' (sala + zamknięte Gastro)
            "wspolpracownicy": [
                {"imie": prac_map.get(w.pracownik_id, ""),
                 "stanowisko": stan_map.get(w.stanowisko_id, ""),
                 "godz_od": w.godz_od.strftime("%H:%M") if w.godz_od else None,
                 "zamyka": bool(w.zamyka)}
                for w in wspol
            ],
        })
    return {"opublikowany": True, "opublikowano_at": pub.opublikowano_at.isoformat() if pub else None,
            "zmiany": zmiany, "rozliczenia_oczekujace": oczekujace}

# --- GRAFIK SPRZĄTANIA (dział techniczny + admin) ---

def _wymagaj_technicznego(user: models.User, db) -> models.Pracownik:
    """Sprzątanie widzi dział techniczny (i admin). Zwraca pracownika (dla odhaczeń)."""
    prac = db.get(models.Pracownik, user.pracownik_id) if user.pracownik_id else None
    if user.rola != "admin" and (not prac or prac.dzial != "techniczny"):
        raise HTTPException(403, "Grafik sprzątania jest dostępny dla działu technicznego.")
    return prac


@app.get("/api/me/sprzatanie")
def moje_sprzatanie(
    start: date = Query(...), end: date = Query(...),
    user: models.User = Depends(get_current_user), db: Session = Depends(get_db),
):
    _wymagaj_technicznego(user, db)
    return {"pozycje": sprzatanie.generuj(db, start, end), "sale": list(sprzatanie.SALE)}


@app.put("/api/me/sprzatanie/zrobione", status_code=204)
def odhacz_sprzatanie(
    dane: schemas.SprzatanieZrobioneIn,
    user: models.User = Depends(get_current_user), db: Session = Depends(get_db),
):
    prac = _wymagaj_technicznego(user, db)
    if dane.sala not in sprzatanie.SALE:
        raise HTTPException(400, "Nieznana sala.")
    istn = db.query(models.SprzatanieOdhaczenie).filter_by(data=dane.data, sala=dane.sala).first()
    if dane.zrobione and not istn:
        db.add(models.SprzatanieOdhaczenie(
            data=dane.data, sala=dane.sala,
            pracownik_id=prac.id if prac else None, odhaczono_at=utcnow_naive(),
        ))
    elif not dane.zrobione and istn:
        db.delete(istn)  # odznaczenie ✓ (cofnięcie własnego odhaczenia)
    db.commit()


@app.get("/api/sprzatanie")
def sprzatanie_admin(start: date = Query(...), end: date = Query(...), db: Session = Depends(get_db)):
    return {"pozycje": sprzatanie.generuj(db, start, end), "sale": list(sprzatanie.SALE)}


@app.post("/api/sprzatanie/korekty", status_code=204)
def korekta_sprzatania(dane: schemas.SprzatanieKorektaIn, db: Session = Depends(get_db)):
    """Dodaj/usuń pozycję sprzątania. Przeciwna akcja do istniejącej korekty KASUJE ją
    (powrót do automatu) — dzięki temu przyciski w UI działają jak przełącznik."""
    if dane.sala not in sprzatanie.SALE:
        raise HTTPException(400, "Nieznana sala.")
    if dane.akcja not in ("dodaj", "usun"):
        raise HTTPException(400, "Akcja musi być 'dodaj' albo 'usun'.")
    istn = db.query(models.SprzatanieKorekta).filter_by(data=dane.data, sala=dane.sala).first()
    if istn:
        if istn.akcja != dane.akcja:
            db.delete(istn)   # przeciwna korekta = cofnięcie poprzedniej
        # ta sama akcja -> idempotentnie nic
    else:
        db.add(models.SprzatanieKorekta(data=dane.data, sala=dane.sala, akcja=dane.akcja))
    db.commit()


# --- ZAMÓWIENIA SPRZĄTACZKI (dział techniczny) ---

ZDJECIE_MAX = 2_000_000   # ~2 MB data URL (front i tak zmniejsza zdjęcie przed wysyłką)


def _zamowienie_out(z, prac_map):
    # Lista NIE zawiera samego zdjęcia (może być ciężkie) — tylko flagę; obrazek pobiera się osobno.
    return {
        "id": z.id, "pracownik": prac_map.get(z.pracownik_id),
        "nazwa": z.nazwa, "ilosc": z.ilosc, "notatka": z.notatka,
        "ma_zdjecie": bool(z.zdjecie), "status": z.status,
        "utworzono_at": z.utworzono_at.isoformat() if z.utworzono_at else None,
    }


@app.post("/api/me/zamowienia", status_code=201)
def utworz_zamowienie(dane: schemas.ZamowienieIn,
                      user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Sprzątaczka zgłasza zamówienie produktu → push do administratorów."""
    prac = db.get(models.Pracownik, user.pracownik_id) if user.pracownik_id else None
    if not _jest_sprzataczka(prac):
        raise HTTPException(403, 'Formularz zamówień jest dla sprzątaczki (dział techniczny z kwalifikacją „Sprzątaczka").')
    nazwa = (dane.nazwa or "").strip()
    if not nazwa:
        raise HTTPException(400, "Podaj nazwę produktu.")
    if dane.zdjecie and len(dane.zdjecie) > ZDJECIE_MAX:
        raise HTTPException(400, "Zdjęcie jest za duże — zrób mniejsze lub pomiń.")
    z = models.ZamowienieSprzataczki(
        pracownik_id=prac.id, utworzono_at=utcnow_naive(), nazwa=nazwa,
        ilosc=(dane.ilosc or "").strip() or None, notatka=(dane.notatka or "").strip() or None,
        zdjecie=dane.zdjecie or None, status="nowe",
    )
    db.add(z); db.commit(); db.refresh(z)
    wyslij_push_do_adminow(db, "Nowe zamówienie", f"{prac.imie} {prac.nazwisko}: {nazwa}", url="/")
    return {"id": z.id}


@app.get("/api/me/zamowienia")
def moje_zamowienia(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    prac = db.get(models.Pracownik, user.pracownik_id) if user.pracownik_id else None
    if not _jest_sprzataczka(prac):
        raise HTTPException(403, "Tylko dla sprzątaczki.")
    rows = (db.query(models.ZamowienieSprzataczki).filter_by(pracownik_id=prac.id)
            .order_by(models.ZamowienieSprzataczki.utworzono_at.desc()).all())
    prac_map = {prac.id: f"{prac.imie} {prac.nazwisko}"}
    return {"zamowienia": [_zamowienie_out(z, prac_map) for z in rows]}


@app.get("/api/me/zamowienia/{zid}/zdjecie")
def moje_zamowienie_zdjecie(zid: int, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    z = db.get(models.ZamowienieSprzataczki, zid)
    if not z or z.pracownik_id != user.pracownik_id:
        raise HTTPException(404, "Nie znaleziono.")
    return {"zdjecie": z.zdjecie}


@app.get("/api/zamowienia")
def lista_zamowien(db: Session = Depends(get_db)):
    """Wszystkie zamówienia (admin) — od najnowszych."""
    rows = (db.query(models.ZamowienieSprzataczki)
            .order_by(models.ZamowienieSprzataczki.utworzono_at.desc()).all())
    prac_map = {p.id: f"{p.imie} {p.nazwisko}" for p in db.query(models.Pracownik).all()}
    return {"zamowienia": [_zamowienie_out(z, prac_map) for z in rows]}


@app.get("/api/zamowienia/{zid}/zdjecie")
def zamowienie_zdjecie(zid: int, db: Session = Depends(get_db)):
    z = db.get(models.ZamowienieSprzataczki, zid)
    if not z:
        raise HTTPException(404, "Nie znaleziono.")
    return {"zdjecie": z.zdjecie}


@app.put("/api/zamowienia/{zid}/status", status_code=204)
def zmien_status_zamowienia(zid: int, dane: schemas.ZamowienieStatusIn, db: Session = Depends(get_db)):
    """Admin: 'odczytane' albo 'zamowione' → push do autorki."""
    z = db.get(models.ZamowienieSprzataczki, zid)
    if not z:
        raise HTTPException(404, "Nie znaleziono zamówienia.")
    if dane.status not in ("odczytane", "zamowione"):
        raise HTTPException(400, "Status musi być 'odczytane' albo 'zamowione'.")
    teraz = utcnow_naive()
    z.status = dane.status
    if dane.status == "odczytane" and not z.odczytano_at:
        z.odczytano_at = teraz
    if dane.status == "zamowione" and not z.zamowiono_at:
        z.zamowiono_at = teraz
    db.commit()
    tresc = ("Twoje zamówienie zostało odczytane." if dane.status == "odczytane"
             else f"Zamówiono: {z.nazwa}.")
    wyslij_push_do_pracownika(db, z.pracownik_id, "Zamówienie", tresc, url="/")


# --- URLOPY (obsługa) ---

def _urlop_out(u, prac_map):
    return {
        "id": u.id, "pracownik": prac_map.get(u.pracownik_id), "pracownik_id": u.pracownik_id,
        "start": str(u.start), "koniec": str(u.koniec), "powod": u.powod,
        "status": u.status, "utworzono_at": u.utworzono_at.isoformat() if u.utworzono_at else None,
    }


@app.post("/api/me/urlopy", status_code=201)
def zloz_urlop(dane: schemas.UrlopIn,
               user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Pracownik OBSŁUGI składa wniosek urlopowy → push do administratorów."""
    prac = db.get(models.Pracownik, user.pracownik_id) if user.pracownik_id else None
    if not prac or prac.dzial != "obsluga":
        raise HTTPException(403, "Wnioski urlopowe są dla pracowników obsługi.")
    if dane.koniec < dane.start:
        raise HTTPException(400, "Data końca nie może być wcześniejsza niż początek.")
    u = models.Urlop(pracownik_id=prac.id, start=dane.start, koniec=dane.koniec,
                     powod=(dane.powod or "").strip() or None, status="oczekuje",
                     utworzono_at=utcnow_naive())
    db.add(u); db.commit(); db.refresh(u)
    wyslij_push_do_adminow(db, "Wniosek urlopowy",
                           f"{prac.imie} {prac.nazwisko}: {dane.start.strftime('%d.%m')}–{dane.koniec.strftime('%d.%m')}", url="/")
    return {"id": u.id}


@app.get("/api/me/urlopy")
def moje_urlopy(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.pracownik_id:
        return {"urlopy": []}
    rows = (db.query(models.Urlop).filter_by(pracownik_id=user.pracownik_id)
            .order_by(models.Urlop.start.desc()).all())
    prac = db.get(models.Pracownik, user.pracownik_id)
    prac_map = {prac.id: f"{prac.imie} {prac.nazwisko}"} if prac else {}
    return {"urlopy": [_urlop_out(u, prac_map) for u in rows]}


@app.delete("/api/me/urlopy/{uid}", status_code=204)
def anuluj_urlop(uid: int, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Pracownik wycofuje WŁASNY wniosek — tylko gdy jeszcze oczekuje."""
    u = db.get(models.Urlop, uid)
    if not u or u.pracownik_id != user.pracownik_id:
        raise HTTPException(404, "Nie znaleziono.")
    if u.status != "oczekuje":
        raise HTTPException(400, "Można wycofać tylko wniosek oczekujący.")
    db.delete(u); db.commit()


@app.get("/api/urlopy")
def lista_urlopow(db: Session = Depends(get_db)):
    """Wszystkie wnioski (admin) — oczekujące najpierw, potem wg daty startu malejąco."""
    rows = db.query(models.Urlop).all()
    prac_map = {p.id: f"{p.imie} {p.nazwisko}" for p in db.query(models.Pracownik).all()}
    rows.sort(key=lambda u: (u.status != "oczekuje", -u.start.toordinal()))
    return {"urlopy": [_urlop_out(u, prac_map) for u in rows]}


@app.put("/api/urlopy/{uid}/status", status_code=204)
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
    wyslij_push_do_pracownika(db, u.pracownik_id, "Urlop",
                              f"Twój wniosek urlopowy ({u.start.strftime('%d.%m')}–{u.koniec.strftime('%d.%m')}) został {slowo}.", url="/")


# --- ROZLICZANIE IMPREZ (osoba wyznaczona w grafiku) ---

def _moze_rozliczyc_imprize(db, pracownik_id: int, data: date):
    """Przydział tej osoby tego dnia na stanowisku imprezowym z flagą rozlicza_imprize (albo None)."""
    imprezy_ids = {s.id for s in db.query(models.Stanowisko).all()
                   if (s.nazwa or "").strip().lower().startswith("imprez")}
    if not imprezy_ids:
        return None
    return (db.query(models.PrzydzialZmiany)
            .filter(models.PrzydzialZmiany.pracownik_id == pracownik_id,
                    models.PrzydzialZmiany.data == data,
                    models.PrzydzialZmiany.rozlicza_imprize == True,  # noqa: E712
                    models.PrzydzialZmiany.stanowisko_id.in_(imprezy_ids))
            .first())


def imp_dla_dnia(db, data: date) -> dict:
    """Kwoty IMP dla rozliczenia dnia (D2). Gotówka SFISKALIZOWANA z imprez → minus w kasach;
    karta z imprez → minus w terminalach i kasach. Gotówka niesfiskalizowana i przelew NIE wchodzą."""
    gotowka_sfisk = karta = 0.0
    for r in db.query(models.RozliczenieImprezy).filter_by(data=data).all():
        for p in r.pozycje:
            if p.forma == "gotowka" and p.sfiskalizowane:
                gotowka_sfisk += p.kwota or 0
            elif p.forma == "karta":
                karta += p.kwota or 0
    return {"gotowka_sfiskalizowana": round(gotowka_sfisk, 2), "karta": round(karta, 2)}


@app.post("/api/me/imprezy/rozlicz", status_code=201)
def rozlicz_imprize(dane: schemas.RozliczenieImprezyIn,
                    user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Osoba wyznaczona w grafiku rozlicza imprezę (upsert na dany dzień) → push do adminów."""
    prac = db.get(models.Pracownik, user.pracownik_id) if user.pracownik_id else None
    if not prac or not _moze_rozliczyc_imprize(db, prac.id, dane.data):
        raise HTTPException(403, "Imprezę rozlicza tylko osoba wyznaczona w grafiku (rozlicza imprezę).")
    for p in dane.pozycje:
        if p.forma not in ("gotowka", "karta", "przelew"):
            raise HTTPException(400, "Forma musi być: gotowka, karta albo przelew.")
    r = db.query(models.RozliczenieImprezy).filter_by(pracownik_id=prac.id, data=dane.data).first()
    if r is None:
        r = models.RozliczenieImprezy(pracownik_id=prac.id, data=dane.data, utworzono_at=utcnow_naive())
        db.add(r)
    r.opis = (dane.opis or "").strip() or None
    r.pozycje.clear()
    for p in dane.pozycje:
        r.pozycje.append(models.RozliczenieImprezyPozycja(
            forma=p.forma, kwota=float(p.kwota or 0),
            sfiskalizowane=bool(p.sfiskalizowane) if p.forma == "gotowka" else False))
    db.commit(); db.refresh(r)
    wyslij_push_do_adminow(db, "Rozliczenie imprezy",
                           f"{prac.imie} {prac.nazwisko}: {dane.data.strftime('%d.%m')}", url="/")
    return {"id": r.id}


@app.get("/api/me/imprezy/rozlicz")
def moje_rozliczenie_imprezy(data: date = Query(...),
                             user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Czy wolno rozliczać + ewentualne dotychczasowe pozycje (prefill/edycja)."""
    prac = db.get(models.Pracownik, user.pracownik_id) if user.pracownik_id else None
    przydzial = _moze_rozliczyc_imprize(db, prac.id, data) if prac else None
    r = db.query(models.RozliczenieImprezy).filter_by(pracownik_id=user.pracownik_id, data=data).first() if prac else None
    return {
        "moze": przydzial is not None,
        "rewir": _rewir_dla_pracownika(przydzial.rewir) if przydzial else None,
        "pozycje": [{"forma": p.forma, "kwota": p.kwota, "sfiskalizowane": p.sfiskalizowane} for p in (r.pozycje if r else [])],
    }


@app.get("/api/imprezy/rozliczenia")
def rejestr_imprez(start: date = Query(...), end: date = Query(...), db: Session = Depends(get_db)):
    """Rejestr rozliczeń imprez (admin) — per impreza, z pozycjami i sumami per forma."""
    rows = (db.query(models.RozliczenieImprezy)
            .filter(models.RozliczenieImprezy.data >= start, models.RozliczenieImprezy.data <= end)
            .order_by(models.RozliczenieImprezy.data.desc()).all())
    prac_map = {p.id: f"{p.imie} {p.nazwisko}" for p in db.query(models.Pracownik).all()}
    out = []
    for r in rows:
        poz = [{"forma": p.forma, "kwota": p.kwota, "sfiskalizowane": p.sfiskalizowane} for p in r.pozycje]
        out.append({
            "id": r.id, "data": str(r.data), "pracownik": prac_map.get(r.pracownik_id), "opis": r.opis,
            "pozycje": poz,
            "suma_gotowka": round(sum(p["kwota"] for p in poz if p["forma"] == "gotowka"), 2),
            "suma_karta": round(sum(p["kwota"] for p in poz if p["forma"] == "karta"), 2),
            "suma_przelew": round(sum(p["kwota"] for p in poz if p["forma"] == "przelew"), 2),
        })
    return {"rozliczenia": out, "razem": {k: round(sum(o[k] for o in out), 2) for k in ("suma_gotowka", "suma_karta", "suma_przelew")}}


# --- ROZLICZENIE DNIA (sala) ---

def _gastro_dla_kelnera(db, pid: int, data: date) -> dict:
    """Prefill kelnera z Gastro: G/T = zadeklarowane gotówka/karta, FV = sprzedaż KARTA_FV+GOTÓWKA_FV.
    (BON pomijamy — nie przechodzi przez kasę i nie wchodzi do utargu.)"""
    rows = db.query(models.RozliczenieGastro).filter_by(pracownik_id=pid, data=data).all()
    g = sum(r.deklarowane for r in rows if r.forma == "GOTÓWKA")
    t = sum(r.deklarowane for r in rows if r.forma == "KARTA")
    fv = sum(r.sprzedaz for r in rows if r.forma in ("KARTA_FV", "GOTÓWKA_FV"))
    return {"gotowka": round(g, 2), "karta": round(t, 2), "fv": round(fv, 2)}


def _zbuduj_rozliczenie(db, data: date) -> models.RozliczenieDnia:
    """Get-or-create rozliczenia dnia + dołożenie wierszy kelnerów z grafiku Sali (prefill z Gastro)."""
    roz = db.query(models.RozliczenieDnia).filter_by(data=data).first()
    if roz is None:
        roz = models.RozliczenieDnia(data=data, status="robocze", utworzono_at=utcnow_naive(),
                                     terminale=[], kasy=[])
        db.add(roz); db.flush()
    sala_ids = _sala_stanowisko_ids(db)
    istn = {k.pracownik_id for k in roz.kelnerzy}
    pids = set()
    if sala_ids:
        # 1) grafik Sali tego dnia
        pids |= {a.pracownik_id for a in db.query(models.PrzydzialZmiany).filter(
            models.PrzydzialZmiany.data == data, models.PrzydzialZmiany.stanowisko_id.in_(sala_ids)).all()}
        # 2) faktycznie pracujący na sali = zamknięte rozliczenie Gastro tego dnia + obsada sali w oknie
        #    (radzi sobie z rozjazdem: data zmiany w grafiku ≠ DataOtwarcia rozliczenia w Gastro)
        sala_staff = {a.pracownik_id for a in db.query(models.PrzydzialZmiany).filter(
            models.PrzydzialZmiany.data >= data - timedelta(days=21),
            models.PrzydzialZmiany.data <= data + timedelta(days=21),
            models.PrzydzialZmiany.stanowisko_id.in_(sala_ids)).all()}
        gastro_pids = {r.pracownik_id for r in db.query(models.RozliczenieGastro).filter(
            models.RozliczenieGastro.data == data, models.RozliczenieGastro.pracownik_id.isnot(None)).all()}
        pids |= (gastro_pids & sala_staff)
    for pid in pids:
        if pid in istn:
            continue
        g = _gastro_dla_kelnera(db, pid, data)
        roz.kelnerzy.append(models.RozliczenieKelner(
            pracownik_id=pid, gotowka=g["gotowka"], karta=g["karta"], fv=g["fv"]))
        istn.add(pid)
    db.commit(); db.refresh(roz)
    return roz


def _kp_dla_dnia(db, data: date) -> float:
    """Σ zadatków (KP „Kasa przyjęła") z Gastro dla dnia (po dacie wystawienia dokumentu kasowego).
    Dokumenty KP idą z agenta do tabeli kp_zadatki. Gotówkowe (KP = dokument kasowy)."""
    rows = db.query(models.KpZadatek).filter(models.KpZadatek.data == data).all()
    return round(sum(z.kwota or 0 for z in rows), 2)


def _imp_wynikowe(db, roz: models.RozliczenieDnia) -> dict:
    """IMP do liczenia: ręczne nadpisanie (gdy imp_reczny) albo automat z rozliczeń imprez."""
    if roz.imp_reczny:
        return {"gotowka_sfiskalizowana": roz.imp_gotowka or 0, "karta": roz.imp_karta or 0}
    return imp_dla_dnia(db, roz.data)


def _wynik_rozliczenia(db, roz: models.RozliczenieDnia) -> dict:
    kelnerzy = [{"gotowka": k.gotowka, "karta": k.karta} for k in roz.kelnerzy]
    fv = sum(k.fv for k in roz.kelnerzy)
    kw = sum(k.kw for k in roz.kelnerzy)
    terminale = [p.get("kwota", 0) for p in (roz.terminale or [])]
    kasy = [p.get("kwota", 0) for p in (roz.kasy or [])]
    return rozliczenia.policz_dzien(kelnerzy=kelnerzy, fv=fv, terminale=terminale, kasy=kasy,
                                    zadatek_gotowka=roz.zadatek_gotowka or 0,
                                    zadatek_karta=roz.zadatek_karta or 0,
                                    kw=kw, imp=_imp_wynikowe(db, roz))


def _rozliczenie_out(db, roz: models.RozliczenieDnia) -> dict:
    pm = {p.id: f"{p.imie} {p.nazwisko}" for p in db.query(models.Pracownik).all()}
    return {
        "data": str(roz.data), "status": roz.status,
        "zadatek_gotowka": roz.zadatek_gotowka or 0, "zadatek_karta": roz.zadatek_karta or 0,
        "kp_baza": _kp_dla_dnia(db, roz.data),    # Σ KP z Gastro (podpowiedź do rozbicia)
        "imp_reczny": roz.imp_reczny, "imp_gotowka": roz.imp_gotowka or 0, "imp_karta": roz.imp_karta or 0,
        "przelew": roz.przelew or 0,
        "kelnerzy": [{"pracownik_id": k.pracownik_id, "pracownik": pm.get(k.pracownik_id),
                      "gotowka": k.gotowka, "karta": k.karta, "fv": k.fv, "kw": k.kw} for k in roz.kelnerzy],
        "terminale": roz.terminale or [], "kasy": roz.kasy or [],
        "wynik": _wynik_rozliczenia(db, roz),
    }


@app.get("/api/rozliczenie")
def get_rozliczenie(data: date = Query(...), db: Session = Depends(get_db)):
    return _rozliczenie_out(db, _zbuduj_rozliczenie(db, data))


@app.put("/api/rozliczenie")
def zapisz_rozliczenie(dane: schemas.RozliczenieDniaIn, data: date = Query(...), db: Session = Depends(get_db)):
    roz = _zbuduj_rozliczenie(db, data)
    roz.zadatek_gotowka = float(dane.zadatek_gotowka or 0)
    roz.zadatek_karta = float(dane.zadatek_karta or 0)
    roz.imp_reczny = bool(dane.imp_reczny)
    roz.imp_gotowka = float(dane.imp_gotowka or 0)
    roz.imp_karta = float(dane.imp_karta or 0)
    roz.przelew = float(dane.przelew or 0)
    roz.terminale = [p.model_dump() for p in dane.terminale]
    roz.kasy = [p.model_dump() for p in dane.kasy]
    by_pid = {k.pracownik_id: k for k in roz.kelnerzy}
    for kin in dane.kelnerzy:
        k = by_pid.get(kin.pracownik_id)
        if k is None:
            k = models.RozliczenieKelner(pracownik_id=kin.pracownik_id); roz.kelnerzy.append(k)
        k.gotowka = kin.gotowka; k.karta = kin.karta; k.fv = kin.fv; k.kw = kin.kw
    db.commit(); db.refresh(roz)
    return _rozliczenie_out(db, roz)


@app.put("/api/rozliczenie/przelew", status_code=204)
def ustaw_przelew(data: date = Query(...), przelew: float = Query(0.0), db: Session = Depends(get_db)):
    """Przelew dnia z palca (admin) — szybki zapis (używany też z Zeszytu na wierszu SALA)."""
    roz = _zbuduj_rozliczenie(db, data)
    roz.przelew = float(przelew or 0)
    db.commit()


@app.post("/api/rozliczenie/przekaz-szef", status_code=204)
def przekaz_szef(data: date = Query(...), db: Session = Depends(get_db)):
    roz = db.query(models.RozliczenieDnia).filter_by(data=data).first()
    if not roz:
        raise HTTPException(404, "Brak rozliczenia tego dnia.")
    roz.status = "u_szefa"; roz.przekazano_szef_at = utcnow_naive(); db.commit()


@app.get("/api/szef/rozliczenie")
def szef_rozliczenie(data: date = Query(...), db: Session = Depends(get_db)):
    """Szef — tylko utarg SALI (G+T), zadatki osobno, braki/nadwyżki. Bez imprez i bez FV."""
    roz = db.query(models.RozliczenieDnia).filter_by(data=data).first()
    if not roz:
        return {"data": str(data), "status": "brak", "utarg": None}
    w = _wynik_rozliczenia(db, roz)
    return {"data": str(data), "status": roz.status,
            "utarg": {"gotowka": w["suma_szef"]["gotowka"], "karta": w["suma_szef"]["karta"],
                      "fv": w["fv"], "razem": round(w["suma_szef"]["razem"] + w["fv"], 2)},   # utarg sali Z FV
            "zadatek": w["zadatek"],
            "roznica_karty": w["terminale"]["roznica_karty"], "roznica_calosc": w["kasy"]["roznica"]}


def _obsada_sali_okno(db, pid: int, data: date, sala_ids) -> bool:
    """Czy pracownik jest obsadą sali w oknie ±21 dni (radzi sobie z rozjazdem dat grafik↔Gastro)."""
    return bool(sala_ids and db.query(models.PrzydzialZmiany).filter(
        models.PrzydzialZmiany.pracownik_id == pid,
        models.PrzydzialZmiany.data >= data - timedelta(days=21),
        models.PrzydzialZmiany.data <= data + timedelta(days=21),
        models.PrzydzialZmiany.stanowisko_id.in_(sala_ids)).first())


def _kelner_sala_dnia(db, pid: int, data: date) -> bool:
    sala_ids = _sala_stanowisko_ids(db)
    if not (pid and sala_ids):
        return False
    # 1) przydział Sali tego dnia (grafik)
    if db.query(models.PrzydzialZmiany).filter(
            models.PrzydzialZmiany.data == data, models.PrzydzialZmiany.pracownik_id == pid,
            models.PrzydzialZmiany.stanowisko_id.in_(sala_ids)).first():
        return True
    # 2) zamknięte rozliczenie Gastro tego dnia + obsada sali w oknie (rozjazd dat grafik↔Gastro)
    if db.query(models.RozliczenieGastro).filter_by(pracownik_id=pid, data=data, zamkniete=True).first() \
            and _obsada_sali_okno(db, pid, data, sala_ids):
        return True
    return False


def _rozliczenia_oczekujace(db, pid: int):
    """Daty (ISO, malejąco) zamkniętych rozliczeń Gastro kelnera sali, których jeszcze NIE przesłał.
    Niezależne od daty zmiany w grafiku — bazuje na realnych zamknięciach w Gastro (DataOtwarcia),
    więc przycisk „Rozlicz się" pojawia się nawet gdy dzień zmiany ≠ dzień rozliczenia w Gastro."""
    if not pid:
        return []
    sala_ids = _sala_stanowisko_ids(db)
    if not sala_ids:
        return []
    od = date.today() - timedelta(days=21)
    # tylko obsada sali (żeby nie pokazywać np. baru/kuchni) — szersze okno łapie rozjazd grafik↔Gastro
    czy_sala = db.query(models.PrzydzialZmiany).filter(
        models.PrzydzialZmiany.pracownik_id == pid, models.PrzydzialZmiany.data >= od,
        models.PrzydzialZmiany.stanowisko_id.in_(sala_ids)).first()
    if not czy_sala:
        return []
    # ale rozliczenia POKAZUJEMY dopiero od startu systemu — bez „zaległych" sprzed wdrożenia
    od_pokaz = max(od, ROZLICZENIA_START) if ROZLICZENIA_START else od
    daty = sorted({r.data for r in db.query(models.RozliczenieGastro).filter_by(
        pracownik_id=pid, zamkniete=True).filter(models.RozliczenieGastro.data >= od_pokaz).all()}, reverse=True)
    out = []
    for d in daty:
        roz = db.query(models.RozliczenieDnia).filter_by(data=d).first()
        k = next((x for x in roz.kelnerzy if x.pracownik_id == pid), None) if roz else None
        if not (k and k.potwierdzone):
            out.append(d.isoformat())
    return out


def _rozlicz_sala_status(db, pid: int, data: date, sala_ids=None):
    """Status przycisku „Rozlicz się": None (push jeszcze nie wyszedł), 'oczekuje' (wysłano push
    „raport oczekuje", kelner ma się rozliczyć), 'wyslane' (kelner przesłał raport).
    Bramka = push_oczekuje_at — przycisk pojawia się DOPIERO gdy push faktycznie poszedł (ingest)."""
    roz = db.query(models.RozliczenieDnia).filter_by(data=data).first()
    k = next((x for x in roz.kelnerzy if x.pracownik_id == pid), None) if roz else None
    if not k or k.push_oczekuje_at is None:
        return None
    return "wyslane" if k.potwierdzone else "oczekuje"


def _kelner_sala_przydzial(db, pid: int, data: date):
    """Flagi zamykania z przydziałów sali kelnera danego dnia: (zamyka, zamyka_rewir, rewir)."""
    sala_ids = _sala_stanowisko_ids(db)
    przy = (db.query(models.PrzydzialZmiany).filter(
        models.PrzydzialZmiany.data == data, models.PrzydzialZmiany.pracownik_id == pid,
        models.PrzydzialZmiany.stanowisko_id.in_(sala_ids)).all()) if sala_ids else []
    zamyka = any(p.zamyka for p in przy)
    zamyka_rewir = any(p.zamyka_rewir for p in przy)
    rewir = next((p.rewir for p in przy if p.zamyka_rewir and p.rewir), None) \
        or next((p.rewir for p in przy if p.rewir), None)
    return zamyka, zamyka_rewir, rewir


@app.get("/api/me/rozliczenie")
def moje_rozliczenie(data: date = Query(...), user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not _kelner_sala_dnia(db, user.pracownik_id, data):
        return {"moze": False}
    roz = _zbuduj_rozliczenie(db, data)
    k = next((x for x in roz.kelnerzy if x.pracownik_id == user.pracownik_id), None)
    zamyka, zamyka_rewir, rewir = _kelner_sala_przydzial(db, user.pracownik_id, data)
    term = [p for p in (roz.terminale or []) if (p.get("rewir") or "") == (rewir or "")] if zamyka_rewir else []
    return {"moze": True, "status": _rozlicz_sala_status(db, user.pracownik_id, data),
            "potwierdzone": bool(k and k.potwierdzone),
            "wiersz": ({"gotowka": k.gotowka, "karta": k.karta, "fv": k.fv, "kw": k.kw} if k else None),
            "zamyka": zamyka, "zamyka_rewir": zamyka_rewir, "rewir": rewir,
            "terminale": term, "kasy": (roz.kasy or []) if zamyka else []}


@app.put("/api/me/rozliczenie", status_code=204)
def zapisz_moje_rozliczenie(dane: schemas.MojRozliczenieIn, data: date = Query(...),
                            user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not _kelner_sala_dnia(db, user.pracownik_id, data):
        raise HTTPException(403, "Rozliczenie wypełnia kelner sali w dniu swojej zmiany.")
    roz = _zbuduj_rozliczenie(db, data)
    k = next((x for x in roz.kelnerzy if x.pracownik_id == user.pracownik_id), None)
    if k is None:
        k = models.RozliczenieKelner(pracownik_id=user.pracownik_id); roz.kelnerzy.append(k)
    k.gotowka = dane.gotowka; k.karta = dane.karta; k.kw = dane.kw
    k.potwierdzone = True            # kelner przesłał raport → przycisk znika
    # Zamykający dosyła terminale (swój rewir) / kasy (cała zmiana) — trafiają do rozliczenia dnia
    zamyka, zamyka_rewir, rewir = _kelner_sala_przydzial(db, user.pracownik_id, data)
    if zamyka_rewir:
        inne = [t for t in (roz.terminale or []) if (t.get("rewir") or "") != (rewir or "")]
        roz.terminale = inne + [{"etykieta": None, "kwota": float(t.kwota or 0), "rewir": rewir} for t in dane.terminale]
    if zamyka:
        roz.kasy = [{"etykieta": t.etykieta, "kwota": float(t.kwota or 0), "rewir": None} for t in dane.kasy]
    db.commit()
    # Gdy WSZYSCY kelnerzy sali danego dnia się rozliczyli → push do admina (raz)
    if roz.kelnerzy and all(x.potwierdzone for x in roz.kelnerzy) and roz.push_admin_at is None:
        roz.push_admin_at = utcnow_naive()
        wyslij_push_do_adminow(db, "Raport finansowy",
                               f"Raport finansowy {data.strftime('%d.%m')} czeka na zatwierdzenie", url="/")
        db.commit()


# ── ZESZYT KASOWY ─────────────────────────────────────────────────────────────
# Kasa dzienna: PRZYCHÓD (SALA z rozliczenia + imprezy) − ROZCHÓD (ręczne wpisy) → STAN
# (saldo gotówkowe narastająco od „stanu początkowego"). Liczone tylko z gotówki.

def _zeszyt_dane(db, start: date, end: date) -> dict:
    cfg = db.query(models.ZeszytConfig).first()
    stan0 = float(cfg.stan_poczatkowy) if cfg else 0.0
    anchor = cfg.stan_poczatkowy_data if (cfg and cfg.stan_poczatkowy_data) else start
    if anchor > start:
        anchor = start                       # licz zawsze od początku okna, gdyby data startowa była później
    rozl = {r.data: r for r in db.query(models.RozliczenieDnia)
            .filter(models.RozliczenieDnia.data >= anchor, models.RozliczenieDnia.data <= end).all()}
    imp_by_day = {}
    for im in (db.query(models.RozliczenieImprezy)
               .filter(models.RozliczenieImprezy.data >= anchor, models.RozliczenieImprezy.data <= end).all()):
        imp_by_day.setdefault(im.data, []).append(im)
    poz_by_day = {}
    for p in (db.query(models.ZeszytPozycja)
              .filter(models.ZeszytPozycja.data >= anchor, models.ZeszytPozycja.data <= end).all()):
        poz_by_day.setdefault(p.data, []).append(p)
    przy_by_day = {}
    for p in (db.query(models.ZeszytPrzychod)
              .filter(models.ZeszytPrzychod.data >= anchor, models.ZeszytPrzychod.data <= end).all()):
        przy_by_day.setdefault(p.data, []).append(p)

    dni, stan = [], stan0
    for ordv in range(anchor.toordinal(), end.toordinal() + 1):
        d = date.fromordinal(ordv)
        wiersze, cash_in = [], 0.0
        r = rozl.get(d)
        if r:                          # SALA z rozliczenia (także wersji roboczej) trafia do zeszytu
            w = _wynik_rozliczenia(db, r)
            sg, sk = w["suma_zeszyt"]["gotowka"], w["suma_zeszyt"]["karta"]
            pz = float(r.przelew or 0)
            if sg or sk or pz:
                wiersze.append({"zrodlo": "SALA", "gotowka": sg, "terminal": sk, "przelew": pz, "impreza": 0.0,
                                "manualny": False, "sala_id": r.id})   # sala_id → edycja przelewu z palca w zeszycie
                cash_in += sg
        for im in imp_by_day.get(d, []):
            g_sf = round(sum(p.kwota for p in im.pozycje if p.forma == "gotowka" and p.sfiskalizowane), 2)
            g_ns = round(sum(p.kwota for p in im.pozycje if p.forma == "gotowka" and not p.sfiskalizowane), 2)
            kt = round(sum(p.kwota for p in im.pozycje if p.forma == "karta"), 2)
            pz = round(sum(p.kwota for p in im.pozycje if p.forma == "przelew"), 2)
            wiersze.append({"zrodlo": im.opis or "Impreza", "gotowka": g_sf, "terminal": kt, "przelew": pz, "impreza": g_ns, "manualny": False})
            cash_in += g_sf + g_ns
        for p in przy_by_day.get(d, []):
            wiersze.append({"id": p.id, "zrodlo": p.zrodlo or "—", "gotowka": p.gotowka, "terminal": p.terminal,
                            "przelew": p.przelew, "impreza": p.impreza, "manualny": True})
            cash_in += (p.gotowka or 0) + (p.impreza or 0)
        rozchod = [{"id": p.id, "kolumna": p.kolumna, "opis": p.opis, "kwota": p.kwota} for p in poz_by_day.get(d, [])]
        rozchod_suma = round(sum(p.kwota for p in poz_by_day.get(d, [])), 2)
        stan = round(stan + cash_in - rozchod_suma, 2)
        if d >= start:
            dni.append({"data": str(d), "wiersze": wiersze, "rozchod": rozchod,
                        "przychod_gotowka": round(cash_in, 2), "rozchod_suma": rozchod_suma, "stan": stan})
    return {"stan_poczatkowy": stan0,
            "stan_poczatkowy_data": str(cfg.stan_poczatkowy_data) if (cfg and cfg.stan_poczatkowy_data) else None,
            "dni": dni}


@app.get("/api/zeszyt")
def get_zeszyt(start: date = Query(...), end: date = Query(...), db: Session = Depends(get_db)):
    return _zeszyt_dane(db, start, end)


@app.get("/api/szef/zeszyt")
def szef_zeszyt(start: date = Query(...), end: date = Query(...), db: Session = Depends(get_db)):
    return _zeszyt_dane(db, start, end)


@app.post("/api/zeszyt/pozycja", status_code=201)
def dodaj_zeszyt_pozycja(dane: schemas.ZeszytPozycjaIn, db: Session = Depends(get_db)):
    if dane.kolumna not in ("towar", "koszty", "wyplaty", "inne"):
        raise HTTPException(400, "Nieznana kolumna rozchodu.")
    p = models.ZeszytPozycja(data=dane.data, kolumna=dane.kolumna, opis=dane.opis, kwota=float(dane.kwota or 0))
    db.add(p); db.commit(); db.refresh(p)
    return {"id": p.id}


@app.delete("/api/zeszyt/pozycja/{poz_id}", status_code=204)
def usun_zeszyt_pozycja(poz_id: int, db: Session = Depends(get_db)):
    p = db.get(models.ZeszytPozycja, poz_id)
    if p:
        db.delete(p); db.commit()


@app.post("/api/zeszyt/przychod", status_code=201)
def dodaj_zeszyt_przychod(dane: schemas.ZeszytPrzychodIn, db: Session = Depends(get_db)):
    p = models.ZeszytPrzychod(data=dane.data, zrodlo=dane.zrodlo, gotowka=float(dane.gotowka or 0),
                              terminal=float(dane.terminal or 0), przelew=float(dane.przelew or 0),
                              impreza=float(dane.impreza or 0))
    db.add(p); db.commit(); db.refresh(p)
    return {"id": p.id}


@app.delete("/api/zeszyt/przychod/{poz_id}", status_code=204)
def usun_zeszyt_przychod(poz_id: int, db: Session = Depends(get_db)):
    p = db.get(models.ZeszytPrzychod, poz_id)
    if p:
        db.delete(p); db.commit()


@app.get("/api/zeszyt/config")
def get_zeszyt_config(db: Session = Depends(get_db)):
    cfg = db.query(models.ZeszytConfig).first()
    return {"stan_poczatkowy": float(cfg.stan_poczatkowy) if cfg else 0.0,
            "stan_poczatkowy_data": str(cfg.stan_poczatkowy_data) if (cfg and cfg.stan_poczatkowy_data) else None}


@app.put("/api/zeszyt/config")
def set_zeszyt_config(dane: schemas.ZeszytConfigIn, db: Session = Depends(get_db)):
    cfg = db.query(models.ZeszytConfig).first()
    if cfg is None:
        cfg = models.ZeszytConfig(id=1); db.add(cfg)
    cfg.stan_poczatkowy = float(dane.stan_poczatkowy or 0)
    cfg.stan_poczatkowy_data = dane.stan_poczatkowy_data
    db.commit()
    return {"stan_poczatkowy": cfg.stan_poczatkowy,
            "stan_poczatkowy_data": str(cfg.stan_poczatkowy_data) if cfg.stan_poczatkowy_data else None}


# ═══════════════════════════════════════════════════════════════════════════
# PULPIT WŁAŚCICIELA (KPI cockpit) — agregacja istniejących danych, zero nowych tabel
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/pulpit")
def pulpit(start: date = Query(...), end: date = Query(...), db: Session = Depends(get_db)):
    """Zbiorcze KPI lokalu za okres [start, end]: przychód (z zeszytu kasowego), saldo kasy,
    rozchód, ruch (rachunki z POS), rezerwacje (moduł stolików) oraz koszt pracy miesiąca
    końca okresu. Czysta agregacja — nie zapisuje nic do bazy."""
    if end < start:
        raise HTTPException(400, "Koniec okresu przed początkiem.")

    # — Przychód, rozchód i saldo kasy: z zeszytu kasowego (SALA + imprezy + ręczne wpisy) —
    z = _zeszyt_dane(db, start, end)
    dni = z["dni"]
    got = term = przel = impr = przychod_total = rozchod_total = 0.0
    przychod_dzienny = []
    for d in dni:
        dsum = 0.0
        for w in d["wiersze"]:
            g = float(w.get("gotowka") or 0); k = float(w.get("terminal") or 0)
            p = float(w.get("przelew") or 0); i = float(w.get("impreza") or 0)
            got += g; term += k; przel += p; impr += i; dsum += g + k + p + i
        rozchod_total += float(d["rozchod_suma"] or 0)
        przychod_total += dsum
        przychod_dzienny.append({"data": d["data"], "przychod": round(dsum, 2),
                                 "rozchod": round(float(d["rozchod_suma"] or 0), 2)})
    saldo = dni[-1]["stan"] if dni else z["stan_poczatkowy"]

    # — Ruch (liczba rachunków z POS) —
    ruch_rows = sorted(db.query(models.StolikiHistoria).filter(
        models.StolikiHistoria.data >= start, models.StolikiHistoria.data <= end).all(),
        key=lambda r: r.data)
    ruch_total = sum(int(r.liczba or 0) for r in ruch_rows)
    ruch_dzienny = [{"data": str(r.data), "liczba": int(r.liczba or 0)} for r in ruch_rows]

    # — Rezerwacje (moduł stolików) —
    rez = db.query(models.Termin).filter(
        models.Termin.rodzaj == "stolik",
        models.Termin.data >= start, models.Termin.data <= end).all()
    rez_status, rez_goscie = {}, 0
    for r in rez:
        rez_status[r.status] = rez_status.get(r.status, 0) + 1
        if r.status in ("rezerwacja", "potwierdzona", "odbyla"):
            rez_goscie += int(r.liczba_osob or 0)

    # — Koszt pracy: miesiąc końca okresu (z raportu godzin × stawki) —
    rap = raporty.raport_godzin_miesiac(db, end.year, end.month)
    koszt_pracy = round(sum(float(p["do_wyplaty"] or 0) for p in rap["pracownicy"]), 2)
    alerty = _alerty_kasowe(db, start, end)

    n = max(1, len(przychod_dzienny))
    return {
        "okres": {"start": str(start), "end": str(end), "dni": len(dni)},
        "przychod": {
            "razem": round(przychod_total, 2), "gotowka": round(got, 2), "karta": round(term, 2),
            "przelew": round(przel, 2), "impreza": round(impr, 2),
            "srednia_dzienna": round(przychod_total / n, 2), "dzienny": przychod_dzienny,
        },
        "rozchod": {"razem": round(rozchod_total, 2)},
        "wynik": round(przychod_total - rozchod_total - koszt_pracy, 2),   # poglądowo: przychód − rozchód − koszt pracy
        "saldo_kasy": saldo,
        "ruch": {"rachunki": ruch_total, "dzienny": ruch_dzienny,
                 "srednia_dzienna": round(ruch_total / max(1, len(ruch_dzienny)), 1) if ruch_dzienny else 0},
        "rezerwacje": {"razem": len(rez), "wg_statusu": rez_status, "goscie": rez_goscie},
        "koszt_pracy_miesiac": {"rok": end.year, "miesiac": end.month, "kwota": koszt_pracy},
        "alerty_kasowe": {"dni_z_anomalia": alerty["dni_z_anomalia"],
                          "suma_braki": alerty["suma_braki"], "suma_nadwyzki": alerty["suma_nadwyzki"]},
    }


# ── ALERTY KASOWE (różnice w rozliczeniu: brak/nadwyżka na kartach lub w kasie) ──

def _alerty_kasowe(db, start: date, end: date, prog: float = 1.0) -> dict:
    """Skanuje rozliczenia dnia w okresie i zwraca dni z różnicą ponad próg [zł].
    Źródło: policz_dzien → terminale.roznica_karty (karty) i kasy.roznica (fiskalizacja)."""
    rozl = db.query(models.RozliczenieDnia).filter(
        models.RozliczenieDnia.data >= start, models.RozliczenieDnia.data <= end).all()
    alerty = []
    for r in sorted(rozl, key=lambda x: x.data):
        w = _wynik_rozliczenia(db, r)
        rk = float(w["terminale"]["roznica_karty"])
        rc = float(w["kasy"]["roznica"])
        problemy = []
        if abs(rk) >= prog:
            problemy.append({"typ": "karty", "roznica": rk, "etykieta": w["terminale"]["etykieta"]})
        if abs(rc) >= prog:
            problemy.append({"typ": "kasa", "roznica": rc, "etykieta": w["kasy"]["etykieta"]})
        if problemy:
            alerty.append({
                "data": str(r.data), "status": r.status, "problemy": problemy,
                "braki": round(sum(p["roznica"] for p in problemy if p["roznica"] < 0), 2),
                "nadwyzki": round(sum(p["roznica"] for p in problemy if p["roznica"] > 0), 2),
            })
    return {"prog": prog, "alerty": alerty, "dni_z_anomalia": len(alerty),
            "suma_braki": round(sum(a["braki"] for a in alerty), 2),
            "suma_nadwyzki": round(sum(a["nadwyzki"] for a in alerty), 2)}


@app.get("/api/alerty-kasowe")
def alerty_kasowe(start: date = Query(...), end: date = Query(...), prog: float = 1.0,
                  db: Session = Depends(get_db)):
    """Dni z anomalią kasową (różnica ≥ prog zł) w okresie. Admin/szef."""
    if end < start:
        raise HTTPException(400, "Koniec okresu przed początkiem.")
    return _alerty_kasowe(db, start, end, max(0.0, float(prog)))


# ── PROGNOZA RUCHU (z historii StolikiHistoria — wsparcie decyzji o obsadzie) ──

_DNI_TYG = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"]


@app.get("/api/prognoza-ruchu")
def prognoza_ruchu(dni: int = 90, db: Session = Depends(get_db)):
    """Prognoza ruchu (liczba rachunków) z historii: średnia per dzień tygodnia, trend
    28d vs poprzednie 28d, projekcja na najbliższe 7 dni. Czysto z danych StolikiHistoria."""
    dni = max(7, min(int(dni), 365))
    today = date.today()
    od = today - timedelta(days=dni)
    rows = db.query(models.StolikiHistoria).filter(models.StolikiHistoria.data >= od,
                                                   models.StolikiHistoria.data <= today).all()
    wg_dnia = defaultdict(list)
    for r in rows:
        wg_dnia[r.data.weekday()].append(int(r.liczba or 0))
    per_dzien = []
    for w in range(7):
        vals = wg_dnia.get(w, [])
        per_dzien.append({"dzien": w, "nazwa": _DNI_TYG[w],
                          "srednia": round(sum(vals) / len(vals), 1) if vals else 0,
                          "max": max(vals) if vals else 0, "probek": len(vals)})
    # Trend: ostatnie 28 dni vs poprzednie 28 dni.
    def _suma(start, end):
        return sum(int(r.liczba or 0) for r in rows if start <= r.data < end)
    okno1 = _suma(today - timedelta(days=28), today + timedelta(days=1))
    okno0 = _suma(today - timedelta(days=56), today - timedelta(days=28))
    trend = round((okno1 - okno0) / okno0 * 100, 1) if okno0 else None
    # Projekcja na 7 dni wg średniej dnia tygodnia.
    srednie = {p["dzien"]: p["srednia"] for p in per_dzien}
    projekcja = []
    for i in range(1, 8):
        d = today + timedelta(days=i)
        projekcja.append({"data": str(d), "nazwa": _DNI_TYG[d.weekday()], "prognoza": srednie.get(d.weekday(), 0)})
    return {"okres_dni": dni, "probek": len(rows),
            "srednia_dzienna": round(sum(int(r.liczba or 0) for r in rows) / len(rows), 1) if rows else 0,
            "trend_28d_proc": trend,
            "per_dzien_tygodnia": per_dzien,
            "projekcja_7dni": projekcja}


# ── KALENDARZ IMPREZ ──────────────────────────────────────────────────────────

def _termin_out(t: models.Termin, zadatek_kp: float = 0.0) -> dict:
    return {"id": t.id, "data": str(t.data), "nazwisko": t.nazwisko, "typ": t.typ,
            "liczba_osob": t.liczba_osob, "telefon": t.telefon, "sala": t.sala,
            "notatka": t.notatka, "status": t.status, "zadatek": t.zadatek or 0,
            "zadatek_kp": round(zadatek_kp, 2)}   # suma zadatków KP przypisanych do terminu


@app.get("/api/terminy")
def get_terminy(start: date = Query(...), end: date = Query(...), db: Session = Depends(get_db)):
    rows = (db.query(models.Termin)
            .filter(models.Termin.data >= start, models.Termin.data <= end)
            .order_by(models.Termin.data.asc(), models.Termin.id.asc()).all())
    kp_sum = {}
    ids = [t.id for t in rows]
    if ids:
        for z in db.query(models.KpZadatek).filter(models.KpZadatek.termin_id.in_(ids)).all():
            kp_sum[z.termin_id] = kp_sum.get(z.termin_id, 0) + (z.kwota or 0)
    return {"terminy": [_termin_out(t, kp_sum.get(t.id, 0)) for t in rows]}


@app.post("/api/terminy", status_code=201)
def dodaj_termin(dane: schemas.TerminIn, db: Session = Depends(get_db)):
    t = models.Termin(data=dane.data, nazwisko=dane.nazwisko.strip(), typ=dane.typ,
                      liczba_osob=dane.liczba_osob, telefon=dane.telefon, sala=dane.sala,
                      notatka=dane.notatka, status=dane.status or "rezerwacja",
                      zadatek=float(dane.zadatek or 0), utworzono_at=utcnow_naive())
    db.add(t); db.commit(); db.refresh(t)
    return _termin_out(t)


@app.put("/api/terminy/{termin_id}")
def edytuj_termin(termin_id: int, dane: schemas.TerminIn, db: Session = Depends(get_db)):
    t = db.get(models.Termin, termin_id)
    if not t:
        raise HTTPException(404, "Brak terminu.")
    stara_data = t.data
    t.data = dane.data; t.nazwisko = dane.nazwisko.strip(); t.typ = dane.typ
    t.liczba_osob = dane.liczba_osob; t.telefon = dane.telefon; t.sala = dane.sala
    t.notatka = dane.notatka; t.status = dane.status or "rezerwacja"; t.zadatek = float(dane.zadatek or 0)
    # Termin z iCloud ma sparowaną Imprezę (obsada) — synchronizujemy ją z ręczną edycją,
    # żeby korekta liczby osób / daty / sali zmieniła wymagania obsady.
    if t.ical_uid:
        imp = db.query(models.Impreza).filter(models.Impreza.sciezka_pliku == f"ical:{t.ical_uid}").first()
        if imp is not None:
            imp.data = t.data; imp.klient = t.nazwisko
            imp.liczba_osob = (t.liczba_osob or 0); imp.sala = (t.sala or "Brak")
    db.commit(); db.refresh(t)
    if t.ical_uid:
        _odswiez_wymagania_imprez(db, min(stara_data, t.data), max(stara_data, t.data))
    return _termin_out(t)


@app.delete("/api/terminy/{termin_id}", status_code=204)
def usun_termin(termin_id: int, db: Session = Depends(get_db)):
    t = db.get(models.Termin, termin_id)
    if t:
        for z in db.query(models.KpZadatek).filter_by(termin_id=termin_id).all():
            z.termin_id = None       # odepnij zadatki (zostają w skrzynce)
        uid, data_t = t.ical_uid, t.data
        db.delete(t)
        # Usuń też sparowaną Imprezę z iCloud (obsada) i odśwież wymagania na ten dzień.
        if uid:
            imp = db.query(models.Impreza).filter(models.Impreza.sciezka_pliku == f"ical:{uid}").first()
            if imp is not None:
                db.delete(imp)
        db.commit()
        if uid:
            _odswiez_wymagania_imprez(db, data_t, data_t)


# ═══════════════════════════════════════════════════════════════════════════
# MODUŁ REZERWACJI (stoliki + godziny otwarcia + rezerwacje na encji Termin)
# ═══════════════════════════════════════════════════════════════════════════

REZ_STATUSY = ("rezerwacja", "potwierdzona", "odbyla", "no_show", "odwolana")
# Dozwolone przejścia statusu rezerwacji (rezerwacja/potwierdzona = aktywne, reszta terminalna).
REZ_PRZEJSCIA = {
    "rezerwacja":   {"potwierdzona", "odbyla", "no_show", "odwolana"},
    "potwierdzona": {"odbyla", "no_show", "odwolana"},
    "odbyla": set(), "no_show": set(), "odwolana": set(),
}
REZ_AKTYWNE = ("rezerwacja", "potwierdzona")   # blokują stolik (liczą się do kolizji)
DOMYSLNY_SLOT_MIN = 120


def _wymagaj_modul_rezerwacje(db: Session = Depends(get_db)):
    if not get_lokal_config(db).modul_rezerwacje:
        raise HTTPException(403, "Moduł rezerwacji jest wyłączony.")


def _dodaj_minuty(t: time, minuty: int) -> time:
    """t + minuty, obcięte do tej samej doby (rezerwacje nie przechodzą przez północ w MVP)."""
    total = min(t.hour * 60 + t.minute + minuty, 23 * 60 + 59)
    return time(total // 60, total % 60)


def _slot_dlugosc(db, data: date) -> int:
    go = db.query(models.GodzinyOtwarcia).filter_by(dzien_tygodnia=data.weekday(), aktywny=True).first()
    return go.dlugosc_slotu_min if go else DOMYSLNY_SLOT_MIN


def _waliduj_rezerwacje(db, data, godz_od, godz_do, stolik_id, liczba_osob, pomin_id=None):
    """Walidacja rezerwacji stolika: pojemność + brak kolizji w oknie [godz_od, godz_do].
    Zwraca policzone godz_do. Bez stolika/godziny nie ma okna kolizji."""
    if stolik_id is None:
        return godz_do
    stolik = db.get(models.Stolik, stolik_id)
    if not stolik or not stolik.aktywny:
        raise HTTPException(400, "Nieznany lub nieaktywny stolik.")
    if liczba_osob and stolik.pojemnosc and liczba_osob > stolik.pojemnosc:
        raise HTTPException(400, f"Stolik „{stolik.nazwa}” mieści {stolik.pojemnosc} os. (próba: {liczba_osob}).")
    if godz_od is None:
        return godz_do
    if godz_do is None:
        godz_do = _dodaj_minuty(godz_od, _slot_dlugosc(db, data))
    q = db.query(models.Termin).filter(
        models.Termin.stolik_id == stolik_id, models.Termin.data == data,
        models.Termin.status.in_(REZ_AKTYWNE), models.Termin.godz_od.isnot(None))
    if pomin_id is not None:
        q = q.filter(models.Termin.id != pomin_id)
    for r in q.all():
        r_do = r.godz_do or _dodaj_minuty(r.godz_od, _slot_dlugosc(db, data))
        if godz_od < r_do and r.godz_od < godz_do:   # nachodzą
            raise HTTPException(409, f"Stolik zajęty w tym czasie (kolizja od {r.godz_od.strftime('%H:%M')}).")
    return godz_do


def _hm(t):
    return t.strftime("%H:%M") if t else None


def _rezerwacja_out(t: models.Termin) -> dict:
    return {"id": t.id, "data": str(t.data), "godz_od": _hm(t.godz_od), "godz_do": _hm(t.godz_do),
            "stolik_id": t.stolik_id, "nazwisko": t.nazwisko, "telefon": t.telefon, "email": t.email,
            "liczba_osob": t.liczba_osob, "notatka": t.notatka, "status": t.status,
            "zadatek": t.zadatek or 0, "kanal": t.kanal}


def _tresc_potwierdzenia(t: models.Termin, cfg) -> str:
    nazwa = cfg.nazwa_lokalu or "Lokal"
    czesci = [f"dzień {t.data}"]
    if t.godz_od:
        czesci.append(f"godz. {_hm(t.godz_od)}")
    if t.liczba_osob:
        czesci.append(f"{t.liczba_osob} os.")
    return (f"Dzień dobry,\n\n"
            f"Twoja rezerwacja w {nazwa} ({', '.join(czesci)}) została przyjęta.\n\n"
            f"Do zobaczenia!\n{nazwa}")


def _wyslij_potwierdzenie_rezerwacji(db, t: models.Termin) -> bool:
    """Best-effort e-mail potwierdzenia do gościa (gdy ma adres i integracja e-mail aktywna)."""
    if not t.email:
        return False
    cfg = get_lokal_config(db)
    return mailer.wyslij_email(t.email, f"Potwierdzenie rezerwacji — {cfg.nazwa_lokalu}",
                               _tresc_potwierdzenia(t, cfg))


# ── Stoliki ──────────────────────────────────────────────────────────────────
@app.get("/api/stoliki", dependencies=[Depends(_wymagaj_modul_rezerwacje)])
def get_stoliki(db: Session = Depends(get_db)):
    rows = db.query(models.Stolik).order_by(models.Stolik.kolejnosc, models.Stolik.id).all()
    return {"stoliki": [schemas.StolikOut.model_validate(s).model_dump() for s in rows]}


@app.post("/api/stoliki", status_code=201, dependencies=[Depends(_wymagaj_modul_rezerwacje)])
def dodaj_stolik(dane: schemas.StolikIn, db: Session = Depends(get_db)):
    s = models.Stolik(**dane.model_dump()); db.add(s); db.commit(); db.refresh(s)
    return schemas.StolikOut.model_validate(s).model_dump()


@app.put("/api/stoliki/{sid}", dependencies=[Depends(_wymagaj_modul_rezerwacje)])
def edytuj_stolik(sid: int, dane: schemas.StolikIn, db: Session = Depends(get_db)):
    s = db.get(models.Stolik, sid)
    if not s:
        raise HTTPException(404, "Brak stolika.")
    for k, v in dane.model_dump().items():
        setattr(s, k, v)
    db.commit(); db.refresh(s)
    return schemas.StolikOut.model_validate(s).model_dump()


@app.delete("/api/stoliki/{sid}", status_code=204, dependencies=[Depends(_wymagaj_modul_rezerwacje)])
def usun_stolik(sid: int, db: Session = Depends(get_db)):
    s = db.get(models.Stolik, sid)
    if s:
        db.query(models.Termin).filter_by(stolik_id=sid).update({"stolik_id": None})
        db.delete(s); db.commit()


# ── Godziny otwarcia ─────────────────────────────────────────────────────────
@app.get("/api/godziny-otwarcia", dependencies=[Depends(_wymagaj_modul_rezerwacje)])
def get_godziny_otwarcia(db: Session = Depends(get_db)):
    rows = db.query(models.GodzinyOtwarcia).order_by(models.GodzinyOtwarcia.dzien_tygodnia,
                                                     models.GodzinyOtwarcia.godz_od).all()
    return {"godziny": [schemas.GodzinyOtwarciaOut.model_validate(g).model_dump() for g in rows]}


@app.post("/api/godziny-otwarcia", status_code=201, dependencies=[Depends(_wymagaj_modul_rezerwacje)])
def dodaj_godziny_otwarcia(dane: schemas.GodzinyOtwarciaIn, db: Session = Depends(get_db)):
    if not (0 <= dane.dzien_tygodnia <= 6):
        raise HTTPException(400, "dzien_tygodnia musi być 0–6.")
    g = models.GodzinyOtwarcia(**dane.model_dump()); db.add(g); db.commit(); db.refresh(g)
    return schemas.GodzinyOtwarciaOut.model_validate(g).model_dump()


@app.delete("/api/godziny-otwarcia/{gid}", status_code=204, dependencies=[Depends(_wymagaj_modul_rezerwacje)])
def usun_godziny_otwarcia(gid: int, db: Session = Depends(get_db)):
    g = db.get(models.GodzinyOtwarcia, gid)
    if g:
        db.delete(g); db.commit()


# ── Rezerwacje (rodzaj=stolik na encji Termin) ───────────────────────────────
@app.get("/api/rezerwacje-stolik", dependencies=[Depends(_wymagaj_modul_rezerwacje)])
def get_rezerwacje_stolik(start: date = Query(...), end: date = Query(...),
                          status: Optional[str] = None, stolik_id: Optional[int] = None,
                          db: Session = Depends(get_db)):
    q = db.query(models.Termin).filter(models.Termin.rodzaj == "stolik",
                                       models.Termin.data >= start, models.Termin.data <= end)
    if status:
        q = q.filter(models.Termin.status == status)
    if stolik_id:
        q = q.filter(models.Termin.stolik_id == stolik_id)
    rows = q.order_by(models.Termin.data, models.Termin.godz_od).all()
    return {"rezerwacje": [_rezerwacja_out(t) for t in rows]}


@app.post("/api/rezerwacje-stolik", status_code=201, dependencies=[Depends(_wymagaj_modul_rezerwacje)])
def dodaj_rezerwacje_stolik(dane: schemas.RezerwacjaIn, db: Session = Depends(get_db)):
    godz_do = _waliduj_rezerwacje(db, dane.data, dane.godz_od, dane.godz_do,
                                  dane.stolik_id, dane.liczba_osob)
    t = models.Termin(
        data=dane.data, nazwisko=dane.nazwisko.strip(), telefon=dane.telefon, email=dane.email,
        liczba_osob=dane.liczba_osob, notatka=dane.notatka, status="potwierdzona",
        zadatek=float(dane.zadatek or 0), utworzono_at=utcnow_naive(),
        godz_od=dane.godz_od, godz_do=godz_do, stolik_id=dane.stolik_id,
        rodzaj="stolik", kanal="reczna")
    db.add(t); db.commit(); db.refresh(t)
    wyslij_push_do_adminow(db, "Nowa rezerwacja",
                           f"{t.nazwisko} — {t.data} {_hm(t.godz_od) or ''}".strip(), url="/")
    _wyslij_potwierdzenie_rezerwacji(db, t)   # best-effort (no-op gdy brak SMTP/adresu)
    return _rezerwacja_out(t)


@app.put("/api/rezerwacje-stolik/{rid}", dependencies=[Depends(_wymagaj_modul_rezerwacje)])
def edytuj_rezerwacje_stolik(rid: int, dane: schemas.RezerwacjaIn, db: Session = Depends(get_db)):
    t = db.get(models.Termin, rid)
    if not t or t.rodzaj != "stolik":
        raise HTTPException(404, "Brak rezerwacji.")
    godz_do = _waliduj_rezerwacje(db, dane.data, dane.godz_od, dane.godz_do,
                                  dane.stolik_id, dane.liczba_osob, pomin_id=rid)
    t.data = dane.data; t.nazwisko = dane.nazwisko.strip(); t.telefon = dane.telefon
    t.email = dane.email; t.liczba_osob = dane.liczba_osob; t.notatka = dane.notatka
    t.zadatek = float(dane.zadatek or 0); t.godz_od = dane.godz_od; t.godz_do = godz_do
    t.stolik_id = dane.stolik_id
    db.commit(); db.refresh(t)
    return _rezerwacja_out(t)


@app.post("/api/rezerwacje-stolik/{rid}/status", dependencies=[Depends(_wymagaj_modul_rezerwacje)])
def zmien_status_rezerwacji_stolik(rid: int, dane: schemas.RezerwacjaStatusIn, db: Session = Depends(get_db)):
    t = db.get(models.Termin, rid)
    if not t or t.rodzaj != "stolik":
        raise HTTPException(404, "Brak rezerwacji.")
    nowy = (dane.status or "").strip()
    if nowy not in REZ_STATUSY:
        raise HTTPException(400, "Nieznany status.")
    if nowy not in REZ_PRZEJSCIA.get(t.status, set()):
        raise HTTPException(409, f"Niedozwolone przejście {t.status} → {nowy}.")
    t.status = nowy
    if nowy == "potwierdzona":
        t.potwierdzono_at = utcnow_naive()
    elif nowy == "odwolana":
        t.odwolano_at = utcnow_naive()
    db.commit(); db.refresh(t)
    return _rezerwacja_out(t)


@app.delete("/api/rezerwacje-stolik/{rid}", status_code=204, dependencies=[Depends(_wymagaj_modul_rezerwacje)])
def usun_rezerwacje_stolik(rid: int, db: Session = Depends(get_db)):
    t = db.get(models.Termin, rid)
    if t and t.rodzaj == "stolik":
        db.delete(t); db.commit()


@app.post("/api/rezerwacje-stolik/{rid}/wyslij-potwierdzenie", dependencies=[Depends(_wymagaj_modul_rezerwacje)])
def wyslij_potwierdzenie_stolik(rid: int, db: Session = Depends(get_db)):
    """Ponowna wysyłka e-maila z potwierdzeniem rezerwacji. Zwraca {wyslano, powod?}."""
    t = db.get(models.Termin, rid)
    if not t or t.rodzaj != "stolik":
        raise HTTPException(404, "Brak rezerwacji.")
    if not t.email:
        raise HTTPException(400, "Rezerwacja nie ma adresu e-mail.")
    if not integracje.skonfigurowane("email"):
        return {"wyslano": False, "powod": "Integracja e-mail nieskonfigurowana."}
    return {"wyslano": _wyslij_potwierdzenie_rezerwacji(db, t)}


# ── Lista oczekujących (waitlist) ────────────────────────────────────────────
def _lista_out(w: models.ListaOczekujacych) -> dict:
    return {"id": w.id, "data": str(w.data), "godz_od": _hm(w.godz_od), "liczba_osob": w.liczba_osob,
            "nazwisko": w.nazwisko, "telefon": w.telefon, "email": w.email, "notatka": w.notatka,
            "status": w.status, "termin_id": w.termin_id}


@app.get("/api/lista-oczekujacych", dependencies=[Depends(_wymagaj_modul_rezerwacje)])
def get_lista_oczekujacych(data: date = Query(...), db: Session = Depends(get_db)):
    rows = (db.query(models.ListaOczekujacych)
            .filter(models.ListaOczekujacych.data == data)
            .order_by(models.ListaOczekujacych.status, models.ListaOczekujacych.godz_od,
                      models.ListaOczekujacych.id).all())
    return {"lista": [_lista_out(w) for w in rows]}


@app.post("/api/lista-oczekujacych", status_code=201, dependencies=[Depends(_wymagaj_modul_rezerwacje)])
def dodaj_lista_oczekujacych(dane: schemas.ListaOczekujacychIn, db: Session = Depends(get_db)):
    if not dane.nazwisko or not dane.nazwisko.strip():
        raise HTTPException(400, "Podaj nazwisko / klienta.")
    w = models.ListaOczekujacych(
        data=dane.data, godz_od=dane.godz_od, liczba_osob=dane.liczba_osob,
        nazwisko=dane.nazwisko.strip(), telefon=dane.telefon, email=dane.email,
        notatka=dane.notatka, status="oczekuje", utworzono_at=utcnow_naive())
    db.add(w); db.commit(); db.refresh(w)
    return _lista_out(w)


@app.delete("/api/lista-oczekujacych/{wid}", status_code=204, dependencies=[Depends(_wymagaj_modul_rezerwacje)])
def usun_lista_oczekujacych(wid: int, db: Session = Depends(get_db)):
    w = db.get(models.ListaOczekujacych, wid)
    if w:
        db.delete(w); db.commit()


@app.post("/api/lista-oczekujacych/{wid}/odwolaj", dependencies=[Depends(_wymagaj_modul_rezerwacje)])
def odwolaj_lista_oczekujacych(wid: int, db: Session = Depends(get_db)):
    w = db.get(models.ListaOczekujacych, wid)
    if not w:
        raise HTTPException(404, "Brak wpisu.")
    w.status = "odwolany"
    db.commit(); db.refresh(w)
    return _lista_out(w)


@app.post("/api/lista-oczekujacych/{wid}/zrealizuj", dependencies=[Depends(_wymagaj_modul_rezerwacje)])
def zrealizuj_lista_oczekujacych(wid: int, dane: schemas.ZrealizujIn, db: Session = Depends(get_db)):
    """Realizuje wpis z listy oczekujących → tworzy rezerwację na wskazanym stoliku
    (walidacja pojemności/kolizji). Wpis dostaje status 'zrealizowany'."""
    w = db.get(models.ListaOczekujacych, wid)
    if not w:
        raise HTTPException(404, "Brak wpisu.")
    if w.status != "oczekuje":
        raise HTTPException(409, "Wpis już zrealizowany lub odwołany.")
    godz = dane.godz_od or w.godz_od
    godz_do = _waliduj_rezerwacje(db, w.data, godz, None, dane.stolik_id, w.liczba_osob)
    t = models.Termin(
        data=w.data, nazwisko=w.nazwisko, telefon=w.telefon, email=w.email,
        liczba_osob=w.liczba_osob, notatka=w.notatka, status="potwierdzona", zadatek=0.0,
        utworzono_at=utcnow_naive(), godz_od=godz, godz_do=godz_do, stolik_id=dane.stolik_id,
        rodzaj="stolik", kanal="reczna")
    db.add(t); db.flush()
    w.status = "zrealizowany"; w.zrealizowano_at = utcnow_naive(); w.termin_id = t.id
    db.commit(); db.refresh(t)
    _wyslij_potwierdzenie_rezerwacji(db, t)   # best-effort
    return {"rezerwacja": _rezerwacja_out(t), "wpis": _lista_out(w)}


# ═══════════════════════════════════════════════════════════════════════════
# REZERWACJE ONLINE (publiczny widget — bez logowania, za flagą rezerwacje_online)
# ═══════════════════════════════════════════════════════════════════════════

ONLINE_LIMIT_DZIENNY = 5   # anty-spam: maks. aktywnych rezerwacji online/dzień po telefonie/e-mailu


def _wymagaj_rezerwacje_online(db: Session = Depends(get_db)):
    cfg = get_lokal_config(db)
    if not (cfg.modul_rezerwacje and cfg.rezerwacje_online):
        raise HTTPException(404, "Rezerwacje online są niedostępne.")


def _sloty_dnia(db, data: date):
    """(lista godzin slotów, długość slotu w min) wg GodzinyOtwarcia dla dnia. Pusta gdy zamknięte."""
    go = db.query(models.GodzinyOtwarcia).filter_by(dzien_tygodnia=data.weekday(), aktywny=True).first()
    if not go:
        return [], DOMYSLNY_SLOT_MIN
    krok = go.dlugosc_slotu_min or DOMYSLNY_SLOT_MIN
    last = go.ostatni_zasiadek or go.godz_do
    start_m, last_m = go.godz_od.hour * 60 + go.godz_od.minute, last.hour * 60 + last.minute
    sloty, m = [], start_m
    while m <= last_m:
        sloty.append(time(m // 60, m % 60))
        m += krok
    return sloty, krok


def _stolik_zajety(db, data, stolik_id, godz_od, godz_do) -> bool:
    for r in db.query(models.Termin).filter(
            models.Termin.stolik_id == stolik_id, models.Termin.data == data,
            models.Termin.status.in_(REZ_AKTYWNE), models.Termin.godz_od.isnot(None)).all():
        r_do = r.godz_do or _dodaj_minuty(r.godz_od, _slot_dlugosc(db, data))
        if godz_od < r_do and r.godz_od < godz_do:
            return True
    return False


def _wybierz_wolny_stolik(db, data, godz_od, godz_do, osoby):
    """Najmniejszy wolny aktywny stolik mieszczący 'osoby' w oknie [godz_od, godz_do]. None gdy brak."""
    kandydaci = sorted([s for s in db.query(models.Stolik).filter_by(aktywny=True).all()
                        if (s.pojemnosc or 0) >= max(1, osoby or 1)],
                       key=lambda s: (s.pojemnosc, s.id))
    for s in kandydaci:
        if not _stolik_zajety(db, data, s.id, godz_od, godz_do):
            return s
    return None


def _online_rez_out(t: models.Termin, stolik=None) -> dict:
    return {"data": str(t.data), "godz_od": _hm(t.godz_od), "godz_do": _hm(t.godz_do),
            "liczba_osob": t.liczba_osob, "nazwisko": t.nazwisko, "status": t.status,
            "stolik": (stolik.nazwa if stolik else None), "token": t.token_potwierdzenia}


def _rez_po_tokenie(db, token: str):
    return db.query(models.Termin).filter_by(token_potwierdzenia=token, kanal="online").first()


@app.get("/api/online/dostepnosc", dependencies=[Depends(_wymagaj_rezerwacje_online)])
def online_dostepnosc(data: date = Query(...), osoby: int = 2, db: Session = Depends(get_db)):
    """Publicznie: wolne sloty na dany dzień (godzina → liczba wolnych stolików dla 'osoby')."""
    osoby = max(1, osoby)
    sloty, krok = _sloty_dnia(db, data)
    stoliki = [s for s in db.query(models.Stolik).filter_by(aktywny=True).all() if (s.pojemnosc or 0) >= osoby]
    out = []
    for g in sloty:
        g_do = _dodaj_minuty(g, krok)
        wolne = sum(1 for s in stoliki if not _stolik_zajety(db, data, s.id, g, g_do))
        out.append({"godz_od": _hm(g), "wolne": wolne})
    return {"data": str(data), "osoby": osoby, "sloty": out}


@app.post("/api/online/rezerwacja", status_code=201, dependencies=[Depends(_wymagaj_rezerwacje_online)])
def online_rezerwacja(dane: schemas.OnlineRezerwacjaIn, db: Session = Depends(get_db)):
    """Publicznie: utworzenie rezerwacji online. System sam dobiera wolny stolik."""
    if not dane.nazwisko or not dane.nazwisko.strip():
        raise HTTPException(400, "Podaj imię/nazwisko.")
    if (dane.liczba_osob or 0) < 1:
        raise HTTPException(400, "Liczba osób musi być dodatnia.")
    if dane.data < date.today():
        raise HTTPException(400, "Nie można rezerwować wstecz.")
    # Anty-spam: limit aktywnych rezerwacji online/dzień po tym samym telefonie/e-mailu.
    # Telefon/e-mail są szyfrowane at-rest (niedeterministycznie) — nie da się filtrować
    # po nich w SQL; pobieramy dzienny (mały) zbiór online i porównujemy po odszyfrowaniu.
    if dane.telefon or dane.email:
        dzisiaj_online = db.query(models.Termin).filter(
            models.Termin.kanal == "online", models.Termin.data == dane.data,
            models.Termin.status.in_(REZ_AKTYWNE)).all()
        ile = sum(1 for t in dzisiaj_online
                  if (dane.telefon and t.telefon == dane.telefon)
                  or (dane.email and t.email == dane.email))
        if ile >= ONLINE_LIMIT_DZIENNY:
            raise HTTPException(429, "Przekroczono dzienny limit rezerwacji online.")

    godz_do = _dodaj_minuty(dane.godz_od, _slot_dlugosc(db, dane.data))
    stolik = _wybierz_wolny_stolik(db, dane.data, dane.godz_od, godz_do, dane.liczba_osob)
    if not stolik:
        raise HTTPException(409, "Brak wolnego stolika w wybranym czasie.")
    cfg = get_lokal_config(db)
    status = "potwierdzona" if cfg.rezerwacje_auto_potwierdzenie else "rezerwacja"
    t = models.Termin(
        data=dane.data, nazwisko=dane.nazwisko.strip(), telefon=dane.telefon, email=dane.email,
        liczba_osob=dane.liczba_osob, notatka=dane.notatka, status=status, zadatek=0.0,
        utworzono_at=utcnow_naive(), godz_od=dane.godz_od, godz_do=godz_do, stolik_id=stolik.id,
        rodzaj="stolik", kanal="online", token_potwierdzenia=secrets.token_urlsafe(24),
        potwierdzono_at=(utcnow_naive() if status == "potwierdzona" else None))
    db.add(t); db.commit(); db.refresh(t)
    wyslij_push_do_adminow(db, "Rezerwacja online",
                           f"{t.nazwisko} — {t.data} {_hm(t.godz_od) or ''}".strip(), url="/")
    _wyslij_potwierdzenie_rezerwacji(db, t)   # best-effort
    return {"token": t.token_potwierdzenia, "rezerwacja": _online_rez_out(t, stolik)}


@app.get("/api/online/rezerwacja/{token}", dependencies=[Depends(_wymagaj_rezerwacje_online)])
def online_rezerwacja_get(token: str, db: Session = Depends(get_db)):
    t = _rez_po_tokenie(db, token)
    if not t:
        raise HTTPException(404, "Nie znaleziono rezerwacji.")
    return _online_rez_out(t, db.get(models.Stolik, t.stolik_id) if t.stolik_id else None)


@app.post("/api/online/rezerwacja/{token}/potwierdz", dependencies=[Depends(_wymagaj_rezerwacje_online)])
def online_rezerwacja_potwierdz(token: str, db: Session = Depends(get_db)):
    t = _rez_po_tokenie(db, token)
    if not t:
        raise HTTPException(404, "Nie znaleziono rezerwacji.")
    if t.status == "rezerwacja":
        t.status = "potwierdzona"; t.potwierdzono_at = utcnow_naive(); db.commit(); db.refresh(t)
    return _online_rez_out(t, db.get(models.Stolik, t.stolik_id) if t.stolik_id else None)


@app.post("/api/online/rezerwacja/{token}/odwolaj", dependencies=[Depends(_wymagaj_rezerwacje_online)])
def online_rezerwacja_odwolaj(token: str, db: Session = Depends(get_db)):
    t = _rez_po_tokenie(db, token)
    if not t:
        raise HTTPException(404, "Nie znaleziono rezerwacji.")
    if t.status in REZ_AKTYWNE:
        t.status = "odwolana"; t.odwolano_at = utcnow_naive(); db.commit(); db.refresh(t)
    return _online_rez_out(t, db.get(models.Stolik, t.stolik_id) if t.stolik_id else None)


# --- POWIADOMIENIA WEB PUSH (pracownik) ---

@app.get("/api/me/push/public-key", status_code=200)
def push_public_key(user: models.User = Depends(get_current_user)):
    return {"publicKey": VAPID_PUBLIC_KEY}

@app.post("/api/me/push/subscribe", status_code=204)
def push_subscribe(sub: dict, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    endpoint = sub.get("endpoint")
    keys = sub.get("keys") or {}
    p256dh, auth = keys.get("p256dh"), keys.get("auth")
    if not endpoint or not p256dh or not auth:
        raise HTTPException(400, "Nieprawidłowa subskrypcja push.")
    existing = db.query(models.PushSubscription).filter_by(endpoint=endpoint).first()
    if existing:
        existing.user_id, existing.p256dh, existing.auth = user.id, p256dh, auth
    else:
        db.add(models.PushSubscription(user_id=user.id, endpoint=endpoint, p256dh=p256dh, auth=auth))
    db.commit()

# --- PUBLIKACJA GRAFIKU (admin — chronione middleware) ---

@app.get("/api/grafik/publikacja", status_code=200)
def status_publikacji(start: date = Query(...), end: date = Query(...), db: Session = Depends(get_db)):
    p = db.query(models.PublikacjaGrafiku).filter_by(start=start, koniec=end).first()
    return {"opublikowany": bool(p), "opublikowano_at": p.opublikowano_at.isoformat() if p else None}

@app.post("/api/grafik/publikuj", status_code=200)
def publikuj_grafik(start: date = Query(...), end: date = Query(...), cisza: bool = False, db: Session = Depends(get_db)):
    """Publikuje grafik tygodnia. cisza=true -> bez powiadomien push (np. dla starych tygodni)."""
    teraz = utcnow_naive()
    p = db.query(models.PublikacjaGrafiku).filter_by(start=start, koniec=end).first()
    if p:
        p.opublikowano_at = teraz
    else:
        db.add(models.PublikacjaGrafiku(start=start, koniec=end, opublikowano_at=teraz))
    db.commit()
    # AUTO „zamyka lokal": ustaw zamykającego dla każdego dnia tygodnia (też backfill
    # wcześniej wprowadzonych dni, zanim automat działał).
    dzien = start
    while dzien <= end:
        _przelicz_zamykajacego(db, dzien)
        dzien += timedelta(days=1)
    wyslano = 0
    if not cisza:
        wyslano = wyslij_push(
            db,
            "Grafik udostępniony",
            f"Twój grafik na tydzień {start.strftime('%d.%m')}–{end.strftime('%d.%m')} jest gotowy.",
            url="/",
        )
    return {"opublikowano_at": teraz.isoformat(), "push_wyslano": wyslano}

@app.delete("/api/grafik/publikuj", status_code=204)
def cofnij_publikacje(start: date = Query(...), end: date = Query(...), db: Session = Depends(get_db)):
    db.query(models.PublikacjaGrafiku).filter_by(start=start, koniec=end).delete()
    db.commit()


@app.get("/api/stanowiska", response_model=List[schemas.StanowiskoOut])
def get_stanowiska(db: Session = Depends(get_db)):
    _ensure_kwalifikacje_techniczne(db)  # Sprzątaczka/Stróż dostępne do nadania w Pracownikach
    return db.query(models.Stanowisko).all()

@app.post("/api/stanowiska", response_model=schemas.StanowiskoOut, status_code=201)
def create_stanowisko(data: schemas.StanowiskoCreate, db: Session = Depends(get_db)):
    if db.query(models.Stanowisko).filter_by(nazwa=data.nazwa).first():
        raise HTTPException(400, "Stanowisko o tej nazwie już istnieje.")
    s = models.Stanowisko(**data.model_dump())
    s.grupa_widocznosci = (s.grupa_widocznosci or "").strip() or None  # pusty string -> brak grupy
    s.rola = (s.rola or "").strip() or None
    db.add(s); db.commit(); db.refresh(s)
    return s

@app.put("/api/stanowiska/{sid}", response_model=schemas.StanowiskoOut)
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

@app.delete("/api/stanowiska/{sid}", status_code=204)
def delete_stanowisko(sid: int, db: Session = Depends(get_db)):
    s = db.get(models.Stanowisko, sid)
    if not s:
        raise HTTPException(404, "Nie znaleziono.")
    db.delete(s); db.commit()

@app.post("/api/stanowiska/{sid}/podkategorie", response_model=schemas.PodkategoriaOut)
def create_podkategoria(sid: int, data: schemas.PodkategoriaCreate, db: Session = Depends(get_db)):
    p = models.Podkategoria(**data.model_dump(), stanowisko_id=sid)
    db.add(p); db.commit(); db.refresh(p)
    return p

@app.delete("/api/podkategorie/{pid}", status_code=204)
def delete_podkategoria(pid: int, db: Session = Depends(get_db)):
    p = db.get(models.Podkategoria, pid)
    if p:
        db.delete(p); db.commit()


# ═══════════════════════════════════════════════════════════════════════════
# PRACOWNICY
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/pracownicy", response_model=List[schemas.PracownikOut])
def get_pracownicy(db: Session = Depends(get_db)):
    return db.query(models.Pracownik).order_by(models.Pracownik.kolejnosc, models.Pracownik.id).all()


@app.get("/api/grafik/kuchnia-stanowisko")
def kuchnia_stanowisko_info(db: Session = Depends(get_db)):
    """Zwraca (tworząc w razie potrzeby) ukryte stanowisko kuchni — front używa jego id do
    grafiku kuchni i stawki kuchni. Tylko admin (wymusza middleware)."""
    s = _kuchnia_stanowisko(db)
    return {"id": s.id, "nazwa": s.nazwa}


@app.get("/api/grafik/techniczny-stanowisko")
def techniczny_stanowisko_info(db: Session = Depends(get_db)):
    """Ukryte stanowisko techniczne — front używa jego id do stawki technicznej. Tylko admin."""
    s = _techniczny_stanowisko(db)
    return {"id": s.id, "nazwa": s.nazwa}

def _ustaw_stawki(db, p, stawki):
    """Nadpisuje stawki godzinowe pracownika (per stanowisko). Zapisuje tylko dodatnie."""
    db.query(models.StawkaPracownika).filter_by(pracownik_id=p.id).delete()
    for s in (stawki or []):
        if s.stanowisko_id and s.stawka and s.stawka > 0:
            db.add(models.StawkaPracownika(
                pracownik_id=p.id, stanowisko_id=s.stanowisko_id, stawka=float(s.stawka)
            ))


@app.post("/api/pracownicy", response_model=schemas.PracownikOut, status_code=201)
def create_pracownik(data: schemas.PracownikCreate, db: Session = Depends(get_db)):
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

@app.put("/api/pracownicy/kolejnosc", status_code=200)
def ustaw_kolejnosc(data: schemas.KolejnoscIn, db: Session = Depends(get_db)):
    """Ręczna kolejność wyświetlania pracowników: kolejnosc = pozycja na liście ids."""
    for idx, pid in enumerate(data.ids):
        p = db.get(models.Pracownik, pid)
        if p:
            p.kolejnosc = idx
    db.commit()
    return {"ok": True}


@app.put("/api/pracownicy/{pid}", response_model=schemas.PracownikOut)
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

@app.delete("/api/pracownicy/{pid}", status_code=204)
def delete_pracownik(pid: int, db: Session = Depends(get_db)):
    p = db.get(models.Pracownik, pid)
    if not p:
        raise HTTPException(404, "Nie znaleziono.")
    db.delete(p); db.commit()


# ═══════════════════════════════════════════════════════════════════════════
# WYMAGANIA DNIA
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/wymagania", response_model=List[schemas.WymaganiaOut])
def get_wymagania(
    start: Optional[date] = None,
    end: Optional[date] = None,
    db: Session = Depends(get_db)
):
    if start and end:
        _odswiez_wymagania_imprez(db, start, end)   # świeże wymagania imprez przed odczytem widoku
    q = db.query(models.WymaganiaDnia)
    if start: q = q.filter(models.WymaganiaDnia.data >= start)
    if end:   q = q.filter(models.WymaganiaDnia.data <= end)
    return q.all()

@app.post("/api/wymagania", response_model=schemas.WymaganiaOut, status_code=201)
def create_wymagania(data: schemas.WymaganiaCreate, db: Session = Depends(get_db)):
    existing = db.query(models.WymaganiaDnia).filter_by(
        data=data.data,
        stanowisko_id=data.stanowisko_id,
        godz_od=data.godz_od,
        rewir=data.rewir
    ).first()
    
    if existing:
        existing.liczba_osob = data.liczba_osob
        db.commit(); db.refresh(existing)
        return existing
        
    w = models.WymaganiaDnia(**data.model_dump())
    db.add(w); db.commit(); db.refresh(w)
    return w

@app.delete("/api/wymagania/{wid}", status_code=204)
def delete_wymagania(wid: int, db: Session = Depends(get_db)):
    w = db.get(models.WymaganiaDnia, wid)
    if not w:
        raise HTTPException(404, "Nie znaleziono.")
    db.delete(w); db.commit()

@app.post("/api/wymagania/kopiuj", status_code=200)
def kopiuj_wymagania(body: dict, db: Session = Depends(get_db)):
    source = date.fromisoformat(body["source_date"])
    start  = date.fromisoformat(body["start_date"])
    end    = date.fromisoformat(body["end_date"])

    source_reqs = db.query(models.WymaganiaDnia).filter_by(data=source).all()
    if not source_reqs:
        raise HTTPException(404, "Brak wymagań dla dnia źródłowego.")

    count = 0
    current = start
    while current <= end:
        if current == source:
            current += timedelta(days=1)
            continue
        for req in source_reqs:
            existing = db.query(models.WymaganiaDnia).filter_by(
                data=current,
                stanowisko_id=req.stanowisko_id,
                godz_od=req.godz_od,
                rewir=req.rewir
            ).first()
            
            if existing:
                existing.liczba_osob = req.liczba_osob
            else:
                db.add(models.WymaganiaDnia(
                    data=current,
                    stanowisko_id=req.stanowisko_id,
                    godz_od=req.godz_od,
                    rewir=req.rewir,
                    liczba_osob=req.liczba_osob,
                ))
            count += 1
        current += timedelta(days=1)
    db.commit()
    return {"skopiowano": count}


@app.post("/api/wymagania/kopiuj-tydzien", status_code=200)
def kopiuj_wymagania_tydzien(body: dict, db: Session = Depends(get_db)):
    """Kopiuje wszystkie wymagania z tygodnia źródłowego na docelowy (dzień w dzień,
    przez offset dat). Tygodnie środa→wtorek mają ten sam układ dni tygodnia."""
    src_start = date.fromisoformat(body["source_start"])
    dst_start = date.fromisoformat(body["target_start"])
    offset = (dst_start - src_start).days
    if offset == 0:
        raise HTTPException(400, "Tydzień źródłowy i docelowy są takie same.")
    src_reqs = db.query(models.WymaganiaDnia).filter(
        models.WymaganiaDnia.data >= src_start,
        models.WymaganiaDnia.data <= src_start + timedelta(days=6),
    ).all()
    if not src_reqs:
        raise HTTPException(404, "Brak wymagań w tygodniu źródłowym.")
    count = 0
    for req in src_reqs:
        new_date = req.data + timedelta(days=offset)
        existing = db.query(models.WymaganiaDnia).filter_by(
            data=new_date,
            stanowisko_id=req.stanowisko_id,
            godz_od=req.godz_od,
            rewir=req.rewir,
        ).first()
        if existing:
            existing.liczba_osob = req.liczba_osob
        else:
            db.add(models.WymaganiaDnia(
                data=new_date,
                stanowisko_id=req.stanowisko_id,
                godz_od=req.godz_od,
                rewir=req.rewir,
                liczba_osob=req.liczba_osob,
            ))
        count += 1
    db.commit()
    return {"skopiowano": count}


# ═══════════════════════════════════════════════════════════════════════════
# DYSPOZYCJE (ZAKŁADKA IMPORtowania
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/dyspozycje", response_model=List[schemas.DyspozycjaOut])
def get_dyspozycje(
    start: Optional[date] = None,
    end: Optional[date] = None,
    db: Session = Depends(get_db)
):
    q = db.query(models.Dyspozycja)
    if start: q = q.filter(models.Dyspozycja.data >= start)
    if end:   q = q.filter(models.Dyspozycja.data <= end)
    return q.all()

@app.post("/api/dyspozycje", response_model=schemas.DyspozycjaOut, status_code=201)
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

@app.delete("/api/dyspozycje/{did}", status_code=204)
def delete_dyspozycja(did: int, db: Session = Depends(get_db)):
    """Czyści dyspozycyjność (admin) — wraca do stanu „brak zgłoszenia"."""
    d = db.get(models.Dyspozycja, did)
    if not d:
        raise HTTPException(404, "Nie znaleziono.")
    db.delete(d); db.commit()


# ═══════════════════════════════════════════════════════════════════════════
# PRZYDZIAŁY (ZAKTUALIZOWANE DLA WIELU ZMIAN CZASOWYCH)
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/przydzialy", response_model=List[schemas.PrzydzialOut])
def get_przydzialy(
    start: Optional[date] = None,
    end: Optional[date] = None,
    db: Session = Depends(get_db)
):
    q = db.query(models.PrzydzialZmiany)
    if start: q = q.filter(models.PrzydzialZmiany.data >= start)
    if end:   q = q.filter(models.PrzydzialZmiany.data <= end)
    return q.all()


def _powiadom_kuchnie_o_zmianie(db, pracownik_id, tytul, tresc):
    """Push do pracownika KUCHNI o KAŻDEJ zmianie w jego grafiku (dodanie/zmiana/wykreślenie).
    Dla obsługi nic nie robi (ci dostają push przy publikacji). Best-effort — błędy łykamy."""
    p = db.get(models.Pracownik, pracownik_id)
    if p and p.dzial == "kuchnia":
        try:
            wyslij_push_do_pracownika(db, pracownik_id, tytul, tresc, url="/")
        except Exception:
            pass


@app.post("/api/przydzialy", response_model=schemas.PrzydzialOut, status_code=201)
def create_przydział(data: schemas.PrzydzialCreate, db: Session = Depends(get_db)):
    stan = db.get(models.Stanowisko, data.stanowisko_id)
    if stan and stan.tylko_weekend and data.data.weekday() < 5:
        raise HTTPException(400, f"Stanowisko '{stan.nazwa}' jest aktywne tylko w weekendy.")
    
    # Zasada biznesowa: maksymalnie JEDNA zmiana na pracownika w danym dniu.
    istniejaca = db.query(models.PrzydzialZmiany).filter_by(
        data=data.data,
        pracownik_id=data.pracownik_id,
    ).first()

    if istniejaca:
        raise HTTPException(400, "Pracownik ma już przydzieloną zmianę w tym dniu (maks. 1 zmiana dziennie).")

    a = models.PrzydzialZmiany(**data.model_dump())
    db.add(a); db.commit(); db.refresh(a)
    _przelicz_zamykajacego(db, a.data)   # AUTO „zamyka lokal": najpóźniejszy na parkiecie tego dnia
    db.refresh(a)
    _powiadom_kuchnie_o_zmianie(db, a.pracownik_id, "Nowa zmiana w grafiku", "Dodano Ci zmianę w grafiku kuchni.")
    return a

@app.put("/api/przydzialy/{aid}", response_model=schemas.PrzydzialOut)
def update_przydział(aid: int, data: schemas.PrzydzialCreate, db: Session = Depends(get_db)):
    a = db.get(models.PrzydzialZmiany, aid)
    if not a:
        raise HTTPException(404, "Nie znaleziono.")
    stan = db.get(models.Stanowisko, data.stanowisko_id)
    if stan and stan.tylko_weekend and data.data.weekday() < 5:
        raise HTTPException(400, f"Stanowisko '{stan.nazwa}' jest aktywne tylko w weekendy.")

    # Maks. 1 zmiana/dzień — blokuj przeniesienie na dzień, gdzie pracownik ma już inną zmianę.
    kolizja = db.query(models.PrzydzialZmiany).filter(
        models.PrzydzialZmiany.data == data.data,
        models.PrzydzialZmiany.pracownik_id == data.pracownik_id,
        models.PrzydzialZmiany.id != aid,
    ).first()
    if kolizja:
        raise HTTPException(400, "Pracownik ma już przydzieloną zmianę w tym dniu (maks. 1 zmiana dziennie).")

    stara_data = a.data
    for k, v in data.model_dump().items():
        setattr(a, k, v)
    db.commit(); db.refresh(a)
    _przelicz_zamykajacego(db, a.data)              # AUTO „zamyka lokal" dla (nowego) dnia
    if stara_data != a.data:
        _przelicz_zamykajacego(db, stara_data)      # i dla dnia, z którego zmiana zniknęła
    db.refresh(a)
    _powiadom_kuchnie_o_zmianie(db, a.pracownik_id, "Zmiana w grafiku", "Zaktualizowano Twoją zmianę w grafiku kuchni.")
    return a

@app.delete("/api/przydzialy/{aid}", status_code=204)
def delete_przydział(aid: int, db: Session = Depends(get_db)):
    a = db.get(models.PrzydzialZmiany, aid)
    if not a:
        raise HTTPException(404, "Nie znaleziono.")
    pid = a.pracownik_id
    dzien = a.data
    db.delete(a); db.commit()
    _przelicz_zamykajacego(db, dzien)   # AUTO „zamyka lokal": po usunięciu zmiany przelicz dzień
    _powiadom_kuchnie_o_zmianie(db, pid, "Zmiana w grafiku", "Wykreślono Cię ze zmiany w grafiku kuchni.")

@app.put("/api/przydzialy/{aid}/zamyka", status_code=200)
def ustaw_zamykajacego(aid: int, payload: dict, db: Session = Depends(get_db)):
    """Ręczne nadpisanie zamykającego (domyślnie automat wybiera najpóźniejszego z parkietu).
      • {"reczny": true}  → TEN przydział zamyka lokal ręcznie; automat go nie zmienia,
        reszta dnia ma zamyka=False.
      • {"reczny": false} → zdejmij ręczne ustawienie i wróć do automatu dla tego dnia."""
    a = db.get(models.PrzydzialZmiany, aid)
    if not a:
        raise HTTPException(404, "Nie znaleziono.")
    if bool(payload.get("reczny")):
        for r in db.query(models.PrzydzialZmiany).filter(models.PrzydzialZmiany.data == a.data).all():
            r.zamyka = r.id == aid
            r.zamyka_reczny = r.id == aid
        db.commit()
    else:
        a.zamyka_reczny = False
        db.commit()
        _przelicz_zamykajacego(db, a.data)   # powrót do automatu
    db.refresh(a)
    return {"id": a.id, "zamyka": bool(a.zamyka), "zamyka_reczny": bool(a.zamyka_reczny)}

@app.delete("/api/przydzialy", status_code=204)
def clear_przydzialy(
    start: date = Query(...),
    end: date = Query(...),
    dzial: Optional[str] = Query(None),   # 'obsluga' | 'kuchnia' — czyść TYLKO grafik tego działu
    db: Session = Depends(get_db)
):
    q = db.query(models.PrzydzialZmiany).filter(
        models.PrzydzialZmiany.data >= start,
        models.PrzydzialZmiany.data <= end,
    )
    if dzial:
        # Czyść tylko grafik wskazanego działu (np. obsługa) — drugi grafik (kuchnia) zostaje.
        prac_ids = [pid for (pid,) in db.query(models.Pracownik.id)
                    .filter(models.Pracownik.dzial == dzial).all()]
        q = q.filter(models.PrzydzialZmiany.pracownik_id.in_(prac_ids))
    q.delete(synchronize_session=False)
    db.commit()
    # Po wyczyszczeniu przelicz zamykającego dla każdego dnia zakresu (zniknęli kandydaci).
    dzien = start
    while dzien <= end:
        _przelicz_zamykajacego(db, dzien)
        dzien += timedelta(days=1)


# ═══════════════════════════════════════════════════════════════════════════
# AUTO-ASSIGN
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/api/auto-assign", response_model=schemas.AutoAssignResult)
def auto_assign_endpoint(
    start: date = Query(...),
    end: date = Query(...),
    db: Session = Depends(get_db)
):
    # Świeże wymagania pod imprezy z aktualnej tabeli — żeby auto-przydział miał co obsadzać.
    _odswiez_wymagania_imprez(db, start, end)
    result = _auto_assign(db, start, end)
    # Auto-przydział TYLKO SZKICUJE: cofamy publikację tygodnia, żeby zmiany NIE trafiły od razu
    # do obsługi. Admin sprawdza grafik i publikuje ręcznie („Udostępnij pracownikom").
    db.query(models.PublikacjaGrafiku).filter(
        models.PublikacjaGrafiku.start <= end,
        models.PublikacjaGrafiku.koniec >= start,
    ).delete(synchronize_session=False)
    db.commit()
    # AUTO „zamyka lokal": po automatycznym ułożeniu grafiku przelicz zamykającego per dzień.
    dzien = start
    while dzien <= end:
        _przelicz_zamykajacego(db, dzien)
        dzien += timedelta(days=1)
    return result


# ═══════════════════════════════════════════════════════════════════════════
# EKSPORT CSV
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/eksport-csv")
def eksport_csv(start: date, end: date, db: Session = Depends(get_db)):
    # 1. Pobieramy wszystkie przydziały z wybranego zakresu dat
    przydzialy = db.query(models.PrzydzialZmiany).filter(
        models.PrzydzialZmiany.data >= start,
        models.PrzydzialZmiany.data <= end
    ).all()
    
    # 2. Pobieramy wyłącznie pracowników, którzy są w grafiku "Aktywni"
    pracownicy = db.query(models.Pracownik).filter(models.Pracownik.aktywny == True).all()
    
    # 3. Pobieramy nazwy stanowisk ze słownika (żeby nie wyświetlać samych numerów ID)
    stanowiska_db = db.query(models.Stanowisko).all()
    stanowiska_slownik = {s.id: s.nazwa for s in stanowiska_db}
    
    # 4. Matematyka dat: Tworzymy listę wszystkich dni pomiędzy 'start' i 'end'
    ilosc_dni = (end - start).days
    lista_dat = [start + timedelta(days=i) for i in range(ilosc_dni + 1)]
    
    # 5. Tworzymy specjalny słownik do sortowania przydziałów w konkretne "kratki" tabeli
    # Kluczem jest (pracownik_id, data), a wartością lista tekstów ze zmianami
    przydzialy_w_kratkach = defaultdict(list)
    
    for p in przydzialy:
        # Odczytanie nazwy stanowiska
        nazwa_stanowiska = stanowiska_slownik.get(p.stanowisko_id, "Nieznane")
        
        # Przygotowanie ładnego formatu godzin
        g_od = p.godz_od.strftime("%H:%M") if p.godz_od else ""
        
        if g_od:
            tekst_zmiany = f"{nazwa_stanowiska} ({g_od})"
        else:
            tekst_zmiany = f"{nazwa_stanowiska} (Cały dzień)"
        
        przydzialy_w_kratkach[(p.pracownik_id, p.data)].append(tekst_zmiany)

    output = io.StringIO()
    # Używamy średnika! Polski Excel często psuje układ, jeśli użyje się standardowego przecinka
    writer = csv.writer(output, delimiter=';')
    
    # ---- TWORZENIE NAGŁÓWKA TABELI ----
    # Wygląda tak: ["Pracownik", "2026-06-01", "2026-06-02", "2026-06-03"...]
    naglowek = ["Pracownik"] + [d.strftime("%d.%m.%Y") for d in lista_dat]
    writer.writerow(naglowek)
    
    # ---- TWORZENIE WIERSZY PRACOWNIKÓW ----
    for pracownik in pracownicy:
        wiersz = [f"{pracownik.imie} {pracownik.nazwisko}"]
        
        for d in lista_dat:
            # Szukamy, czy pracownik ma w danym dniu wpisane zmiany
            zmiany = przydzialy_w_kratkach.get((pracownik.id, d), [])
            
            if zmiany:
                # Łączymy wszystkie zmiany pracownika z tego dnia znakiem |
                # (Zabezpieczenie na wypadek, gdyby pracował np. rano na Barze, a po południu na Sali)
                wiersz.append(" | ".join(zmiany))
            else:
                # Jeśli w tym dniu ma wolne, zostawiamy pustą komórkę
                wiersz.append("")
                
        writer.writerow(wiersz)
        
    # Przygotowanie pliku do wysłania
    output.seek(0)
    
    headers = {
        "Content-Disposition": f"attachment; filename=grafik_{start}_do_{end}.csv"
    }
    
    # Konwersja na bajty z ukrytym znacznikiem 'utf-8-sig'. 
    # Bez tego polskie znaki takie jak ą, ę, ł wyglądałyby w Excelu jak błędy (np. "krzaczki").
    return StreamingResponse(
        iter([output.getvalue().encode("utf-8-sig")]), 
        media_type="text/csv", 
        headers=headers
    )

# ═══════════════════════════════════════════════════════════════════════════
# IMPREZY Z SERWERA NAS (ZINTEGROWANE Z AUTOMATYKĄ WYMAGAŃ)
# ═══════════════════════════════════════════════════════════════════════════

# Ścieżka do plików imprez. Ustaw IMPREZY_PATH na katalog, do którego lokalny agent wgrywa
# kopie plików (VPS tylko je odczytuje). Puste = funkcja importu plików imprez wyłączona.
NAS_BASE_PATH = os.environ.get("IMPREZY_PATH", "")

@app.get("/api/imprezy", response_model=List[schemas.ImprezaOut])
def get_imprezy(start: date = Query(...), end: date = Query(...), db: Session = Depends(get_db)):
    return db.query(models.Impreza).filter(models.Impreza.data >= start, models.Impreza.data <= end).order_by(models.Impreza.data.asc()).all()


def _imprezy_stanowisko(db):
    """Stanowisko imprez — najpierw po roli 'imprezy', potem fallback po nazwie (zaczyna się od
    „imprez": łapie „Impreza"/„Imprezy"). Zwraca pierwsze pasujące stanowisko albo None."""
    s = db.query(models.Stanowisko).filter_by(rola="imprezy").first()
    if s:
        return s
    for s in db.query(models.Stanowisko).all():
        if (s.nazwa or "").strip().lower().startswith("imprez"):
            return s
    return None


def _imprezy_wymagania_warning(db):
    """Ostrzeżenie dla obsadzania imprez przez auto-przydział: brak stanowiska imprez
    albo brak AKTYWNEGO pracownika z tą kwalifikacją (wtedy auto-przydział nie obsadzi imprez)."""
    stan = _imprezy_stanowisko(db)
    if not stan:
        return 'Brak stanowiska imprez (np. „Impreza"/„Imprezy") — utwórz je w zakładce Stanowiska, inaczej imprezy nie zostaną obsadzone.'
    ma_ktos = db.query(models.Pracownik).filter(
        models.Pracownik.aktywny == True,
        models.Pracownik.kwalifikacje.any(models.Stanowisko.id == stan.id),
    ).first()
    if not ma_ktos:
        return f'Żaden aktywny pracownik nie ma kwalifikacji „{stan.nazwa}" — nadaj ją w zakładce Pracownicy, inaczej auto-przydział nie obsadzi imprez.'
    return None


def _impreza_params(cfg) -> dict:
    """Parametry obsady imprez z konfiguracji lokalu (LokalConfig) → dict dla
    algorithm.przelicz_imprezy_na_wymagania. `impreza_sale_min2` to lista po przecinku."""
    sale = [s.strip() for s in (cfg.impreza_sale_min2 or "").split(",") if s.strip()]
    return {
        "osoby_na_obsluge": cfg.impreza_osoby_na_obsluge,
        "wyprzedzenie_min": cfg.impreza_wyprzedzenie_min,
        "najwczesniej": cfg.impreza_najwczesniej,
        "sale_min2": sale,
    }


def _odswiez_wymagania_imprez(db, start, end):
    """Przelicza wymagania imprez dla [start, end] z AKTUALNEJ tabeli imprez: kasuje stare
    auto-wymagania imprez (jest_impreza=True) i tworzy świeże na stanowisku imprez. Dzięki temu
    auto-przydział i widok „Wymagania" ZAWSZE mają aktualne wymagania pod imprezy — bez ręcznego
    re-syncu. Bez stanowiska imprez („Impreza"/„Imprezy") nic nie robi."""
    stan = _imprezy_stanowisko(db)
    if not stan:
        return
    imprezy = db.query(models.Impreza).filter(
        models.Impreza.data >= start, models.Impreza.data <= end
    ).all()
    nowe = przelicz_imprezy_na_wymagania(imprezy, _impreza_params(get_lokal_config(db)))
    db.query(models.WymaganiaDnia).filter(
        models.WymaganiaDnia.data >= start,
        models.WymaganiaDnia.data <= end,
        models.WymaganiaDnia.jest_impreza == True,
    ).delete(synchronize_session=False)
    for w in nowe:
        db.add(models.WymaganiaDnia(**w, stanowisko_id=stan.id))
    db.commit()


@app.post("/api/imprezy/sync")
def sync_imprezy(start: date = Query(...), end: date = Query(...), db: Session = Depends(get_db)):
    if not os.path.exists(NAS_BASE_PATH):
        raise HTTPException(status_code=404, detail="Brak połączenia z serwerem NAS.")

    file_pattern = re.compile(r"(\d{4}\.\d{2}\.\d{2})\s*-\s*(.+)\.xlsx$")
    dodano = zaktualizowano = bledy = 0

    for root, dirs, files in os.walk(NAS_BASE_PATH):
        for file in [f for f in files if not f.startswith('.')]:
            match = file_pattern.match(file)
            if not match: continue

            event_date = datetime.strptime(match.group(1), "%Y.%m.%d").date()
            if not (start <= event_date <= end): continue

            file_path = os.path.join(root, file)
            existing = db.query(models.Impreza).filter(models.Impreza.sciezka_pliku == file_path).first()

            try:
                wb = openpyxl.load_workbook(file_path, data_only=True)
                ws = wb.active
                godz = str(ws['J1'].value).strip() if ws['J1'].value else "Brak"
                osob = int(ws['H8'].value) if isinstance(ws['H8'].value, (int, float)) else 0
                sala = str(ws['J2'].value).strip() if ws['J2'].value else "Brak"
                wb.close()
            except: bledy += 1; continue

            if existing:
                if existing.liczba_osob != osob or existing.godzina != godz or existing.sala != sala:
                    existing.liczba_osob, existing.godzina, existing.sala = osob, godz, sala
                    zaktualizowano += 1
            else:
                db.add(models.Impreza(data=event_date, klient=match.group(2).strip(), liczba_osob=osob, godzina=godz, sala=sala, sciezka_pliku=file_path))
                dodano += 1
    db.commit()

    # Auto-wymagania pod imprezy (świeże z aktualnej tabeli imprez; bez fallbacku na Bar).
    _odswiez_wymagania_imprez(db, start, end)

    return {"dodano": dodano, "zaktualizowano": zaktualizowano, "bledy": bledy,
            "ostrzezenie": _imprezy_wymagania_warning(db)}


# ═══════════════════════════════════════════════════════════════════════════
# IMPREZY — INGEST Z LAPTOPA (admin wysyła już sparsowane pola, nie całe pliki)
#   Laptop ma NAS w Finderze, czyta pliki .xlsx LOKALNIE, wyciąga (data, klient, godzina,
#   sala, liczba_osob) i wysyła maleńki JSON. VPS nie parsuje Excela i nie czyta NAS-a.
# ═══════════════════════════════════════════════════════════════════════════
def _normalizuj_godzine(g) -> str:
    """Godzina może przyjść jako ułamek doby z Excela (np. '0.6041666' = 14:30),
    jako 'HH:MM' lub 'HH:MM:SS'. Sprowadzamy do 'HH:MM' (albo 'Brak')."""
    if g is None:
        return "Brak"
    s = str(g).strip()
    if not s or s.lower() in ("none", "brak"):
        return "Brak"
    try:
        f = float(s.replace(",", "."))
        if 0 <= f < 1:  # ułamek doby
            total = round(f * 1440) % 1440
            return f"{total // 60:02d}:{total % 60:02d}"
    except ValueError:
        pass
    return s  # już tekst typu '14:30' lub '14:30:00' (backend przeliczy oba)


@app.post("/api/imprezy/ingest")
def imprezy_ingest(payload: dict, start: date = Query(...), end: date = Query(...), db: Session = Depends(get_db)):
    """Przyjmuje listę sparsowanych imprez, upsertuje (klucz = nazwa pliku lub data|klient),
    a na końcu przelicza automatyczne wymagania dla [start, end] — jak skan NAS."""
    lista = payload.get("imprezy", []) if isinstance(payload, dict) else []
    dodano = zaktualizowano = bledy = 0
    for it in lista:
        try:
            data_imp = date.fromisoformat(str(it["data"])[:10])
            klient = (it.get("klient") or "").strip()
            godz = _normalizuj_godzine(it.get("godzina"))
            sala = str(it["sala"]).strip() if it.get("sala") not in (None, "") else "Brak"
            osob = int(it.get("liczba_osob") or 0)
            klucz = (it.get("nazwa_pliku") or f"{data_imp}|{klient}").strip()
        except (KeyError, ValueError, TypeError):
            bledy += 1
            continue

        existing = db.query(models.Impreza).filter(models.Impreza.sciezka_pliku == klucz).first()
        if existing:
            zmiana = (
                existing.liczba_osob != osob or existing.godzina != godz or existing.sala != sala
                or existing.klient != klient or existing.data != data_imp
            )
            if zmiana:
                existing.liczba_osob, existing.godzina, existing.sala = osob, godz, sala
                existing.klient, existing.data = klient, data_imp
                zaktualizowano += 1
        else:
            db.add(models.Impreza(
                data=data_imp, klient=klient, liczba_osob=osob,
                godzina=godz, sala=sala, sciezka_pliku=klucz,
            ))
            dodano += 1
    db.commit()

    # Auto-wymagania pod imprezy (świeże z aktualnej tabeli imprez).
    _odswiez_wymagania_imprez(db, start, end)

    return {"dodano": dodano, "zaktualizowano": zaktualizowano, "bledy": bledy,
            "ostrzezenie": _imprezy_wymagania_warning(db)}


# ═══════════════════════════════════════════════════════════════════════════
# IMPREZY — IMPORT Z PLIKU .ics (eksport z iCloud / Apple Calendar)
#   Admin wgrywa plik .ics; backend tworzy z każdego wydarzenia Termin (kalendarz imprez)
#   ORAZ Imprezę (źródło obsady). „iCloud tylko dodaje" — istniejące (po UID) pomijamy.
#   Godzina z kalendarza jest NIEISTOTNA (impreza dostaje 'Brak'); obsada liczy się z osób.
# ═══════════════════════════════════════════════════════════════════════════
@app.post("/api/imprezy/import-ics")
def import_imprez_ics(payload: dict, db: Session = Depends(get_db)):
    """Import imprez z .ics. Body: {"ics": "<zawartość pliku>"}. Admin-only (middleware).
    Dla każdego VEVENT (jeśli jeszcze nie ma — dedup po UID):
      • Termin  — wpis w kalendarzu imprez (zadatki KP dopną się po nazwisku+dacie),
      • Imprezę — źródło wymagań obsady (godzina='Brak').
    Istniejące (po UID) POMIJAMY — ręcznych zmian w aplikacji nie nadpisujemy."""
    tekst = (payload or {}).get("ics") or ""
    if not isinstance(tekst, str) or not tekst.strip():
        raise HTTPException(400, "Pusty albo nieprawidłowy plik .ics.")

    rekordy = ical_import.wczytaj_imprezy_z_ics(tekst)
    dodano_terminy = dodano_imprezy = pominieto = bez_daty = bez_uid = bez_osob = 0
    daty = []

    for r in rekordy:
        uid = (r.get("uid") or "").strip()
        d = r.get("data")
        if not d:
            bez_daty += 1
            continue
        if not uid:
            bez_uid += 1   # bez UID nie ma jak bezpiecznie deduplikować — pomijamy
            continue
        daty.append(d)
        nazwa = (r.get("nazwisko") or "").strip() or "(bez nazwy)"
        liczba = r.get("liczba_osob")
        if not liczba:
            bez_osob += 1

        # --- Termin (kalendarz imprez) ---
        ist_t = db.query(models.Termin).filter(models.Termin.ical_uid == uid).first()
        if ist_t is None:
            db.add(models.Termin(
                data=d, nazwisko=nazwa, typ=r.get("typ"),
                liczba_osob=liczba, telefon=r.get("telefon"), sala=r.get("sala"),
                notatka=r.get("notatka"), status="rezerwacja",
                zadatek=float(r.get("zadatek") or 0), ical_uid=uid,
                utworzono_at=utcnow_naive(),
            ))
            dodano_terminy += 1
        else:
            pominieto += 1

        # --- Impreza (źródło obsady; godzina nieistotna -> 'Brak') ---
        klucz = f"ical:{uid}"
        ist_i = db.query(models.Impreza).filter(models.Impreza.sciezka_pliku == klucz).first()
        if ist_i is None:
            db.add(models.Impreza(
                data=d, klient=nazwa, liczba_osob=(liczba or 0),
                godzina="Brak", sala=(r.get("sala") or "Brak"), sciezka_pliku=klucz,
            ))
            dodano_imprezy += 1

    db.commit()

    # Świeże wymagania obsady dla zakresu importu + próba dopięcia zadatków ze skrzynki
    # (nowo dodane terminy mogą pasować do wcześniej nieprzypisanych KP).
    if daty:
        _odswiez_wymagania_imprez(db, min(daty), max(daty))
    for z in db.query(models.KpZadatek).filter(models.KpZadatek.termin_id.is_(None)).all():
        _dopasuj_zadatek(db, z)
    db.commit()

    ostrzezenia = []
    w = _imprezy_wymagania_warning(db)
    if w:
        ostrzezenia.append(w)
    if bez_osob:
        ostrzezenia.append(f"{bez_osob} imprez bez liczby osób — dla nich obsada nie zostanie policzona (uzupełnij liczbę osób w kalendarzu).")
    if bez_daty:
        ostrzezenia.append(f"{bez_daty} wydarzeń bez poprawnej daty — pominięto.")
    if bez_uid:
        ostrzezenia.append(f"{bez_uid} wydarzeń bez UID — pominięto (brak klucza do deduplikacji).")

    return {
        "dodano_terminy": dodano_terminy,
        "dodano_imprezy": dodano_imprezy,
        "pominieto": pominieto,
        "bez_daty": bez_daty,
        "ostrzezenia": ostrzezenia,
    }


# ═══════════════════════════════════════════════════════════════════════════
# RCP — ODBICIA (przyjmowane od lokalnego agenta) + GODZINY/STANOWISKO
#   VPS nie łączy się z bazą RCP/Gastro. Lokalny agent (na serwerze Gastro) czyta
#   odbicia read-only (NOLOCK) i WYPYCHA je tutaj. Autoryzacja: stały token X-RCP-Token.
# ═══════════════════════════════════════════════════════════════════════════
import unicodedata

RCP_INGEST_TOKEN = os.environ.get("RCP_INGEST_TOKEN", "")

# Push wysylamy tylko dla SWIEZYCH zdarzen (wejscie/wyjscie w ostatnich N minutach),
# zeby pierwszy ingest / restart agenta nie zasypal pracownikow powiadomieniami o starych
# zmianach. Dane i tak zapisujemy zawsze — bramka dotyczy WYLACZNIE powiadomien.
RCP_POWIADOM_OKNO = timedelta(minutes=int(os.environ.get("RCP_POWIADOM_OKNO_MIN", "60")))


def _teraz_lokalnie():
    """Czas sciany zegarowej w strefie RCP (Europe/Warsaw) jako naive datetime — timestampy
    z RCP sa lokalne i naive. Gdy strefa niedostepna -> None (wtedy NIE blokujemy powiadomien)."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Warsaw")).replace(tzinfo=None)
    except Exception:
        return None


# Litery 'ł/Ł' (i kilka innych) NIE rozkładają się przez NFKD — mapujemy je ręcznie,
# inaczej wypadłyby z dopasowania imion (np. „Łukasz" → „ukasz").
_PL_SPEC = str.maketrans({"ł": "l", "Ł": "L", "ø": "o", "Ø": "O", "đ": "d", "Đ": "D"})


def _norm_nazwa(s: str) -> str:
    s = (s or "").translate(_PL_SPEC)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


def _przypisz_odbicia_do_pracownika(db, prac) -> int:
    """Po dodaniu/edycji pracownika podlinkuj wczesniej NIEDOPASOWANE odbicia RCP
    (pracownik_id IS NULL), ktorych znormalizowane imie+nazwisko pasuje do tego pracownika.
    Dzieki temu godziny z RCP trafiaja na konto od razu, bez czekania na okno agenta
    (agent dosyla tylko ostatnie OKNO_DNI dni). Zwraca liczbe podlinkowanych odbic."""
    cele = {
        _norm_nazwa(f"{prac.imie} {prac.nazwisko}"),
        _norm_nazwa(f"{prac.nazwisko} {prac.imie}"),
    }
    cele.discard("")
    if not cele:
        return 0
    n = 0
    for o in db.query(models.OdbicieRcp).filter(models.OdbicieRcp.pracownik_id.is_(None)).all():
        if _norm_nazwa(o.imie_nazwisko or "") in cele:
            o.pracownik_id = prac.id
            n += 1
    if n:
        db.commit()
    return n


def _parse_dt(v):
    if not v:
        return None
    if isinstance(v, datetime):
        return v
    s = str(v)
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
    return None


@app.post("/api/rcp/ingest")
def rcp_ingest(payload: dict, request: Request, db: Session = Depends(get_db)):
    """Przyjmuje paczkę odbić od lokalnego agenta i robi upsert po `rcp_id`.
    Wykrywa wejście (push „start zmiany") i wyjście (push „koniec zmiany" + godziny).
    Idempotentne — flagi powiadomień zapobiegają dublom."""
    if not RCP_INGEST_TOKEN or request.headers.get("x-rcp-token") != RCP_INGEST_TOKEN:
        raise HTTPException(401, "Nieprawidłowy lub brakujący token agenta RCP.")

    odbicia = payload.get("odbicia", []) if isinstance(payload, dict) else []
    mapa = {}
    for p in db.query(models.Pracownik).all():
        mapa.setdefault(_norm_nazwa(f"{p.imie} {p.nazwisko}"), p.id)
        mapa.setdefault(_norm_nazwa(f"{p.nazwisko} {p.imie}"), p.id)

    nowe = zakonczone = powiadomienia = 0
    teraz = _teraz_lokalnie()  # do bramki swiezosci powiadomien
    for o in odbicia:
        try:
            rcp_id = str(o["rcp_id"])
            nazwa = (o.get("imie_nazwisko") or "").strip()
            d = date.fromisoformat(str(o["data"])[:10])
        except (KeyError, ValueError, TypeError):
            continue
        wejscie = _parse_dt(o.get("wejscie"))
        wyjscie = _parse_dt(o.get("wyjscie"))
        pid = mapa.get(_norm_nazwa(nazwa))

        rec = db.query(models.OdbicieRcp).filter_by(rcp_id=rcp_id).first()
        if rec is None:
            rec = models.OdbicieRcp(
                rcp_id=rcp_id, imie_nazwisko=nazwa, pracownik_id=pid, data=d,
                wejscie=wejscie, wyjscie=wyjscie,
            )
            db.add(rec)
            nowe += 1
        else:
            if nazwa:
                rec.imie_nazwisko = nazwa
            if pid is not None:
                rec.pracownik_id = pid
            if wejscie:
                rec.wejscie = wejscie
            if wyjscie:
                rec.wyjscie = wyjscie
        if rec.wejscie and rec.wyjscie:
            rec.godziny = round((rec.wyjscie - rec.wejscie).total_seconds() / 3600.0, 2)
        rec.zaktualizowano_at = utcnow_naive()
        db.flush()

        if rec.wejscie and rec.pracownik_id and not rec.powiadomiono_wejscie:
            if teraz is None or rec.wejscie >= teraz - RCP_POWIADOM_OKNO:
                powiadomienia += wyslij_push_do_pracownika(
                    db, rec.pracownik_id, "Rozpoczęto zmianę",
                    f"Odbicie o {rec.wejscie.strftime('%H:%M')} — miłej pracy!", url="/",
                )
            rec.powiadomiono_wejscie = True  # zaznaczamy obsluzone (stare = bez spamu)
        if rec.wyjscie and rec.pracownik_id and not rec.powiadomiono_wyjscie:
            if teraz is None or rec.wyjscie >= teraz - RCP_POWIADOM_OKNO:
                powiadomienia += wyslij_push_do_pracownika(
                    db, rec.pracownik_id, "Zakończono zmianę",
                    f"Przepracowano {rec.godziny:.2f} h — dopisano do konta.", url="/",
                )
            rec.powiadomiono_wyjscie = True
            zakonczone += 1

    db.commit()
    return {"przyjeto": len(odbicia), "nowe": nowe, "zakonczone": zakonczone, "powiadomienia": powiadomienia}


@app.get("/api/me/godziny", status_code=200)
def moje_godziny(
    rok: int = Query(...), miesiac: int = Query(...),
    user: models.User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Miesięczne podsumowanie przepracowanych godzin zalogowanego pracownika
    z podziałem na stanowiska (z opublikowanego grafiku)."""
    if not user.pracownik_id:
        raise HTTPException(400, "Konto nie jest powiązane z pracownikiem.")
    raport = raporty.raport_godzin_miesiac(db, rok, miesiac, tylko_pracownik_id=user.pracownik_id)
    moj = next((p for p in raport["pracownicy"] if p["pracownik_id"] == user.pracownik_id), None)

    # Trwajaca (niezakonczona) zmiana: wejscie jest, wyjscia brak. Pokazujemy tylko swieza
    # (rozpoczeta w ostatnich ~18h), zeby nie wyswietlac zapomnianych odbic sprzed dni.
    aktywna_out = None
    aktywna = (
        db.query(models.OdbicieRcp)
        .filter(
            models.OdbicieRcp.pracownik_id == user.pracownik_id,
            models.OdbicieRcp.wyjscie.is_(None),
            models.OdbicieRcp.wejscie.isnot(None),
        )
        .order_by(models.OdbicieRcp.wejscie.desc())
        .first()
    )
    if aktywna:
        teraz = _teraz_lokalnie()
        if teraz is None or aktywna.wejscie >= teraz - timedelta(hours=18):
            aktywna_out = {"data": aktywna.data.isoformat(), "wejscie": aktywna.wejscie.isoformat()}

    # Podzial na DNI: ile godzin pracownik przepracowal kazdego dnia (zakonczone zmiany),
    # PRZYCIETE do grafiku tak jak w raporcie (od zaplanowanej godziny), by suma dni == suma_godzin.
    from calendar import monthrange
    start = date(rok, miesiac, 1)
    end = date(rok, miesiac, monthrange(rok, miesiac)[1])
    zakresy_pub = raporty._zakresy_publikacji(db)
    przydz = defaultdict(list)
    for a in db.query(models.PrzydzialZmiany).filter(
        models.PrzydzialZmiany.pracownik_id == user.pracownik_id,
        models.PrzydzialZmiany.data >= start,
        models.PrzydzialZmiany.data <= end,
    ).all():
        przydz[a.data].append(a)
    per_dzien = {}
    for o in db.query(models.OdbicieRcp).filter(
        models.OdbicieRcp.pracownik_id == user.pracownik_id,
        models.OdbicieRcp.data >= start,
        models.OdbicieRcp.data <= end,
        models.OdbicieRcp.wyjscie.isnot(None),
    ).all():
        h = float(o.godziny or 0.0)
        przy = przydz.get(o.data, [])
        if przy and raporty._opublikowany(o.data, zakresy_pub):
            wt = o.wejscie.time() if o.wejscie else None
            wybrany = raporty._wybierz_przydzial(przy, wt)
            h, _ = raporty.efektywne_i_oszczednosc(wt, wybrany.godz_od, h)
        per_dzien[o.data] = per_dzien.get(o.data, 0.0) + h
    dni_out = [{"data": d.isoformat(), "godziny": round(g, 2)} for d, g in sorted(per_dzien.items())]

    return {
        "rok": rok, "miesiac": miesiac,
        "suma_godzin": moj["suma_godzin"] if moj else 0.0,
        "stanowiska": moj["stanowiska"] if moj else [],
        "do_wyplaty": moj["do_wyplaty"] if moj else 0.0,
        "dni": dni_out,
        "aktywna_zmiana": aktywna_out,
    }


def _trwajace_zmiany(db):
    """Pracownicy aktualnie NA ZMIANIE: wejscie jest, wyjscia brak, rozpoczete w ~18h.
    Dopasowani -> imie+nazwisko z konta; niedopasowani -> nazwa z RCP."""
    teraz = _teraz_lokalnie()
    prac = {p.id: f"{p.imie} {p.nazwisko}" for p in db.query(models.Pracownik).all()}
    out = []
    for o in (
        db.query(models.OdbicieRcp)
        .filter(models.OdbicieRcp.wyjscie.is_(None), models.OdbicieRcp.wejscie.isnot(None))
        .order_by(models.OdbicieRcp.wejscie.desc())
        .all()
    ):
        if teraz is not None and o.wejscie < teraz - timedelta(hours=18):
            continue
        out.append({
            "pracownik_id": o.pracownik_id,
            "pracownik": prac.get(o.pracownik_id) or o.imie_nazwisko,
            "wejscie": o.wejscie.isoformat(),
            "dopasowany": o.pracownik_id is not None,
        })
    return out


@app.get("/api/raporty/godziny", status_code=200)
def raport_godzin(request: Request, rok: int = Query(...), miesiac: int = Query(...),
                  user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Raport godzin wszystkich pracowników (admin + szef — wymusza middleware).
    Dorzuca `na_zmianie` (kto teraz na zmianie) oraz cięcia godzin (duze/male) — widzą je
    admin i szef (szef_kuchni ma osobny endpoint /api/szefkuchni/godziny, bez cięć).
    Dostęp do danych płacowych jest zapisywany w dzienniku audytu (RODO)."""
    raport = raporty.raport_godzin_miesiac(db, rok, miesiac)
    raport["na_zmianie"] = _trwajace_zmiany(db)
    zapisz_audyt(db, user, "raport_godzin", zasob=f"{rok}-{miesiac:02d}", request=request)
    return raport


def _kuchnia_pids(db):
    """Id pracowników KUCHNI — po DZIALE (tak jak grafik kuchni), niezależnie od roli konta.
    Dzięki temu kucharz dział=kuchnia z kontem 'employee' też jest widziany przez szefa kuchni."""
    return {p.id for p in db.query(models.Pracownik).filter(models.Pracownik.dzial == "kuchnia").all()}


@app.get("/api/szefkuchni/godziny", status_code=200)
def raport_godzin_kuchnia(rok: int = Query(...), miesiac: int = Query(...), db: Session = Depends(get_db)):
    """Godziny pracowników KUCHNI (dział „kuchnia") — BEZ kwot wypłaty. Dla szefa kuchni.
    Zwraca te same godziny/stanowiska co raport admina, ale OBCINA pola finansowe
    (stawka/kwota/do_wyplaty). Dorzuca `na_zmianie`: kto z kuchni jest teraz na zmianie (live)."""
    kuchnia_pids = _kuchnia_pids(db)
    raport = raporty.raport_godzin_miesiac(db, rok, miesiac)
    pracownicy = [
        {
            "pracownik_id": p["pracownik_id"],
            "pracownik": p["pracownik"],
            "suma_godzin": p["suma_godzin"],
            # tylko stanowisko + godziny — bez stawki i kwoty
            "stanowiska": [{"stanowisko": s["stanowisko"], "godziny": s["godziny"]} for s in p["stanowiska"]],
        }
        for p in raport["pracownicy"]
        if p["pracownik_id"] in kuchnia_pids
    ]
    na_zmianie = [z for z in _trwajace_zmiany(db) if z.get("pracownik_id") in kuchnia_pids]
    return {"rok": rok, "miesiac": miesiac, "pracownicy": pracownicy, "na_zmianie": na_zmianie}


# --- Szef kuchni: KOREKTY grafiku kuchni (tylko pracownicy działu kuchnia) ---
# Grafik publikuje admin, ale szef kuchni może na bieżąco poprawiać zmiany kuchni.
# Każda zmiana jest natychmiast widoczna kucharzowi (grafik kuchni jest „żywy") i wysyła push.

def _kuchnia_pracownik_lub_403(db, pracownik_id):
    p = db.get(models.Pracownik, pracownik_id)
    if not p:
        raise HTTPException(404, "Nie znaleziono pracownika.")
    if p.dzial != "kuchnia":
        raise HTTPException(403, "Szef kuchni może edytować tylko pracowników kuchni.")
    return p


@app.post("/api/szefkuchni/przydzialy", response_model=schemas.PrzydzialOut, status_code=201)
def szefkuchni_dodaj_przydzial(data: schemas.PrzydzialCreate,
                               user: models.User = Depends(get_current_user),
                               db: Session = Depends(get_db)):
    """Szef kuchni dodaje zmianę pracownikowi kuchni (stanowisko zawsze = Kuchnia)."""
    _kuchnia_pracownik_lub_403(db, data.pracownik_id)
    a = models.PrzydzialZmiany(
        data=data.data, stanowisko_id=_kuchnia_stanowisko(db).id, pracownik_id=data.pracownik_id,
        godz_od=data.godz_od, rewir=data.rewir, zamyka=data.zamyka,
    )
    db.add(a); db.commit(); db.refresh(a)
    _powiadom_kuchnie_o_zmianie(db, a.pracownik_id, "Nowa zmiana w grafiku", "Dodano Ci zmianę w grafiku kuchni.")
    return a


@app.put("/api/szefkuchni/przydzialy/{aid}", response_model=schemas.PrzydzialOut)
def szefkuchni_edytuj_przydzial(aid: int, data: schemas.PrzydzialCreate,
                                user: models.User = Depends(get_current_user),
                                db: Session = Depends(get_db)):
    """Szef kuchni zmienia istniejącą zmianę kuchni (godzina / rewir / kto zamyka)."""
    a = db.get(models.PrzydzialZmiany, aid)
    if not a:
        raise HTTPException(404, "Nie znaleziono.")
    _kuchnia_pracownik_lub_403(db, a.pracownik_id)
    a.godz_od = data.godz_od
    a.rewir = data.rewir
    a.zamyka = data.zamyka
    db.commit(); db.refresh(a)
    _powiadom_kuchnie_o_zmianie(db, a.pracownik_id, "Zmiana w grafiku", "Zaktualizowano Twoją zmianę w grafiku kuchni.")
    return a


@app.delete("/api/szefkuchni/przydzialy/{aid}", status_code=204)
def szefkuchni_usun_przydzial(aid: int,
                              user: models.User = Depends(get_current_user),
                              db: Session = Depends(get_db)):
    """Szef kuchni wykreśla kucharza ze zmiany."""
    a = db.get(models.PrzydzialZmiany, aid)
    if not a:
        raise HTTPException(404, "Nie znaleziono.")
    pid = a.pracownik_id
    _kuchnia_pracownik_lub_403(db, pid)
    db.delete(a); db.commit()
    _powiadom_kuchnie_o_zmianie(db, pid, "Zmiana w grafiku", "Wykreślono Cię ze zmiany w grafiku kuchni.")


@app.get("/api/szefkuchni/grafik", status_code=200)
def szefkuchni_grafik(start: date = Query(...), end: date = Query(...),
                      user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Dane edytowalnego grafiku kuchni dla szefa kuchni: pracownicy kuchni + ich przydziały."""
    kucharze = (db.query(models.Pracownik)
                .filter(models.Pracownik.dzial == "kuchnia")
                .order_by(models.Pracownik.kolejnosc, models.Pracownik.id).all())
    pracownicy = [{"id": p.id, "imie": p.imie, "nazwisko": p.nazwisko,
                   "kolor": p.kolor, "aktywny": bool(p.aktywny)} for p in kucharze]
    kuchnia_pids = [p.id for p in kucharze]
    przydzialy = []
    if kuchnia_pids:
        rows = (db.query(models.PrzydzialZmiany)
                .filter(models.PrzydzialZmiany.data >= start, models.PrzydzialZmiany.data <= end,
                        models.PrzydzialZmiany.pracownik_id.in_(kuchnia_pids)).all())
        przydzialy = [{"id": a.id, "data": str(a.data), "pracownik_id": a.pracownik_id,
                       "godz_od": a.godz_od.strftime("%H:%M") if a.godz_od else None,
                       "rewir": a.rewir, "zamyka": bool(a.zamyka)} for a in rows]
    # Kto z kuchni jest teraz na zmianie (live) — szef kuchni widzi to na głównej zakładce „Grafik".
    na_zmianie = [z for z in _trwajace_zmiany(db) if z.get("pracownik_id") in set(kuchnia_pids)]
    return {"pracownicy": pracownicy, "przydzialy": przydzialy, "na_zmianie": na_zmianie}


# ═══════════════════════════════════════════════════════════════════════════
# STOŁY (live z Gastro) — osobna, addytywna ścieżka. NIE dotyka RCP/godzin.
# Mapowanie rewirów (NGastroUzytkownik.Numer) na widok:
STOLY_WEWNATRZ = [(42, "Parter"), (52, "Góra"), (56, "Zielona"), (57, "Kryształowa")]
STOLY_ZEWNATRZ = [54, 55, 53, 108]   # TARAS, STRZECHA, ABCD+FLINSTONY, Zetka+Ka → suma
STOLY_WYNOS = 46
STOLY_KUCHNIA = -1          # pseudo-rewir: zamówienia „do wydania" na kuchni (firingi KDS, kierunek Kuchnia)
STOLY_KUCHNIA_POZYCJE = -2  # pseudo-rewir: liczba pozycji (dań) na tych niewydanych bloczkach


@app.post("/api/gastro/stoly")
def gastro_stoly_ingest(payload: dict, request: Request, db: Session = Depends(get_db)):
    """Snapshot zajętości stołów od agenta (X-RCP-Token). Upsert per rewir. NIE dotyka RCP."""
    if not RCP_INGEST_TOKEN or request.headers.get("x-rcp-token") != RCP_INGEST_TOKEN:
        raise HTTPException(401, "Nieprawidłowy lub brakujący token agenta.")
    teraz = utcnow_naive()
    for it in (payload.get("stoly") or []):
        try:
            nr = int(it["rewir_nr"])
            ile = int(it.get("otwarte") or 0)
        except (KeyError, ValueError, TypeError):
            continue
        rec = db.get(models.StanStolow, nr)
        if rec is None:
            db.add(models.StanStolow(rewir_nr=nr, otwarte=ile, zaktualizowano_at=teraz))
        else:
            rec.otwarte = ile
            rec.zaktualizowano_at = teraz
    db.commit()
    return {"ok": True}


@app.get("/api/gastro/stoly")
def gastro_stoly(db: Session = Depends(get_db)):
    """Aktualny stan stołów (admin + szef): wewnątrz (sale osobno) + na zewnątrz (suma) + wynos."""
    stan = {s.rewir_nr: s.otwarte for s in db.query(models.StanStolow).all()}
    last = db.query(models.StanStolow).order_by(models.StanStolow.zaktualizowano_at.desc()).first()
    wewnatrz = [{"nazwa": nazwa, "liczba": stan.get(nr, 0)} for nr, nazwa in STOLY_WEWNATRZ]
    return {
        "wewnatrz": wewnatrz,
        "wewnatrz_suma": sum(w["liczba"] for w in wewnatrz),
        "na_zewnatrz": sum(stan.get(nr, 0) for nr in STOLY_ZEWNATRZ),
        "wynos": stan.get(STOLY_WYNOS, 0),
        "kuchnia": stan.get(STOLY_KUCHNIA, 0),
        "kuchnia_pozycje": stan.get(STOLY_KUCHNIA_POZYCJE, 0),
        # Znacznik UTC (zapis przez utcnow_naive()) — z offsetem, żeby przeglądarka
        # przeliczyła na czas lokalny (bez tego pokazywało −2h: UTC czytane jako lokalny).
        "zaktualizowano_at": (last.zaktualizowano_at.replace(tzinfo=timezone.utc).isoformat()
                              if last and last.zaktualizowano_at else None),
    }


@app.post("/api/gastro/stoly-historia")
def gastro_stoly_historia_ingest(payload: dict, request: Request, db: Session = Depends(get_db)):
    """Dzienna historia liczby stolików od agenta (X-RCP-Token). Upsert per dzień. NIE dotyka RCP."""
    if not RCP_INGEST_TOKEN or request.headers.get("x-rcp-token") != RCP_INGEST_TOKEN:
        raise HTTPException(401, "Nieprawidłowy lub brakujący token agenta.")
    teraz = utcnow_naive()
    for it in (payload.get("dni") or []):
        try:
            d = date.fromisoformat(str(it["data"])[:10])
            ile = int(it.get("liczba") or 0)
        except (KeyError, ValueError, TypeError):
            continue
        rec = db.get(models.StolikiHistoria, d)
        if rec is None:
            db.add(models.StolikiHistoria(data=d, liczba=ile, zaktualizowano_at=teraz))
        else:
            rec.liczba = ile
            rec.zaktualizowano_at = teraz
    db.commit()
    return {"ok": True}


@app.get("/api/gastro/stoly-historia")
def gastro_stoly_historia(db: Session = Depends(get_db)):
    """Historia liczby obsłużonych stolików na dzień (admin + szef) — ostatnie 30 dni."""
    od = date.today() - timedelta(days=30)
    rows = (
        db.query(models.StolikiHistoria)
        .filter(models.StolikiHistoria.data >= od)
        .order_by(models.StolikiHistoria.data.asc())
        .all()
    )
    return {"dni": [{"data": r.data.isoformat(), "liczba": r.liczba} for r in rows]}


@app.post("/api/gastro/rozliczenia")
def gastro_rozliczenia_ingest(payload: dict, request: Request, db: Session = Depends(get_db)):
    """Pozycje rozliczeń kelnerów z Gastro od agenta (X-RCP-Token). Upsert po poz_id,
    mapowanie kelnera po imieniu i nazwisku (jak RCP). NIE dotyka RCP — osobna gałąź."""
    if not RCP_INGEST_TOKEN or request.headers.get("x-rcp-token") != RCP_INGEST_TOKEN:
        raise HTTPException(401, "Nieprawidłowy lub brakujący token agenta.")
    mapa = {}
    for p in db.query(models.Pracownik).all():
        mapa.setdefault(_norm_nazwa(f"{p.imie} {p.nazwisko}"), p.id)
        mapa.setdefault(_norm_nazwa(f"{p.nazwisko} {p.imie}"), p.id)
    teraz = utcnow_naive()
    n = 0
    dni_batch = set()
    for it in (payload.get("pozycje") or []):
        try:
            poz_id = str(it["poz_id"])
            roz_id = str(it["rozliczenie_id"])
            d = date.fromisoformat(str(it["data"])[:10])
        except (KeyError, ValueError, TypeError):
            continue
        dni_batch.add(d)
        nazwa = (it.get("imie_nazwisko") or "").strip()
        try:
            zamkniete = bool(int(it.get("zamkniete") or 0))
        except (ValueError, TypeError):
            zamkniete = bool(it.get("zamkniete"))
        rec = db.get(models.RozliczenieGastro, poz_id)
        if rec is None:
            rec = models.RozliczenieGastro(poz_id=poz_id)
            db.add(rec)
        rec.rozliczenie_id = roz_id
        if nazwa:
            rec.imie_nazwisko = nazwa
        pid = mapa.get(_norm_nazwa(nazwa))
        if pid is not None:
            rec.pracownik_id = pid
        rec.data = d
        rec.zamknieto = _parse_dt(it.get("zamknieto"))
        rec.zamkniete = zamkniete
        rec.forma = (it.get("forma") or "").strip()
        rec.sprzedaz = float(it.get("sprzedaz") or 0)
        rec.deklarowane = float(it.get("deklarowane") or 0)
        rec.zaktualizowano_at = teraz
        n += 1
    db.commit()
    # Push „raport oczekuje" do kelnerów sali z ZAMKNIĘTYM rozliczeniem Gastro (wpisane w komputer)
    # — raz na kelnera/dzień (push_oczekuje_at). Po przesłaniu raportu (potwierdzone) przycisk znika.
    for d in dni_batch:
        if ROZLICZENIA_START and d < ROZLICZENIA_START:
            continue   # nie powiadamiaj o zmianach sprzed startu systemu (zaległe)
        try:
            roz = _zbuduj_rozliczenie(db, d)
        except Exception:
            continue
        for k in roz.kelnerzy:
            if k.potwierdzone or k.push_oczekuje_at is not None:
                continue
            zamk = (db.query(models.RozliczenieGastro)
                    .filter_by(pracownik_id=k.pracownik_id, data=d, zamkniete=True).first())
            if zamk:
                wyslij_push_do_pracownika(db, k.pracownik_id, "Rozliczenie zmiany",
                                          "Twój raport oczekuje na przesłanie", url="/")
                k.push_oczekuje_at = teraz
        db.commit()
    return {"ok": True, "pozycje": n}


_RE_NAZW = re.compile(r"\bp\.?\s*([A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+)")
_RE_DATA = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})|(\d{4})\.(\d{1,2})\.(\d{1,2})")


def _parsuj_zadatek(opis):
    """Z opisu KP wyciąga nazwisko (słowo po „p.") i datę imprezy (DD.MM.RRRR lub RRRR.MM.DD)."""
    if not opis:
        return None, None
    mn = _RE_NAZW.search(opis)
    nazwisko = mn.group(1) if mn else None
    data_imp = None
    for m in _RE_DATA.finditer(opis):
        try:
            if m.group(3):
                d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            else:
                y, mo, d = int(m.group(4)), int(m.group(5)), int(m.group(6))
            data_imp = date(y, mo, d)
            break
        except (ValueError, TypeError):
            continue
    return nazwisko, data_imp


def _dopasuj_zadatek(db, z) -> bool:
    """Auto-dopasowanie: termin z tą datą imprezy + nazwiskiem (zawiera). Tylko gdy DOKŁADNIE 1 trafienie."""
    if z.termin_id or not z.nazwisko or not z.data_imprezy:
        return False
    naz = z.nazwisko.lower()
    kand = [t for t in db.query(models.Termin).filter(models.Termin.data == z.data_imprezy).all()
            if naz in (t.nazwisko or "").lower()]
    if len(kand) == 1:
        z.termin_id = kand[0].id
        return True
    return False


@app.post("/api/gastro/zadatki")
def gastro_zadatki_ingest(payload: dict, request: Request, db: Session = Depends(get_db)):
    """Zadatki (KP „Kasa przyjęła") z Gastro od agenta (X-RCP-Token). Upsert po id. Parsuje opis
    (nazwisko + data imprezy) i próbuje auto-dopasować do terminu w kalendarzu."""
    if not RCP_INGEST_TOKEN or request.headers.get("x-rcp-token") != RCP_INGEST_TOKEN:
        raise HTTPException(401, "Nieprawidłowy lub brakujący token agenta.")
    teraz = utcnow_naive()
    n = 0
    for it in (payload.get("zadatki") or []):
        try:
            zid = str(it["id"])
            d = date.fromisoformat(str(it["data"])[:10])
        except (KeyError, ValueError, TypeError):
            continue
        rec = db.get(models.KpZadatek, zid)
        if rec is None:
            rec = models.KpZadatek(id=zid); db.add(rec)
        rec.numer = (it.get("numer") or None)
        rec.kwota = float(it.get("kwota") or 0)
        rec.opis = (it.get("opis") or None)
        rec.data = d
        rec.nazwisko, rec.data_imprezy = _parsuj_zadatek(rec.opis)
        rec.zaktualizowano_at = teraz
        n += 1
    db.commit()
    for z in db.query(models.KpZadatek).filter(models.KpZadatek.termin_id.is_(None)).all():
        _dopasuj_zadatek(db, z)
    db.commit()
    return {"ok": True, "zadatki": n}


def _zadatek_out(db, z) -> dict:
    t = db.get(models.Termin, z.termin_id) if z.termin_id else None
    return {"id": z.id, "numer": z.numer, "kwota": z.kwota, "opis": z.opis, "data": str(z.data),
            "nazwisko": z.nazwisko, "data_imprezy": str(z.data_imprezy) if z.data_imprezy else None,
            "termin_id": z.termin_id,
            "termin": ({"id": t.id, "nazwisko": t.nazwisko, "data": str(t.data), "typ": t.typ} if t else None)}


@app.get("/api/zadatki")
def get_zadatki(db: Session = Depends(get_db)):
    """Zadatki KP: przypisane do terminów + skrzynka „do przypisania" (niedopasowane)."""
    rows = db.query(models.KpZadatek).order_by(models.KpZadatek.data.desc()).all()
    return {"przypisane": [_zadatek_out(db, z) for z in rows if z.termin_id],
            "do_przypisania": [_zadatek_out(db, z) for z in rows if not z.termin_id]}


@app.post("/api/zadatki/dopasuj")
def dopasuj_zadatki(db: Session = Depends(get_db)):
    n = sum(1 for z in db.query(models.KpZadatek).filter(models.KpZadatek.termin_id.is_(None)).all()
            if _dopasuj_zadatek(db, z))
    db.commit()
    return {"dopasowano": n}


@app.put("/api/zadatki/{zid}/przypisz", status_code=204)
def przypisz_zadatek(zid: str, termin_id: int = Query(...), db: Session = Depends(get_db)):
    z = db.get(models.KpZadatek, zid)
    if not z:
        raise HTTPException(404, "Brak zadatku.")
    if not db.get(models.Termin, termin_id):
        raise HTTPException(404, "Brak terminu.")
    z.termin_id = termin_id; db.commit()


@app.put("/api/zadatki/{zid}/odepnij", status_code=204)
def odepnij_zadatek(zid: str, db: Session = Depends(get_db)):
    z = db.get(models.KpZadatek, zid)
    if z:
        z.termin_id = None; db.commit()


@app.get("/api/gastro/rozliczenia")
def gastro_rozliczenia(start: date = Query(...), end: date = Query(...), db: Session = Depends(get_db)):
    """Podgląd zebranych rozliczeń kelnerów (admin) — zgrupowane per rozliczenie.
    Posłuży jako prefill formularzy rozliczeń dnia (Etap D2). REPREZENTACJA nie wchodzi
    do utargu — front pokaże ją osobno."""
    rows = (
        db.query(models.RozliczenieGastro)
        .filter(models.RozliczenieGastro.data >= start, models.RozliczenieGastro.data <= end)
        .order_by(models.RozliczenieGastro.data.desc(), models.RozliczenieGastro.imie_nazwisko.asc(),
                  models.RozliczenieGastro.forma.asc())
        .all()
    )
    prac_map = {p.id: f"{p.imie} {p.nazwisko}" for p in db.query(models.Pracownik).all()}
    return {"pozycje": [{
        "poz_id": r.poz_id, "rozliczenie_id": r.rozliczenie_id,
        "imie_nazwisko": r.imie_nazwisko, "pracownik_id": r.pracownik_id,
        "pracownik": prac_map.get(r.pracownik_id), "data": str(r.data),
        "zamknieto": r.zamknieto.isoformat() if r.zamknieto else None,
        "zamkniete": bool(r.zamkniete), "forma": r.forma,
        "sprzedaz": r.sprzedaz, "deklarowane": r.deklarowane,
    } for r in rows]}


# ═══════════════════════════════════════════════════════════════════════════
# REZERWACJE (Google Calendar) — odczyt; pracownik widzi tylko sumy dzienne.
@app.get("/api/rezerwacje")
def get_rezerwacje():
    """Admin + szef: rezerwacje na 30 dni — per dzień z rozbiciem per godzina."""
    return {"dni": rezerwacje.rezerwacje_per_dzien(30)}


@app.get("/api/me/rezerwacje")
def moje_rezerwacje(user: models.User = Depends(get_current_user)):
    """Pracownik: TYLKO sumy dzienne (liczba rezerwacji + suma osób), bez godzin i danych klienta."""
    dane = rezerwacje.rezerwacje_per_dzien(30)
    return {"dni": [{"data": d["data"], "liczba": d["liczba"], "osoby": d["osoby"]} for d in dane]}


# ── SERWOWANIE FRONTENDU (zbudowany React z frontend/dist) ─────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIST = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend", "dist"))
if os.path.isdir(FRONTEND_DIST):
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
else:
    # Tryb deweloperski: frontend serwuje Vite (:5173), backend udostępnia tylko /api.
    logger.warning("frontend/dist nie istnieje — pomijam serwowanie frontu. Uruchom 'npm --prefix frontend run build' lub 'npm run dev'.")