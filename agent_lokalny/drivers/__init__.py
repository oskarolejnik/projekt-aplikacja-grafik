"""Rejestr driverów POS. Nowy system = nowy moduł + wpis tutaj (nic więcej)."""

from .gastro_mssql import GastroMssqlDriver
from .soga_firebird import SogaFirebirdDriver
from .x2_postgres import X2PostgresDriver

DRIVERY = {
    GastroMssqlDriver.driver_id: GastroMssqlDriver,   # Gastro/Softech-LSI, S4H (MSSQL)
    SogaFirebirdDriver.driver_id: SogaFirebirdDriver,  # SOGA/NSoft (Firebird)
    X2PostgresDriver.driver_id: X2PostgresDriver,      # X2System/Adith (PostgreSQL)
}


def zbuduj_driver(nazwa: str, konfiguracja: dict):
    if nazwa not in DRIVERY:
        raise ValueError(f"Nieznany driver '{nazwa}'. Dostępne: {', '.join(sorted(DRIVERY))}")
    return DRIVERY[nazwa](konfiguracja)
