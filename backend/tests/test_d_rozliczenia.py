"""Etap D — rozliczenia. D1: flagi przydziału „zamyka rewir" i „rozlicza imprezę"
(ustawiane w grafiku, widoczne w „Moim grafiku")."""

from datetime import datetime, time, date, timedelta

import models
import factories
from auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(u)}"}


def test_przydzial_flagi_zamyka_rewir_i_rozlicza_imprize(admin_client, client, db):
    sala = factories.StanowiskoFactory(nazwa="Sala")
    p = factories.PracownikFactory(dzial="obsluga")
    u = factories.UserFactory(login="emp_d1", rola="employee", pracownik=p)
    d = factories.dzien(0)
    r = admin_client.post("/api/przydzialy", json={
        "data": str(d), "stanowisko_id": sala.id, "pracownik_id": p.id,
        "godz_od": "16:00", "rewir": "Parter", "zamyka_rewir": True, "rozlicza_imprize": True})
    assert r.status_code == 201
    aid = r.json()["id"]
    assert r.json()["zamyka_rewir"] is True and r.json()["rozlicza_imprize"] is True

    db.add(models.PublikacjaGrafiku(start=d, koniec=factories.dzien(6), opublikowano_at=datetime.utcnow()))
    db.commit()
    z = client.get("/api/me/grafik", headers=_h(u),
                   params={"start": str(d), "end": str(factories.dzien(6))}).json()["zmiany"][0]
    assert z["zamyka_rewir"] is True and z["rozlicza_imprize"] is True

    # PUT może je wyłączyć
    admin_client.put(f"/api/przydzialy/{aid}", json={
        "data": str(d), "stanowisko_id": sala.id, "pracownik_id": p.id, "rewir": "Parter",
        "zamyka_rewir": False, "rozlicza_imprize": False})
    db.expire_all()
    rec = db.get(models.PrzydzialZmiany, aid)
    assert rec.zamyka_rewir is False and rec.rozlicza_imprize is False


def test_flagi_domyslnie_false(admin_client, db):
    sala = factories.StanowiskoFactory(nazwa="Sala")
    p = factories.PracownikFactory(dzial="obsluga")
    r = admin_client.post("/api/przydzialy", json={
        "data": str(factories.dzien(1)), "stanowisko_id": sala.id, "pracownik_id": p.id})
    assert r.status_code == 201
    assert r.json()["zamyka_rewir"] is False and r.json()["rozlicza_imprize"] is False


# ── D-imprezy: rozliczanie imprez + IMP ───────────────────────────────────────

def _rozliczajacy(db, login="imp1"):
    imprezy = factories.StanowiskoFactory(nazwa="Imprezy")
    p = factories.PracownikFactory(dzial="obsluga")
    u = factories.UserFactory(login=login, rola="employee", pracownik=p)
    d = factories.dzien(0)
    db.add(models.PrzydzialZmiany(data=d, stanowisko_id=imprezy.id, pracownik_id=p.id,
                                  rozlicza_imprize=True, rewir="IMPREZA: Wesele (R2P)"))
    db.commit()
    return p, u, d


def test_rozliczanie_imprezy_upsert_i_imp(client, db):
    import main
    p, u, d = _rozliczajacy(db)
    r = client.post("/api/me/imprezy/rozlicz", headers=_h(u), json={"data": str(d), "pozycje": [
        {"forma": "gotowka", "kwota": 1000, "sfiskalizowane": True},
        {"forma": "gotowka", "kwota": 500, "sfiskalizowane": False},
        {"forma": "karta", "kwota": 2000},
        {"forma": "przelew", "kwota": 300},
    ]})
    assert r.status_code == 201
    # IMP = gotówka sfiskalizowana (1000) + karta (2000); niesfisk 500 i przelew 300 NIE wchodzą
    assert main.imp_dla_dnia(db, d) == {"gotowka_sfiskalizowana": 1000.0, "karta": 2000.0}
    # upsert: ponowny submit ZASTĘPUJE pozycje (nie dubluje)
    client.post("/api/me/imprezy/rozlicz", headers=_h(u), json={"data": str(d), "pozycje": [{"forma": "karta", "kwota": 999}]})
    assert db.query(models.RozliczenieImprezyPozycja).count() == 1
    assert main.imp_dla_dnia(db, d)["karta"] == 999.0


