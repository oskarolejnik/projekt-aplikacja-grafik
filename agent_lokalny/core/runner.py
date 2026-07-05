"""Pętla uniwersalnego agenta: per capability fetch → upload, heartbeat co cykl.

Odporność (jak legacy agent.py): błąd jednego strumienia nie wywala cyklu,
błąd cyklu nie wywala agenta — wszystko trafia do logu i do heartbeatu
(panel Lokalo pokazuje ostatnie błędy przy zdrowiu agenta)."""

import logging
import time
from datetime import date, timedelta

from drivers import zbuduj_driver

from .uploader import Uploader

log = logging.getLogger("agent_pos")

WERSJA = "2.0.0"

# capability → (ścieżka API, funkcja budująca payload z listy rekordów).
# `zrodlo` (driver_id) leci w obu strumieniach — utarg keyuje po nim wiersz, a odbicia
# pozwalają chmurze wybrać właściwą mapę pracowników POS→Lokalo.
STRUMIENIE = {
    "utarg": ("/api/pos/utarg-dnia", lambda dni, zrodlo: {"zrodlo": zrodlo, "dni": dni}),
    "odbicia": ("/api/rcp/ingest", lambda odbicia, zrodlo: {"zrodlo": zrodlo, "odbicia": odbicia}),
}


def cykl(driver, uploader, okno_dni: int):
    """Jeden przebieg: wszystkie capabilities drivera. Zwraca listę błędów (dla heartbeatu)."""
    end = date.today()
    start = end - timedelta(days=okno_dni)
    bledy = []
    for cap in sorted(driver.capabilities):
        sciezka, zbuduj = STRUMIENIE.get(cap, (None, None))
        if sciezka is None:
            continue
        try:
            rekordy = getattr(driver, f"fetch_{'utarg_dnia' if cap == 'utarg' else cap}")(start, end)
            if not rekordy:
                log.info("[%s] brak danych w oknie %s..%s.", cap, start, end)
                continue
            wynik = uploader.wyslij(sciezka, zbuduj(rekordy, driver.driver_id))
            # UWAGA: logi agenta tylko w ASCII-safe znakach — konsola Windows (cp1250)
            # wywala się na znakach spoza strony kodowej (np. strzałkach).
            log.info("[%s] wyslano %d rekordow -> %s", cap, len(rekordy), wynik)
        except Exception as e:  # noqa: BLE001 — jeden strumień nie blokuje reszty
            log.error("[%s] błąd: %s", cap, e)
            bledy.append(f"{cap}: {e}"[:200])
    return bledy


def heartbeat(driver, uploader, bledy):
    try:
        uploader.wyslij("/api/pos/heartbeat", {
            "driver": driver.driver_id, "wersja": WERSJA,
            "capabilities": sorted(driver.capabilities), "bledy": bledy,
        })
    except Exception as e:  # noqa: BLE001 — heartbeat jest best-effort
        log.error("heartbeat: %s", e)


def uruchom(cfg: dict, raz: bool = False):
    driver = zbuduj_driver(cfg["driver"], cfg.get(cfg["driver"], {}))
    uploader = Uploader(cfg["lokalo"]["url"], cfg["lokalo"]["token"])

    ok, komunikat = driver.test_connection()
    log.info("Test połączenia z POS: %s", komunikat)
    if not ok and raz:
        raise SystemExit(2)

    poll = int(cfg["agent"]["poll_sekundy"])
    okno = int(cfg["agent"]["okno_dni"])
    log.info("Agent POS %s wystartował (driver=%s, capabilities=%s, poll=%ss, okno=%s dni).",
             WERSJA, driver.driver_id, sorted(driver.capabilities), poll, okno)

    while True:
        try:
            bledy = cykl(driver, uploader, okno)
        except Exception as e:  # noqa: BLE001 — pętla nigdy nie może się wywalić
            bledy = [f"cykl: {e}"[:200]]
            log.error("Błąd cyklu: %s", e)
        heartbeat(driver, uploader, bledy)
        if raz:
            return
        time.sleep(poll)
