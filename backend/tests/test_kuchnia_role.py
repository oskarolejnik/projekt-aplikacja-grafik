"""Nowe role: 'kuchnia' (Pracownik kuchnia) i 'szef_kuchni' (Szef kuchni).

- kuchnia      — zwykły pracownik: dostęp tylko do /api/me/* (front pokazuje 2 zakładki).
- szef_kuchni  — oversight TYLKO odczyt: godziny kuchni (BEZ wypłat) + stoły + rezerwacje.
"""

from datetime import datetime

import models
import factories
from auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(u)}"}


def _kuchnia_z_godzinami(db, login_konta="kuch1", godziny=8.0):
    """Tworzy pracownika kuchni (konto rola='kuchnia') z 8h w opublikowanym grafiku."""
    kuchnia_stan = factories.StanowiskoFactory(nazwa="Kuchnia")
    p = factories.PracownikFactory(imie="Kucharz", nazwisko="Pierwszy", dzial="kuchnia")
    factories.UserFactory(login=login_konta, rola="kuchnia", pracownik=p)
    factories.PrzydzialFactory(stanowisko=kuchnia_stan, pracownik=p, data=factories.dzien(0))
    db.add(models.PublikacjaGrafiku(start=factories.dzien(0), koniec=factories.dzien(6),
                                    opublikowano_at=datetime.utcnow()))
    db.add(models.StawkaPracownika(pracownik_id=p.id, stanowisko_id=kuchnia_stan.id, stawka=25.0))
    db.add(models.OdbicieRcp(rcp_id=f"k-{p.id}", imie_nazwisko="Kucharz Pierwszy", pracownik_id=p.id,
                             data=factories.dzien(0), wejscie=datetime(2026, 6, 1, 10, 0),
                             wyjscie=datetime(2026, 6, 1, 18, 0), godziny=godziny))
    db.commit()
    return p


# ── Szef kuchni: godziny kuchni BEZ wypłat ────────────────────────────────────
def test_szef_kuchni_widzi_godziny_kuchni_bez_kwot(client, db):
    _kuchnia_z_godzinami(db)
    szef_k = factories.UserFactory(login="szefk1", rola="szef_kuchni")
    r = client.get("/api/szefkuchni/godziny?rok=2026&miesiac=6", headers=_h(szef_k))
    assert r.status_code == 200
    body = r.json()
    assert len(body["pracownicy"]) == 1
    p = body["pracownicy"][0]
    assert p["pracownik"] == "Kucharz Pierwszy"
    assert p["suma_godzin"] == 8.0
    # KLUCZOWE: żadnych pól finansowych
    assert "do_wyplaty" not in p
    assert p["stanowiska"][0]["stanowisko"] == "Kuchnia"
    assert "kwota" not in p["stanowiska"][0]
    assert "stawka" not in p["stanowiska"][0]


def test_szef_kuchni_widzi_tylko_kuchnie(client, db):
    _kuchnia_z_godzinami(db)
    # pracownik obsługi (employee) z godzinami — NIE powinien się pojawić u szefa kuchni
    sala = factories.StanowiskoFactory(nazwa="Sala")
    obs = factories.PracownikFactory(imie="Kelner", nazwisko="Drugi")
    factories.UserFactory(login="obs1", rola="employee", pracownik=obs)
    factories.PrzydzialFactory(stanowisko=sala, pracownik=obs, data=factories.dzien(0))
    db.add(models.OdbicieRcp(rcp_id="o-1", imie_nazwisko="Kelner Drugi", pracownik_id=obs.id,
                             data=factories.dzien(0), wejscie=datetime(2026, 6, 1, 10, 0),
                             wyjscie=datetime(2026, 6, 1, 16, 0), godziny=6.0))
    db.commit()
    szef_k = factories.UserFactory(login="szefk2", rola="szef_kuchni")
    body = client.get("/api/szefkuchni/godziny?rok=2026&miesiac=6", headers=_h(szef_k)).json()
    imiona = [p["pracownik"] for p in body["pracownicy"]]
    assert imiona == ["Kucharz Pierwszy"]  # bez „Kelner Drugi"


def test_szef_kuchni_na_zmianie_po_dziale(client, db):
    """Kucharz dział=kuchnia z kontem 'employee' i otwartym odbiciem → na_zmianie u szefa kuchni
    (filtr po dziale, nie po roli konta) — i w grafiku, i w godzinach."""
    import main
    teraz = main._teraz_lokalnie() or datetime.now()
    p = factories.PracownikFactory(imie="Janek", nazwisko="Kuchta", dzial="kuchnia")
    factories.UserFactory(login="janek_k", rola="employee", pracownik=p)  # konto NIE 'kuchnia'
    db.add(models.OdbicieRcp(rcp_id="open-kuch", imie_nazwisko="Janek Kuchta", pracownik_id=p.id,
                             data=teraz.date(), wejscie=teraz.replace(microsecond=0), wyjscie=None))
    db.commit()
    h = _h(factories.UserFactory(login="szefk_nz", rola="szef_kuchni"))
    g = client.get(f"/api/szefkuchni/grafik?start={factories.dzien(0)}&end={factories.dzien(6)}", headers=h).json()
    assert any(z["pracownik"] == "Janek Kuchta" for z in g["na_zmianie"])
    gg = client.get("/api/szefkuchni/godziny?rok=2026&miesiac=6", headers=h).json()
    assert any(z["pracownik"] == "Janek Kuchta" for z in gg["na_zmianie"])


