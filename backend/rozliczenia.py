"""Rozliczenie zmiany (dnia) — silnik liczący 1:1 z papierowego zeszytu właściciela.

Wejście (kwoty w zł):
  • kelnerzy — lista deklaracji kelnerów Sali: [{"gotowka": G, "karta": T}, ...]  (kelner wpisuje TYLKO G i T),
  • fv             — suma faktur (KARTA_FV + GOTÓWKA_FV) z Gastro (poza kasą fiskalną),
  • terminale      — lista kwot z wydruków terminali (wpisują zamykający rewir/lokal),
  • kasy           — lista kwot z raportów dobowych kas fiskalnych (j.w.),
  • zadatek_gotowka/_karta — zadatki dnia (KP) ROZBITE przez admina na gotówkę i kartę.
        Zadatki czytamy GLOBALNIE z Gastro (forma „KP", wszystkie osoby — przyjmuje je zwykle
        menadżer, który nie drukuje własnego rozliczenia). Przechodzą przez kasę i ZMNIEJSZAJĄ
        utarg podawany szefowi; admin decyduje, czy zdjąć je z gotówki czy z karty,
  • kw             — kasa WYDANA (np. zwrot kaucji) — powiększa utarg gotówkowy,
  • imp            — IMP z imprez: {"gotowka_sfiskalizowana": x, "karta": y} (z imp_dla_dnia lub ręcznie).

Reguły (potwierdzone na realnym przykładzie z arkusza):
  DO SZEFA   = Σ kelnerzy + KW − zadatek   (G zdejmuje zadatek_gotowka; T zdejmuje zadatek_karta),
  ZAFISKALIZOWANE (utarg sali) = Σ kelnerzy + KW   (bez zdejmowania zadatku),
  TERMINALE  = Σ terminale − IMP_karta ;  różnica_kart = TERMINALE − Σ deklaracje_karty,
  KASY       = Σ kasy + FV − IMP_kasy − zadatek ;  różnica = DO SZEFA − KASY  (zadatek się skraca),
  gdzie IMP_karta = imp.karta ; IMP_kasy = imp.gotowka_sfiskalizowana + imp.karta.
"""


def _suma(xs):
    return round(sum(float(x or 0) for x in xs), 2)


def policz_dzien(kelnerzy=None, fv=0.0, terminale=None, kasy=None,
                 zadatek_gotowka=0.0, zadatek_karta=0.0, kw=0.0, imp=None):
    kelnerzy = kelnerzy or []
    terminale = terminale or []
    kasy = kasy or []
    imp = imp or {}
    fv = float(fv or 0)
    zadatek_gotowka = float(zadatek_gotowka or 0)
    zadatek_karta = float(zadatek_karta or 0)
    zadatek = round(zadatek_gotowka + zadatek_karta, 2)
    kw = float(kw or 0)
    imp_got_sfisk = float(imp.get("gotowka_sfiskalizowana") or 0)
    imp_karta = float(imp.get("karta") or 0)

    sigma_G = _suma(k.get("gotowka") for k in kelnerzy)   # Σ zadeklarowana gotówka (Sala)
    sigma_T = _suma(k.get("karta") for k in kelnerzy)      # Σ zadeklarowana karta (Sala)

    # „Do szefa" — utarg sali pomniejszony o zadatek (zdejmowany z właściwej formy)
    suma_szef_G = round(sigma_G + kw - zadatek_gotowka, 2)
    suma_szef_T = round(sigma_T - zadatek_karta, 2)
    suma_szef = round(suma_szef_G + suma_szef_T, 2)
    # „Zafiskalizowane" — utarg sali bez zdejmowania zadatku
    suma_zeszyt_G = round(sigma_G + kw, 2)
    suma_zeszyt_T = round(sigma_T, 2)

    imp_terminale = imp_karta
    imp_kasy = round(imp_got_sfisk + imp_karta, 2)

    terminale_suma = round(_suma(terminale) - imp_terminale, 2)
    roznica_karty = round(terminale_suma - sigma_T, 2)     # < 0 = brak na kartach, > 0 = nadwyżka

    kasy_suma = round(_suma(kasy) + fv - imp_kasy - zadatek, 2)
    roznica_calosc = round(suma_szef - kasy_suma, 2)       # < 0 = brak, > 0 = nadwyżka

    return {
        "sigma_gotowka": sigma_G, "sigma_karta": sigma_T, "fv": round(fv, 2),
        "zadatek": zadatek, "zadatek_gotowka": round(zadatek_gotowka, 2),
        "zadatek_karta": round(zadatek_karta, 2), "kw": round(kw, 2),
        "imp": {"gotowka_sfiskalizowana": round(imp_got_sfisk, 2), "karta": round(imp_karta, 2)},
        "suma_szef": {"gotowka": suma_szef_G, "karta": suma_szef_T, "razem": suma_szef},
        "suma_zeszyt": {"gotowka": suma_zeszyt_G, "karta": suma_zeszyt_T,
                        "razem": round(suma_zeszyt_G + suma_zeszyt_T, 2)},
        "terminale": {"suma": terminale_suma, "roznica_karty": roznica_karty,
                      "etykieta": "nadwyżka" if roznica_karty > 0 else ("brak na kartach" if roznica_karty < 0 else "zgodne")},
        "kasy": {"suma": kasy_suma, "roznica": roznica_calosc,
                 "etykieta": "nadwyżka" if roznica_calosc > 0 else ("brak fiskalizacji" if roznica_calosc < 0 else "zgodne")},
        # podsumowanie pomocnicze (nie pokazywane w widoku admina)
        "G_do_oddania": suma_szef_G, "T": suma_szef_T, "SALA": suma_szef,
    }
