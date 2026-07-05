"""Driver SOGA (NSoft, dystrybucja Novitus) — lokalna baza Firebird (open source, łatwy odczyt).
Ten sam interfejs co reszta driverów SQL; różni się sterownikiem (firebird) i domyślnymi SQL-ami.
Wymaga: pip install firebird-driver (lub sqlalchemy-firebird) — patrz requirements.txt.
Przykład database_url: firebird+firebird://SYSDBA:haslo@localhost:3050//sciezka/SOGA.FDB"""

from ._sql_base import SqlDriver


class SogaFirebirdDriver(SqlDriver):
    driver_id = "soga_firebird"
    nazwa_bazy = "SOGA (Firebird)"
    test_sql = "SELECT 1 FROM RDB$DATABASE"