# ── Szef kuchni: granice dostępu ──────────────────────────────────────────────
def test_szef_kuchni_nie_widzi_raportu_z_wyplatami(client, db):
    szef_k = factories.UserFactory(login="szefk3", rola="szef_kuchni")
    h = _h(szef_k)
    assert client.get("/api/raporty/godziny?rok=2026&miesiac=6", headers=h).status_code == 403
    assert client.get("/api/pracownicy", headers=h).status_code == 403
    assert client.get("/api/users", headers=h).status_code == 403


def test_szef_kuchni_widzi_stoly_i_rezerwacje(client, db):
    szef_k = factories.UserFactory(login="szefk4", rola="szef_kuchni")
    h = _h(szef_k)
    assert client.get("/api/gastro/stoly", headers=h).status_code == 200
    # rezerwacje: middleware przepuszcza (nie 403); treść zależy od konfiguracji Google
    assert client.get("/api/rezerwacje", headers=h).status_code != 403


# ── Kuchnia: zwykły pracownik (bez oversight) ─────────────────────────────────
def test_kuchnia_nie_ma_dostepu_oversight(client, db):
    p = factories.PracownikFactory()
    kuch = factories.UserFactory(login="kuchx", rola="kuchnia", pracownik=p)
    h = _h(kuch)
    assert client.get("/api/raporty/godziny?rok=2026&miesiac=6", headers=h).status_code == 403
    assert client.get("/api/szefkuchni/godziny?rok=2026&miesiac=6", headers=h).status_code == 403
    assert client.get("/api/pracownicy", headers=h).status_code == 403
    # ale własne /api/me/* działa
    assert client.get("/api/me/godziny?rok=2026&miesiac=6", headers=h).status_code == 200


def test_kuchnia_widzi_rezerwacje_i_anonimowe_imprezy(client, db):
    """Pracownik kuchni: podgląd rezerwacji (agregat, bez danych klienta) + imprez
    przez /api/me/imprezy (sala/godzina/osoby, BEZ nazwy klienta). Pełnego
    /api/imprezy (z nazwą klienta) NIE widzi — zgodnie z preferencją prywatności."""
    p = factories.PracownikFactory()
    kuch = factories.UserFactory(login="kuchrez", rola="kuchnia", pracownik=p)
    h = _h(kuch)
    # rezerwacje: middleware przepuszcza (nie 403); treść zależy od konfiguracji Google
    assert client.get("/api/rezerwacje", headers=h).status_code != 403
    # imprezy anonimowo przez /api/me/* — działa
    assert client.get("/api/me/imprezy?start=2026-06-08&end=2026-06-14", headers=h).status_code == 200
    # pełne /api/imprezy (z nazwą klienta) — zablokowane dla kuchni
    assert client.get("/api/imprezy?start=2026-06-08&end=2026-06-14", headers=h).status_code == 403


# ── Zakładanie kont z nowymi rolami ───────────────────────────────────────────
def test_admin_zaklada_konta_kuchnia_i_szefkuchni(admin_client, db):
    for rola in ("kuchnia", "szef_kuchni"):
        r = admin_client.post("/api/users", json={"login": f"konto_{rola}", "haslo": "Haslo123!", "rola": rola})
        assert r.status_code == 201, rola
        assert r.json()["rola"] == rola
    # nieprawidłowa rola dalej odrzucana
    assert admin_client.post(
        "/api/users", json={"login": "zle", "haslo": "Haslo123!", "rola": "ktokolwiek"}
    ).status_code == 400


# ── Dział pracownika (osobne grafiki) + stanowisko kuchni ─────────────────────
def test_pracownik_dzial_domyslnie_obsluga_i_zapis(admin_client, db):
    r = admin_client.post("/api/pracownicy", json={
        "imie": "Kuch", "nazwisko": "Arz", "aktywny": True, "kwalifikacje_ids": [], "dzial": "kuchnia"})
    assert r.status_code == 201 and r.json()["dzial"] == "kuchnia"
    # brak działu → domyślnie obsługa
    r2 = admin_client.post("/api/pracownicy", json={
        "imie": "Obs", "nazwisko": "Luga", "aktywny": True, "kwalifikacje_ids": []})
    assert r2.json()["dzial"] == "obsluga"


