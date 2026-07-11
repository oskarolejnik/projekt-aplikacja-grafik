"""Płatności zadatków online (Rec#7) — abstrakcja providera z trybem sandbox.

Bez realnej bramki (integracja "platnosci" nieskonfigurowana) działa w trybie SANDBOX:
generuje token i lokalny link „do zapłaty" (potwierdzenie/demo), status 'oczekuje'.
Realną bramkę (Stripe / Przelewy24) dopina się w `_utworz_u_dostawcy` — zwraca (provider, link).
Płatność oznacza się jako 'oplacona' przez webhook bramki albo ręcznie (admin). Nigdy nie rzuca.
"""

from __future__ import annotations

import logging
import secrets

import integracje
import models
from deps import utcnow_naive

logger = logging.getLogger(__name__)


def _utworz_u_dostawcy(kwota: float, external_id: str) -> tuple:
    """Zwraca (provider, link) dla płatności. Miejsce na realną bramkę Stripe/Przelewy24.
    Domyślnie tryb sandbox: lokalny link do potwierdzenia (do testów/demo)."""
    if integracje.skonfigurowane("platnosci"):
        # TODO: realna integracja bramki (Stripe/Przelewy24) — utwórz sesję płatności na `kwota`
        #       i zwróć (nazwa_providera, checkout_url). Do dopięcia z kluczami klienta.
        logger.info("Integracja płatności skonfigurowana — podłącz realną bramkę (TODO).")
        return ("api", f"/?platnosc={external_id}")
    return ("sandbox", f"/?platnosc={external_id}")


def utworz_platnosc(db, termin_id, kwota, *, commit: bool = True) -> models.Platnosc:
    """Tworzy płatność zadatku (status ``oczekuje``).

    ``commit=False`` pozwala rezerwacji, płatności i wynikowi idempotencji trafić do
    jednej transakcji. Dotychczasowi wywołujący zachowują historyczny auto-commit.
    """
    external_id = secrets.token_urlsafe(24)
    try:
        provider, link = _utworz_u_dostawcy(float(kwota or 0), external_id)
    except Exception as e:  # noqa: BLE001 — błąd bramki nie wywraca zapisu
        logger.warning("Błąd tworzenia płatności u dostawcy: %s", e)
        provider, link = ("sandbox", f"/?platnosc={external_id}")
    p = models.Platnosc(
        termin_id=termin_id, kwota=float(kwota or 0), status="oczekuje",
        provider=provider, external_id=external_id, link=link, utworzono_at=utcnow_naive(),
    )
    db.add(p)
    if commit:
        db.commit(); db.refresh(p)
    else:
        db.flush()
    return p


def _znajdz(db, external_id):
    return db.query(models.Platnosc).filter(models.Platnosc.external_id == external_id).first()


def oznacz_oplacona(db, external_id) -> models.Platnosc | None:
    """Oznacza płatność jako opłaconą (idempotentnie). Zwraca płatność albo None (nie znaleziono)."""
    p = _znajdz(db, external_id)
    if p is None:
        return None
    if p.status != "oplacona":
        p.status = "oplacona"
        p.oplacono_at = utcnow_naive()
        if p.termin_id:                                   # jedno źródło prawdy dla UI: kwota na Termin.zadatek
            t = db.get(models.Termin, p.termin_id)
            if t is not None:
                t.zadatek = p.kwota
        db.commit(); db.refresh(p)
    return p
