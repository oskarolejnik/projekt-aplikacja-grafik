"""Logika billingu subskrypcji: proration przy zmianie planu w środku okresu.

Wymaganie: lokal z Pro (199) przechodzący na Premium (349) dopłaca TYLKO RÓŻNICĘ za
pozostałe dni okresu, nie pełną cenę. Downgrade = kredyt na saldo (kolejna płatność mniejsza).

Czyste funkcje (bez DB) — łatwe do testu. Ceny netto podaje wołający (z cennik.py).
"""

from datetime import date

import cennik


def _okno(data_od, data_do, dzis):
    """(dni_w_okresie, pozostale_dni). Gdy brak okresu (bezterminowa/free) → (0, 0)."""
    if not data_od or not data_do or data_do < data_od:
        return 0, 0
    dni = (data_do - data_od).days + 1
    pozostale = max(0, (data_do - dzis).days + 1) if dzis <= data_do else 0
    return dni, min(pozostale, dni)


def oblicz_prorate(stary_tier, nowy_tier, data_od, data_do,
                   dzis=None, cena_override_stary=None, cena_override_nowy=None,
                   saldo_kredytu=0.0):
    """Rozbicie zmiany planu. Zwraca dict:
      kierunek: upgrade|downgrade|bez_zmiany
      wspolczynnik, pozostale_dni, dni_w_okresie
      roznica_netto: (nowa−stara)·współczynnik (dodatnia=dopłata, ujemna=kredyt)
      doplata_netto: do zapłaty TERAZ (upgrade; po odjęciu salda kredytu, ≥0)
      kredyt_netto:  dopisany do salda (downgrade; ≥0)
      vat, brutto: dla doplata_netto
      nowa_cena_pelna: pełna cena nowego tieru od następnego okresu
    """
    dzis = dzis or date.today()
    stara = cennik.cena_netto(stary_tier, cena_override_stary)
    nowa = cennik.cena_netto(nowy_tier, cena_override_nowy)
    poz_s, poz_n = cennik.poziom(stary_tier), cennik.poziom(nowy_tier)

    dni, pozostale = _okno(data_od, data_do, dzis)
    wsp = round(pozostale / dni, 4) if dni else 0.0
    roznica = round((nowa - stara) * wsp, 2)

    kierunek = "bez_zmiany" if poz_n == poz_s else ("upgrade" if poz_n > poz_s else "downgrade")
    doplata = kredyt = 0.0
    if kierunek == "upgrade":
        doplata = round(max(0.0, roznica - float(saldo_kredytu or 0)), 2)
    elif kierunek == "downgrade":
        kredyt = round(abs(roznica), 2)

    return {
        "kierunek": kierunek,
        "stary_tier": stary_tier, "nowy_tier": nowy_tier,
        "stara_cena_netto": stara, "nowa_cena_netto": nowa,
        "wspolczynnik": wsp, "pozostale_dni": pozostale, "dni_w_okresie": dni,
        "roznica_netto": roznica,
        "doplata_netto": doplata, "doplata_vat": cennik.vat(doplata), "doplata_brutto": cennik.brutto(doplata),
        "kredyt_netto": kredyt,
        "saldo_kredytu_uzyte": round(min(float(saldo_kredytu or 0), max(0.0, roznica)), 2) if kierunek == "upgrade" else 0.0,
        "nowa_cena_pelna_netto": nowa,
    }
