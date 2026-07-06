"""Cennik subskrypcji Lokalo — jedno źródło prawdy dla cen, poziomów i VAT.

Ceny NETTO miesięczne (zł). Poziom = porządek tierów (do walidacji upgrade/downgrade).
enterprise = wycena indywidualna (0 w cenniku → cena_netto ustawiana ręcznie na subskrypcji).
"""

CENNIK_NETTO = {
    "free": 0.0,
    "basic": 99.0,
    "pro": 199.0,
    "premium": 349.0,
    "enterprise": 0.0,   # wycena indywidualna — patrz Subskrypcja.cena_netto
}

POZIOM = {"free": 0, "basic": 1, "pro": 2, "premium": 3, "enterprise": 4}

STAWKA_VAT = 0.23

TIERY = tuple(CENNIK_NETTO)


def cena_netto(tier: str, override=None) -> float:
    """Cena netto tieru; `override` (Subskrypcja.cena_netto) ma pierwszeństwo — np. enterprise
    albo indywidualny rabat."""
    if override is not None:
        return round(float(override), 2)
    return round(CENNIK_NETTO.get(tier, 0.0), 2)


def brutto(netto: float) -> float:
    return round(float(netto) * (1 + STAWKA_VAT), 2)


def vat(netto: float) -> float:
    return round(float(netto) * STAWKA_VAT, 2)


def poziom(tier: str) -> int:
    return POZIOM.get(tier, 0)


# ── Moduły wg pakietu (tier-gating) ──────────────────────────────────────────
# Moduł → NAJNIŻSZY tier, który go odblokowuje. Rdzeń (auto-grafik, RCP→wypłaty,
# prognoza obsady, giełda zmian, strażnik prawa pracy) jest ZAWSZE dostępny (brak flagi).
# Kolejność = drabina wartości i ścieżka upsellu.
MODUL_MIN_TIER = {
    "modul_rozliczenia": "basic",     # Basic+: rozliczenia kasowe dnia
    "modul_rezerwacje":  "pro",       # Pro+: rezerwacje stolików + CRM gości
    "rezerwacje_online": "pro",       # Pro+: publiczny widget rezerwacji
    "modul_pos":         "pro",       # Pro+: integracja POS / stoły live / antyfraud
    "modul_imprezy":     "premium",   # Premium+: imprezy, wesela, zadatki
    "modul_sprzatanie":  "premium",   # Premium+: grafik sprzątania
}
WSZYSTKIE_MODULY = tuple(MODUL_MIN_TIER)

# Plan Free: pełny rdzeń, ale z limitem aktywnych pracowników — powyżej wymaga Basic+
# (dźwignia upsellu dla rosnących lokali). Płatne plany = bez limitu (None).
FREE_LIMIT_PRACOWNIKOW = 10


def moduly_dostepne(tier: str) -> set:
    """Zbiór modułów odblokowanych przez dany tier (wg MODUL_MIN_TIER). Enterprise = wszystkie."""
    p = poziom(tier)
    return {m for m, t in MODUL_MIN_TIER.items() if poziom(t) <= p}


def modul_dozwolony(tier: str, modul: str) -> bool:
    """Czy dany tier odblokowuje moduł."""
    return poziom(MODUL_MIN_TIER.get(modul, "free")) <= poziom(tier)


def plan_dla_modulu(modul: str) -> str:
    """Najniższy plan, który odblokowuje moduł (do etykiet upsellu „dostępne w …")."""
    return MODUL_MIN_TIER.get(modul, "free")


def limit_pracownikow(tier: str):
    """Limit aktywnych pracowników dla planu (None = bez limitu). Tylko Free jest limitowany."""
    return FREE_LIMIT_PRACOWNIKOW if tier == "free" else None
