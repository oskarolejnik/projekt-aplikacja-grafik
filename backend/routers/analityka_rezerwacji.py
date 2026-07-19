"""Router: analityka rezerwacji — covery, no-show, mix kanałów, lead time, szczyty (roadmapa: pętla wartości).

Wszystko to AGREGATY (bez PII) liczone z encji Termin (rodzaj=stolik) po stronie Pythona —
można pokazać właścicielowi bez audytu RODO. Bez nowych tabel/migracji (wzór jak /api/crm, /api/pulpit).
Gating: moduł rezerwacji (Pro+).
"""

from collections import Counter, defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import models
import reservation_demand
import reservation_operational
import uprawnienia
from auth import get_current_user
from database import get_db
from deps import modul_aktywny

router = APIRouter()

_AKTYWNE = ("rezerwacja", "potwierdzona")
_KANALY = ("online", "reczna", "google", "ical", "walk_in")
DNI_PL = ["Pon", "Wt", "Śr", "Czw", "Pt", "Sob", "Nd"]
MAX_ANALYTICS_DAYS = 366


def _wymagaj_rezerwacje(db: Session = Depends(get_db)):
    if not modul_aktywny(db, "modul_rezerwacje"):
        raise HTTPException(403, "Moduł rezerwacji jest niedostępny w tym planie — odblokujesz go w pakiecie Pro.")


