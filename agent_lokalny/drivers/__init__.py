"""Rejestr driverów POS. Nowy system = nowy moduł + wpis tutaj (nic więcej)."""

from .gastro_mssql import GastroMssqlDriver

DRIVERY = {
    GastroMssqlDriver.driver_id: GastroMssqlDriver,
    # "soga_firebird": ...   (faza 2 — patrz docs/POS-INTEGRACJA.md)
    # "x2_postgres":   ...   (faza 2)
}


def zbuduj_driver(nazwa: str, konfiguracja: dict):
    if nazwa not in DRIVERY:
        raise ValueError(f"Nieznany driver '{nazwa}'. Dostępne: {', '.join(sorted(DRIVERY))}")
    return DRIVERY[nazwa](konfiguracja)
