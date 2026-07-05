"""Driver X2System (Adith) — lokalna baza PostgreSQL. Sieci wielolokalowe.
Ten sam interfejs co reszta driverów SQL. Wymaga: pip install psycopg2-binary.
Przykład database_url: postgresql+psycopg2://czytelnik:haslo@localhost:5432/x2"""

from ._sql_base import SqlDriver


class X2PostgresDriver(SqlDriver):
    driver_id = "x2_postgres"
    nazwa_bazy = "X2System (PostgreSQL)"
    test_sql = "SELECT 1"
