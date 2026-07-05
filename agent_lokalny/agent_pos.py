#!/usr/bin/env python3
"""Uniwersalny agent POS Lokalo — rdzeń + wymienne drivery (docs/POS-INTEGRACJA.md).

Instalacja u klienta:
  1. W panelu Lokalo: Ustawienia → Utarg (POS) → „Podłącz agenta" → pobierz config.yaml
     (token i adres instancji są już wypełnione).
  2. Na serwerze POS uzupełnij w config.yaml dane bazy (connection string READ-ONLY!)
     i ewentualnie SQL-e strumieni.
  3. pip install -r requirements.txt
  4. Test:   python agent_pos.py --raz         (jeden cykl + heartbeat, kod wyjścia ≠0 przy błędzie)
     Praca:  python agent_pos.py               (pętla; rejestruj jako usługę/Harmonogram zadań)

Legacy `agent.py` (tylko odbicia RCP, konfiguracja .env) działa dalej bez zmian —
ten agent to jego następca dla nowych wdrożeń.
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.config import wczytaj          # noqa: E402
from core.runner import uruchom          # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])


def main():
    p = argparse.ArgumentParser(description="Uniwersalny agent POS Lokalo")
    p.add_argument("--config", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml"),
                   help="ścieżka do config.yaml (domyślnie obok agenta)")
    p.add_argument("--raz", action="store_true",
                   help="wykonaj jeden cykl i zakończ (test instalacji)")
    args = p.parse_args()
    uruchom(wczytaj(args.config), raz=args.raz)


if __name__ == "__main__":
    main()