def test_tylko_wyznaczony_rozlicza_imprize(client, db):
    imprezy = factories.StanowiskoFactory(nazwa="Imprezy")
    p = factories.PracownikFactory(dzial="obsluga")
    u = factories.UserFactory(login="imp_no", rola="employee", pracownik=p)
    d = factories.dzien(0)
    db.add(models.PrzydzialZmiany(data=d, stanowisko_id=imprezy.id, pracownik_id=p.id, rozlicza_imprize=False))
    db.commit()
    assert client.post("/api/me/imprezy/rozlicz", headers=_h(u), json={"data": str(d), "pozycje": []}).status_code == 403


def test_rejestr_imprez_admin(client, admin_client, db):
    p, u, d = _rozliczajacy(db)
    client.post("/api/me/imprezy/rozlicz", headers=_h(u), json={"data": str(d), "pozycje": [
        {"forma": "gotowka", "kwota": 1000, "sfiskalizowane": True}, {"forma": "karta", "kwota": 2000}]})
    r = admin_client.get(f"/api/imprezy/rozliczenia?start={d}&end={d}")
    assert r.status_code == 200
    rozl = r.json()["rozliczenia"]
    assert len(rozl) == 1 and rozl[0]["suma_gotowka"] == 1000 and rozl[0]["suma_karta"] == 2000
    assert rozl[0]["pracownik"] == f"{p.imie} {p.nazwisko}"
    assert r.json()["razem"]["suma_karta"] == 2000
    assert client.get(f"/api/imprezy/rozliczenia?start={d}&end={d}", headers=_h(u)).status_code == 403  # nie-admin


def _gastro(db, pid, d, forma, dekl=0.0, sprz=0.0):
    import uuid
    db.add(models.RozliczenieGastro(poz_id=str(uuid.uuid4()), rozliczenie_id="z", imie_nazwisko="x",
           pracownik_id=pid, data=d, zamkniete=True, forma=forma, sprzedaz=sprz, deklarowane=dekl))


def test_rozliczenie_dnia_prefill_oblicz_i_obieg(admin_client, db):
    sala = factories.StanowiskoFactory(nazwa="Sala")
    k1 = factories.PracownikFactory(dzial="obsluga")
    k2 = factories.PracownikFactory(dzial="obsluga")
    d = factories.dzien(0)
    for k in (k1, k2):
        db.add(models.PrzydzialZmiany(data=d, stanowisko_id=sala.id, pracownik_id=k.id))
    _gastro(db, k1.id, d, "GOTÓWKA", dekl=2300)
    _gastro(db, k1.id, d, "KARTA", dekl=4999)
    _gastro(db, k1.id, d, "KARTA_FV", sprz=186)
    # impreza tego dnia: gotówka sfiskalizowana 100 -> IMP(kasy)=100 (jak w arkuszu)
    imp = models.RozliczenieImprezy(data=d, pracownik_id=k1.id, utworzono_at=datetime.utcnow())
    imp.pozycje.append(models.RozliczenieImprezyPozycja(forma="gotowka", kwota=100, sfiskalizowane=True))
    db.add(imp)
    db.commit()
    # GET -> auto-create + prefill z Gastro
    body = admin_client.get(f"/api/rozliczenie?data={d}").json()
    assert len(body["kelnerzy"]) == 2
    seb = next(k for k in body["kelnerzy"] if k["pracownik_id"] == k1.id)
    assert seb["gotowka"] == 2300 and seb["karta"] == 4999 and seb["fv"] == 186
    # PUT: kwoty 1:1 z arkusza (sigma_G 6541, sigma_T 16382), zadatek 500 (gotówką), terminale 16354, kasy 23000
    payload = {"zadatek_gotowka": 500, "zadatek_karta": 0, "terminale": [{"kwota": 16354}], "kasy": [{"kwota": 23000}], "kelnerzy": [
        {"pracownik_id": k1.id, "gotowka": 2300, "karta": 4999, "fv": 0, "kw": 0},
        {"pracownik_id": k2.id, "gotowka": 4241, "karta": 11383, "fv": 0, "kw": 0},
    ]}
    w = admin_client.put(f"/api/rozliczenie?data={d}", json=payload).json()["wynik"]
    assert w["suma_szef"]["razem"] == 22423.0
    assert w["kasy"]["roznica"] == 23.0 and w["terminale"]["roznica_karty"] == -28.0
    # obieg
    assert admin_client.post(f"/api/rozliczenie/przekaz-szef?data={d}").status_code == 204
    db.expire_all()
    assert db.query(models.RozliczenieDnia).filter_by(data=d).first().status == "u_szefa"
    # szef widzi utarg sali (bez FV)
    szef = factories.UserFactory(login="szefr", rola="szef")
    s = admin_client.get  # admin też; sprawdźmy endpoint szefa osobnym klientem
    from auth import create_access_token
    import main
    from fastapi.testclient import TestClient
    c = TestClient(main.app); c.headers.update({"Authorization": f"Bearer {create_access_token(szef)}"})
    rs = c.get(f"/api/szef/rozliczenie?data={d}").json()
    assert rs["utarg"]["razem"] == 22423.0 and "fv" in rs["utarg"]   # szef widzi utarg Z FV


