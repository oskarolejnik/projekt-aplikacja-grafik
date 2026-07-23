"""Granularne uprawnienia: domyślna rola + wyjątki per konto.

Krytyczny enforcement tras nadal robi middleware ``role_guard``. Ten moduł jest
kanonicznym źródłem skutecznych uprawnień dla UI i redakcji danych w endpointach.
Konwencja klucza: ``<obszar>.<akcja>``.
"""

from __future__ import annotations

# Pełny katalog znanych uprawnień. Administrator zawsze dostaje wszystkie.
WSZYSTKIE = [
    "pulpit.podglad",
    "pracownicy.zarzadzaj",
    "stanowiska.zarzadzaj",
    "konta.zarzadzaj",
    "grafik.zarzadzaj",
    "grafik.podglad",
    "dyspozycje.zarzadzaj",
    "urlopy.zarzadzaj",
    "raporty.podglad",
    "wyplaty.podglad",
    "rozliczenia.zarzadzaj",
    "rozliczenia.podglad",
    "zeszyt.zarzadzaj",
    "zeszyt.podglad",
    "imprezy.zarzadzaj",
    "imprezy.podglad",
    "rezerwacje.zarzadzaj",
    "rezerwacje.podglad",
    "rezerwacje.operacje",
    "rezerwacje.host",
    "rezerwacje.nadpisuj_limity",
    "rezerwacje.sala",
    "rezerwacje.reguly",
    "rezerwacje.analityka",
    "rezerwacje.eksport",
    "rezerwacje.crm_zarzadzaj",
    "rezerwacje.finanse",
    "rezerwacje.dane_kontaktowe",
    "rezerwacje.notatki_wewnetrzne",
    "rezerwacje.dane_wrazliwe",
    "sprzatanie.zarzadzaj",
    "lokal.ustawienia",
    "integracje.podglad",
    "godziny_kuchni.podglad",
    "me.dyspozycje",
    "me.grafik",
    "me.godziny",
]

# Bezpieczny katalog praw zmienianych per konto nadzorcze. Administrator pozostaje
# nieograniczony; zapis rezerwacji jest egzekwowany osobno przez role_guard.
EDYTOWALNE_ODCZYTY = (
    "pulpit.podglad",
    "grafik.podglad",
    "raporty.podglad",
    "wyplaty.podglad",
    "rozliczenia.podglad",
    "zeszyt.podglad",
    "imprezy.podglad",
    "rezerwacje.podglad",
    "rezerwacje.operacje",
    "rezerwacje.host",
    "rezerwacje.nadpisuj_limity",
    "rezerwacje.sala",
    "rezerwacje.reguly",
    "rezerwacje.analityka",
    "rezerwacje.eksport",
    "rezerwacje.crm_zarzadzaj",
    "rezerwacje.finanse",
    "rezerwacje.dane_kontaktowe",
    "rezerwacje.notatki_wewnetrzne",
    "rezerwacje.dane_wrazliwe",
)


PRESET_RECEPCJA_HOST = "recepcja_host"
PRESETY = {
    PRESET_RECEPCJA_HOST: frozenset({
        "rezerwacje.operacje",
        "rezerwacje.host",
        "rezerwacje.nadpisuj_limity",
        "rezerwacje.dane_kontaktowe",
    }),
}

UPRAWNIENIA_ROLI = {
    "admin": list(WSZYSTKIE),
    # Szef domyślnie zachowuje dotychczasowe odczyty; admin może je zawęzić per konto.
    "szef": [
        "pulpit.podglad",
        "raporty.podglad",
        "wyplaty.podglad",
        "rozliczenia.podglad",
        "zeszyt.podglad",
        "grafik.podglad",
        "imprezy.podglad",
        "rezerwacje.podglad",
    ],
    "szef_kuchni": [
        "godziny_kuchni.podglad",
        "grafik.podglad",
        "rezerwacje.podglad",
    ],
    "kuchnia": ["me.grafik", "me.godziny"],
    "employee": ["me.dyspozycje", "me.grafik", "me.godziny"],
}


def uprawnienia(rola: str) -> list:
    """Lista domyślnych uprawnień roli (pusta dla nieznanej)."""
    return list(UPRAWNIENIA_ROLI.get(rola, []))


def ma(rola: str, perm: str) -> bool:
    """Czy rola ma dane uprawnienie domyślnie (stary, kompatybilny interfejs)."""
    return perm in UPRAWNIENIA_ROLI.get(rola, [])


def efektywne(user) -> list[str]:
    """Lista uprawnień po nałożeniu bezpiecznych wyjątków konkretnego konta.

    Nieznane klucze i wartości inne niż bool są ignorowane. Administrator zawsze
    zachowuje pełny katalog, nawet jeśli w bazie pozostały stare override'y.
    """
    rola = getattr(user, "rola", None)
    if rola == "admin":
        return list(WSZYSTKIE)
    if rola not in UPRAWNIENIA_ROLI:
        return []

    wynik = set(UPRAWNIENIA_ROLI[rola])
    override = getattr(user, "uprawnienia_override", None)
    if isinstance(override, dict):
        for perm in EDYTOWALNE_ODCZYTY:
            wartosc = override.get(perm)
            if type(wartosc) is not bool:
                continue
            if wartosc:
                wynik.add(perm)
            else:
                wynik.discard(perm)
    return [perm for perm in WSZYSTKIE if perm in wynik]


def ma_user(user, perm: str) -> bool:
    """Czy konkretne konto ma dane skuteczne uprawnienie."""
    return perm in efektywne(user)


def znormalizuj_override(rola: str, mapa: dict) -> dict[str, bool]:
    """Zostawia tylko boolowskie odchylenia od domyślnych wartości roli."""
    if rola == "admin" or rola not in UPRAWNIENIA_ROLI:
        return {}
    domyslne = set(UPRAWNIENIA_ROLI[rola])
    return {
        perm: mapa[perm]
        for perm in EDYTOWALNE_ODCZYTY
        if perm in mapa
        and type(mapa[perm]) is bool
        and mapa[perm] != (perm in domyslne)
    }


def override_dla_presetu(rola: str, preset: str) -> dict[str, bool]:
    """Pełny zestaw odchyleń, który daje dokładnie wskazany preset bez nowej roli domenowej."""
    if rola != "szef" or preset not in PRESETY:
        raise ValueError("unsupported permission preset")
    docelowe = PRESETY[preset]
    domyslne = set(UPRAWNIENIA_ROLI[rola])
    return {
        perm: perm in docelowe
        for perm in EDYTOWALNE_ODCZYTY
        if (perm in docelowe) != (perm in domyslne)
    }


def rozpoznaj_preset(user) -> str | None:
    """Zwraca nazwę presetu tylko przy dokładnym dopasowaniu skutecznych praw konta."""
    if getattr(user, "rola", None) != "szef":
        return None
    effective = set(efektywne(user))
    for name, permissions in PRESETY.items():
        if effective == set(permissions):
            return name
    return None
