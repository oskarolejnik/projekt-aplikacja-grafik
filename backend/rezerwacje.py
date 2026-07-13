"""PII-safe agregat rezerwacji stolikowych z kanonicznego ``Termin``.

Historycznie moduł był mostem migracyjnym Google Calendar → ``Termin`` (tryby legacy/shadow/
canonical). Integracja Google została wycofana — czytamy WYŁĄCZNIE bazę (``Termin``). Zwracamy
tylko liczby, datę i godzinę: nazwisko, telefon, e-mail i notatka nigdy nie opuszczają bazy.
"""

import logging
from datetime import date, datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("Europe/Warsaw")
except Exception:  # noqa: BLE001
    _TZ = None

_STATUSY_KANONICZNE = ("rezerwacja", "potwierdzona", "odbyla")


def _dzis_lokalnie() -> date:
    now = datetime.now(_TZ) if _TZ else datetime.now()
    return now.date()


def rezerwacje_z_terminow(db, dni_naprzod: int = 30, start=None):
    """PII-safe agregat kanonicznych rezerwacji stolikowych z ``Termin``.

    Zakres jest półotwarty: ``[start, start + dni_naprzod)``. Zapytanie pobiera wyłącznie
    datę, godzinę i liczbę osób — nazwisko, telefon, e-mail i notatka nie opuszczają bazy.
    """
    start = start or _dzis_lokalnie()
    if isinstance(start, datetime):
        start = start.date()
    if dni_naprzod <= 0:
        return []
    end = start + timedelta(days=dni_naprzod)

    # Import leniwy utrzymuje moduł niezależny od inicjalizacji aplikacji/ORM.
    import models

    rows = (
        db.query(models.Termin.data, models.Termin.godz_od, models.Termin.liczba_osob)
        .filter(
            models.Termin.rodzaj == "stolik",
            models.Termin.data >= start,
            models.Termin.data < end,
            models.Termin.status.in_(_STATUSY_KANONICZNE),
        )
        .order_by(models.Termin.data, models.Termin.godz_od, models.Termin.id)
        .all()
    )

    dni = defaultdict(lambda: {
        "liczba": 0,
        "osoby": 0,
        "godz": defaultdict(lambda: {"liczba": 0, "osoby": 0}),
    })
    for data_rezerwacji, godz_od, liczba_osob in rows:
        osoby = int(liczba_osob or 0)
        godzina = godz_od.strftime("%H:%M") if godz_od else "—"
        dzien = dni[data_rezerwacji.isoformat()]
        dzien["liczba"] += 1
        dzien["osoby"] += osoby
        dzien["godz"][godzina]["liczba"] += 1
        dzien["godz"][godzina]["osoby"] += osoby

    wynik = []
    for data_iso in sorted(dni):
        dzien = dni[data_iso]
        godziny = [
            {"godzina": godzina, "liczba": wartosci["liczba"], "osoby": wartosci["osoby"]}
            for godzina, wartosci in sorted(dzien["godz"].items())
        ]
        wynik.append({
            "data": data_iso,
            "liczba": dzien["liczba"],
            "osoby": dzien["osoby"],
            "godziny": godziny,
        })
    return wynik


def czytaj_rezerwacje(db, dni_naprzod: int = 30, start=None):
    """Wspólny reader agregatu (pracownik/manager). Zawsze kanoniczny — czyta tylko ``Termin``."""
    return rezerwacje_z_terminow(db, dni_naprzod=dni_naprzod, start=start)
