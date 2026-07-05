"""Płatności za subskrypcję (abonament + dopłaty upgrade) — abstrakcja providera z sandboxem.

Wzorzec jak platnosci.py (zadatki): bez realnej bramki działa w SANDBOX (link + ręczne
„opłacona"); driver stripe/p24 dopina się w _utworz_u_dostawcy (Faza 4). Opłacenie
abonamentu przedłuża Subskrypcja.data_do (Faza 4 przez webhook; teraz ręcznie w sandboxie).
"""

from __future__ import annotations

import logging
import secrets

import cennik
import integracje
import models
from deps import utcnow_naive

logger = logging.getLogger(__name__)


def _utworz_u_dostawcy(brutto: float, external_id: str) -> tuple:
    """(provider, link) dla płatności subskrypcji. Miejsce na Stripe/P24 (Faza 4)."""
    if integracje.skonfigurowane("platnosci"):
        logger.info("Integracja płatności skonfigurowana — podłącz bramkę subskrypcji (TODO Faza 4).")
        return ("api", f"/?platnosc-sub={external_id}")
    return ("sandbox", f"/?platnosc-sub={external_id}")


def utworz(db, rodzaj: str, tier: str, netto: float, okres_od=None, okres_do=None) -> models.PlatnoscSubskrypcji:
    """Tworzy płatność subskrypcji (status 'oczekuje') z rozbiciem VAT i linkiem."""
    netto = round(float(netto or 0), 2)
    brutto = cennik.brutto(netto)
    external_id = secrets.token_urlsafe(24)
    try:
        provider, link = _utworz_u_dostawcy(brutto, external_id)
    except Exception as e:  # noqa: BLE001 — błąd bramki nie wywraca zapisu
        logger.warning("Błąd tworzenia płatności subskrypcji u dostawcy: %s", e)
        provider, link = ("sandbox", f"/?platnosc-sub={external_id}")
    p = models.PlatnoscSubskrypcji(
        rodzaj=rodzaj, tier=tier, netto=netto, vat=cennik.vat(netto), brutto=brutto,
        okres_od=okres_od, okres_do=okres_do, status="oczekuje",
        provider=provider, external_id=external_id, link=link, utworzono_at=utcnow_naive(),
    )
    db.add(p); db.commit(); db.refresh(p)
    return p


def oznacz_oplacona(db, external_id) -> models.PlatnoscSubskrypcji | None:
    """Oznacza płatność subskrypcji jako opłaconą (idempotentnie)."""
    p = (db.query(models.PlatnoscSubskrypcji)
         .filter(models.PlatnoscSubskrypcji.external_id == external_id).first())
    if p is None:
        return None
    if p.status != "oplacona":
        p.status = "oplacona"
        p.oplacono_at = utcnow_naive()
        db.commit(); db.refresh(p)
    return p