def test_kelner_zapisuje_wiersz(client, admin_client, db):
    sala = factories.StanowiskoFactory(nazwa="Sala")
    k = factories.PracownikFactory(dzial="obsluga")
    u = factories.UserFactory(login="kel1", rola="employee", pracownik=k)
    d = factories.dzien(0)
    db.add(models.PrzydzialZmiany(data=d, stanowisko_id=sala.id, pracownik_id=k.id)); db.commit()
    assert client.get(f"/api/me/rozliczenie?data={d}", headers=_h(u)).json()["moze"] is True
    assert client.put(f"/api/me/rozliczenie?data={d}", headers=_h(u),
                      json={"gotowka": 1000, "karta": 200, "kw": 0}).status_code == 204
    w = admin_client.get(f"/api/rozliczenie?data={d}").json()["wynik"]
    assert w["suma_zeszyt"]["gotowka"] == 1000.0 and w["suma_zeszyt"]["karta"] == 200.0


def test_kp_globalny_i_zadatek_rozbity(admin_client, db):
    """KP (zadatek) czytany GLOBALNIE z Gastro — łapie też zadatek przyjęty przez menadżera,
    który nie jest kelnerem Sali. Admin rozbija go na gotówkę/kartę (zdejmuje z utargu szefa)."""
    sala = factories.StanowiskoFactory(nazwa="Sala")
    k = factories.PracownikFactory(dzial="obsluga")
    menadzer = factories.PracownikFactory(dzial="obsluga")
    d = factories.dzien(0)
    db.add(models.PrzydzialZmiany(data=d, stanowisko_id=sala.id, pracownik_id=k.id))
    _gastro(db, k.id, d, "GOTÓWKA", dekl=1000)
    db.add(models.KpZadatek(id="kp-1", numer="1/2026", kwota=500, opis="Zadatek za impreze p.Test", data=d))
    db.commit()
    body = admin_client.get(f"/api/rozliczenie?data={d}").json()
    assert body["kp_baza"] == 500.0               # suma KP (dokument kasowy) z Gastro dla dnia
    payload = {"zadatek_gotowka": 500, "zadatek_karta": 0, "terminale": [], "kasy": [],
               "kelnerzy": [{"pracownik_id": k.id, "gotowka": 1000, "karta": 0, "fv": 0, "kw": 0}]}
    w = admin_client.put(f"/api/rozliczenie?data={d}", json=payload).json()["wynik"]
    assert w["suma_szef"]["gotowka"] == 500.0     # 1000 − 500 (zadatek zdjęty z gotówki)
    assert w["suma_zeszyt"]["gotowka"] == 1000.0  # zafiskalizowane bez zdejmowania zadatku


