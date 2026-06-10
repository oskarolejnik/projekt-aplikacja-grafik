import csv
import io
import re
import os
from datetime import date, time, timedelta, datetime, timezone
from typing import Optional, List
from collections import defaultdict

from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.orm import Session

import models, schemas, raporty, rezerwacje
from database import get_db, init_db, SessionLocal
from algorithm import auto_assign as _auto_assign, przelicz_imprezy_na_wymagania

import jwt
from auth import (
    get_current_user, hash_password, verify_password,
    create_access_token, SECRET_KEY, ALGORITHM,
)
from validators import sprawdz_login, sprawdz_haslo
from push import wyslij_push, wyslij_push_do_pracownika, VAPID_PUBLIC_KEY

import openpyxl

app = FastAPI(title="Scheduler API")

ALLOWED_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")
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
        "/api/rezerwacje",
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
}


# Centralna ochrona API: /api/auth/* publiczne, /api/me/* dla każdego zalogowanego,
# pozostałe /api/* tylko dla administratora (role nadzorcze: wybrane GET — patrz OVERSIGHT_GET).
# Statyczny frontend jest publiczny.
@app.middleware("http")
async def role_guard(request: Request, call_next):
    path = request.url.path
    # /api/rcp/ingest — wyjątek: autoryzacja stałym tokenem agenta (X-RCP-Token), nie JWT.
    if request.method != "OPTIONS" and path.startswith("/api/") and not path.startswith("/api/auth/") and path != "/api/health" and path != "/api/rcp/ingest" and not (path.startswith("/api/gastro/stoly") and request.method == "POST"):
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


def _kuchnia_stanowisko(db) -> models.Stanowisko:
    s = db.query(models.Stanowisko).filter_by(nazwa=KUCHNIA_STANOWISKO).first()
    if not s:
        s = models.Stanowisko(nazwa=KUCHNIA_STANOWISKO)
        db.add(s); db.commit(); db.refresh(s)
    return s


# Stanowisko dla pracowników technicznych — pełne godziny RCP × stawka (bez grafiku). Jak kuchnia.
TECHNICZNY_STANOWISKO = "Techniczny"


def _techniczny_stanowisko(db) -> models.Stanowisko:
    s = db.query(models.Stanowisko).filter_by(nazwa=TECHNICZNY_STANOWISKO).first()
    if not s:
        s = models.Stanowisko(nazwa=TECHNICZNY_STANOWISKO)
        db.add(s); db.commit(); db.refresh(s)
    return s


# „Parkiet": stanowiska, których nazwa zaczyna się od „Sala" (Sala, Sala-ABC, Sala-RZP,
# Sala-Bar...). Spośród nich wybieramy osobę ZAMYKAJĄCĄ lokal — patrz _przelicz_zamykajacego.
SALA_PREFIX = "sala"


def _sala_stanowisko_ids(db) -> set:
    return {s.id for s in db.query(models.Stanowisko).all()
            if (s.nazwa or "").strip().lower().startswith(SALA_PREFIX)}


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
        imie=u.pracownik.imie if u.pracownik else None,
        nazwisko=u.pracownik.nazwisko if u.pracownik else None,
    )

@app.post("/api/auth/login", response_model=schemas.TokenOut)
def login(dane: schemas.LoginIn, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.login == dane.login).first()
    if not user or not user.aktywny or not verify_password(dane.haslo, user.haslo_hash):
        raise HTTPException(401, "Nieprawidłowy login lub hasło.")
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

@app.get("/api/auth/me", response_model=schemas.UserOut)
def auth_me(user: models.User = Depends(get_current_user)):
    return _user_out(user)

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
    # Kuchnia: grafik „żywy" — kucharz widzi swoje zmiany od razu (bez czekania na publikację).
    if not pub and not jest_kuchnia:
        return {"opublikowany": False, "opublikowano_at": None, "zmiany": []}

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
    stan_map = {s.id: s.nazwa for s in db.query(models.Stanowisko).all()}
    prac_map = {p.id: f"{p.imie} {p.nazwisko}" for p in db.query(models.Pracownik).all()}

    zmiany = []
    for a in moje:
        # Współpracownicy = WSZYSCY na tym samym STANOWISKU danego dnia — niezależnie od godziny
        # przyjścia i rewiru. Pracownik widzi, z kim dzieli stanowisko (sortujemy wg godz_od).
        wspol = (
            db.query(models.PrzydzialZmiany)
            .filter(
                models.PrzydzialZmiany.data == a.data,
                models.PrzydzialZmiany.stanowisko_id == a.stanowisko_id,
                models.PrzydzialZmiany.pracownik_id != user.pracownik_id,
            )
            .order_by(models.PrzydzialZmiany.godz_od.asc())
            .all()
        )
        zmiany.append({
            "data": str(a.data),
            "godz_od": a.godz_od.strftime("%H:%M") if a.godz_od else None,
            "stanowisko": stan_map.get(a.stanowisko_id, ""),
            "rewir": _rewir_dla_pracownika(a.rewir),
            "zamyka": bool(a.zamyka),
            "wspolpracownicy": [
                {"imie": prac_map.get(w.pracownik_id, ""),
                 "godz_od": w.godz_od.strftime("%H:%M") if w.godz_od else None,
                 "zamyka": bool(w.zamyka)}
                for w in wspol
            ],
        })
    return {"opublikowany": True, "opublikowano_at": pub.opublikowano_at.isoformat() if pub else None, "zmiany": zmiany}

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
    teraz = datetime.utcnow()
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
    return db.query(models.Stanowisko).all()

