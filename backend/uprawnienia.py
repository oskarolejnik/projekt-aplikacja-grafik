"""Granularne uprawnienia (RBAC) — warstwa NAD rolami (User.rola).

Mapuje rolę na zbiór uprawnień (stringi 'obszar.akcja'). To warstwa GRANULARNA do
sterowania UI i fundament pod przyszłe role własne / nadawanie uprawnień per konto.
Krytyczny enforcement po stronie API dalej robi middleware `role_guard` — ten moduł
go NIE zastępuje (zmiana enforcement = ryzyko regresji ról).

Konwencja: '<obszar>.<akcja>', akcja 'zarzadzaj' (pełny dostęp) / 'podglad' (tylko odczyt).
"""

# Pełny katalog uprawnień (admin dostaje wszystkie).
WSZYSTKIE = [
    "pulpit.podglad",
    "pracownicy.zarzadzaj",
    "stanowiska.zarzadzaj",
    "konta.zarzadzaj",
    "grafik.zarzadzaj",
    "dyspozycje.zarzadzaj",
    "urlopy.zarzadzaj",
    "raporty.podglad",
    "rozliczenia.zarzadzaj",
    "zeszyt.zarzadzaj",
    "imprezy.zarzadzaj",
    "rezerwacje.zarzadzaj",
    "sprzatanie.zarzadzaj",
    "lokal.ustawienia",
    "integracje.podglad",
    "godziny_kuchni.podglad",
    "me.dyspozycje",
    "me.grafik",
    "me.godziny",
]

UPRAWNIENIA_ROLI = {
    # Administrator — pełnia uprawnień.
    "admin": list(WSZYSTKIE),
    # Szef — oversight (tylko podgląd) finansów, grafiku, imprez, rezerwacji.
    "szef": ["pulpit.podglad", "raporty.podglad", "rozliczenia.podglad", "zeszyt.podglad",
             "grafik.podglad", "imprezy.podglad", "rezerwacje.podglad"],
    # Szef kuchni — godziny kuchni (bez wypłat), grafik kuchni, rezerwacje (planowanie).
    "szef_kuchni": ["godziny_kuchni.podglad", "grafik.podglad", "rezerwacje.podglad"],
    # Pracownik kuchni / obsługi — samoobsługa.
    "kuchnia": ["me.grafik", "me.godziny"],
    "employee": ["me.dyspozycje", "me.grafik", "me.godziny"],
}


def uprawnienia(rola: str) -> list:
    """Lista uprawnień dla roli (pusta dla nieznanej)."""
    return list(UPRAWNIENIA_ROLI.get(rola, []))


def ma(rola: str, perm: str) -> bool:
    """Czy rola ma dane uprawnienie."""
    return perm in UPRAWNIENIA_ROLI.get(rola, [])