def test_zeszyt_stan_narastajaco(admin_client, db):
    """Zeszyt: SALA z rozliczenia (gotówka liczona do salda, terminal poza), rozchód minus,
    STAN narastająco od stanu początkowego."""
    sala = factories.StanowiskoFactory(nazwa="Sala")
    k = factories.PracownikFactory(dzial="obsluga")
    d = factories.dzien(0)
    db.add(models.PrzydzialZmiany(data=d, stanowisko_id=sala.id, pracownik_id=k.id))
    _gastro(db, k.id, d, "GOTÓWKA", dekl=1000)
    _gastro(db, k.id, d, "KARTA", dekl=500)
    db.commit()
    admin_client.get(f"/api/rozliczenie?data={d}")  # auto-create rozliczenia (wersja robocza też wchodzi do zeszytu)
    admin_client.put("/api/zeszyt/config", json={"stan_poczatkowy": 200, "stan_poczatkowy_data": str(d)})
    admin_client.post("/api/zeszyt/pozycja", json={"data": str(d), "kolumna": "towar", "opis": "Dostawa", "kwota": 150})
    day = admin_client.get(f"/api/zeszyt?start={d}&end={d}").json()["dni"][0]
    assert day["wiersze"][0]["zrodlo"] == "SALA"
    assert day["wiersze"][0]["gotowka"] == 1000.0 and day["wiersze"][0]["terminal"] == 500.0
    assert day["przychod_gotowka"] == 1000.0      # tylko gotówka wchodzi do salda
    assert day["rozchod_suma"] == 150.0
    assert day["stan"] == 1050.0                  # 200 + 1000 − 150


def test_przelew_z_palca_w_rozliczeniu_i_zeszycie(admin_client, db):
    """Admin wpisuje przelew z palca — zapisuje się w rozliczeniu dnia, pojawia w Zeszycie na
    wierszu SALA (poza saldem gotówki), i da się zmienić lekkim endpointem (z Zeszytu)."""
    sala = factories.StanowiskoFactory(nazwa="Sala")
    k = factories.PracownikFactory(dzial="obsluga")
    d = factories.dzien(0)
    db.add(models.PrzydzialZmiany(data=d, stanowisko_id=sala.id, pracownik_id=k.id))
    _gastro(db, k.id, d, "GOTÓWKA", dekl=500)
    db.commit()
    admin_client.get(f"/api/rozliczenie?data={d}")
    admin_client.put(f"/api/rozliczenie?data={d}", json={"przelew": 700, "zadatek_gotowka": 0, "zadatek_karta": 0,
        "imp_reczny": False, "imp_gotowka": 0, "imp_karta": 0, "terminale": [], "kasy": [],
        "kelnerzy": [{"pracownik_id": k.id, "gotowka": 500, "karta": 0, "fv": 0, "kw": 0}]})
    assert admin_client.get(f"/api/rozliczenie?data={d}").json()["przelew"] == 700
    day = admin_client.get(f"/api/zeszyt?start={d}&end={d}").json()["dni"][0]
    sala_w = next(w for w in day["wiersze"] if w["zrodlo"] == "SALA")
    assert sala_w["przelew"] == 700 and sala_w.get("sala_id")
    assert day["przychod_gotowka"] == 500          # przelew NIE wchodzi do salda gotówki
    assert admin_client.put(f"/api/rozliczenie/przelew?data={d}&przelew=1234").status_code == 204
    assert admin_client.get(f"/api/rozliczenie?data={d}").json()["przelew"] == 1234


def test_szef_widzi_zeszyt_nie_edytuje(db):
    from auth import create_access_token
    from fastapi.testclient import TestClient
    import main
    szef = factories.UserFactory(login="szefz", rola="szef")
    c = TestClient(main.app); c.headers.update({"Authorization": f"Bearer {create_access_token(szef)}"})
    d = factories.dzien(0)
    assert c.get(f"/api/szef/zeszyt?start={d}&end={d}").status_code == 200
    assert c.post("/api/zeszyt/pozycja", json={"data": str(d), "kolumna": "towar", "kwota": 10}).status_code == 403


