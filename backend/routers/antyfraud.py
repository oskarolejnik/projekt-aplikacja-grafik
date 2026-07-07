"""Router: antyfraud POS — storna, rabaty i anulacje per kelner (roadmapa v2, TOP 3).

Nadużycia kelnerskie to w gastro typowo 1–3% obrotu. Agent lokalny czyta z bazy Gastro
storna/rabaty/anulacje (NOLOCK, jednokierunkowo) i wypycha je pod /api/gastro/storna
(token X-RCP-Token — jak pozostałe strumienie agenta). Analiza porównuje każdego kelnera
do reszty zespołu (średnia + odchylenie standardowe liczby i kwoty zdarzeń) i FLAGUJE
odstających. Wynik komunikujemy jako „flagi do rozmowy", nie oskarżenia — a opcjonalne
podsumowanie AI (Claude) pisze je po polsku, zrozumiale dla właściciela.
"""

import logging
import os
import statistics
import unicodedata
from datetime import date, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

import ai
import models
from auth import require_admin
from database import get_db
from deps import utcnow_naive, token_agenta_ok

router = APIRouter()
logger = logging.getLogger(__name__)

TYPY = ("storno", "rabat", "anulacja")
MIN_ZDARZEN_DO_FLAGI = 5      # poniżej tego progu nie flagujemy (szum małych liczb)
# Flaga = wynik kelnera ≥ PROG_KROTNOSC × średnia RESZTY zespołu (bez niego). Porównanie
# do reszty (nie do średniej z nim samym) działa też w małych zespołach, gdzie z-score
# pojedynczego outliera nigdy nie przekroczy sqrt(n-1) — klasyczna pułapka progu z≥2.
PROG_KROTNOSC = 2.0

_PL_SPEC = str.maketrans("łŁ", "lL")


def _norm_nazwa(s: str) -> str:
    """Normalizacja jak przy odbiciach RCP (main._norm_nazwa) — kopia, by uniknąć importu main."""
    s = (s or "").translate(_PL_SPEC)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return " ".join(s.split())


# ─────────────────────────────────────────────────────────────────────────────
# Ingest od agenta (X-RCP-Token) — allowlista role_guard w main.py
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/api/gastro/storna")
def gastro_storna_ingest(payload: dict, request: Request, db: Session = Depends(get_db)):
    """Storna/rabaty/anulacje z Gastro. Upsert po id (GUID). Payload:
    {"storna": [{id, data, imie_nazwisko, typ, kwota, opis?, godzina?}]}"""
    # Kanoniczny check (jak reszta ingestu): token z panelu (rotowalny, hash) LUB env, w stałym
    # czasie i akceptujący X-RCP-Token oraz Bearer — koniec lokalnego env-only porównania (L16/L1).
    if not token_agenta_ok(request, db):
        raise HTTPException(401, "Nieprawidłowy lub brakujący token agenta.")
    mapa = {}
    for p in db.query(models.Pracownik).all():
        mapa.setdefault(_norm_nazwa(f"{p.imie} {p.nazwisko}"), p.id)
        mapa.setdefault(_norm_nazwa(f"{p.nazwisko} {p.imie}"), p.id)
    teraz = utcnow_naive()
    n = 0
    for it in (payload.get("storna") or []):
        try:
            sid = str(it["id"])
            d = date.fromisoformat(str(it["data"])[:10])
        except (KeyError, ValueError, TypeError):
            continue
        rec = db.get(models.StornoGastro, sid)
        if rec is None:
            rec = models.StornoGastro(id=sid)
            db.add(rec)
        rec.data = d
        nazwa = (it.get("imie_nazwisko") or "").strip()
        if nazwa:
            rec.imie_nazwisko = nazwa
        pid = mapa.get(_norm_nazwa(nazwa))
        if pid is not None:
            rec.pracownik_id = pid
        typ = (it.get("typ") or "storno").strip().lower()
        rec.typ = typ if typ in TYPY else "storno"
        try:
            rec.kwota = abs(float(it.get("kwota") or 0))
        except (ValueError, TypeError):
            rec.kwota = 0.0
        rec.opis = (it.get("opis") or None)
        g = it.get("godzina")
        if g:
            try:
                rec.godzina = time.fromisoformat(str(g)[:8])
            except ValueError:
                pass
        rec.zaktualizowano_at = teraz
        n += 1
    db.commit()
    return {"przyjeto": n}


# ─────────────────────────────────────────────────────────────────────────────
# Analiza (admin)
# ─────────────────────────────────────────────────────────────────────────────
def _z_score(x: float, srednia: float, odch: float) -> float:
    if odch <= 0:
        return 0.0
    return (x - srednia) / odch