def test_kuchnia_stanowisko_endpoint_idempotentny(admin_client, db):
    r1 = admin_client.get("/api/grafik/kuchnia-stanowisko")
    assert r1.status_code == 200 and r1.json()["nazwa"] == "Kuchnia"
    id1 = r1.json()["id"]
    assert admin_client.get("/api/grafik/kuchnia-stanowisko").json()["id"] == id1  # bez duplikatu
    assert db.query(models.Stanowisko).filter_by(nazwa="Kuchnia").count() == 1


# ── Szef kuchni: KOREKTY grafiku kuchni (tylko kuchnia) ──────────────────────
def _przydzial_json(pracownik_id, godz="14:00"):
    return {"data": str(factories.dzien(0)), "stanowisko_id": 1, "pracownik_id": pracownik_id, "godz_od": godz}


def test_szef_kuchni_edytuje_grafik_kuchni(client, db):
    kucharz = factories.PracownikFactory(imie="Kucharz", nazwisko="Edyt", dzial="kuchnia")
    szef_k = factories.UserFactory(login="szefke", rola="szef_kuchni")
    h = _h(szef_k)
    r = client.post("/api/szefkuchni/przydzialy", headers=h, json=_przydzial_json(kucharz.id))
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    # stanowisko wymuszone na „Kuchnia" (niezależnie od przesłanego stanowisko_id)
    assert db.get(models.PrzydzialZmiany, aid).stanowisko.nazwa == "Kuchnia"
    assert client.put(f"/api/szefkuchni/przydzialy/{aid}", headers=h, json=_przydzial_json(kucharz.id, "15:00")).status_code == 200
    assert client.delete(f"/api/szefkuchni/przydzialy/{aid}", headers=h).status_code == 204


def test_szef_kuchni_nie_edytuje_obslugi(client, db):
    obs = factories.PracownikFactory(imie="Kelner", nazwisko="Obs", dzial="obsluga")
    szef_k = factories.UserFactory(login="szefko", rola="szef_kuchni")
    r = client.post("/api/szefkuchni/przydzialy", headers=_h(szef_k), json=_przydzial_json(obs.id))
    assert r.status_code == 403  # tylko kuchnia


def test_szef_kuchni_nie_uzywa_endpointu_admina(client, db):
    kucharz = factories.PracownikFactory(dzial="kuchnia")
    szef_k = factories.UserFactory(login="szefka2", rola="szef_kuchni")
    r = client.post("/api/przydzialy", headers=_h(szef_k), json={"data": str(factories.dzien(0)),
                    "stanowisko_id": 1, "pracownik_id": kucharz.id})
    assert r.status_code == 403  # endpoint admina nadal zablokowany


def test_zmiana_grafiku_kuchni_wysyla_push(client, db, monkeypatch):
    import main
    wyslane = []
    monkeypatch.setattr(main, "wyslij_push_do_pracownika",
                        lambda db, pid, tytul, tresc, url="/": (wyslane.append((pid, tytul)) or 1))
    kucharz = factories.PracownikFactory(dzial="kuchnia")
    szef_k = factories.UserFactory(login="szefkpush", rola="szef_kuchni")
    r = client.post("/api/szefkuchni/przydzialy", headers=_h(szef_k), json=_przydzial_json(kucharz.id))
    assert r.status_code == 201
    assert wyslane and wyslane[0][0] == kucharz.id  # push poszedł do tego kucharza


# ── Grafik kuchni „żywy" — kucharz widzi zmiany bez publikacji ────────────────
def test_kuchnia_grafik_zywy_bez_publikacji(client, db):
    kuchnia_stan = factories.StanowiskoFactory(nazwa="Kuchnia")
    kucharz = factories.PracownikFactory(imie="Kucharz", nazwisko="Live", dzial="kuchnia")
    emp = factories.UserFactory(login="kuchlive", rola="kuchnia", pracownik=kucharz)
    factories.PrzydzialFactory(stanowisko=kuchnia_stan, pracownik=kucharz, data=factories.dzien(0))
    # BRAK publikacji
    r = client.get(f"/api/me/grafik?start={factories.dzien(0)}&end={factories.dzien(6)}", headers=_h(emp))
    assert r.status_code == 200
    body = r.json()
    assert body["opublikowany"] is True       # kuchnia: żywy mimo braku publikacji
    assert len(body["zmiany"]) == 1


def test_obsluga_grafik_wymaga_publikacji(client, db):
    sala = factories.StanowiskoFactory(nazwa="Sala")
    kelner = factories.PracownikFactory(dzial="obsluga")
    emp = factories.UserFactory(login="obslive", rola="employee", pracownik=kelner)
    factories.PrzydzialFactory(stanowisko=sala, pracownik=kelner, data=factories.dzien(0))
    body = client.get(f"/api/me/grafik?start={factories.dzien(0)}&end={factories.dzien(6)}", headers=_h(emp)).json()
    assert body["opublikowany"] is False      # obsługa: bez publikacji nic nie widzi