def _mediana(xs):
    xs = sorted(xs)
    n = len(xs)
    if n == 0:
        return 0
    return xs[n // 2] if n % 2 else round((xs[n // 2 - 1] + xs[n // 2]) / 2, 1)


def _mediana_lub_none(xs):
    return _mediana(xs) if xs else None


def _srednia_lub_none(xs):
    return round(sum(xs) / len(xs), 1) if xs else None


def _turn_time_summary(rows):
    actual = [row["actual"] for row in rows]
    planned = [row["planned"] for row in rows if row["planned"] is not None]
    deviations = [
        row["actual"] - row["planned"]
        for row in rows if row["planned"] is not None
    ]
    return {
        "proba": len(actual),
        "mediana_min": _mediana_lub_none(actual),
        "srednia_min": _srednia_lub_none(actual),
        "planowana_mediana_min": _mediana_lub_none(planned),
        "odchylenie_min": _mediana_lub_none(deviations),
    }


def _empty_usage():
    return {"wizyty": 0, "covery": 0, "rzeczywiste_minuty": 0, "pomiary": 0}


def _add_usage(target, *, covers, minutes):
    target["wizyty"] += 1
    target["covery"] += covers
    target["rzeczywiste_minuty"] += minutes
    target["pomiary"] += 1


def _waliduj_zakres(start: date, end: date) -> int:
    if end < start:
        raise HTTPException(400, "Zakres dat jest odwrócony.")
    dni = (end - start).days + 1
    if dni > MAX_ANALYTICS_DAYS:
        raise HTTPException(400, f"Zakres analityki może obejmować maksymalnie {MAX_ANALYTICS_DAYS} dni.")
    return dni


@router.get("/api/analityka/rezerwacje", dependencies=[Depends(_wymagaj_rezerwacje)])
def analityka_rezerwacje(start: date = Query(...), end: date = Query(...), db: Session = Depends(get_db)):
    """Zbiorcza analityka rezerwacji stolikowych w oknie [start, end]: covery, statusy (no-show %),
    mix kanałów, lead time, rozkład wielkości grup, szczyty (dzień tygodnia × godzina)."""
    dni = _waliduj_zakres(start, end)
    rez = db.query(models.Termin).filter(
        models.Termin.rodzaj == "stolik", models.Termin.data >= start, models.Termin.data <= end).all()

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


@router.get(
    "/api/analityka/rezerwacje/operacyjna",
    dependencies=[Depends(_wymagaj_rezerwacje)],
)
def analityka_rezerwacje_operacyjna(
    start: date = Query(...),
    end: date = Query(...),
    db: Session = Depends(get_db),
):
    """R7.1: faktyczny turn time i wykorzystanie zasobow, bez PII i imputacji."""
    _waliduj_zakres(start, end)
    reservations = db.query(models.Termin).filter(
        models.Termin.rodzaj == "stolik",
        models.Termin.status == "odbyla",
        models.Termin.data >= start,
        models.Termin.data <= end,
    ).all()
    allocations = reservation_operational.allocation_snapshots(db, reservations)
    moved_ids = reservation_operational.moved_during_visit_ids(db, reservations)

    measured = []
    missing = invalid = 0
    for reservation in reservations:
        measurement = reservation_operational.actual_turn_measurement(reservation)
        if measurement["pomiar"] == "missing":
            missing += 1
            continue
        if measurement["pomiar"] == "invalid":
            invalid += 1
            continue
        measured.append({
            "reservation": reservation,
            "actual": measurement["rzeczywisty_czas_min"],
            "planned": reservation_operational.planned_turn_minutes(reservation),
            "group": reservation_operational.party_bucket(reservation.liczba_osob),
            "allocation": allocations.get(reservation.id),
        })

    group_order = ("1-2", "3-4", "5-6", "7+")
    turn_time = _turn_time_summary(measured)
    turn_time["wg_wielkosci_grupy"] = [
        {"grupa": group, **_turn_time_summary([
            row for row in measured if row["group"] == group
        ])}
        for group in group_order
    ]

    room_usage, table_usage, combination_usage = {}, {}, {}
    no_assignment = _empty_usage()
    for row in measured:
        reservation = row["reservation"]
        if reservation.id in moved_ids:
            continue
        minutes = row["actual"]
        covers = max(0, int(reservation.liczba_osob or 0))
        allocation = row["allocation"] or {
            "sala_id": None, "sala_nazwa": None, "stoliki": [], "kombinacja": None,
        }
        tables = allocation["stoliki"]
        if not tables:
            _add_usage(no_assignment, covers=covers, minutes=minutes)
            continue

        room_key = (allocation["sala_id"], allocation["sala_nazwa"])
        room = room_usage.setdefault(room_key, {
            "sala_id": allocation["sala_id"],
            "nazwa": allocation["sala_nazwa"] or "Bez przypisanej sali",
            **_empty_usage(),
        })
        _add_usage(room, covers=covers, minutes=minutes)

        for table in tables:
            table_row = table_usage.setdefault(table["id"], {
                "stolik_id": table["id"],
                "nazwa": table["nazwa"],
                "sala_id": allocation["sala_id"],
                "sala_nazwa": allocation["sala_nazwa"],
                **_empty_usage(),
            })
            _add_usage(table_row, covers=covers, minutes=minutes)

        combination = allocation["kombinacja"]
        if combination is not None:
            combination_key = (
                combination["wersja_id"], combination["id"],
                tuple(sorted(table["id"] for table in tables)),
            )
            combination_row = combination_usage.setdefault(combination_key, {
                "kombinacja_id": combination["id"],
                "wersja_id": combination["wersja_id"],
                "nazwa": combination["nazwa"],
                "sala_id": allocation["sala_id"],
                "sala_nazwa": allocation["sala_nazwa"],
                "stoliki": tables,
                **_empty_usage(),
            })
            _add_usage(combination_row, covers=covers, minutes=minutes)

    complete = len(measured)
    total = len(reservations)
    return {
        "jakosc_danych": {
            "zakonczone_wizyty": total,
            "z_pelnym_pomiarem": complete,
            "bez_pomiaru": missing,
            "nieprawidlowy_pomiar": invalid,
            "pominiete_przeniesienia": sum(
                1 for row in measured if row["reservation"].id in moved_ids
            ),
            "kompletnosc_proc": round(complete / total * 100) if total else 0,
        },
        "turn_time": turn_time,
        "wykorzystanie": {
            "sale": sorted(
                room_usage.values(), key=lambda row: (-row["rzeczywiste_minuty"], row["nazwa"]),
            ),
            "stoliki": sorted(
                table_usage.values(), key=lambda row: (-row["rzeczywiste_minuty"], row["stolik_id"]),
            ),
            "kombinacje": sorted(
                combination_usage.values(),
                key=lambda row: (-row["rzeczywiste_minuty"], row["nazwa"]),
            ),
            "bez_przydzialu": no_assignment,
        },
    }


@router.get(
    "/api/analityka/rezerwacje/popyt",
    dependencies=[Depends(_wymagaj_rezerwacje)],
)
def analityka_rezerwacje_popyt(
    start: date = Query(...),
    end: date = Query(...),
    db: Session = Depends(get_db),
):
    """R7.2: anonimowy odrzucony popyt i lejek waitlisty bez ID, hashy i PII."""
    _waliduj_zakres(start, end)
    return reservation_demand.aggregate_demand(db, start=start, end=end)


@router.get("/api/analityka/oblozenie", dependencies=[Depends(_wymagaj_rezerwacje)])
def analityka_oblozenie(
    start: date = Query(...),
    end: date = Query(...),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Obłożenie stołowe/miejscowe + RevPASH (dzienny + agregat) w oknie [start, end].

    Stołogodziny DOSTĘPNE = aktywne stoły × godziny serwisów danego dnia (blackout z WyjatekKalendarza
    zeruje dzień). WYKORZYSTANE = Σ (liczba stołów rezerwacji × turn-time). RevPASH = utarg netto dnia /
    dostępne stołogodziny — ziarnistość DZIENNA (jedyny wspólny klucz rezerwacja↔utarg to data;
    per-stolik/wydatki gościa wymagają strumienia rachunków z POS → poza tym slice)."""
    import main   # lazy: helpery godzin/turn-time/rozbicia kombinacji (unik cyklu importu z main)
    _waliduj_zakres(start, end)

    stoly = db.query(models.Stolik).filter_by(aktywny=True).all()
    liczba_stolow, miejsca = len(stoly), sum((s.pojemnosc or 0) for s in stoly)

    # Utarg netto per dzień = MAX po źródłach (każde źródło raportuje PEŁNY dzień → suma dublowałaby).
    utarg = {}
    for u in db.query(models.UtargDnia).filter(
            models.UtargDnia.data >= start, models.UtargDnia.data <= end).all():
        utarg[u.data] = max(utarg.get(u.data, 0.0), u.netto or 0.0)

    rez_wg_dnia = defaultdict(list)
    for t in db.query(models.Termin).filter(
            models.Termin.rodzaj == "stolik", models.Termin.data >= start,
            models.Termin.data <= end, models.Termin.godz_od.isnot(None)).all():
        if t.status != "odwolana":
            rez_wg_dnia[t.data].append(t)

    def _proc(licz, mian):
        return round(licz / mian * 100) if mian else 0

    pokaz_finanse = uprawnienia.ma_user(user, "rozliczenia.podglad")
    per_dzien, agr = [], defaultdict(float)
    d = start
    while d <= end:
        godziny_h = 0.0
        for s in main._serwisy_dnia(db, d):                        # blackout → [] → 0 h
            koniec = s.godz_do or s.ostatni_zasiadek
            if koniec and s.godz_od:
                godziny_h += max(0.0, (koniec.hour * 60 + koniec.minute
                                       - (s.godz_od.hour * 60 + s.godz_od.minute)) / 60.0)
        dost_stolog, dost_miejscog = liczba_stolow * godziny_h, miejsca * godziny_h
        wyk_stolog = wyk_miejscog = 0.0
        covery = 0
        for t in rez_wg_dnia.get(d, []):
            tt_h = main._turn_time(main._serwis_dla_godziny(db, d, t.godz_od), t.liczba_osob) / 60.0
            wyk_stolog += len(main._stoly_terminu(t)) * tt_h
            wyk_miejscog += (t.liczba_osob or 0) * tt_h
            covery += (t.liczba_osob or 0)
        ma_utarg = d in utarg                                      # brak wiersza ≠ zerowy utarg (RevPASH = None)
        netto = utarg.get(d, 0.0)
        per_dzien.append({
            "data": str(d),
            "dostepne_stologodziny": round(dost_stolog, 1),
            "wykorzystane_stologodziny": round(wyk_stolog, 1),
            "oblozenie_stolowe_proc": _proc(wyk_stolog, dost_stolog),
            "oblozenie_miejscowe_proc": _proc(wyk_miejscog, dost_miejscog),
            "covery": covery,
            "utarg_netto": round(netto, 2) if (pokaz_finanse and ma_utarg) else None,
            "revpash": round(netto / dost_stolog, 2) if (pokaz_finanse and dost_stolog and ma_utarg) else None,
        })
        agr["dost_stolog"] += dost_stolog; agr["wyk_stolog"] += wyk_stolog
        agr["dost_miejscog"] += dost_miejscog; agr["wyk_miejscog"] += wyk_miejscog
        agr["covery"] += covery; agr["utarg"] += netto
        d += timedelta(days=1)

    return {
        "start": str(start), "end": str(end), "stoly_aktywne": liczba_stolow, "miejsca": miejsca,
        "per_dzien": per_dzien,
        "dane_finansowe_ukryte": not pokaz_finanse,
        "agregat": {
            "dostepne_stologodziny": round(agr["dost_stolog"], 1),
            "wykorzystane_stologodziny": round(agr["wyk_stolog"], 1),
            "oblozenie_stolowe_proc": _proc(agr["wyk_stolog"], agr["dost_stolog"]),
            "oblozenie_miejscowe_proc": _proc(agr["wyk_miejscog"], agr["dost_miejscog"]),
            "covery": int(agr["covery"]),
            "utarg_netto": round(agr["utarg"], 2) if (pokaz_finanse and utarg) else None,
            "revpash": round(agr["utarg"] / agr["dost_stolog"], 2)
            if (pokaz_finanse and agr["dost_stolog"] and utarg) else None,
        },
    }
