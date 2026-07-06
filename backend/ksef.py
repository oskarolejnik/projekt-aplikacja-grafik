"""Integracja KSeF — generator faktury FA(3) + wysyłka (abstrakcja z trybem stub).

Tryby (env KSEF_TRYB):
- 'stub' (domyślnie) — generuje poprawny XML FA(3) i MOCKUJE przyjęcie (fałszywy numer KSeF+UPO),
  żeby cały przepływ fakturowania działał bez certyfikatu firmy. Do developmentu i sandboxu.
- 'test' / 'prod' — realna wysyłka przez bibliotekę `ksef2` na ksef-test.mf.gov.pl / produkcję.
  Wymaga certyfikatu (env KSEF_*), stąd TODO — cienki adapter, żeby wymiana biblioteki była tania.

Sprzedawca (operator) z env; nabywca (lokal) z argumentów. Patrz docs/ROADMAP-MONETYZACJA.md.
"""

from __future__ import annotations

import hashlib
import os
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone

import cennik

NS = "http://crd.gov.pl/wzor/2025/06/25/13775/"   # przestrzeń nazw FA(3)


def tryb() -> str:
    return os.getenv("KSEF_TRYB", "stub").strip().lower()


def sprzedawca() -> dict:
    """Dane operatora (sprzedawcy) z env; w trybie stub sensowne wartości testowe."""
    return {
        "nip": os.getenv("KSEF_SPRZEDAWCA_NIP", "0000000000"),
        "nazwa": os.getenv("KSEF_SPRZEDAWCA_NAZWA", "Lokalo (środowisko testowe)"),
        "adres_l1": os.getenv("KSEF_SPRZEDAWCA_ADRES_L1", "ul. Testowa 1"),
        "adres_l2": os.getenv("KSEF_SPRZEDAWCA_ADRES_L2", "00-001 Warszawa"),
    }


def _sub(parent, tag, text=None):
    el = ET.SubElement(parent, tag)
    if text is not None:
        el.text = str(text)
    return el


def _kwota(x) -> str:
    return f"{float(x):.2f}"


def generuj_fa3(*, numer, data_wystawienia, okres_od, okres_do, opis,
                netto, vat, brutto, stawka_vat_proc, nabywca, sprz=None, rodzaj="VAT") -> str:
    """Buduje XML FA(3) faktury za subskrypcję. `nabywca` = {nip,nazwa,adres_l1,adres_l2}.
    Zwraca string XML (UTF-8). Struktura wg minimalnego zestawu FA(3) (Naglowek/Podmiot1/2/Fa)."""
    sprz = sprz or sprzedawca()
    ET.register_namespace("", NS)
    root = ET.Element(f"{{{NS}}}Faktura")

    nag = _sub(root, f"{{{NS}}}Naglowek")
    kf = _sub(nag, f"{{{NS}}}KodFormularza", "FA")
    kf.set("kodSystemowy", "FA (3)"); kf.set("wersjaSchemy", "1-0E")
    _sub(nag, f"{{{NS}}}WariantFormularza", "3")
    _sub(nag, f"{{{NS}}}DataWytworzeniaFa",
         datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

    p1 = _sub(root, f"{{{NS}}}Podmiot1")
    di1 = _sub(p1, f"{{{NS}}}DaneIdentyfikacyjne")
    _sub(di1, f"{{{NS}}}NIP", sprz["nip"])
    _sub(di1, f"{{{NS}}}Nazwa", sprz["nazwa"])
    ad1 = _sub(p1, f"{{{NS}}}Adres")
    _sub(ad1, f"{{{NS}}}KodKraju", "PL")
    _sub(ad1, f"{{{NS}}}AdresL1", sprz["adres_l1"])
    _sub(ad1, f"{{{NS}}}AdresL2", sprz["adres_l2"])

    p2 = _sub(root, f"{{{NS}}}Podmiot2")
    di2 = _sub(p2, f"{{{NS}}}DaneIdentyfikacyjne")
    _sub(di2, f"{{{NS}}}NIP", nabywca.get("nip") or "")
    _sub(di2, f"{{{NS}}}Nazwa", nabywca.get("nazwa") or "")
    ad2 = _sub(p2, f"{{{NS}}}Adres")
    _sub(ad2, f"{{{NS}}}KodKraju", "PL")
    _sub(ad2, f"{{{NS}}}AdresL1", nabywca.get("adres_l1") or "")
    _sub(ad2, f"{{{NS}}}AdresL2", nabywca.get("adres_l2") or "")

    fa = _sub(root, f"{{{NS}}}Fa")
    _sub(fa, f"{{{NS}}}KodWaluty", "PLN")
    _sub(fa, f"{{{NS}}}P_1", str(data_wystawienia))
    _sub(fa, f"{{{NS}}}P_2", numer)
    if okres_od and okres_do:
        okr = _sub(fa, f"{{{NS}}}OkresFa")
        _sub(okr, f"{{{NS}}}P_6_Od", str(okres_od))
        _sub(okr, f"{{{NS}}}P_6_Do", str(okres_do))
    _sub(fa, f"{{{NS}}}P_13_1", _kwota(netto))
    _sub(fa, f"{{{NS}}}P_14_1", _kwota(vat))
    _sub(fa, f"{{{NS}}}P_15", _kwota(brutto))
    _sub(fa, f"{{{NS}}}RodzajFaktury", rodzaj)

    w = _sub(fa, f"{{{NS}}}FaWiersz")
    _sub(w, f"{{{NS}}}NrWierszaFa", "1")
    _sub(w, f"{{{NS}}}P_7", (opis or "")[:512])
    _sub(w, f"{{{NS}}}P_8B", "1")
    _sub(w, f"{{{NS}}}P_9A", _kwota(netto))
    _sub(w, f"{{{NS}}}P_11", _kwota(netto))
    _sub(w, f"{{{NS}}}P_12", str(int(stawka_vat_proc)))

    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def wyslij(xml: str, numer: str) -> tuple:
    """Wysyła fakturę do KSeF. Zwraca (ksef_number, upo, status).
    - stub: mock (fałszywy numer KSeF + UPO), status 'przyjeta' — przepływ działa bez certyfikatu.
    - test/prod: TODO realna wysyłka przez ksef2 (wymaga certyfikatu; env KSEF_*)."""
    if tryb() in ("test", "prod"):
        # TODO(Faza 3 prod): ksef2 → sesja → send_invoice(xml) → poll UPO + numer KSeF.
        #   Wymaga certyfikatu KSeF (pieczęć/token) firmy operatora. Do dopięcia z kluczami.
        raise NotImplementedError("Realna wysyłka KSeF (ksef2) — do dopięcia z certyfikatem operatora.")
    # stub: deterministyczny „numer KSeF" i UPO na podstawie treści faktury
    skrot = hashlib.sha256((numer + xml).encode("utf-8")).hexdigest()[:20].upper()
    ksef_number = f"TEST-{date.today():%Y%m%d}-{skrot}"
    upo = f"UPO-STUB-{skrot}"
    return ksef_number, upo, "przyjeta"


def opis_abonament(tier: str, okres_od, okres_do) -> str:
    nazwa = {"basic": "Basic", "pro": "Pro", "premium": "Premium", "enterprise": "Enterprise"}.get(tier, tier)
    return f"Abonament Lokalo {nazwa} — okres {okres_od}–{okres_do}"