def test_rozlicz_sala_dopiero_po_pushu(client, db, monkeypatch):
    """Przycisk „Rozlicz się" pojawia się DOPIERO po wysłaniu pusha (ingest agenta ustawia
    push_oczekuje_at). Samo zamknięte Gastro w bazie (bez ingestu) nie pokazuje przycisku."""
    import main
    monkeypatch.setattr(main, "RCP_INGEST_TOKEN", "tok123")
    sala = factories.StanowiskoFactory(nazwa="Sala")
    k = factories.PracownikFactory(dzial="obsluga")
    u = factories.UserFactory(login="kelpush", rola="employee", pracownik=k)
    d = factories.dzien(0)
    db.add(models.PrzydzialZmiany(data=d, stanowisko_id=sala.id, pracownik_id=k.id, godz_od=time(16, 0)))
    db.add(models.PublikacjaGrafiku(start=d, koniec=factories.dzien(6), opublikowano_at=datetime.utcnow()))
    db.commit()

    def status():
        z = client.get("/api/me/grafik", headers=_h(u),
                       params={"start": str(d), "end": str(factories.dzien(6))}).json()["zmiany"]
        return z[0]["rozlicz_sala"]

    # zamknięte Gastro w bazie, ale push jeszcze nie poszedł → brak przycisku
    _gastro(db, k.id, d, "GOTÓWKA", dekl=900); db.commit()
    assert status() is None
    # ingest agenta (zamknięte) → push + push_oczekuje_at → 'oczekuje'
    payload = {"pozycje": [{"poz_id": "p1", "rozliczenie_id": "r1", "data": str(d),
                            "imie_nazwisko": f"{k.imie} {k.nazwisko}", "zamkniete": 1,
                            "forma": "GOTÓWKA", "sprzedaz": 0, "deklarowane": 900}]}
    assert client.post("/api/gastro/rozliczenia", json=payload, headers={"X-RCP-Token": "tok123"}).status_code == 200
    assert status() == "oczekuje"
    # kelner przesyła raport → 'wyslane'
    assert client.put(f"/api/me/rozliczenie?data={d}", headers=_h(u),
                      json={"gotowka": 900, "karta": 0, "kw": 0}).status_code == 204
    assert status() == "wyslane"


def test_gastro_zadatki_ingest_i_kp_baza(client, db, monkeypatch):
    """Agent wysyła zadatki (KP) → upsert po id → suma KP dla dnia w rozliczeniu."""
    import main
    monkeypatch.setattr(main, "RCP_INGEST_TOKEN", "tok123")
    d = factories.dzien(0)
    payload = {"zadatki": [
        {"id": "g1", "numer": "120/2026", "kwota": 500, "opis": "Zadatek za komunie p.Nowak 15.05.2027", "data": str(d)},
        {"id": "g2", "numer": "121/2026", "kwota": 200, "opis": "kaucja za koryta", "data": str(d)},
    ]}
    r = client.post("/api/gastro/zadatki", json=payload, headers={"X-RCP-Token": "tok123"})
    assert r.status_code == 200 and r.json()["zadatki"] == 2
    assert main._kp_dla_dnia(db, d) == 700.0
    client.post("/api/gastro/zadatki", json={"zadatki": [{"id": "g1", "kwota": 500, "data": str(d)}]},
                headers={"X-RCP-Token": "tok123"})
    assert db.query(models.KpZadatek).count() == 2          # upsert, bez dubli
    assert client.post("/api/gastro/zadatki", json={"zadatki": []}).status_code == 401   # bez tokenu


def test_zamykajacy_dosyla_terminale_kasy_i_push_admina(client, admin_client, db):
    """Zamykający rewir dosyła terminale (swój rewir), zamykający zmianę — kasy. Gdy wszyscy
    kelnerzy sali się rozliczą → push do admina (push_admin_at ustawione raz)."""
    sala = factories.StanowiskoFactory(nazwa="Sala")
    k = factories.PracownikFactory(dzial="obsluga")
    u = factories.UserFactory(login="zamyk", rola="employee", pracownik=k)
    d = factories.dzien(0)
    db.add(models.PrzydzialZmiany(data=d, stanowisko_id=sala.id, pracownik_id=k.id,
                                  godz_od=time(16, 0), rewir="Parter", zamyka=True, zamyka_rewir=True))
    db.commit()
    g = client.get(f"/api/me/rozliczenie?data={d}", headers=_h(u)).json()
    assert g["zamyka_rewir"] is True and g["zamyka"] is True and g["rewir"] == "Parter"
    assert client.put(f"/api/me/rozliczenie?data={d}", headers=_h(u), json={
        "gotowka": 500, "karta": 800, "kw": 0,
        "terminale": [{"kwota": 800}], "kasy": [{"kwota": 1300}]}).status_code == 204
    body = admin_client.get(f"/api/rozliczenie?data={d}").json()
    assert any((t.get("kwota") == 800 and t.get("rewir") == "Parter") for t in body["terminale"])
    assert any(t.get("kwota") == 1300 for t in body["kasy"])
    db.expire_all()
    roz = db.query(models.RozliczenieDnia).filter_by(data=d).first()
    assert roz.push_admin_at is not None          # jedyny kelner sali → komplet → push do admina


