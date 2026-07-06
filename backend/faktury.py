"""Wystawianie faktur za subskrypcję: numeracja + budowa Faktura z płatności + wysyłka KSeF.

Nabywca = dane firmowe lokalu (LokalConfig.faktura_*), sprzedawca = operator (ksef.sprzedawca()).
Faktura powstaje po OPŁACENIU płatności subskrypcji (abonament/dopłata). W trybie stub numer KSeF
i UPO są mockowane — cały przepływ działa bez certyfikatu firmy.
"""

from __future__ import annotations

import logging
from datetime import date

import cennik
import ksef
import models
from deps import utcnow_naive, get_lokal_config

logger = logging.getLogger(__name__)


def _nastepny_numer(db, dzis: date) -> str:
    """Kolejny numer faktury w miesiącu: LOK/RRRR/MM/NNNN (sekwencja per miesiąc)."""
    prefiks = f"LOK/{dzis:%Y}/{dzis:%m}/"
    ostatni = (db.query(models.Faktura)
               .filter(models.Faktura.numer.like(prefiks + "%"))
               .order_by(models.Faktura.numer.desc()).first())
    n = 1
    if ostatni:
        try:
            n = int(ostatni.numer.rsplit("/", 1)[1]) + 1
        except (ValueError, IndexError):
            n = 1
    return f"{prefiks}{n:04d}"


def _nabywca(db) -> dict:
    cfg = get_lokal_config(db)
    return {"nip": cfg.faktura_nip, "nazwa": cfg.faktura_nazwa or cfg.nazwa_lokalu,
            "adres_l1": cfg.faktura_adres_l1, "adres_l2": cfg.faktura_adres_l2}


def wystaw_z_platnosci(db, platnosc: models.PlatnoscSubskrypcji) -> models.Faktura:
    """Wystawia fakturę VAT za opłaconą płatność subskrypcji (idempotentnie — jedna faktura/płatność)."""
    istn = db.query(models.Faktura).filter_by(platnosc_id=platnosc.id).first()
    if istn:
        return istn

    dzis = date.today()
    nabywca = _nabywca(db)
    if platnosc.rodzaj == "doplata":
        opis = f"Dopłata do pakietu {platnosc.tier} — okres {platnosc.okres_od}–{platnosc.okres_do}"
    else:
        opis = ksef.opis_abonament(platnosc.tier, platnosc.okres_od, platnosc.okres_do)

    numer = _nastepny_numer(db, dzis)
    xml = ksef.generuj_fa3(
        numer=numer, data_wystawienia=dzis, okres_od=platnosc.okres_od, okres_do=platnosc.okres_do,
        opis=opis, netto=platnosc.netto, vat=platnosc.vat, brutto=platnosc.brutto,
        stawka_vat_proc=round(cennik.STAWKA_VAT * 100), nabywca=nabywca)

    f = models.Faktura(
        numer=numer, platnosc_id=platnosc.id, rodzaj="VAT",
        nabywca_nip=nabywca["nip"], nabywca_nazwa=nabywca["nazwa"],
        netto=platnosc.netto, vat=platnosc.vat, brutto=platnosc.brutto,
        okres_od=platnosc.okres_od, okres_do=platnosc.okres_do, opis=opis, xml=xml,
        status_ksef="roboczy", data_wystawienia=dzis, utworzono_at=utcnow_naive())
    db.add(f); db.flush()

    try:
        ksef_number, upo, status = ksef.wyslij(xml, numer)
        f.ksef_number = ksef_number; f.upo = upo; f.status_ksef = status
    except Exception as e:  # noqa: BLE001 — brak KSeF nie wywraca płatności; faktura zostaje 'roboczy'
        logger.warning("Wysyłka faktury %s do KSeF nie powiodła się: %s", numer, e)
        f.status_ksef = "blad"
    db.commit(); db.refresh(f)
    return f


def wyslij_ponownie(db, faktura: models.Faktura) -> models.Faktura:
    """Ponawia wysyłkę faktury do KSeF (gdy poprzednia zakończyła się błędem)."""
    try:
        ksef_number, upo, status = ksef.wyslij(faktura.xml or "", faktura.numer)
        faktura.ksef_number = ksef_number; faktura.upo = upo; faktura.status_ksef = status
    except Exception as e:  # noqa: BLE001
        logger.warning("Ponowna wysyłka faktury %s nie powiodła się: %s", faktura.numer, e)
        faktura.status_ksef = "blad"
    db.commit(); db.refresh(faktura)
    return faktura
