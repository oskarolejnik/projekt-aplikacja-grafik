"""Strażnik prawa pracy — walidacja ręcznego przydziału zmian (roadmapa v1.5).

Czyste funkcje (bez DB) sprawdzające ograniczenia Kodeksu pracy przy dodawaniu nowej
zmiany pracownikowi. Parametry (limity) pochodzą z LokalConfig; 0 = limit wyłączony.

Model danych zmiany ma tylko godzinę STARTU (godz_od), bez godziny końca — dlatego:
  • odpoczynek liczymy jako różnicę momentów startu dwóch zmian (start-do-startu).
    Dla realnych grafików (zamknięcie wieczorem → otwarcie rano) to konserwatywne,
    poprawne zabezpieczenie; gdy któraś zmiana nie ma godz_od, reguły nie stosujemy.
  • limity tygodnia/miesiąca liczymy w DNIACH pracy (1 zmiana = 1 dzień; maks. 1/dzień
    egzekwuje osobna reguła w endpoincie).
"""

from datetime import date, datetime, time, timedelta
from typing import List, Optional, Tuple


def _moment(d: date, g: Optional[time]) -> Optional[datetime]:
    return datetime.combine(d, g) if g is not None else None


def naruszenie_odpoczynku(inne: List[Tuple[date, Optional[time]]],
                          data: date, godz_od: Optional[time], min_h: int) -> Optional[str]:
    """Zwraca komunikat, gdy nowa zmiana łamie minimalny odpoczynek względem istniejących
    zmian pracownika; inaczej None. `inne` = (data, godz_od) pozostałych zmian pracownika."""
    if not min_h or godz_od is None:
        return None
    t = _moment(data, godz_od)
    prog = timedelta(hours=min_h)
    for d2, g2 in inne:
        t2 = _moment(d2, g2)
        if t2 is None:
            continue
        if abs(t - t2) < prog:
            return f"Za krótki odpoczynek między zmianami — wymagane min. {min_h} h."
    return None


def granice_tygodnia(data: date) -> Tuple[date, date]:
    """Poniedziałek–niedziela tygodnia zawierającego `data`."""
    poniedzialek = data - timedelta(days=data.weekday())
    return poniedzialek, poniedzialek + timedelta(days=6)


def naruszenie_limitu_tygodnia(daty_pracownika: List[date], data: date, max_dni: int) -> Optional[str]:
    """Komunikat, gdy dodanie zmiany przekroczy limit dni pracy w tygodniu; inaczej None."""
    if not max_dni:
        return None
    od, do = granice_tygodnia(data)
    w_tygodniu = {d for d in daty_pracownika if od <= d <= do}
    w_tygodniu.add(data)
    if len(w_tygodniu) > max_dni:
        return f"Przekroczony limit dni pracy w tygodniu (maks. {max_dni})."
    return None


def naruszenie_limitu_miesiaca(daty_pracownika: List[date], data: date, max_dni: int) -> Optional[str]:
    """Komunikat, gdy dodanie zmiany przekroczy limit dni pracy w miesiącu; inaczej None."""
    if not max_dni:
        return None
    w_miesiacu = {d for d in daty_pracownika if d.year == data.year and d.month == data.month}
    w_miesiacu.add(data)
    if len(w_miesiacu) > max_dni:
        return f"Przekroczony limit dni pracy w miesiącu (maks. {max_dni})."
    return None


def sprawdz(inne: List[Tuple[date, Optional[time]]], data: date, godz_od: Optional[time],
           min_odpoczynek_h: int, max_dni_tydzien: int, max_dni_miesiac: int) -> Optional[str]:
    """Uruchamia wszystkie reguły; zwraca PIERWSZY komunikat o naruszeniu lub None.
    `inne` = lista (data, godz_od) pozostałych zmian pracownika (bez tej dodawanej)."""
    daty = [d for d, _ in inne]
    return (
        naruszenie_odpoczynku(inne, data, godz_od, min_odpoczynek_h)
        or naruszenie_limitu_tygodnia(daty, data, max_dni_tydzien)
        or naruszenie_limitu_miesiaca(daty, data, max_dni_miesiac)
    )