def test_me_rozliczenie_tylko_kelner_sali(client, db):
    k = factories.PracownikFactory(dzial="obsluga")
    u = factories.UserFactory(login="bezsali", rola="employee", pracownik=k)
    d = factories.dzien(0)
    assert client.get(f"/api/me/rozliczenie?data={d}", headers=_h(u)).json()["moze"] is False
    assert client.put(f"/api/me/rozliczenie?data={d}", headers=_h(u), json={"gotowka": 100}).status_code == 403


def test_prefill_rozliczenia_imprezy(client, db):
    p, u, d = _rozliczajacy(db)
    pre = client.get(f"/api/me/imprezy/rozlicz?data={d}", headers=_h(u)).json()
    assert pre["moze"] is True and pre["pozycje"] == [] and pre["rewir"] == "Impreza (R2P)"
    client.post("/api/me/imprezy/rozlicz", headers=_h(u), json={"data": str(d), "pozycje": [{"forma": "karta", "kwota": 50}]})
    pre2 = client.get(f"/api/me/imprezy/rozlicz?data={d}", headers=_h(u)).json()
    assert len(pre2["pozycje"]) == 1 and pre2["pozycje"][0]["forma"] == "karta"


def test_rozlicz_sala_po_dacie_gastro_mimo_rozjazdu_grafiku(client, db):
    """Rozjazd dat grafik↔Gastro: kelner sali z ZAMKNIĘTYM rozliczeniem Gastro w dniu,
    w którym NIE ma zmiany w grafiku, i tak widzi „do rozliczenia" (po realnej dacie z
    Gastro) oraz może się rozliczyć. Po przesłaniu pozycja znika."""
    sala = factories.StanowiskoFactory(nazwa="Sala")
    p = factories.PracownikFactory(dzial="obsluga")
    u = factories.UserFactory(login="emp_rozjazd", rola="employee", pracownik=p)
    g_day = date.today()                            # dzień zamknięcia w Gastro
    grafik_day = date.today() - timedelta(days=2)   # zmiana w grafiku — INNY dzień (ale obsada sali)
    db.add(models.PrzydzialZmiany(data=grafik_day, stanowisko_id=sala.id, pracownik_id=p.id))
    _gastro(db, p.id, g_day, "GOTÓWKA", dekl=1500)
    _gastro(db, p.id, g_day, "KARTA", dekl=2500)
    db.commit()

    # /me/grafik zwraca dzień Gastro w „rozliczenia_oczekujace" (mimo braku zmiany tego dnia)
    r = client.get("/api/me/grafik", headers=_h(u),
                   params={"start": str(grafik_day), "end": str(g_day)}).json()
    assert g_day.isoformat() in r["rozliczenia_oczekujace"]

    # kelner może pobrać (prefill z Gastro) i przesłać rozliczenie dla daty Gastro
    info = client.get("/api/me/rozliczenie", headers=_h(u), params={"data": str(g_day)}).json()
    assert info["moze"] is True
    assert info["wiersz"]["gotowka"] == 1500 and info["wiersz"]["karta"] == 2500
    put = client.put("/api/me/rozliczenie", headers=_h(u), params={"data": str(g_day)},
                     json={"gotowka": 1500, "karta": 2500, "kw": 0, "terminale": [], "kasy": []})
    assert put.status_code == 204

    # po przesłaniu znika z „do rozliczenia"
    r2 = client.get("/api/me/grafik", headers=_h(u),
                    params={"start": str(grafik_day), "end": str(g_day)}).json()
    assert g_day.isoformat() not in r2["rozliczenia_oczekujace"]


