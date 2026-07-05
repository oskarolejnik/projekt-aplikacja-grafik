"""Konfiguracja uniwersalnego agenta: config.yaml wygenerowany przez panel
(Ustawienia → Utarg (POS) → Podłącz agenta) i uzupełniony na miejscu o dane
bazy POS. Patrz config.example.yaml."""

import os
import sys

try:
    import yaml
except ImportError:
    print("Brak biblioteki 'PyYAML'. Zainstaluj: pip install -r requirements.txt")
    sys.exit(1)

WYMAGANE = ("lokalo", "driver")


def wczytaj(sciezka: str) -> dict:
    if not os.path.isfile(sciezka):
        raise SystemExit(f"Brak pliku konfiguracji: {sciezka} (pobierz z panelu Lokalo).")
    with open(sciezka, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    braki = [k for k in WYMAGANE if not cfg.get(k)]
    if not (cfg.get("lokalo") or {}).get("url"):
        braki.append("lokalo.url")
    if not (cfg.get("lokalo") or {}).get("token"):
        braki.append("lokalo.token")
    if braki:
        raise SystemExit(f"Niekompletna konfiguracja ({sciezka}): brakuje {', '.join(braki)}.")

    cfg.setdefault("agent", {})
    cfg["agent"].setdefault("poll_sekundy", 300)
    cfg["agent"].setdefault("okno_dni", 3)
    return cfg
