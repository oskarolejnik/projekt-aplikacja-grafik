"""Wspólna baza driverów opartych na bazie SQL (Gastro/MSSQL, SOGA/Firebird, X2/Postgres,
S4H/MSSQL). Różnią się tylko: driver_id, sterownik w database_url, ewentualny hint izolacji
przed zapytaniem (NOLOCK dla MSSQL) i SQL testu połączenia. SQL-e strumieni z config.yaml.

Kontrakt kolumn (aliasy):
  utarg_sql   → data, netto, gotowka?, karta?, liczba_rachunkow?
  odbicia_sql → rcp_id, imie_nazwisko, pos_pracownik_id?, data, wejscie, wyjscie
Bindowane :start i :end (daty).
"""

from datetime import date, datetime

from sqlalchemy import create_engine, text

from .base import PosDriver


def _iso(v):
    if v is None:
        return None
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return str(v)


class SqlDriver(PosDriver):
    # Nadpisywane w podklasach:
    driver_id = "sql"
    test_sql = "SELECT 1"       # zapytanie testu połączenia
    isolation_nolock = False    # True dla MSSQL (READ UNCOMMITTED — zero blokad na tabelach POS)
    nazwa_bazy = "POS"

    def __init__(self, konfiguracja: dict):
        super().__init__(konfiguracja)
        self._engine = None

    @property
    def capabilities(self):
        caps = set()
        if self.konfiguracja.get("utarg_sql"):
            caps.add("utarg")
        if self.konfiguracja.get("odbicia_sql"):
            caps.add("odbicia")
        return caps

    def _polacz(self):
        if self._engine is None:
            self._engine = create_engine(self.konfiguracja["database_url"], pool_pre_ping=True)
        return self._engine

    def _zapytaj(self, sql, start, end):
        with self._polacz().connect() as conn:
            # NOLOCK tylko na realnym MSSQL — guard dialektu pozwala testować na SQLite.
            if self.isolation_nolock and conn.dialect.name == "mssql":
                conn.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
            return conn.execute(text(sql), {"start": start, "end": end}).mappings().all()

    def test_connection(self):
        try:
            with self._polacz().connect() as conn:
                conn.exec_driver_sql(self.test_sql)
            return True, f"Połączenie z bazą {self.nazwa_bazy} OK."
        except Exception as e:  # noqa: BLE001 — komunikat dla instalatora, nie stack
            return False, f"Brak połączenia z bazą {self.nazwa_bazy}: {e}"

    def fetch_utarg_dnia(self, start, end):
        sql = self.konfiguracja.get("utarg_sql")
        if not sql:
            return None
        out = []
        for r in self._zapytaj(sql, start, end):
            try:
                out.append({
                    "data": _iso(r["data"])[:10],
                    "netto": float(r.get("netto") or 0),
                    "gotowka": None if r.get("gotowka") is None else float(r["gotowka"]),
                    "karta": None if r.get("karta") is None else float(r["karta"]),
                    "liczba_rachunkow": (None if r.get("liczba_rachunkow") is None
                                         else int(r["liczba_rachunkow"])),
                })
            except (KeyError, TypeError, ValueError):
                continue
        return out

    def fetch_odbicia(self, start, end):
        sql = self.konfiguracja.get("odbicia_sql")
        if not sql:
            return None
        out = []
        for r in self._zapytaj(sql, start, end):
            try:
                out.append({
                    "rcp_id": str(r["rcp_id"]),
                    "imie_nazwisko": (r.get("imie_nazwisko") or "").strip(),
                    "pos_pracownik_id": (None if r.get("pos_pracownik_id") is None
                                         else str(r["pos_pracownik_id"])),
                    "data": _iso(r["data"])[:10],
                    "wejscie": _iso(r.get("wejscie")),
                    "wyjscie": _iso(r.get("wyjscie")),
                })
            except (KeyError, TypeError):
                continue
        return out
