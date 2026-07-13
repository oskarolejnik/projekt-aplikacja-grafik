"""Struktura lokalu z konfiguracji (de-Rajculizacja, kroki 3–4): sale i reguły
sprzątania, mapa rewirów POS, kolumny zeszytu. Default (NULL) = zachowanie legacy."""

from datetime import date, timedelta

import models
import sprzatanie
from deps import get_lokal_config


def _niedziela():
    d = date.today()
    return d + timedelta(days=(6 - d.weekday()) % 7)


def test_sprzatanie_defaulty_legacy(admin_client):
    nd = _niedziela()
    r = admin_client.get(f"/api/sprzatanie?start={nd}&end={nd}").json()
    assert r["sale"] == list(sprzatanie.SALE)
    sale_dnia = {p["sala"] for p in r["pozycje"]}
    assert {"Parter (R1)", "Góra (R1)", "Zielona"} <= sale_dnia   # codzienne + niedziela


def test_sprzatanie_wlasna_struktura(admin_client, db):
    cfg = get_lokal_config(db)
    cfg.sale = ["Główna", "Ogródek"]
    cfg.sprzatanie_sale_codziennie = ["Główna"]
    cfg.sprzatanie_sala_niedziela = ""          # reguła niedzieli wyłączona
    db.commit()

    nd = _niedziela()
    r = admin_client.get(f"/api/sprzatanie?start={nd}&end={nd}").json()
    assert r["sale"] == ["Główna", "Ogródek"]
    sale_dnia = {p["sala"] for p in r["pozycje"]}
    assert sale_dnia == {"Główna"}              # tylko codzienna; bez Zielonej, bez niedzieli

    # walidacja korekt honoruje nowe sale
    assert admin_client.post("/api/sprzatanie/korekty", json={
        "data": str(nd), "sala": "Ogródek", "akcja": "dodaj"}).status_code == 204
    assert admin_client.post("/api/sprzatanie/korekty", json={
        "data": str(nd), "sala": "Zielona", "akcja": "dodaj"}).status_code == 400


def test_sprzatanie_mapa_sal_imprez_z_configu(admin_client, db):
    cfg = get_lokal_config(db)
    cfg.imprezy_mapa_sal = {"bankietowa": "Bankietowa"}
    cfg.sale = ["Bankietowa"]
    cfg.sprzatanie_sale_codziennie = []          # pusta lista w JSON == falsy → legacy...
    db.commit()
    # pusta lista → legacy defaulty (walidator PUT zamienia [] na NULL; tu wprost w DB)
    imp_data = date.today()
    db.add(models.Impreza(data=imp_data, klient="Wesele", sala="BANKIETOWA",
                          sciezka_pliku="x.xlsx"))
    db.commit()
    dzien_po = imp_data + timedelta(days=1)
    r = admin_client.get(f"/api/sprzatanie?start={dzien_po}&end={dzien_po}").json()
    poz = [p for p in r["pozycje"] if p["sala"] == "Bankietowa"]
    assert poz and any("po imprezie" in pw for pw in poz[0]["powody"])


def test_stoly_mapa_rewirow_z_configu(admin_client, db):
    db.add(models.StanStolow(rewir_nr=7, otwarte=4))
    db.add(models.StanStolow(rewir_nr=8, otwarte=2))
    db.add(models.StanStolow(rewir_nr=9, otwarte=1))
    db.commit()

    # default (Rajcula): rewir 7 nie jest zmapowany → zera w salach
    r = admin_client.get("/api/gastro/stoly").json()
    assert r["wewnatrz_suma"] == 0

    cfg = get_lokal_config(db)
    cfg.pos_mapa_rewirow = {"wewnatrz": [[7, "Główna"], [8, "Ogródek"]], "zewnatrz": [9], "wynos": 99}
    db.commit()
    r2 = admin_client.get("/api/gastro/stoly").json()
    assert r2["wewnatrz"] == [{"nazwa": "Główna", "liczba": 4}, {"nazwa": "Ogródek", "liczba": 2}]
    assert r2["wewnatrz_suma"] == 6 and r2["na_zewnatrz"] == 1 and r2["wynos"] == 0


def test_config_roundtrip_struktury(admin_client):
    w = admin_client.put("/api/lokal/config", json={
        "sale": [" Główna ", "Ogródek", ""],
        "sprzatanie_sala_niedziela": "",
        "imprezy_mapa_sal": {" kod ": " Sala X ", "": "pomin"},
        "zeszyt_kolumny": ["towar", "media"],
    })
    assert w.status_code == 200
    r = admin_client.get("/api/lokal/config").json()
    assert r["sale"] == ["Główna", "Ogródek"]
    assert r["sprzatanie_sala_niedziela"] == ""
    assert r["imprezy_mapa_sal"] == {"kod": "Sala X"}
    assert r["zeszyt_kolumny"] == ["towar", "media"]

    # pusta lista = powrót do NULL (legacy)
    admin_client.put("/api/lokal/config", json={"sale": [], "zeszyt_kolumny": []})
    r2 = admin_client.get("/api/lokal/config").json()
    assert r2["sale"] is None and r2["zeszyt_kolumny"] is None
