"""Interfejs drivera POS uniwersalnego agenta Lokalo (docs/POS-INTEGRACJA.md).

Driver tłumaczy JEDEN system POS na kanoniczne payloady chmury. Jedyna metoda
obowiązkowa to `fetch_utarg_dnia` — dzienny agregat wystarcza do prognoz
i kosztu pracy. Reszta to capabilities: runner woła tylko te metody, dla których
driver zgłasza możliwość (na podstawie konfiguracji, np. obecności SQL-a).

Kanoniczne payloady (kontrakt z backendem Lokalo):
  utarg   → {"data": "YYYY-MM-DD", "netto": float,
             "gotowka": float|None, "karta": float|None, "liczba_rachunkow": int|None}
  odbicia → {"rcp_id": str, "imie_nazwisko": str, "data": "YYYY-MM-DD",
             "wejscie": iso|None, "wyjscie": iso|None}
"""


class PosDriver:
    """Klasa bazowa. Driver nadpisuje metody fetch_* dla swoich capabilities;
    nienaadpisana metoda zwraca None = capability niedostępna."""

    driver_id = "base"

    def __init__(self, konfiguracja: dict):
        self.konfiguracja = konfiguracja or {}

    @property
    def capabilities(self):
        """Zbiór dostępnych strumieni — driver wyznacza go z konfiguracji."""
        return set()

    def test_connection(self):
        """→ (ok: bool, komunikat: str). Wołane przy starcie agenta."""
        return False, "Driver bazowy nie łączy się z niczym."

    # --- capabilities (None = niedostępne w tym driverze/konfiguracji) ---

    def fetch_utarg_dnia(self, start, end):
        """→ lista payloadów utargu za [start, end] (WYMAGANE w każdym driverze)."""
        raise NotImplementedError

    def fetch_odbicia(self, start, end):
        return None
