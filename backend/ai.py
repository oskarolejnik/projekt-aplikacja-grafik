"""Opcjonalny klient Claude API (Anthropic) — zero nowych zależności (stdlib urllib).

Funkcje AI w Lokalo są ZAWSZE opcjonalne: bez klucza działa ścieżka regułowa (fallback),
klucz podnosi jakość. Konfiguracja per instancja przez środowisko:
  ANTHROPIC_API_KEY  — klucz API (brak = AI wyłączone),
  ANTHROPIC_MODEL    — model (domyślnie claude-sonnet-5).
"""

import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

API_URL = "https://api.anthropic.com/v1/messages"
DOMYSLNY_MODEL = "claude-sonnet-5"
TIMEOUT_S = 30


def ai_dostepne() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def zapytaj_claude(system: str, prompt: str, max_tokens: int = 1024) -> str:
    """Jedno wywołanie Claude (messages API), zwraca tekst odpowiedzi.
    Rzuca RuntimeError przy braku klucza lub błędzie sieci/API — wołający decyduje o fallbacku."""
    klucz = os.environ.get("ANTHROPIC_API_KEY")
    if not klucz:
        raise RuntimeError("Brak ANTHROPIC_API_KEY — AI wyłączone.")
    body = json.dumps({
        "model": os.environ.get("ANTHROPIC_MODEL", DOMYSLNY_MODEL),
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(API_URL, data=body, method="POST", headers={
        "content-type": "application/json",
        "x-api-key": klucz,
        "anthropic-version": "2023-06-01",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            dane = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:  # błąd API (4xx/5xx)
        szczegoly = e.read().decode("utf-8", "replace")[:300]
        logger.warning("Claude API HTTP %s: %s", e.code, szczegoly)
        raise RuntimeError(f"Claude API: HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        logger.warning("Claude API niedostępne: %s", e)
        raise RuntimeError("Claude API niedostępne.") from e
    czesci = [b.get("text", "") for b in dane.get("content", []) if b.get("type") == "text"]
    return "".join(czesci).strip()


def zapytaj_claude_json(system: str, prompt: str, max_tokens: int = 1024) -> dict:
    """Jak zapytaj_claude, ale oczekuje JSON-a w odpowiedzi (wycina ewentualny płot ```)."""
    tekst = zapytaj_claude(system, prompt, max_tokens)
    if tekst.startswith("```"):
        tekst = tekst.strip("`")
        if tekst.startswith("json"):
            tekst = tekst[4:]
    poczatek, koniec = tekst.find("{"), tekst.rfind("}")
    if poczatek == -1 or koniec == -1:
        raise RuntimeError("Claude nie zwrócił JSON-a.")
    return json.loads(tekst[poczatek:koniec + 1])