@app.post("/api/stanowiska", response_model=schemas.StanowiskoOut, status_code=201)
def create_stanowisko(data: schemas.StanowiskoCreate, db: Session = Depends(get_db)):
    if db.query(models.Stanowisko).filter_by(nazwa=data.nazwa).first():
        raise HTTPException(400, "Stanowisko o tej nazwie już istnieje.")
    s = models.Stanowisko(**data.model_dump())
    db.add(s); db.commit(); db.refresh(s)
    return s

@app.put("/api/stanowiska/{sid}", response_model=schemas.StanowiskoOut)
def update_stanowisko(sid: int, data: schemas.StanowiskoCreate, db: Session = Depends(get_db)):
    s = db.get(models.Stanowisko, sid)
    if not s:
        raise HTTPException(404, "Nie znaleziono.")
    s.nazwa = data.nazwa
    s.tylko_weekend = data.tylko_weekend
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

# Ścieżka do plików imprez. Domyślnie macowy mount NAS; na serwerze ustaw IMPREZY_PATH
# na katalog, do którego lokalny agent wgrywa kopie plików (VPS tylko je odczytuje).
NAS_BASE_PATH = os.environ.get("IMPREZY_PATH", "/Volumes/RAJCULA/MENU - IMPREZY/USTALONE")

@app.get("/api/imprezy", response_model=List[schemas.ImprezaOut])
def get_imprezy(start: date = Query(...), end: date = Query(...), db: Session = Depends(get_db)):
    return db.query(models.Impreza).filter(models.Impreza.data >= start, models.Impreza.data <= end).order_by(models.Impreza.data.asc()).all()


def _imprezy_stanowisko(db):
    """Stanowisko imprez — dopasowanie ELASTYCZNE po nazwie (zaczyna się od „imprez"):
    łapie „Impreza" (l. poj.) i „Imprezy" (l. mn.), bo admin mógł je nazwać dowolnie.
    Zwraca pierwsze pasujące stanowisko albo None."""
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
    nowe = przelicz_imprezy_na_wymagania(imprezy)
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
        rec.zaktualizowano_at = datetime.utcnow()
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
def raport_godzin(rok: int = Query(...), miesiac: int = Query(...), db: Session = Depends(get_db)):
    """Raport godzin wszystkich pracowników (admin + szef — wymusza middleware).
    Dorzuca `na_zmianie` (kto teraz na zmianie) oraz cięcia godzin (duze/male) — widzą je
    admin i szef (szef_kuchni ma osobny endpoint /api/szefkuchni/godziny, bez cięć)."""
    raport = raporty.raport_godzin_miesiac(db, rok, miesiac)
    raport["na_zmianie"] = _trwajace_zmiany(db)
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
    teraz = datetime.utcnow()
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
        # Znacznik UTC (zapis przez datetime.utcnow()) — z offsetem, żeby przeglądarka
        # przeliczyła na czas lokalny (bez tego pokazywało −2h: UTC czytane jako lokalny).
        "zaktualizowano_at": (last.zaktualizowano_at.replace(tzinfo=timezone.utc).isoformat()
                              if last and last.zaktualizowano_at else None),
    }


@app.post("/api/gastro/stoly-historia")
def gastro_stoly_historia_ingest(payload: dict, request: Request, db: Session = Depends(get_db)):
    """Dzienna historia liczby stolików od agenta (X-RCP-Token). Upsert per dzień. NIE dotyka RCP."""
    if not RCP_INGEST_TOKEN or request.headers.get("x-rcp-token") != RCP_INGEST_TOKEN:
        raise HTTPException(401, "Nieprawidłowy lub brakujący token agenta.")
    teraz = datetime.utcnow()
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
    print("UWAGA: frontend/dist nie istnieje — pomijam serwowanie frontu. Uruchom 'npm --prefix frontend run build' lub 'npm run dev'.")