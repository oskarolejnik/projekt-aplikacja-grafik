"""Router: „Moje" — samoobsługa zalogowanego pracownika (dekompozycja main — audyt CTO).

Wszystkie endpointy /api/me/*: uprawnienia UI, dyspozycje i podgląd imprez, własny grafik,
grafik sprzątania (dział techniczny), zamówienia sprzątaczki, wnioski urlopowe, rozliczanie
imprez i dnia (sala), napiwki, subskrypcje web push, godziny z RCP oraz sumy rezerwacji.
role_guard (main) przepuszcza /api/me/* dla KAŻDEGO zalogowanego — bez roli admin.
"""

from collections import defaultdict
from datetime import date, time, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import models
import raporty
import rezerwacje
import schemas
import sprzatanie
import uprawnienia
from auth import get_current_user
from database import get_db
from deps import (
    ROZLICZENIA_START,
    _jest_sprzataczka,
    _napiwki_podzial,
    _sala_stanowisko_ids,
    _teraz_lokalnie,
    _urlop_out,
    _zamowienie_out,
    _zbuduj_rozliczenie,
    utcnow_naive,
)
from deps import rewir_dla_pracownika as _rewir_dla_pracownika, get_lokal_config
from push import VAPID_PUBLIC_KEY, wyslij_push_do_adminow

router = APIRouter()


@router.get("/api/me/uprawnienia")
def me_uprawnienia(user: models.User = Depends(get_current_user)):
    """Granularne uprawnienia zalogowanego użytkownika (RBAC) — do sterowania UI.
    Krytyczny enforcement po stronie API dalej robi middleware role_guard."""
    return {"rola": user.rola, "uprawnienia": uprawnienia.efektywne(user)}


# --- Samoobsługa: dyspozycyjność zalogowanego pracownika ---

@router.get("/api/me/dyspozycje", response_model=List[schemas.DyspozycjaOut])
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

@router.get("/api/me/imprezy")
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

@router.put("/api/me/dyspozycje", status_code=200)
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


@router.get("/api/me/grafik", status_code=200)
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


@router.get("/api/me/sprzatanie")
def moje_sprzatanie(
    start: date = Query(...), end: date = Query(...),
    user: models.User = Depends(get_current_user), db: Session = Depends(get_db),
):
    _wymagaj_technicznego(user, db)
    return {"pozycje": sprzatanie.generuj(db, start, end), "sale": list(sprzatanie.sale_lokalu(db))}


@router.put("/api/me/sprzatanie/zrobione", status_code=204)
def odhacz_sprzatanie(
    dane: schemas.SprzatanieZrobioneIn,
    user: models.User = Depends(get_current_user), db: Session = Depends(get_db),
):
    prac = _wymagaj_technicznego(user, db)
    if dane.sala not in sprzatanie.sale_lokalu(db):
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


# --- ZAMÓWIENIA SPRZĄTACZKI (dział techniczny) ---

ZDJECIE_MAX = 2_000_000   # ~2 MB data URL (front i tak zmniejsza zdjęcie przed wysyłką)


@router.post("/api/me/zamowienia", status_code=201)
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


