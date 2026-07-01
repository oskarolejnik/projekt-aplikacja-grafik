"""Współdzielone helpery używane zarówno przez main.py, jak i przez routery.

Wydzielone tutaj, aby routery mogły z nich korzystać BEZ importowania main.py
(co dawałoby cykl importów: main → router → main). Zależą tylko od models.
"""

from datetime import date, datetime, timezone

import models


def utcnow_naive() -> datetime:
    """Bieżący czas UTC jako NAIWNY datetime (bez tzinfo) — zamiennik przestarzałego
    `datetime.utcnow()` (deprecated od Pythona 3.12). Zachowuje dotychczasowy format
    zapisu w kolumnach DateTime (naiwny UTC, spójny na SQLite i PostgreSQL)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_subskrypcja(db) -> models.Subskrypcja:
    """Singleton subskrypcji/licencji instancji (id=1). Tworzony leniwie (domyślnie aktywny)."""
    s = db.get(models.Subskrypcja, 1)
    if s is None:
        s = models.Subskrypcja(id=1)
        db.add(s)
        try:
            db.commit(); db.refresh(s)
        except Exception:
            db.rollback()
            s = db.get(models.Subskrypcja, 1)   # wyścig przy pierwszym zapisie — ktoś już utworzył
    return s


def subskrypcja_aktywna(db) -> bool:
    """Czy instancja ma aktywną subskrypcję (status aktywna/trial i przed data_do)."""
    s = get_subskrypcja(db)
    if s is None or s.status not in ("aktywna", "trial"):
        return False
    return s.data_do is None or s.data_do >= date.today()
