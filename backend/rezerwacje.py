"""PII-safe agregat rezerwacji z kontrolowanym przejściem Google → kanoniczny ``Termin``.

Legacy Google czyta TYLKO do odczytu (scope calendar.readonly). Konfiguracja przez .env:
  GOOGLE_SA_JSON     – ścieżka do pliku JSON konta serwisowego,
  GOOGLE_CALENDAR_ID – ID kalendarza z rezerwacjami (udostępniony temu kontu).

Wszystkie tryby zwracają wyłącznie liczby, datę i godzinę. Shadow-read raportuje tylko
PII-free różnice bucketów, a tryb canonical nigdy nie wywołuje Google.
"""

import json
import logging
import os
import re
import time
from datetime import date, datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)

from dotenv import load_dotenv

load_dotenv()  # wczytaj .env, gdy moduł jest importowany niezależnie / przed innymi (jak database.py/push.py)

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("Europe/Warsaw")
except Exception:  # noqa: BLE001
    _TZ = None


def _sa_json() -> str:
    return os.environ.get("GOOGLE_SA_JSON", "")


def _cal_id() -> str:
    return os.environ.get("GOOGLE_CALENDAR_ID", "")

_OSOBY_RE = re.compile(r"Liczba\s+os[oó]b\s*:\s*(\d+)", re.IGNORECASE)
_CACHE_TTL = 60  # sekundy
_cache = {"ts": 0.0, "dane": None}

_STATUSY_KANONICZNE = ("rezerwacja", "potwierdzona", "odbyla")
_TRYBY_ODCZYTU = {"legacy", "shadow", "canonical"}


def skonfigurowane() -> bool:
    p = _sa_json()
    return bool(p and _cal_id() and os.path.isfile(p))


def _osoby_z_opisu(opis: str) -> int:
    m = _OSOBY_RE.search(opis or "")
    return int(m.group(1)) if m else 0


def _start_lokalny(ev):
    """Zwraca (data_iso, 'HH:MM' albo None) z wydarzenia (dateTime lub all-day)."""
    st = ev.get("start", {})
    if st.get("dateTime"):
        try:
            dt = datetime.fromisoformat(st["dateTime"].replace("Z", "+00:00"))
            if _TZ is not None and dt.tzinfo is not None:
                dt = dt.astimezone(_TZ)
            return dt.date().isoformat(), dt.strftime("%H:%M")
        except ValueError:
            return None, None
    if st.get("date"):
        return st["date"], None
    return None, None


def parsuj(events):
    """Agreguje listę wydarzeń: dzień → (liczba, osoby) + rozbicie per godzina."""
    dni = defaultdict(lambda: {"liczba": 0, "osoby": 0,
                               "godz": defaultdict(lambda: {"liczba": 0, "osoby": 0})})
    for ev in events:
        data, godz = _start_lokalny(ev)
        if not data:
            continue
        osoby = _osoby_z_opisu(ev.get("description", ""))
        d = dni[data]
        d["liczba"] += 1
        d["osoby"] += osoby
        g = d["godz"][godz or "—"]
        g["liczba"] += 1
        g["osoby"] += osoby
    out = []
    for data in sorted(dni):
        d = dni[data]
        godziny = [{"godzina": g, "liczba": v["liczba"], "osoby": v["osoby"]}
                   for g, v in sorted(d["godz"].items())]
        out.append({"data": data, "liczba": d["liczba"], "osoby": d["osoby"], "godziny": godziny})
    return out