@router.get("/api/me/zamowienia")
def moje_zamowienia(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    prac = db.get(models.Pracownik, user.pracownik_id) if user.pracownik_id else None
    if not _jest_sprzataczka(prac):
        raise HTTPException(403, "Tylko dla sprzątaczki.")
    rows = (db.query(models.ZamowienieSprzataczki).filter_by(pracownik_id=prac.id)
            .order_by(models.ZamowienieSprzataczki.utworzono_at.desc()).all())
    prac_map = {prac.id: f"{prac.imie} {prac.nazwisko}"}
    return {"zamowienia": [_zamowienie_out(z, prac_map) for z in rows]}


@router.get("/api/me/zamowienia/{zid}/zdjecie")
def moje_zamowienie_zdjecie(zid: int, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    z = db.get(models.ZamowienieSprzataczki, zid)
    if not z or z.pracownik_id != user.pracownik_id:
        raise HTTPException(404, "Nie znaleziono.")
    return {"zdjecie": z.zdjecie}


# --- URLOPY (obsługa) ---

@router.post("/api/me/urlopy", status_code=201)
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


@router.get("/api/me/urlopy")
def moje_urlopy(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.pracownik_id:
        return {"urlopy": []}
    rows = (db.query(models.Urlop).filter_by(pracownik_id=user.pracownik_id)
            .order_by(models.Urlop.start.desc()).all())
    prac = db.get(models.Pracownik, user.pracownik_id)
    prac_map = {prac.id: f"{prac.imie} {prac.nazwisko}"} if prac else {}
    return {"urlopy": [_urlop_out(u, prac_map) for u in rows]}


@router.delete("/api/me/urlopy/{uid}", status_code=204)
def anuluj_urlop(uid: int, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Pracownik wycofuje WŁASNY wniosek — tylko gdy jeszcze oczekuje."""
    u = db.get(models.Urlop, uid)
    if not u or u.pracownik_id != user.pracownik_id:
        raise HTTPException(404, "Nie znaleziono.")
    if u.status != "oczekuje":
        raise HTTPException(400, "Można wycofać tylko wniosek oczekujący.")
    db.delete(u); db.commit()


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


@router.post("/api/me/imprezy/rozlicz", status_code=201)
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


@router.get("/api/me/imprezy/rozlicz")
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


# --- ROZLICZENIE DNIA (sala) — część pracownika ---

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
    # Tryb „pula": obsługa rozlicza się zbiorczo — pracownik nie ma indywidualnego rozliczenia,
    # więc nie pokazujemy mu wezwania „Rozlicz się" (endpoint i tak by je odrzucił).
    if (get_lokal_config(db).rozliczenia_tryb_kelnera or "indywidualnie") == "pula":
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


@router.get("/api/me/rozliczenie")
def moje_rozliczenie(data: date = Query(...), user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Tryb „pula": rozlicza się cała zmiana zbiorczo — pracownik nie ma własnego wiersza.
    if (get_lokal_config(db).rozliczenia_tryb_kelnera or "indywidualnie") == "pula":
        return {"moze": False}
    if not _kelner_sala_dnia(db, user.pracownik_id, data):
        return {"moze": False}
    roz = _zbuduj_rozliczenie(db, data)
    k = next((x for x in roz.kelnerzy if x.pracownik_id == user.pracownik_id), None)
    zamyka, zamyka_rewir, rewir = _kelner_sala_przydzial(db, user.pracownik_id, data)
    # Filtrujemy po SUROWYM rewirze (dopasowanie 1:1 do zapisu), ale w odpowiedzi dla pracownika
    # MASKUJEMY nazwę klienta imprezy — jak w /api/me/grafik (model prywatności).
    term = [{**p, "rewir": _rewir_dla_pracownika(p.get("rewir"))}
            for p in (roz.terminale or []) if (p.get("rewir") or "") == (rewir or "")] if zamyka_rewir else []
    return {"moze": True, "status": _rozlicz_sala_status(db, user.pracownik_id, data),
            "potwierdzone": bool(k and k.potwierdzone),
            "wiersz": ({"gotowka": k.gotowka, "karta": k.karta, "fv": k.fv, "kw": k.kw} if k else None),
            "zamyka": zamyka, "zamyka_rewir": zamyka_rewir, "rewir": _rewir_dla_pracownika(rewir),
            "terminale": term, "kasy": (roz.kasy or []) if zamyka else []}


@router.put("/api/me/rozliczenie", status_code=204)
def zapisz_moje_rozliczenie(dane: schemas.MojRozliczenieIn, data: date = Query(...),
                            user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if (get_lokal_config(db).rozliczenia_tryb_kelnera or "indywidualnie") == "pula":
        raise HTTPException(403, "Lokal rozlicza salę zbiorczo (wspólna pula) — indywidualne rozliczenie wyłączone.")
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


# --- NAPIWKI (udział pracownika) ---

@router.get("/api/me/napiwki")
def moje_napiwki(start: date = Query(...), end: date = Query(...),
                 user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Pracownik: jego udział w napiwkach w zakresie dat (per dzień + suma)."""
    if not user.pracownik_id:
        raise HTTPException(400, "Konto nie jest powiązane z pracownikiem.")
    pid = user.pracownik_id
    dni = []
    for rec in db.query(models.NapiwkiDnia).filter(
            models.NapiwkiDnia.data >= start, models.NapiwkiDnia.data <= end,
            models.NapiwkiDnia.kwota > 0).all():
        moj = next((x for x in _napiwki_podzial(db, rec.data)["podzial"] if x["pracownik_id"] == pid), None)
        if moj and moj["kwota"] > 0:
            dni.append({"data": str(rec.data), "kwota": moj["kwota"], "godziny": moj["godziny"]})
    dni.sort(key=lambda x: x["data"])
    return {"dni": dni, "suma": round(sum(d["kwota"] for d in dni), 2)}


# --- POWIADOMIENIA WEB PUSH (pracownik) ---

@router.get("/api/me/push/public-key", status_code=200)
def push_public_key(user: models.User = Depends(get_current_user)):
    return {"publicKey": VAPID_PUBLIC_KEY}

@router.post("/api/me/push/subscribe", status_code=204)
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

@router.post("/api/me/push/register-native", status_code=204)
def push_register_native(dane: dict, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Rejestracja tokenu powiadomień z aplikacji NATYWNEJ (Capacitor: FCM/APNs).
    Web Push nie działa w apce natywnej — token urządzenia zapisujemy osobno (PushDeviceToken)."""
    token = (dane.get("token") or "").strip()
    platform = (dane.get("platform") or "").strip().lower() or None
    if not token:
        raise HTTPException(400, "Brak tokenu powiadomień.")
    if platform and platform not in ("android", "ios"):
        platform = None
    existing = db.query(models.PushDeviceToken).filter_by(token=token).first()
    if existing:
        existing.user_id, existing.platform = user.id, platform
    else:
        db.add(models.PushDeviceToken(user_id=user.id, token=token, platform=platform))
    db.commit()


# --- GODZINY Z RCP (miesięczne podsumowanie pracownika) ---

@router.get("/api/me/godziny", status_code=200)
def moje_godziny(
    rok: int = Query(..., ge=2000, le=2100), miesiac: int = Query(..., ge=1, le=12),
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
        # Przycinamy start do grafiku TYLKO od daty obowiązywania reguły (PRZYCINANIE_OD) — tak samo
        # jak raport miesięczny (raporty.py). Bez tej bramki dni sprzed progu zaniżały godziny i suma
        # słupków przestawała się zgadzać z nagłówkiem suma_godzin (liczonym z raportu).
        if przy and raporty._opublikowany(o.data, zakresy_pub) and o.data >= raporty.PRZYCINANIE_OD:
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


# --- REZERWACJE (pracownik: tylko sumy dzienne) ---

@router.get("/api/me/rezerwacje")
def moje_rezerwacje(
    user: models.User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Pracownik: TYLKO sumy dzienne (liczba rezerwacji + suma osób), bez godzin i danych klienta."""
    dane = rezerwacje.czytaj_rezerwacje(db, 30)
    return {"dni": [{"data": d["data"], "liczba": d["liczba"], "osoby": d["osoby"]} for d in dane]}
