"""Faza 1 — konfigurowalność: rola stanowiska + flagi + LokalConfig.

Dowodzą NOWEJ zdolności: logika nie zależy już od konkretnych NAZW („Sala"/„Kuchnia"/…),
lecz od ROLI/FLAG. Dzięki temu dowolny lokal może nazwać stanowiska po swojemu.
(Kompatybilność wsteczną „po nazwie" pokrywa istniejący zestaw testów.)
"""

from datetime import date, datetime

import main
import models
import raporty
import factories


def test_sala_wykrywana_po_roli_a_nie_nazwie(db):
    """_sala_stanowisko_ids łapie stanowisko z rolą 'sala', choć nazwa nie zaczyna się od „Sala"."""
    stan = factories.StanowiskoFactory(nazwa="Parkiet główny", rola="sala")
    assert stan.id in main._sala_stanowisko_ids(db)


def test_sprzataczka_po_fladze_a_nie_nazwie(db):
    """Dostęp do zamówień wynika z flagi daje_dostep_zamowien, nie z nazwy „Sprzątaczka"."""
    stan = factories.StanowiskoFactory(nazwa="Ekipa porządkowa", daje_dostep_zamowien=True)
    prac = factories.PracownikFactory(dzial="techniczny")
    prac.kwalifikacje = [stan]
    factories.Session.commit()
    assert main._jest_sprzataczka(prac) is True


def test_kuchnia_pelne_godziny_pod_dowolna_nazwa(db):
    """NAJWAŻNIEJSZE: pracownik kuchni (dzial='kuchnia') bez grafiku dostaje pełne godziny RCP
    na stanowisko o roli 'kuchnia' — i poprawnie naliczoną stawkę — MIMO że stanowisko nazywa
    się inaczej niż „Kuchnia". To dawniej dałoby 0 zł (etykieta nie mapowała się na stawkę)."""
    stan = factories.StanowiskoFactory(nazwa="Zaplecze kuchenne", rola="kuchnia")
    prac = factories.PracownikFactory(dzial="kuchnia")
    db.add(models.StawkaPracownika(pracownik_id=prac.id, stanowisko_id=stan.id, stawka=30.0))
    db.commit()

    odbicia = [{
        "pracownik_id": prac.id, "imie_nazwisko": "Jan Kowalski",
        "data": date(2026, 6, 15), "godziny": 5.0,
        "wejscie": datetime(2026, 6, 15, 12, 0), "wyjscie": datetime(2026, 6, 15, 17, 0),
    }]
    raport = raporty.raport_godzin_miesiac(db, 2026, 6, odbicia=odbicia)
    p = next(p for p in raport["pracownicy"] if p["pracownik_id"] == prac.id)
    assert p["do_wyplaty"] == 150.0  # 5 h × 30 zł
    assert any(s["stanowisko"] == "Zaplecze kuchenne" and s["godziny"] == 5.0 for s in p["stanowiska"])


def test_kuchnia_singleton_wg_roli_samonaprawa(db):
    """_kuchnia_stanowisko znajduje istniejące „Kuchnia" i nadaje mu rolę (adopcja danych)."""
    stan = factories.StanowiskoFactory(nazwa="Kuchnia")  # bez roli (dane sprzed migracji)
    got = main._kuchnia_stanowisko(db)
    assert got.id == stan.id
    assert got.rola == "kuchnia"                         # rola nadana w locie (adopcja)
    assert db.get(models.Stanowisko, stan.id).rola == "kuchnia"  # i zapisana w bazie


def test_lokal_branding_publiczny(client):
    """Branding dostępny BEZ logowania (do strony logowania / PWA)."""
    r = client.get("/api/lokal/branding")
    assert r.status_code == 200
    body = r.json()
    assert body["nazwa_lokalu"] == "Lokalo"                 # wartość domyślna singletona
    assert set(body.keys()) == {"nazwa_lokalu", "logo_url", "kolor_primary"}  # bez sekretów


def test_lokal_config_admin_get_i_update(admin_client):
    r = admin_client.get("/api/lokal/config")
    assert r.status_code == 200
    assert r.json()["modul_imprezy"] is True
    r2 = admin_client.put("/api/lokal/config", json={"nazwa_lokalu": "Bistro X", "modul_pos": False})
    assert r2.status_code == 200
    assert r2.json()["nazwa_lokalu"] == "Bistro X"
    assert r2.json()["modul_pos"] is False
    assert r2.json()["modul_imprezy"] is True               # niezmienione pola zostają


def test_lokal_config_pracownik_nie_moze_pisac(make_employee_client, company):
    prac = company["pracownicy"][0]["obj"]
    c, _ = make_employee_client(prac)
    assert c.put("/api/lokal/config", json={"nazwa_lokalu": "hack"}).status_code == 403
