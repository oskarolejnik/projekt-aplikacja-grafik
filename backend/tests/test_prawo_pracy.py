"""Strażnik prawa pracy — moduł prawo_pracy (czyste reguły) + egzekwowanie w POST /api/przydzialy.

Limity parametryzowane w LokalConfig (praca_min_odpoczynek_h / praca_max_dni_tydzien /
praca_max_dni_miesiac); 0 = limit wyłączony. Domyślne: 11 h / 6 dni / 22 dni.
"""

from datetime import date, time, timedelta

import factories
import prawo_pracy


def _p(stan, prac, data, godz="10:00"):
    return {"data": str(data), "stanowisko_id": stan.id, "pracownik_id": prac.id, "godz_od": godz, "rewir": None}


# ── Reguły (bez DB) ──────────────────────────────────────────────────────────
def test_modul_odpoczynek_za_krotki():
    inne = [(date(2026, 6, 1), time(22, 0))]
    assert prawo_pracy.naruszenie_odpoczynku(inne, date(2026, 6, 2), time(6, 0), 11) is not None   # 8 h
    assert prawo_pracy.naruszenie_odpoczynku(inne, date(2026, 6, 2), time(10, 0), 11) is None       # 12 h


def test_modul_odpoczynek_wylaczony_lub_brak_godziny():
    inne = [(date(2026, 6, 1), time(22, 0))]
    assert prawo_pracy.naruszenie_odpoczynku(inne, date(2026, 6, 2), time(6, 0), 0) is None          # limit off
    assert prawo_pracy.naruszenie_odpoczynku(inne, date(2026, 6, 2), None, 11) is None               # brak godz_od
    assert prawo_pracy.naruszenie_odpoczynku([(date(2026, 6, 1), None)], date(2026, 6, 2), time(6, 0), 11) is None


def test_modul_limit_tygodnia():
    tydzien = [date(2026, 6, 1) + timedelta(days=i) for i in range(6)]
    assert prawo_pracy.naruszenie_limitu_tygodnia(tydzien, date(2026, 6, 7), 6) is not None           # 7. dzień
    assert prawo_pracy.naruszenie_limitu_tygodnia(tydzien[:5], date(2026, 6, 6), 6) is None            # 6. dzień OK
    assert prawo_pracy.naruszenie_limitu_tygodnia(tydzien, date(2026, 6, 7), 0) is None                # off


def test_modul_limit_miesiaca():
    dni = [date(2026, 6, d) for d in range(1, 23)]           # 22 dni
    assert prawo_pracy.naruszenie_limitu_miesiaca(dni, date(2026, 6, 23), 22) is not None              # 23. dzień
    assert prawo_pracy.naruszenie_limitu_miesiaca(dni[:21], date(2026, 6, 22), 22) is None             # 22. dzień OK
    assert prawo_pracy.naruszenie_limitu_miesiaca(dni, date(2026, 7, 1), 22) is None                   # inny miesiąc


# ── Egzekwowanie w endpoincie ────────────────────────────────────────────────
def test_odpoczynek_ok_gdy_wystarczajacy(admin_client):
    stan = factories.StanowiskoFactory()
    prac = factories.PracownikFactory()
    assert admin_client.post("/api/przydzialy", json=_p(stan, prac, factories.dzien(0), "22:00")).status_code == 201
    # 22:00 → następnego dnia 10:00 = 12 h ≥ 11 h → OK.
    assert admin_client.post("/api/przydzialy", json=_p(stan, prac, factories.dzien(1), "10:00")).status_code == 201


def test_limit_miesiaca_izolowany(admin_client):
    # Wyłącz limit tygodnia, żeby przetestować sam limit miesiąca (dom. 22 dni).
    admin_client.put("/api/lokal/config", json={"praca_max_dni_tydzien": 0})
    stan = factories.StanowiskoFactory()
    prac = factories.PracownikFactory()
    statusy = [admin_client.post("/api/przydzialy", json=_p(stan, prac, factories.dzien(i), "10:00")).status_code
               for i in range(23)]                          # dzien(0..22) = 23 dni czerwca
    assert statusy[:22] == [201] * 22
    assert statusy[22] == 400                                # 23. dzień w miesiącu → odrzucony


def test_limity_wylaczone_zerem(admin_client):
    admin_client.put("/api/lokal/config",
                     json={"praca_min_odpoczynek_h": 0, "praca_max_dni_tydzien": 0, "praca_max_dni_miesiac": 0})
    stan = factories.StanowiskoFactory()
    prac = factories.PracownikFactory()
    statusy = [admin_client.post("/api/przydzialy", json=_p(stan, prac, factories.dzien(i), "10:00")).status_code
               for i in range(10)]                          # 10 dni z rzędu, limity off
    assert all(s == 201 for s in statusy)


def test_limity_sa_per_pracownik(admin_client):
    # Dwóch różnych pracowników może pracować w tych samych dniach — limit liczony osobno.
    stan = factories.StanowiskoFactory()
    a, b = factories.PracownikFactory(), factories.PracownikFactory()
    for i in range(6):                                       # 6 dni każdemu (w granicy tygodnia)
        assert admin_client.post("/api/przydzialy", json=_p(stan, a, factories.dzien(i))).status_code == 201
        assert admin_client.post("/api/przydzialy", json=_p(stan, b, factories.dzien(i))).status_code == 201


def test_config_domyslne_pola_prawo_pracy(admin_client):
    cfg = admin_client.get("/api/lokal/config").json()
    assert cfg["praca_min_odpoczynek_h"] == 11
    assert cfg["praca_max_dni_tydzien"] == 6
    assert cfg["praca_max_dni_miesiac"] == 22
