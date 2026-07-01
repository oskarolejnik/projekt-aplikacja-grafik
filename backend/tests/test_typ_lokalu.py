"""typ_lokalu w LokalConfig (kreator restauracji) — zapamiętanie typu + zapis presetu modułów."""


def test_config_typ_lokalu_domyslnie_none(admin_client):
    cfg = admin_client.get("/api/lokal/config").json()
    assert cfg["typ_lokalu"] is None


def test_put_zapisuje_typ_i_preset_modulow(admin_client):
    # Preset „pizzeria": rezerwacje + online + rozliczenia + POS, bez imprez/sprzątania.
    r = admin_client.put("/api/lokal/config", json={
        "typ_lokalu": "pizzeria",
        "modul_rezerwacje": True, "rezerwacje_online": True,
        "modul_rozliczenia": True, "modul_pos": True,
        "modul_imprezy": False, "modul_sprzatanie": False,
    })
    assert r.status_code == 200
    cfg = admin_client.get("/api/lokal/config").json()
    assert cfg["typ_lokalu"] == "pizzeria"
    assert cfg["modul_imprezy"] is False
    assert cfg["modul_sprzatanie"] is False
    assert cfg["rezerwacje_online"] is True
