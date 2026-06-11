"""Rozliczenie zmiany (dnia) — silnik liczący 1:1 z papierowego zeszytu właściciela.

Wejście (kwoty w zł):
  • kelnerzy — lista deklaracji kelnerów: [{"gotowka": G, "karta": T}, ...]  (kelner wpisuje TYLKO G i T),
  • fv        — suma faktur (KARTA_FV + GOTÓWKA_FV) z Gastro (poza kasą fiskalną),
  • terminale — lista kwot z wydruków terminali (wpisują zamykający rewir/lokal),
  • kasy      — lista kwot z raportów dobowych kas fiskalnych (j.w.),
  • zadatek   — zadatki dnia (fiskalizowane; trzymane osobno od utargu),
  • kp        — kasa PRZYJĘTA (np. zadatek za talerze na wynos) — pomniejsza utarg gotówkowy,
  • kw        — kasa WYDANA (np. zwrot kaucji) — powiększa utarg gotówkowy,
  • imp       — IMP z imprez: {"gotowka_sfiskalizowana": x, "karta": y} (z imp_dla_dnia).

Reguły (potwierdzone na realnym przykładzie z arkusza):
  SUMA SZEF  = Σ kelnerzy − KP + KW − zadatek   (G); T = Σ karta — utarg „dla szefa" bez zadatków,
  SUMA ZESZYT= Σ kelnerzy − KP + KW             (G; z zadatkiem) — co fizycznie w kopercie,
  TERMINALE  = Σ terminale − IMP_karta ;  różnica_kart = TERMINALE − Σ deklaracje_karty,
  KASY       = Σ kasy + FV − IMP_kasy − zadatek ;  różnica = SUMA SZEF − KASY,
  gdzie IMP_karta = imp.karta ; IMP_kasy = imp.gotowka_sfiskalizowana + imp.karta
        (gotówka sfiskalizowana i karta z imprez przechodzą przez kasę fiskalną; karta także przez terminal).
"""


def _suma(xs):
    return round(sum(float(x or 0) for x in xs), 2)


def policz_dzien(kelnerzy=None, fv=0.0, terminale=None, kasy=None,
                 zadatek=0.0, kp=0.0, kw=0.0, imp=None):
    kelnerzy = kelnerzy or []
    terminale = terminale or []
    kasy = kasy or []
    imp = imp or {}
    fv = float(fv or 0)
    zadatek = float(zadatek or 0); kp = float(kp or 0); kw = float(kw or 0)
    imp_got_sfisk = float(imp.get("gotowka_sfiskalizowana") or 0)
    imp_karta = float(imp.get("karta") or 0)

    sigma_G = _suma(k.get("gotowka") for k in kelnerzy)   # Σ zadeklarowana gotówka
    sigma_T = _suma(k.get("karta") for k in kelnerzy)      # Σ zadeklarowana karta

    suma_szef_G = round(sigma_G - kp + kw - zadatek, 2)
    suma_szef_T = round(sigma_T, 2)
    suma_szef = round(suma_szef_G + suma_szef_T, 2)
    suma_zeszyt_G = round(sigma_G - kp + kw, 2)            # z zadatkiem (gotówka fizycznie jest)

    imp_terminale = imp_karta
    imp_kasy = round(imp_got_sfisk + imp_karta, 2)

    terminale_suma = round(_suma(terminale) - imp_terminale, 2)
    roznica_karty = round(terminale_suma - sigma_T, 2)     # < 0 = brak na kartach, > 0 = nadwyżka

    kasy_suma = round(_suma(kasy) + fv - imp_kasy - zadatek, 2)
    roznica_calosc = round(suma_szef - kasy_suma, 2)       # < 0 = brak, > 0 = nadwyżka

    return {
        "sigma_gotowka": sigma_G, "sigma_karta": sigma_T, "fv": round(fv, 2),
        "zadatek": round(zadatek, 2), "kp": round(kp, 2), "kw": round(kw, 2),
        "imp": {"gotowka_sfiskalizowana": round(imp_got_sfisk, 2), "karta": round(imp_karta, 2)},
        "suma_szef": {"gotowka": suma_szef_G, "karta": suma_szef_T, "razem": suma_szef},
        "suma_zeszyt": {"gotowka": suma_zeszyt_G, "karta": suma_szef_T,
                        "razem": round(suma_zeszyt_G + suma_szef_T, 2)},
        "terminale": {"suma": terminale_suma, "roznica_karty": roznica_karty,
                      "etykieta": "nadwyżka" if roznica_karty > 0 else ("brak na kartach" if roznica_karty < 0 else "zgodne")},
        "kasy": {"suma": kasy_suma, "roznica": roznica_calosc,
                 "etykieta": "nadwyżka" if roznica_calosc > 0 else ("brak fiskalizacji" if roznica_calosc < 0 else "zgodne")},
        # podsumowanie końcowe: G do oddania (gotówka „dla szefa"), T, SALA = G+T
        "G_do_oddania": suma_szef_G,
        "T": suma_szef_T,
        "SALA": suma_szef,
    }