def podsumowanie_statystyczne(db: Session, start: date, end: date) -> dict:
    rows = db.query(models.StornoGastro).filter(
        models.StornoGastro.data >= start, models.StornoGastro.data <= end).all()

    per = {}
    for r in rows:
        klucz = r.imie_nazwisko or "(nieznany)"
        k = per.setdefault(klucz, {"nazwa": klucz, "pracownik_id": r.pracownik_id,
                                   "storno": 0, "rabat": 0, "anulacja": 0,
                                   "liczba": 0, "suma": 0.0})
        k[r.typ if r.typ in TYPY else "storno"] += 1
        k["liczba"] += 1
        k["suma"] += (r.kwota or 0)
        if r.pracownik_id and not k["pracownik_id"]:
            k["pracownik_id"] = r.pracownik_id

    kelnerzy = list(per.values())
    liczby = [k["liczba"] for k in kelnerzy]
    sumy = [k["suma"] for k in kelnerzy]
    sr_liczba = statistics.fmean(liczby) if liczby else 0.0
    sr_suma = statistics.fmean(sumy) if sumy else 0.0
    odch_liczba = statistics.pstdev(liczby) if len(liczby) > 1 else 0.0
    odch_suma = statistics.pstdev(sumy) if len(sumy) > 1 else 0.0

    n_osob = len(kelnerzy)
    suma_liczb = sum(liczby)
    suma_sum = sum(sumy)
    for k in kelnerzy:
        k["suma"] = round(k["suma"], 2)
        k["z_liczba"] = round(_z_score(k["liczba"], sr_liczba, odch_liczba), 2)
        k["z_suma"] = round(_z_score(k["suma"], sr_suma, odch_suma), 2)
        # średnia RESZTY zespołu (bez tego kelnera) — odporna na małe zespoły
        reszta_liczba = (suma_liczb - k["liczba"]) / (n_osob - 1) if n_osob > 1 else 0.0
        reszta_suma = (suma_sum - k["suma"]) / (n_osob - 1) if n_osob > 1 else 0.0
        powody = []
        if k["liczba"] >= MIN_ZDARZEN_DO_FLAGI and n_osob > 1:
            if reszta_liczba > 0 and k["liczba"] >= PROG_KROTNOSC * reszta_liczba:
                powody.append(f"{k['liczba']} zdarzeń vs śr. {reszta_liczba:.1f} reszty zespołu "
                              f"({k['liczba'] / reszta_liczba:.1f}×)")
            elif reszta_liczba == 0:
                powody.append(f"{k['liczba']} zdarzeń, reszta zespołu: 0")
            if reszta_suma > 0 and k["suma"] >= PROG_KROTNOSC * reszta_suma:
                powody.append(f"{k['suma']:.0f} zł vs śr. {reszta_suma:.0f} zł reszty zespołu")
        k["flaga"] = bool(powody)
        k["powod"] = "; ".join(powody) or None

    kelnerzy.sort(key=lambda k: (not k["flaga"], -k["suma"]))
    return {
        "start": str(start), "end": str(end),
        "kelnerzy": kelnerzy,
        "zespol": {"osob": len(kelnerzy), "srednia_liczba": round(sr_liczba, 1),
                   "srednia_suma": round(sr_suma, 2), "zdarzen": len(rows)},
    }


def _podsumowanie_ai(wynik: dict) -> str:
    wiersze = "\n".join(
        f"- {k['nazwa']}: storna {k['storno']}, rabaty {k['rabat']}, anulacje {k['anulacja']}, "
        f"suma {k['suma']} zł, z-score liczby {k['z_liczba']}, flaga: {'TAK — ' + k['powod'] if k['flaga'] else 'nie'}"
        for k in wynik["kelnerzy"])
    return ai.zapytaj_claude(
        "Jesteś doradcą właściciela polskiej restauracji. Na podstawie statystyk stornowań "
        "napisz 3–5 zdań po polsku: co wygląda normalnie, kogo warto zaprosić do SPOKOJNEJ "
        "rozmowy i o co dopytać. Ton: flagi do wyjaśnienia, NIE oskarżenia — odstające liczby "
        "mają często niewinne przyczyny (szkolenie nowego, awaria drukarki, duże imprezy). "
        "Bez nagłówków, sam tekst.",
        f"Okres {wynik['start']}–{wynik['end']}, zespół {wynik['zespol']['osob']} os., "
        f"średnio {wynik['zespol']['srednia_liczba']} zdarzeń/os.\n{wiersze}",
        max_tokens=500)


@router.get("/api/antyfraud/podsumowanie")
def antyfraud_podsumowanie(start: date = Query(None), end: date = Query(None),
                           z_ai: int = Query(0, alias="ai"),
                           _admin: models.User = Depends(require_admin),
                           db: Session = Depends(get_db)):
    if end is None:
        end = date.today()
    if start is None:
        start = end - timedelta(days=30)
    wynik = podsumowanie_statystyczne(db, start, end)
    wynik["ai"] = None
    if z_ai and wynik["kelnerzy"] and ai.ai_dostepne():
        try:
            wynik["ai"] = _podsumowanie_ai(wynik)
        except RuntimeError as e:
            logger.warning("Podsumowanie AI antyfraud nieudane: %s", e)
    wynik["ai_dostepne"] = ai.ai_dostepne()
    return wynik
