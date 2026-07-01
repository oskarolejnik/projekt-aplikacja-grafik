"""Ograniczenie prób logowania (rate-limit + czasowy lockout) — ochrona przed brute-force.

Prosty, bezstanowy względem bazy licznik w pamięci procesu. Klucze ustala warstwa wywołująca
(np. `login:<login>|ip:<ip>` oraz `ip:<ip>`), dzięki czemu ta sama logika chroni jednocześnie
przed atakiem na konkretne konto i przed „spray" z jednego adresu, a niezależność IP ogranicza
ryzyko blokady konta ofiary z cudzego adresu (account-lockout DoS).

Reguły:
  • po `MAX_PROBY` nieudanych próbach w oknie `OKNO_SEKUNDY` klucz zostaje zablokowany na `LOCKOUT_SEKUNDY`,
  • sukces czyści licznik klucza,
  • po wygaśnięciu blokady lub okna licznik startuje od zera.

Progi konfiguruje środowisko: LOGIN_MAX_PROBY, LOGIN_LOCKOUT_SEKUNDY, LOGIN_OKNO_SEKUNDY.
Zegar (`_zegar`) jest podmienialny w testach — dzięki temu testy nie używają realnego sleep.

UWAGA (skala): stan jest per-proces. Dla wielu workerów/instancji za reverse proxy wystarczy on
jako pierwsza linia obrony; twardy, współdzielony limit (np. Redis) to element dalszej rozbudowy.
"""

from __future__ import annotations

import math
import os
import threading
import time


def _int_env(nazwa: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(nazwa, default)))
    except (TypeError, ValueError):
        return default


MAX_PROBY = _int_env("LOGIN_MAX_PROBY", 5)
LOCKOUT_SEKUNDY = _int_env("LOGIN_LOCKOUT_SEKUNDY", 300)   # 5 minut blokady
OKNO_SEKUNDY = _int_env("LOGIN_OKNO_SEKUNDY", 900)         # okno akumulacji nieudanych prób

_zegar = time.monotonic           # podmienialne w testach (monkeypatch)
_lock = threading.Lock()
_proby: dict = {}                 # klucz -> {"fails": int, "last": float, "locked_until": float}


def _teraz() -> float:
    return _zegar()


def pozostala_blokada(klucz: str) -> int:
    """Zwraca liczbę sekund pozostałej blokady (>0) albo 0, gdy klucz nie jest zablokowany.
    Po drodze sprząta wygasłe blokady i przeterminowane okna."""
    with _lock:
        e = _proby.get(klucz)
        if not e:
            return 0
        now = _teraz()
        if e["locked_until"] and now < e["locked_until"]:
            return math.ceil(e["locked_until"] - now)
        if e["locked_until"] and now >= e["locked_until"]:
            _proby.pop(klucz, None)          # blokada wygasła — czysty start
            return 0
        if now - e["last"] > OKNO_SEKUNDY:    # okno wygasło — zapomnij nieudane próby
            _proby.pop(klucz, None)
        return 0


def zarejestruj_porazke(klucz: str) -> int:
    """Rejestruje nieudaną próbę logowania. Zwraca sekundy blokady, jeśli właśnie ją nałożono
    (0 = jeszcze poniżej progu)."""
    with _lock:
        now = _teraz()
        e = _proby.get(klucz)
        if e and now - e["last"] > OKNO_SEKUNDY:
            e = None                          # poza oknem — licz od nowa
        fails = (e["fails"] if e else 0) + 1
        locked_until = now + LOCKOUT_SEKUNDY if fails >= MAX_PROBY else 0.0
        _proby[klucz] = {"fails": fails, "last": now, "locked_until": locked_until}
        return math.ceil(locked_until - now) if locked_until else 0


def zarejestruj_sukces(klucz: str) -> None:
    """Udane logowanie — kasuje licznik klucza."""
    with _lock:
        _proby.pop(klucz, None)


def reset() -> None:
    """Czyści cały stan (używane w testach dla izolacji)."""
    with _lock:
        _proby.clear()
