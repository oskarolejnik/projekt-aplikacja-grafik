"""Driver Gastro (Softech/LSI) — lokalna baza MS SQL, odczyt read-only NOLOCK.
Największa baza legacy w PL. SQL-e strumieni w config.yaml (utarg + odbicia RCP).
S4H (też MSSQL) używa tego samego drivera z innym SQL-em."""

from ._sql_base import SqlDriver


class GastroMssqlDriver(SqlDriver):
    driver_id = "gastro_mssql"
    nazwa_bazy = "Gastro (MS SQL)"
    isolation_nolock = True
    test_sql = "SELECT 1"
