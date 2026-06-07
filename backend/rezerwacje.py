"""Rezerwacje z Google Calendar (konto serwisowe) → agregacja per dzień (+ per godzina).

Czyta TYLKO do odczytu (scope calendar.readonly). Konfiguracja przez .env:
  GOOGLE_SA_JSON     – ścieżka do pliku JSON konta serwisowego,
  GOOGLE_CALENDAR_ID – ID kalendarza z rezerwacjami (udostępniony temu kontu).

Pracownik dostaje TYLKO liczby (bez danych klienta). Liczbę osób bierzemy z opisu
wydarzenia ("Liczba osób: N", format Bookero). Wynik cache'owany ~60 s.
"""

import os
import re
import time
from datetime import datetime, timedelta
from collections import defaultdict

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


def rezerwacje_per_dzien(dni_naprzod: int = 30):
    """Lista dni [{data, liczba, osoby, godziny:[{godzina, liczba, osoby}]}] na N dni do przodu.
    Cache ~60 s; błąd Google nie wywala aplikacji (zwraca ostatni wynik albo pustą listę)."""
    if not skonfigurowane():
        return []
    teraz = time.time()
    if _cache["dane"] is not None and teraz - _cache["ts"] < _CACHE_TTL:
        return _cache["dane"]
    now = datetime.now(_TZ) if _TZ else datetime.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=dni_naprzod)
    try:
        dane = parsuj(_pobierz_wydarzenia(start.isoformat(), end.isoformat()))
        _cache["ts"], _cache["dane"] = teraz, dane
    except Exception as e:  # noqa: BLE001
        print("[REZERWACJE] błąd pobierania:", e)
        dane = _cache["dane"] or []
    return dane
