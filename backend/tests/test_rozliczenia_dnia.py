"""Silnik rozliczenia dnia — weryfikacja 1:1 z realnym przykładem z arkusza właściciela
(SUMA SZEF 22 423, −28 na kartach, +23 całość) oraz reguły IMP."""

from rozliczenia import policz_dzien


def test_przyklad_z_arkusza():
    # Kelnerzy (G, T): Sebastian 2300/4999, Kacper 2993/2001, Oskar 1248/9382
    r = policz_dzien(
        kelnerzy=[{"gotowka": 2300, "karta": 4999},
                  {"gotowka": 2993, "karta": 2001},
                  {"gotowka": 1248, "karta": 9382}],
        terminale=[2994, 3885, 3825, 5650],   # Σ 16354
        kasy=[12000, 9000, 2000],             # Σ 23000
        fv=0, zadatek_gotowka=500, zadatek_karta=0, kw=0,
        imp={"gotowka_sfiskalizowana": 100, "karta": 0},   # IMP(−) 100 po stronie kas
    )
    assert r["sigma_gotowka"] == 6541 and r["sigma_karta"] == 16382
    assert r["suma_szef"] == {"gotowka": 6041.0, "karta": 16382.0, "razem": 22423.0}
    assert r["suma_zeszyt"]["gotowka"] == 6541.0          # bez zdejmowania zadatku
    # Karty: terminale 16354 vs deklaracje 16382 -> -28 (brak na kartach)
    assert r["terminale"]["suma"] == 16354.0
    assert r["terminale"]["roznica_karty"] == -28.0 and r["terminale"]["etykieta"] == "brak na kartach"
    # Kasy: 23000 - 100 (IMP) - 500 (zadatek) = 22400 ; 22423 - 22400 = +23 (nadwyżka)
    assert r["kasy"]["suma"] == 22400.0
    assert r["kasy"]["roznica"] == 23.0 and r["kasy"]["etykieta"] == "nadwyżka"
    assert r["G_do_oddania"] == 6041.0 and r["SALA"] == 22423.0


def test_imp_karta_odejmuje_od_terminali_i_kas():
    # Impreza opłacona kartą 1000 -> IMP karta minus w terminalach I w kasach.
    base = dict(kelnerzy=[{"gotowka": 0, "karta": 1000}], terminale=[1000], kasy=[1000])
    bez = policz_dzien(**base, imp={})
    zimp = policz_dzien(**base, imp={"karta": 1000})
    assert zimp["terminale"]["suma"] == bez["terminale"]["suma"] - 1000   # minus terminal
    assert zimp["kasy"]["suma"] == bez["kasy"]["suma"] - 1000             # minus kasa


def test_zadatek_rozbity_i_kw_kierunki():
    # Zadatek zdejmowany z właściwej formy (gotówka/karta), KW na plus,
    # „zafiskalizowane" (zeszyt) bez zdejmowania zadatku.
    r = policz_dzien(kelnerzy=[{"gotowka": 1000, "karta": 800}],
                     kw=50, zadatek_gotowka=200, zadatek_karta=300)
    assert r["suma_szef"]["gotowka"] == 1000 + 50 - 200    # 850
    assert r["suma_szef"]["karta"] == 800 - 300            # 500
    assert r["suma_zeszyt"]["gotowka"] == 1000 + 50        # 1050 (bez zadatku)
    assert r["suma_zeszyt"]["karta"] == 800
    assert r["zadatek"] == 500


def test_zgodne_gdy_brak_roznic():
    r = policz_dzien(kelnerzy=[{"gotowka": 500, "karta": 800}], terminale=[800], kasy=[1300])
    assert r["terminale"]["etykieta"] == "zgodne"
    assert r["kasy"]["etykieta"] == "zgodne" and r["kasy"]["roznica"] == 0.0
