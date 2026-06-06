#!/usr/bin/env python3
"""Agent RCP — działa W SIECI LOKALNEJ (na serwerze Gastro LSI), czyta odbicia z bazy RCP
i WYPYCHA je na VPS. VPS nigdy nie łączy się tutaj.

Bezpieczeństwo (ważne — nie chcemy ruszyć Gastro LSI):
  • Konto bazy RCP musi być TYLKO DO ODCZYTU.
  • Czytamy w trybie READ UNCOMMITTED (NOLOCK) — NIE zakładamy blokad na tabele Gastro.
  • Pobieramy tylko wąskie okno dni (OKNO_DNI) — zapytanie jest lekkie.
  • Pętla jest odporna: błąd bazy/sieci nie wywala agenta, próbuje w kolejnym cyklu.
  • Nigdy nie zapisujemy do bazy RCP. Tylko SELECT.

Konfiguracja: plik `.env` obok tego pliku (patrz `.env.example`).

Kontrakt zapytania RCP_SQL — MUSI zwrócić kolumny (aliasy):
  rcp_id        : stabilny, unikalny identyfikator rekordu zmiany w RCP (do upsertu),
  imie_nazwisko : pełne imię i nazwisko,
  data          : data zmiany (DATE),
  wejscie       : data+godzina wejścia (DATETIME) lub NULL,
  wyjscie       : data+godzina wyjścia (DATETIME) lub NULL.
Parametry bindowane: :start, :end (zakres dat). Przykład w `.env.example`.
"""

import os
import sys
import time
import logging
from datetime import date, datetime, timedelta

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

try:
    import requests
except ImportError:
    print("Brak biblioteki 'requests'. Zainstaluj: pip install -r requirements.txt")
    sys.exit(1)

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("agent_rcp")

RCP_DATABASE_URL = os.environ.get("RCP_DATABASE_URL", "")
RCP_SQL = os.environ.get("RCP_SQL", "")
VPS_INGEST_URL = os.environ.get("VPS_INGEST_URL", "")        # https://twojadomena/api/rcp/ingest
RCP_INGEST_TOKEN = os.environ.get("RCP_INGEST_TOKEN", "")    # ten sam co na VPS
POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "30"))
OKNO_DNI = int(os.environ.get("OKNO_DNI", "2"))
QUERY_TIMEOUT = int(os.environ.get("QUERY_TIMEOUT", "15"))


def _wymagane():
    braki = [k for k, v in {
        "RCP_DATABASE_URL": RCP_DATABASE_URL, "RCP_SQL": RCP_SQL,
        "VPS_INGEST_URL": VPS_INGEST_URL, "RCP_INGEST_TOKEN": RCP_INGEST_TOKEN,
    }.items() if not v]
    if braki:
        log.error("Brak wymaganych zmiennych w .env: %s", ", ".join(braki))
        if not RCP_SQL:
            log.error("Najpierw uruchom: python odkryj_schemat.py — pomoże ułożyć RCP_SQL.")
        sys.exit(2)


# Read-only + NOLOCK: czytamy bez zakładania blokad na tabele Gastro.
_engine = None
def engine():
    global _engine
    if _engine is None:
        _engine = create_engine(RCP_DATABASE_URL, pool_pre_ping=True)
    return _engine


def _iso(v):
    if v is None:
        return None
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return str(v)


def pobierz_odbicia(start: date, end: date):
    with engine().connect() as conn:
        # NOLEKKO dla Gastro: brak blokad współdzielonych na czytanych tabelach.
        conn.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
        rows = conn.execute(text(RCP_SQL), {"start": start, "end": end}).mappings().all()

    odbicia = []
    for r in rows:
        try:
            odbicia.append({
                "rcp_id": str(r["rcp_id"]),
                "imie_nazwisko": (r.get("imie_nazwisko") or "").strip(),
                "data": _iso(r["data"])[:10],
                "wejscie": _iso(r.get("wejscie")),
                "wyjscie": _iso(r.get("wyjscie")),
            })
        except (KeyError, TypeError) as e:
            log.warning("Pomijam rekord RCP (zła struktura): %s", e)
    return odbicia


def wyslij_na_vps(odbicia):
    r = requests.post(
        VPS_INGEST_URL,
        json={"odbicia": odbicia},
        headers={"X-RCP-Token": RCP_INGEST_TOKEN},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


def cykl():
    end = date.today()
    start = end - timedelta(days=OKNO_DNI)
    odbicia = pobierz_odbicia(start, end)
    if not odbicia:
        log.info("Brak odbić w oknie %s..%s.", start, end)
        return
    wynik = wyslij_na_vps(odbicia)
    log.info("Wysłano %d odbić → VPS: %s", len(odbicia), wynik)


def main():
    _wymagane()
    log.info("Agent RCP wystartował. Poll co %ss, okno %s dni. Cel: %s",
             POLL_SECONDS, OKNO_DNI, VPS_INGEST_URL)
    while True:
        try:
            cykl()
        except Exception as e:  # noqa: BLE001 — pętla nigdy nie może się wywalić
            log.error("Błąd cyklu (spróbuję ponownie za %ss): %s", POLL_SECONDS, e)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
