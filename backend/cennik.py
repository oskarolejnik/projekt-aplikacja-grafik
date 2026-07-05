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