def _pobierz_wydarzenia(time_min: str, time_max: str):
    """Wywołuje Google Calendar API (events.list, z paginacją). Lazy import bibliotek Google."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        _sa_json(), scopes=["https://www.googleapis.com/auth/calendar.readonly"]
    )
    svc = build("calendar", "v3", credentials=creds, cache_discovery=False)
    items, token = [], None
    while True:
        resp = svc.events().list(
            calendarId=_cal_id(), timeMin=time_min, timeMax=time_max,
            singleEvents=True, orderBy="startTime", maxResults=2500, pageToken=token,
        ).execute()
        items.extend(resp.get("items", []))
        token = resp.get("nextPageToken")
        if not token:
            break
    return items


def _rezerwacje_per_dzien_status(dni_naprzod: int = 30):
    """Legacy Google wraz ze statusem wiarygodności odczytu.

    Status jest osobny od danych, bo pusta, poprawna odpowiedź Google nie może być mylona
    z brakiem konfiguracji lub awarią. Przy błędzie zachowujemy dotychczasowy fallback do
    cache dla użytkownika, ale shadow-read nie użyje takiego wyniku do raportowania różnic.
    """
    if not skonfigurowane():
        return [], "unconfigured"
    teraz = time.time()
    if _cache["dane"] is not None and teraz - _cache["ts"] < _CACHE_TTL:
        return _cache["dane"], "ok"
    now = datetime.now(_TZ) if _TZ else datetime.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=dni_naprzod)
    try:
        dane = parsuj(_pobierz_wydarzenia(start.isoformat(), end.isoformat()))
        _cache["ts"], _cache["dane"] = teraz, dane
    except Exception as e:  # noqa: BLE001
        # Treść wyjątku dostawcy może zawierać identyfikatory lub fragment odpowiedzi.
        logger.warning("rezerwacje_legacy_unavailable error_type=%s", type(e).__name__)
        dane = _cache["dane"] or []
        return dane, "error"
    return dane, "ok"


def rezerwacje_per_dzien(dni_naprzod: int = 30):
    """Legacy: agregat z Google Calendar na N dni do przodu.

    Publiczny kontrakt pozostaje listą dni; kontrolowany reader używa wewnętrznie także
    statusu źródła, żeby poprawnie obsłużyć shadow-read.
    """
    dane, _status = _rezerwacje_per_dzien_status(dni_naprzod)
    return dane


def _dzis_lokalnie() -> date:
    now = datetime.now(_TZ) if _TZ else datetime.now()
    return now.date()


def rezerwacje_z_terminow(db, dni_naprzod: int = 30, start=None):
    """PII-safe agregat kanonicznych rezerwacji stolikowych z ``Termin``.

    Zakres jest półotwarty: ``[start, start + dni_naprzod)``. Zapytanie pobiera wyłącznie
    datę, godzinę i liczbę osób — nazwisko, telefon, e-mail i notatka nie opuszczają bazy.
    """
    start = start or _dzis_lokalnie()
    if isinstance(start, datetime):
        start = start.date()
    if dni_naprzod <= 0:
        return []
    end = start + timedelta(days=dni_naprzod)

    # Import leniwy utrzymuje moduł legacy niezależny od inicjalizacji aplikacji/ORM.
    import models

    rows = (
        db.query(models.Termin.data, models.Termin.godz_od, models.Termin.liczba_osob)
        .filter(
            models.Termin.rodzaj == "stolik",
            models.Termin.data >= start,
            models.Termin.data < end,
            models.Termin.status.in_(_STATUSY_KANONICZNE),
        )
        .order_by(models.Termin.data, models.Termin.godz_od, models.Termin.id)
        .all()
    )

    dni = defaultdict(lambda: {
        "liczba": 0,
        "osoby": 0,
        "godz": defaultdict(lambda: {"liczba": 0, "osoby": 0}),
    })
    for data_rezerwacji, godz_od, liczba_osob in rows:
        osoby = int(liczba_osob or 0)
        godzina = godz_od.strftime("%H:%M") if godz_od else "—"
        dzien = dni[data_rezerwacji.isoformat()]
        dzien["liczba"] += 1
        dzien["osoby"] += osoby
        dzien["godz"][godzina]["liczba"] += 1
        dzien["godz"][godzina]["osoby"] += osoby

    wynik = []
    for data_iso in sorted(dni):
        dzien = dni[data_iso]
        godziny = [
            {"godzina": godzina, "liczba": wartosci["liczba"], "osoby": wartosci["osoby"]}
            for godzina, wartosci in sorted(dzien["godz"].items())
        ]
        wynik.append({
            "data": data_iso,
            "liczba": dzien["liczba"],
            "osoby": dzien["osoby"],
            "godziny": godziny,
        })
    return wynik


def _tryb_odczytu() -> str:
    """Adapter do centralnego parsera settings, kompatybilny podczas wdrażania flagi."""
    try:
        from settings import rezerwacje_read_mode
    except ImportError:
        mode = os.environ.get("REZERWACJE_READ_MODE", "legacy")
    else:
        mode = rezerwacje_read_mode()
    mode = str(mode).strip().lower()
    if mode not in _TRYBY_ODCZYTU:
        raise ValueError(
            "Nieprawidłowy tryb odczytu rezerwacji. Dozwolone: legacy, shadow, canonical."
        )
    return mode


def _data_cutover_iso():
    """Jawna data operacyjna do logów; tryb nadal przełącza operator, nie zegar."""
    from settings import rezerwacje_cutover_date

    wartosc = rezerwacje_cutover_date()
    return wartosc.isoformat() if wartosc else None


def _metryki_agregatu(dane):
    return {
        "dni": len(dane),
        "rezerwacje": sum(int(dzien.get("liczba") or 0) for dzien in dane),
        "osoby": sum(int(dzien.get("osoby") or 0) for dzien in dane),
    }


def _buckety_agregatu(dane):
    """PII-free mapa (data, godzina) → liczniki do raportu shadow-read."""
    buckety = {}
    for dzien in dane:
        data_iso = str(dzien.get("data") or "")
        for godzina in dzien.get("godziny") or []:
            klucz = (data_iso, str(godzina.get("godzina") or "—"))
            buckety[klucz] = {
                "liczba": int(godzina.get("liczba") or 0),
                "osoby": int(godzina.get("osoby") or 0),
            }
    return buckety


def _roznice_bucketow(legacy, canonical):
    legacy_b = _buckety_agregatu(legacy)
    canonical_b = _buckety_agregatu(canonical)
    roznice = []
    for data_iso, godzina in sorted(set(legacy_b) | set(canonical_b)):
        stare = legacy_b.get((data_iso, godzina), {"liczba": 0, "osoby": 0})
        nowe = canonical_b.get((data_iso, godzina), {"liczba": 0, "osoby": 0})
        if stare == nowe:
            continue
        roznice.append({
            "data": data_iso,
            "godzina": godzina,
            "legacy_liczba": stare["liczba"],
            "canonical_liczba": nowe["liczba"],
            "delta_liczba": nowe["liczba"] - stare["liczba"],
            "legacy_osoby": stare["osoby"],
            "canonical_osoby": nowe["osoby"],
            "delta_osoby": nowe["osoby"] - stare["osoby"],
        })
    return roznice


def czytaj_rezerwacje(db, dni_naprzod: int = 30, start=None):
    """Wspólny reader agregatu dla admina, managera i pracownika.

    ``legacy`` zwraca Google, ``shadow`` nadal zwraca Google i porównuje go z bazą bez
    logowania PII, a ``canonical`` czyta wyłącznie ``Termin`` — bez wywołania i bez
    awaryjnego fallbacku do Google.
    """
    mode = _tryb_odczytu()
    if mode == "canonical":
        return rezerwacje_z_terminow(db, dni_naprzod=dni_naprzod, start=start)

    legacy, legacy_status = _rezerwacje_per_dzien_status(dni_naprzod)
    if mode == "legacy":
        return legacy

    if legacy_status != "ok":
        logger.warning("rezerwacje_shadow_unavailable legacy_status=%s", legacy_status)
        return legacy
    try:
        canonical = rezerwacje_z_terminow(db, dni_naprzod=dni_naprzod, start=start)
    except Exception as exc:  # noqa: BLE001 - shadow-read nie może przerwać źródła podstawowego
        # Nie logujemy treści wyjątku: sterownik/integracja mogłyby zawrzeć w niej dane wejściowe.
        logger.warning(
            "rezerwacje_shadow_unavailable canonical_status=error error_type=%s",
            type(exc).__name__,
        )
        return legacy

    legacy_m = _metryki_agregatu(legacy)
    canonical_m = _metryki_agregatu(canonical)
    podsumowanie = {
        "cutover_date": _data_cutover_iso(),
        "legacy_dni": legacy_m["dni"],
        "canonical_dni": canonical_m["dni"],
        "delta_dni": canonical_m["dni"] - legacy_m["dni"],
        "legacy_rezerwacje": legacy_m["rezerwacje"],
        "canonical_rezerwacje": canonical_m["rezerwacje"],
        "delta_rezerwacje": canonical_m["rezerwacje"] - legacy_m["rezerwacje"],
        "legacy_osoby": legacy_m["osoby"],
        "canonical_osoby": canonical_m["osoby"],
        "delta_osoby": canonical_m["osoby"] - legacy_m["osoby"],
    }
    roznice = _roznice_bucketow(legacy, canonical)
    logger.info(
        "rezerwacje_shadow_delta summary=%s buckets=%s",
        json.dumps(podsumowanie, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        json.dumps(roznice, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
    )
    return legacy
