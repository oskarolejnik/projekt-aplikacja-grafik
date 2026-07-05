"""Wspólna pula kelnerska (de-Rajculizacja, krok 5). Tryb 'pula' = jeden zbiorczy
zestaw G/T/FV/KW dla całej zmiany; silnik policz_dzien liczy jak dla jednego kelnera.
Default 'indywidualnie' = zachowanie historyczne."""

import uuid
from datetime import datetime

import factories
import models
from deps import get_lokal_config


def _gastro(db, pid, d, forma, dekl=0.0, sprz=0.0):
    db.add(models.RozliczenieGastro(poz_id=str(uuid.uuid4()), rozliczenie_id="z", imie_nazwisko="x",
           pracownik_id=pid, data=d, zamkniete=True, forma=forma, sprzedaz=sprz, deklarowane=dekl))


def _wlacz_pule(db):
    get_lokal_config(db).rozliczenia_tryb_kelnera = "pula"
    db.commit()


def test_pula_prefill_z_agregatu_gastro(admin_client, db):
    sala = factories.StanowiskoFactory(nazwa="Sala")
    k1 = factories.PracownikFactory(dzial="obsluga")
    k2 = factories.PracownikFactory(dzial="obsluga")
    d = factories.dzien(0)
    db.add(models.PrzydzialZmiany(data=d, stanowisko_id=sala.id, pracownik_id=k1.id))
    db.add(models.PrzydzialZmiany(data=d, stanowisko_id=sala.id, pracownik_id=k2.id))
    _gastro(db, k1.id, d, "GOTÓWKA", dekl=1000)
    _gastro(db, k1.id, d, "KARTA", dekl=2000)
    _gastro(db, k2.id, d, "GOTÓWKA", dekl=500)
    _gastro(db, k2.id, d, "KARTA_FV", sprz=123)
    db.commit()
    _wlacz_pule(db)

    body = admin_client.get(f"/api/rozliczenie?data={d}").json()
    assert body["tryb_kelnera"] == "pula"
    assert body["kelnerzy"] == []                      # brak wierszy per kelner
    # pula = suma obsady sali z Gastro
    assert body["pula"]["gotowka"] == 1500 and body["pula"]["karta"] == 2000 and body["pula"]["fv"] == 123
    # utarg sali liczony z puli (Σ G + Σ T)
    assert body["wynik"]["suma_zeszyt"]["razem"] == 3500


def test_pula_zapis_i_przeliczenie(admin_client, db):
    factories.StanowiskoFactory(nazwa="Sala")
    d = factories.dzien(1)
    _wlacz_pule(db)
    admin_client.get(f"/api/rozliczenie?data={d}")   # utwórz

    r = admin_client.put(f"/api/rozliczenie?data={d}", json={
        "pula_gotowka": 3000, "pula_karta": 5000, "pula_fv": 200, "pula_kw": 50,
        "terminale": [{"kwota": 5000}], "kasy": [{"kwota": 3050}],
    }).json()
    w = r["wynik"]
    # utarg do szefa = ΣG(3000)+KW(50)+ΣT(5000) = 8050
    assert w["suma_szef"]["razem"] == 8050
    # terminale 5000 vs karta 5000 → zgodne
    assert w["terminale"]["roznica_karty"] == 0
    # kasy 3050 + FV 200 = 3250 ; do szefa gotówka 3050 → różnica całości ...
    assert r["pula"]["gotowka"] == 3000 and r["pula"]["kw"] == 50


def test_indywidualny_niezmieniony(admin_client, db):
    sala = factories.StanowiskoFactory(nazwa="Sala")
    k1 = factories.PracownikFactory(dzial="obsluga")
    d = factories.dzien(2)
    db.add(models.PrzydzialZmiany(data=d, stanowisko_id=sala.id, pracownik_id=k1.id))
    _gastro(db, k1.id, d, "GOTÓWKA", dekl=1200)
    db.commit()
    body = admin_client.get(f"/api/rozliczenie?data={d}").json()
    assert body["tryb_kelnera"] == "indywidualnie"
    assert len(body["kelnerzy"]) == 1 and body["kelnerzy"][0]["gotowka"] == 1200


def test_zmiana_trybu_nie_zeruje_utargu_dnia(admin_client, db):
    """REGRESJA (audyt HIGH): dzień rozliczony indywidualnie, potem przełączenie na pulę —
    utarg musi zostać (źródło podąża za danymi), nie wyzerować się na zeszycie/pulpicie."""
    sala = factories.StanowiskoFactory(nazwa="Sala")
    k1 = factories.PracownikFactory(dzial="obsluga")
    d = factories.dzien(3)
    db.add(models.PrzydzialZmiany(data=d, stanowisko_id=sala.id, pracownik_id=k1.id))
    _gastro(db, k1.id, d, "GOTÓWKA", dekl=3000)
    _gastro(db, k1.id, d, "KARTA", dekl=5000)
    db.commit()
    # rozliczenie indywidualne (default) — dane w wierszu kelnera
    b1 = admin_client.get(f"/api/rozliczenie?data={d}").json()
    assert b1["wynik"]["suma_zeszyt"]["razem"] == 8000

    # globalne przełączenie na pulę — pula_* tego dnia są zerowe
    get_lokal_config(db).rozliczenia_tryb_kelnera = "pula"
    db.commit()
    b2 = admin_client.get(f"/api/rozliczenie?data={d}").json()
    assert b2["wynik"]["suma_zeszyt"]["razem"] == 8000        # NIE 0 — czyta z wierszy
    assert b2["tryb_kelnera"] == "indywidualnie"              # efektywne źródło = dane

    # analogicznie odwrotnie: dzień z pulą przełączony na indywidualnie
    d2 = factories.dzien(4)
    admin_client.get(f"/api/rozliczenie?data={d2}")           # utwórz (pula)
    admin_client.put(f"/api/rozliczenie?data={d2}", json={"pula_gotowka": 1000, "pula_karta": 2000})
    get_lokal_config(db).rozliczenia_tryb_kelnera = "indywidualnie"
    db.commit()
    b3 = admin_client.get(f"/api/rozliczenie?data={d2}").json()
    assert b3["wynik"]["suma_zeszyt"]["razem"] == 3000        # pula nie znika
    assert b3["tryb_kelnera"] == "pula"


def test_pula_wylacza_indywidualne_me_rozliczenie(client, admin_client, db):
    sala = factories.StanowiskoFactory(nazwa="Sala")
    p = factories.PracownikFactory(dzial="obsluga")
    u = factories.UserFactory(login="pula_emp", rola="employee", pracownik=p)
    d = factories.dzien(0)
    db.add(models.PrzydzialZmiany(data=d, stanowisko_id=sala.id, pracownik_id=p.id))
    db.commit()
    _wlacz_pule(db)

    from auth import create_access_token
    h = {"Authorization": f"Bearer {create_access_token(u)}"}
    assert client.get(f"/api/me/rozliczenie?data={d}", headers=h).json() == {"moze": False}
    assert client.put(f"/api/me/rozliczenie?data={d}", headers=h,
                      json={"gotowka": 100, "karta": 0, "kw": 0}).status_code == 403
