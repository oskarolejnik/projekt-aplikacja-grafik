"""Monetyzacja Faza 0–2: cennik, proration (upgrade z dopłatą), grace period, egzekwowanie."""

from datetime import date, timedelta

import cennik
import subskrypcja_billing as sb
from deps import stan_subskrypcji, GRACE_DNI


# ── Faza 2: czysta prorata ────────────────────────────────────────────────────

def test_prorata_pro_na_premium_polowa_okresu():
    # okres 01–30.06 (30 dni), dziś 16.06 → 15 dni pozostało, współczynnik 0.5
    r = sb.oblicz_prorate("pro", "premium", date(2026, 6, 1), date(2026, 6, 30), dzis=date(2026, 6, 16))
    assert r["kierunek"] == "upgrade"
    assert r["wspolczynnik"] == 0.5 and r["pozostale_dni"] == 15
    assert r["doplata_netto"] == 75.0                 # (349-199)*0.5
    assert r["doplata_brutto"] == round(75.0 * 1.23, 2)   # 92.25
    assert r["nowa_cena_pelna_netto"] == 349.0


def test_prorata_downgrade_daje_kredyt():
    r = sb.oblicz_prorate("premium", "pro", date(2026, 6, 1), date(2026, 6, 30), dzis=date(2026, 6, 16))
    assert r["kierunek"] == "downgrade"
    assert r["doplata_netto"] == 0.0 and r["kredyt_netto"] == 75.0


def test_prorata_saldo_kredytu_pomniejsza_doplate():
    r = sb.oblicz_prorate("pro", "premium", date(2026, 6, 1), date(2026, 6, 30),
                          dzis=date(2026, 6, 16), saldo_kredytu=20.0)
    assert r["doplata_netto"] == 55.0 and r["saldo_kredytu_uzyte"] == 20.0


def test_prorata_bez_okresu_wspolczynnik_zero():
    r = sb.oblicz_prorate("pro", "premium", None, None, dzis=date(2026, 6, 16))
    assert r["wspolczynnik"] == 0.0 and r["doplata_netto"] == 0.0


def test_cennik_brutto_vat():
    assert cennik.brutto(199) == round(199 * 1.23, 2)
    assert cennik.cena_netto("premium") == 349.0
    assert cennik.cena_netto("enterprise", override=1200) == 1200.0


# ── Faza 1: grace period + egzekwowanie ───────────────────────────────────────

def test_grace_stany(admin_client, db):
    import models
    from deps import get_subskrypcja
    s = get_subskrypcja(db)
    dzis = date.today()
    # aktywna: okres w przyszłości
    s.status = "aktywna"; s.data_do = dzis + timedelta(days=5); db.commit()
    assert stan_subskrypcji(db) == "aktywna"
    # grace: po data_do ale w oknie GRACE_DNI
    s.data_do = dzis - timedelta(days=1); db.commit()
    assert stan_subskrypcji(db) == "grace"
    # zablokowana: po grace
    s.data_do = dzis - timedelta(days=GRACE_DNI + 1); db.commit()
    assert stan_subskrypcji(db) == "zablokowana"
    # zawieszona ręcznie blokuje mimo daty w przyszłości (bez grace)
    s.status = "zawieszona"; s.data_do = dzis + timedelta(days=30); db.commit()
    assert stan_subskrypcji(db) == "zablokowana"


def test_grace_przepuszcza_zapis_po_terminie(admin_client, db):
    from deps import get_subskrypcja
    s = get_subskrypcja(db)
    s.status = "aktywna"; s.data_do = date.today() - timedelta(days=2); db.commit()   # 2 dni po terminie = grace
    # zapis PRZECHODZI w grace (miękka degradacja)
    assert admin_client.post("/api/stoliki", json={"nazwa": "G1", "pojemnosc": 2}).status_code in (201, 403)
    # (403 tylko gdy modul_rezerwacje off; kluczowe: NIE 402)
    r = admin_client.get("/api/subskrypcja").json()
    assert r["stan"] == "grace" and r["data_grace"]


def test_po_grace_402(admin_client, db):
    from deps import get_subskrypcja
    s = get_subskrypcja(db)
    s.status = "aktywna"; s.data_do = date.today() - timedelta(days=GRACE_DNI + 1); db.commit()
    assert admin_client.post("/api/stoliki", json={"nazwa": "B1", "pojemnosc": 2}).status_code == 402


# ── Faza 2: endpointy upgrade ─────────────────────────────────────────────────

def test_upgrade_endpoint_podglad_i_wykonanie(admin_client, db):
    from deps import get_subskrypcja
    s = get_subskrypcja(db)
    dzis = date.today()
    s.tier = "pro"; s.status = "aktywna"; s.data_od = dzis.replace(day=1)
    s.data_do = (dzis.replace(day=1) + timedelta(days=29)); db.commit()

    pod = admin_client.get("/api/subskrypcja/upgrade/podglad?tier=premium").json()
    assert pod["kierunek"] == "upgrade" and pod["doplata_netto"] > 0

    r = admin_client.post("/api/subskrypcja/upgrade", json={"tier": "premium"})
    assert r.status_code == 200
    b = r.json()
    assert b["subskrypcja"]["tier"] == "premium"          # tier w górę od razu
    assert b["platnosc"] and b["platnosc"]["link"]        # płatność-dopłata utworzona

    # ten sam tier → 400
    assert admin_client.post("/api/subskrypcja/upgrade", json={"tier": "premium"}).status_code == 400


def test_odnow_i_oplac_przedluza_i_odblokuje(admin_client, db):
    from deps import get_subskrypcja
    s = get_subskrypcja(db)
    s.tier = "pro"; s.status = "wygasla"; s.data_do = date.today() - timedelta(days=30); db.commit()
    # zablokowana → zapis 402
    assert admin_client.post("/api/stoliki", json={"nazwa": "Z1", "pojemnosc": 2}).status_code == 402

    p = admin_client.post("/api/subskrypcja/odnow").json()
    assert p["link"] and p["brutto"] > 0
    admin_client.post(f"/api/subskrypcja/platnosc/{p['external_id']}/oplac")
    # po opłaceniu: aktywna + data_do w przyszłości → zapis przechodzi
    r = admin_client.get("/api/subskrypcja").json()
    assert r["stan"] == "aktywna"
    assert admin_client.post("/api/stoliki", json={"nazwa": "Z2", "pojemnosc": 2}).status_code in (201, 403)
