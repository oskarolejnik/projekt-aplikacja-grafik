#!/usr/bin/env python3
"""Pomocnik: pokazuje strukturę bazy RCP (tabele + kolumny), żeby ułożyć RCP_SQL.
Czyta TYLKO do odczytu (READ UNCOMMITTED). Nic nie zapisuje.

Użycie:
  python odkryj_schemat.py                # lista tabel i kolumn
  python odkryj_schemat.py NazwaTabeli    # + 5 przykładowych wierszy z tej tabeli
"""

import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

URL = os.environ.get("RCP_DATABASE_URL", "")
if not URL:
    print("Ustaw RCP_DATABASE_URL w .env (np. mssql+pymssql://czytelnik:***@host:1433/RCP).")
    sys.exit(2)

engine = create_engine(URL, pool_pre_ping=True)
PODPOWIEDZI = ("rcp", "czas", "rejestr", "odbic", "obecn", "pracow", "event", "time", "clock", "card", "karta")


def main():
    insp = inspect(engine)
    tabele = list(insp.get_table_names()) + list(insp.get_view_names())
    print(f"Znaleziono {len(tabele)} tabel/widoków.\n")

    if len(sys.argv) > 1:
        nazwa = sys.argv[1]
        print(f"== Kolumny {nazwa} ==")
        for c in insp.get_columns(nazwa):
            print(f"  - {c['name']} ({c['type']})")
        print(f"\n== 5 przykładowych wierszy z {nazwa} ==")
        with engine.connect() as conn:
            conn.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
            for row in conn.execute(text(f"SELECT TOP 5 * FROM [{nazwa}]")).mappings():
                print("  ", dict(row))
        return

    for t in sorted(tabele):
        gwiazdka = "  <-- możliwy kandydat" if any(p in t.lower() for p in PODPOWIEDZI) else ""
        kolumny = ", ".join(c["name"] for c in insp.get_columns(t))
        print(f"[{t}]{gwiazdka}\n    {kolumny}\n")

    print("Następnie: python odkryj_schemat.py <Tabela>  (zobacz przykładowe dane)")
    print("Na końcu ułóż RCP_SQL w .env wg kontraktu z .env.example.")


if __name__ == "__main__":
    main()
