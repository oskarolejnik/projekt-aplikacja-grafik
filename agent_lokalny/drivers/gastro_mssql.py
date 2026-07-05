"""Driver Gastro (Softech/LSI) — lokalna baza MS SQL, odczyt read-only NOLOCK.

Dzisiejszy `agent.py` (tylko odbicia RCP) przeniesiony pod interfejs PosDriver
+ nowy strumień utargu dziennego. SQL-e siedzą w config.yaml, więc różnice
wersji Gastro nie wymagają nowego wydania agenta.

Kontrakt SQL-i (aliasy kolumn):
  utarg_sql   → data (DATE), netto, gotowka?, karta?, liczba_rachunkow?
  odbicia_sql → rcp_id, imie_nazwisko, data, wejscie, wyjscie
Oba dostają bindowane :start i :end (daty).
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


class GastroMssqlDriver(PosDriver):
    driver_id = "gastro_mssql"

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

    def _zapytaj(self, sql: str, start, end):
        with self._polacz().connect() as conn:
            # Bezpieczeństwo Gastro: zero blokad na tabelach POS (READ UNCOMMITTED),
            # wyłącznie SELECT, wąskie okno dat. Guard dialektu pozwala testować
            # driver na innej bazie (np. SQLite w smoke-testach).
            if conn.dialect.name == "mssql":
                conn.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
            return conn.execute(text(sql), {"start": start, "end": end}).mappings().all()

    def test_connection(self):
        try:
            with self._polacz().connect() as conn:
                conn.exec_driver_sql("SELECT 1")
            return True, "Połączenie z bazą Gastro OK."
        except Exception as e:  # noqa: BLE001 — komunikat dla instalatora, nie stack
            return False, f"Brak połączenia z bazą Gastro: {e}"

    def fetch_utarg_dnia(self, start, end):
        sql = self.konfiguracja.get("utarg_sql")
        if not sql:
            return None
        dni = []
        for r in self._zapytaj(sql, start, end):
            try:
                dni.append({
                    "data": _iso(r["data"])[:10],
                    "netto": float(r.get("netto") or 0),
                    "gotowka": None if r.get("gotowka") is None else float(r["gotowka"]),
                    "karta": None if r.get("karta") is None else float(r["karta"]),
                    "liczba_rachunkow": (None if r.get("liczba_rachunkow") is None
                                         else int(r["liczba_rachunkow"])),
                })
            except (KeyError, TypeError, ValueError):
                continue
        return dni

    def fetch_odbicia(self, start, end):
        sql = self.konfiguracja.get("odbicia_sql")
        if not sql:
            return None
        odbicia = []
        for r in self._zapytaj(sql, start, end):
            try:
                odbicia.append({
                    "rcp_id": str(r["rcp_id"]),
                    "imie_nazwisko": (r.get("imie_nazwisko") or "").strip(),
                    "data": _iso(r["data"])[:10],
                    "wejscie": _iso(r.get("wejscie")),
                    "wyjscie": _iso(r.get("wyjscie")),
                })
            except (KeyError, TypeError):
                continue
        return odbicia
