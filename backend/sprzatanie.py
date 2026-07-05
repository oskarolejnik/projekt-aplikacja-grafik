"""Grafik sprzątania sal — generowany W LOCIE z reguł + tabeli imprez, z korektami admina.

Reguły (konfigurowalne per lokal w LokalConfig; wartości domyślne = historyczne):
  • sale „codzienne"          — sprzątane każdego dnia (tam codziennie siedzą goście),
  • sala „niedzielna"         — w każdą niedzielę (pusta wartość = reguła wyłączona),
  • po imprezie               — sala sprzątana NASTĘPNEGO dnia; mapowanie kodów sal
                                z plików imprez (np. R2P→Zielona) w konfiguracji.

Pozycje NIE są zapisywane w bazie — liczymy je na żądanie (jak wymagania imprez), więc
zmiany w imprezach od razu zmieniają grafik. Trwałe są tylko: korekty admina
(SprzatanieKorekta: dodaj/usun, przesunięcie = usun+dodaj) i odhaczenia „zrobione"
(SprzatanieOdhaczenie).
"""

from datetime import date, timedelta

import models
from deps import get_lokal_config

# Wartości historyczne (jeden lokal) — używane, gdy konfiguracja ma NULL.
SALE_CODZIENNIE = ("Parter (R1)", "Góra (R1)")
SALA_NIEDZIELA = "Zielona"
# kod sali z pliku imprezy (lower) -> sala sprzątana dzień po imprezie
MAPA_SAL_IMPREZ = {"r2p": "Zielona", "r2piw": "Lustrzana", "r2g": "Kryształowa"}
# wszystkie sale w stałej kolejności wyświetlania
SALE = ("Parter (R1)", "Góra (R1)", "Zielona", "Lustrzana", "Kryształowa")


def sale_lokalu(db):
    """Lista sal tego lokalu (kolejność wyświetlania). NULL w konfiguracji = legacy."""
    cfg = get_lokal_config(db)
    return tuple(cfg.sale) if cfg.sale else SALE


def _reguly(db):
    """Efektywne reguły sprzątania z konfiguracji lokalu (NULL = wartości legacy)."""
    cfg = get_lokal_config(db)
    sale = tuple(cfg.sale) if cfg.sale else SALE
    codziennie = tuple(cfg.sprzatanie_sale_codziennie) if cfg.sprzatanie_sale_codziennie else SALE_CODZIENNIE
    # NULL = legacy „Zielona"; pusty string = reguła niedzieli wyłączona
    niedziela = SALA_NIEDZIELA if cfg.sprzatanie_sala_niedziela is None else (cfg.sprzatanie_sala_niedziela or None)
    mapa = {str(k).strip().lower(): v
            for k, v in (cfg.imprezy_mapa_sal or MAPA_SAL_IMPREZ).items()}
    return sale, codziennie, niedziela, mapa


def generuj(db, start: date, end: date):
    """Pozycje sprzątania w zakresie [start, end]: data, sala, powody[], zrobione (+przez kogo)."""
    sale, sale_codziennie, sala_niedziela, mapa_sal_imprez = _reguly(db)
    # Imprezy z dnia poprzedzającego zakres też wpływają (sprzątanie = dzień PO imprezie).
    imprezy = (
        db.query(models.Impreza)
        .filter(models.Impreza.data >= start - timedelta(days=1), models.Impreza.data <= end)
        .all()
    )
    po_imprezie = {}  # data_sprzatania -> [(sala, data_imprezy), ...]
    for imp in imprezy:
        sala = mapa_sal_imprez.get((imp.sala or "").strip().lower())
        if sala:
            po_imprezie.setdefault(imp.data + timedelta(days=1), []).append((sala, imp.data))

    korekty = {
        (k.data, k.sala): k.akcja
        for k in db.query(models.SprzatanieKorekta)
        .filter(models.SprzatanieKorekta.data >= start, models.SprzatanieKorekta.data <= end)
        .all()
    }
    odhaczenia = {
        (o.data, o.sala): o
        for o in db.query(models.SprzatanieOdhaczenie)
        .filter(models.SprzatanieOdhaczenie.data >= start, models.SprzatanieOdhaczenie.data <= end)
        .all()
    }
    prac_map = {p.id: f"{p.imie} {p.nazwisko}" for p in db.query(models.Pracownik).all()}

    wynik = []
    d = start
    while d <= end:
        powody = {}  # sala -> [powód, ...]
        for s in sale_codziennie:
            powody.setdefault(s, []).append("codziennie")
        if sala_niedziela and d.weekday() == 6:  # niedziela (reguła wyłączalna w konfiguracji)
            powody.setdefault(sala_niedziela, []).append("niedziela")
        for sala, data_imp in po_imprezie.get(d, []):
            powody.setdefault(sala, []).append(f"po imprezie z {data_imp.strftime('%d.%m')}")
        for sala in sale:  # korekty admina nadpisują automat
            akcja = korekty.get((d, sala))
            if akcja == "usun":
                powody.pop(sala, None)
            elif akcja == "dodaj" and sala not in powody:
                powody[sala] = ["dodane ręcznie"]
        for sala in sale:  # stała kolejność sal w wyniku
            if sala not in powody:
                continue
            o = odhaczenia.get((d, sala))
            wynik.append({
                "data": str(d),
                "sala": sala,
                "powody": powody[sala],
                "zrobione": o is not None,
                "zrobione_przez": prac_map.get(o.pracownik_id) if o else None,
            })
        d += timedelta(days=1)
    return wynik