def test_do_rozliczenia_tylko_dla_obsady_sali(client, db):
    """Pracownik BEZ żadnej zmiany na sali (np. tylko kuchnia) nie dostaje „do rozliczenia",
    nawet jeśli istnieje wpis Gastro na jego id."""
    factories.StanowiskoFactory(nazwa="Sala")
    p = factories.PracownikFactory(dzial="kuchnia")
    u = factories.UserFactory(login="emp_kuch_norozl", rola="employee", pracownik=p)
    g_day = date.today()
    _gastro(db, p.id, g_day, "GOTÓWKA", dekl=999)
    db.commit()
    r = client.get("/api/me/grafik", headers=_h(u),
                   params={"start": str(g_day), "end": str(g_day)}).json()
    assert r.get("rozliczenia_oczekujace") == []


def test_rozliczenia_oczekujace_tnie_zalegle_sprzed_startu(client, db, monkeypatch):
    """„Rozlicz się" nie pokazuje zaległych rozliczeń sprzed startu systemu (ROZLICZENIA_START)."""
    import main
    sala = factories.StanowiskoFactory(nazwa="Sala")
    p = factories.PracownikFactory(dzial="obsluga")
    u = factories.UserFactory(login="emp_cutoff", rola="employee", pracownik=p)
    start = date.today() - timedelta(days=3)
    monkeypatch.setattr(main, "ROZLICZENIA_START", start)
    przed = start - timedelta(days=1)   # sprzed startu -> ma zniknąć
    po = start + timedelta(days=1)       # po starcie -> ma zostać
    db.add(models.PrzydzialZmiany(data=po, stanowisko_id=sala.id, pracownik_id=p.id))
    _gastro(db, p.id, przed, "GOTÓWKA", dekl=100)
    _gastro(db, p.id, po, "GOTÓWKA", dekl=200)
    db.commit()
    daty = main._rozliczenia_oczekujace(db, p.id)
    assert po.isoformat() in daty
    assert przed.isoformat() not in daty
    # to samo przez /me/grafik (źródło bannera)
    r = client.get("/api/me/grafik", headers=_h(u), params={"start": str(przed), "end": str(po)}).json()
    assert po.isoformat() in r["rozliczenia_oczekujace"]
    assert przed.isoformat() not in r["rozliczenia_oczekujace"]


def test_push_oczekuje_tnie_dni_sprzed_startu(client, db, monkeypatch):
    """Ingest zamkniętych rozliczeń Gastro NIE wysyła pusha „raport oczekuje" za dni sprzed startu."""
    import main
    monkeypatch.setattr(main, "wyslij_push_do_pracownika", lambda *a, **k: 0)
    sala = factories.StanowiskoFactory(nazwa="Sala")
    p = factories.PracownikFactory(dzial="obsluga")
    start = date.today() - timedelta(days=3)
    monkeypatch.setattr(main, "ROZLICZENIA_START", start)
    przed = start - timedelta(days=1)
    po = start + timedelta(days=1)
    db.add(models.PrzydzialZmiany(data=po, stanowisko_id=sala.id, pracownik_id=p.id))
    db.add(models.PrzydzialZmiany(data=przed, stanowisko_id=sala.id, pracownik_id=p.id))
    db.commit()
    poz = [
        {"poz_id": "A", "rozliczenie_id": "r1", "data": str(przed),
         "imie_nazwisko": f"{p.imie} {p.nazwisko}", "zamkniete": 1, "forma": "GOTÓWKA", "deklarowane": 100},
        {"poz_id": "B", "rozliczenie_id": "r2", "data": str(po),
         "imie_nazwisko": f"{p.imie} {p.nazwisko}", "zamkniete": 1, "forma": "GOTÓWKA", "deklarowane": 200},
    ]
    r = client.post("/api/gastro/rozliczenia", headers={"x-rcp-token": "test-rcp-token"}, json={"pozycje": poz})
    assert r.status_code == 200
    # po starcie: rozliczenie zbudowane, push poszedł
    roz_po = db.query(models.RozliczenieDnia).filter_by(data=po).first()
    k_po = next((x for x in roz_po.kelnerzy if x.pracownik_id == p.id), None) if roz_po else None
    assert k_po is not None and k_po.push_oczekuje_at is not None
    # sprzed startu: trigger w ogóle nie budował rozliczenia -> brak pusha
    roz_przed = db.query(models.RozliczenieDnia).filter_by(data=przed).first()
    assert roz_przed is None or all(k.push_oczekuje_at is None for k in roz_przed.kelnerzy)
