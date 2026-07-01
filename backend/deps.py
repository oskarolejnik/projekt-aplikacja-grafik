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


def get_lokal_config(db) -> models.LokalConfig:
    """Singleton konfiguracji lokalu (id=1). Tworzony leniwie z domyślnymi wartościami."""
    cfg = db.get(models.LokalConfig, 1)
    if cfg is None:
        cfg = models.LokalConfig(id=1)
        db.add(cfg)
        try:
            db.commit(); db.refresh(cfg)
        except Exception:
            db.rollback()
            cfg = db.get(models.LokalConfig, 1)   # wyścig przy pierwszym zapisie — ktoś już utworzył
    return cfg


def rewir_dla_pracownika(rewir):
    """Ukrywa nazwę klienta/imprezy przed pracownikiem (model prywatności). Rewir imprezy ma
    postać „IMPREZA: {klient} ({sala})" — zwracamy tylko „Impreza ({sala})". Zwykłe rewiry bez zmian.
    Współdzielone przez main (/api/me/grafik, rozliczenia) i routery (giełda), żeby nazwisko klienta
    NIGDY nie wyciekło pracownikowi. Widoki managera (admin) mogą pokazywać surowy rewir."""
    if rewir and rewir.startswith("IMPREZA:"):
        sala = rewir[rewir.rfind("(") + 1 : -1].strip() if rewir.endswith(")") and "(" in rewir else ""
        return f"Impreza ({sala})" if sala and sala.lower() not in ("brak", "none") else "Impreza"
    return rewir
