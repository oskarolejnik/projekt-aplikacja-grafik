"""Router: analityka rezerwacji — covery, no-show, mix kanałów, lead time, szczyty (roadmapa: pętla wartości).

Wszystko to AGREGATY (bez PII) liczone z encji Termin (rodzaj=stolik) po stronie Pythona —
można pokazać właścicielowi bez audytu RODO. Bez nowych tabel/migracji (wzór jak /api/crm, /api/pulpit).
Gating: moduł rezerwacji (Pro+).
"""

from collections import Counter, defaultdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import models
from database import get_db
from deps import modul_aktywny

router = APIRouter()

_AKTYWNE = ("rezerwacja", "potwierdzona")
_KANALY = ("online", "reczna", "google", "ical", "walk_in")
DNI_PL = ["Pon", "Wt", "Śr", "Czw", "Pt", "Sob", "Nd"]


def _wymagaj_rezerwacje(db: Session = Depends(get_db)):
    if not modul_aktywny(db, "modul_rezerwacje"):
        raise HTTPException(403, "Moduł rezerwacji jest niedostępny w tym planie — odblokujesz go w pakiecie Pro.")


def _mediana(xs):
    xs = sorted(xs)
    n = len(xs)
    if n == 0:
        return 0
    return xs[n // 2] if n % 2 else round((xs[n // 2 - 1] + xs[n // 2]) / 2, 1)


@router.get("/api/analityka/rezerwacje", dependencies=[Depends(_wymagaj_rezerwacje)])
def analityka_rezerwacje(start: date = Query(...), end: date = Query(...), db: Session = Depends(get_db)):
    """Zbiorcza analityka rezerwacji stolikowych w oknie [start, end]: covery, statusy (no-show %),
    mix kanałów, lead time, rozkład wielkości grup, szczyty (dzień tygodnia × godzina)."""
    rez = db.query(models.Termin).filter(
        models.Termin.rodzaj == "stolik", models.Termin.data >= start, models.Termin.data <= end).all()

    dni = (end - start).days + 1
    covery_wg_dnia = defaultdict(lambda: {"covery": 0, "rezerwacje": 0})
    covery_suma = 0
    st = {"odbyla": 0, "no_show": 0, "odwolana": 0, "aktywne": 0}
    kanaly = Counter()
    lead_dni, grupy, wg_dnia_tyg, wg_godziny = [], Counter(), Counter(), Counter()

    for t in rez:
        status = t.status
        if status in _AKTYWNE:
            st["aktywne"] += 1
        elif status in st:
            st[status] += 1
        kanaly[t.kanal if t.kanal in _KANALY else "reczna"] += 1
        # Covery = zabukowani goście (bez anulowanych) — podstawa planowania obsady.
        if status != "odwolana":
            osoby = t.liczba_osob or 0
            covery_suma += osoby
            d = covery_wg_dnia[str(t.data)]
            d["covery"] += osoby
            d["rezerwacje"] += 1
            wg_dnia_tyg[t.data.weekday()] += osoby
            if t.godz_od:
                wg_godziny[t.godz_od.hour] += osoby
            if osoby:
                grupy[min(osoby, 9)] += 1              # rozkład wielkości grup (10+ → kubełek 9)
        # Lead time = ile dni wcześniej zabukowano (data − utworzono_at.date()).
        if t.utworzono_at:
            lead_dni.append(max(0, (t.data - t.utworzono_at.date()).days))

    zamkniete = st["odbyla"] + st["no_show"] + st["odwolana"]
    no_show_proc = round(st["no_show"] / zamkniete * 100) if zamkniete else 0
    pokazani = st["odbyla"] + st["no_show"]
    konwersja_proc = round(st["odbyla"] / pokazani * 100) if pokazani else 0

    return {
        "start": str(start), "end": str(end), "dni": dni,
        "covery": {
            "suma": covery_suma,
            "srednia_dzienna": round(covery_suma / dni, 1) if dni else 0,
            "wg_dnia": [{"data": d, **v} for d, v in sorted(covery_wg_dnia.items())],
        },
        "statusy": {**st, "no_show_proc": no_show_proc, "konwersja_proc": konwersja_proc},
        "kanaly": [{"kanal": k, "liczba": kanaly[k], "proc": round(kanaly[k] / len(rez) * 100)}
                   for k in sorted(kanaly, key=lambda x: -kanaly[x])] if rez else [],
        "lead_time": {"mediana_dni": _mediana(lead_dni), "srednia_dni": round(sum(lead_dni) / len(lead_dni), 1) if lead_dni else 0},
        "wielkosc_grup": [{"osoby": g, "etykieta": ("10+" if g == 9 else str(g)), "liczba": grupy[g]}
                          for g in sorted(grupy)],
        "szczyty": {
            "wg_dnia_tygodnia": [{"dzien": DNI_PL[i], "covery": wg_dnia_tyg.get(i, 0)} for i in range(7)],
            "wg_godziny": [{"godz": f"{h:02d}:00", "covery": wg_godziny[h]} for h in sorted(wg_godziny)],
        },
    }
