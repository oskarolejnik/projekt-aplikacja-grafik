"""Tier-gating modułów wg pakietu + trial 14 dni (pełny Premium → Free) + limit pracowników Free."""

from datetime import date, timedelta

import cennik
import factories


# ── cennik: drabina modułów ──────────────────────────────────────────────────
def test_moduly_dostepne_rosna_z_tierem():
    assert cennik.moduly_dostepne("free") == set()
    assert cennik.moduly_dostepne("basic") == {"modul_rozliczenia"}
    assert cennik.moduly_dostepne("pro") == {"modul_rozliczenia", "modul_rezerwacje",
                                             "rezerwacje_online", "modul_pos"}
    assert "modul_imprezy" not in cennik.moduly_dostepne("pro")
    assert cennik.moduly_dostepne("premium") == set(cennik.WSZYSTKIE_MODULY)
    assert cennik.moduly_dostepne("enterprise") == set(cennik.WSZYSTKIE_MODULY)
    assert cennik.plan_dla_modulu("modul_imprezy") == "premium"
    assert cennik.limit_pracownikow("free") == cennik.FREE_LIMIT_PRACOWNIKOW
    assert cennik.limit_pracownikow("pro") is None


# ── backend guard wg tieru ───────────────────────────────────────────────────
def test_free_blokuje_platne_moduly_wyzsze_odblokowuja(admin_client):
    admin_client.put("/api/subskrypcja", json={"tier": "free"})
    assert admin_client.get("/api/stoliki").status_code == 403       # rezerwacje = Pro
    admin_client.put("/api/subskrypcja", json={"tier": "pro"})
    assert admin_client.get("/api/stoliki").status_code == 200       # Pro odblokowuje
    assert admin_client.get("/api/imprezy?start=2026-01-01&end=2026-12-31").status_code == 403       # imprezy = Premium
    admin_client.put("/api/subskrypcja", json={"tier": "premium"})
    assert admin_client.get("/api/imprezy?start=2026-01-01&end=2026-12-31").status_code == 200


def test_antyfraud_wymaga_premium(admin_client):
    # Antyfraud POS = wirtualny moduł Premium (na modul_pos). Pro nie ma, Premium odblokowuje.
    admin_client.put("/api/subskrypcja", json={"tier": "pro"})
    assert admin_client.get("/api/antyfraud/podsumowanie").status_code == 403
    admin_client.put("/api/subskrypcja", json={"tier": "premium"})
    assert admin_client.get("/api/antyfraud/podsumowanie").status_code == 200


def test_subskrypcja_wystawia_dostepne_moduly(admin_client):
    admin_client.put("/api/subskrypcja", json={"tier": "pro"})
    s = admin_client.get("/api/subskrypcja").json()
    assert set(s["dostepne_moduly"]) == {"modul_rozliczenia", "modul_rezerwacje",
                                         "rezerwacje_online", "modul_pos"}
    assert s["moduly_wg_planu"]["modul_imprezy"] == "premium"
    assert s["poziom"] == cennik.poziom("pro")


# ── read-only nie miesza się z tier-gatingiem ────────────────────────────────
def test_wygasla_subskrypcja_czyta_ale_nie_zapisuje_w_planie_z_modulem(admin_client):
    admin_client.put("/api/subskrypcja", json={"tier": "premium", "status": "wygasla"})
    # odczyt modułu Premium działa (tryb tylko-odczyt), zapis blokuje middleware (402)
    assert admin_client.get("/api/imprezy?start=2026-01-01&end=2026-12-31").status_code == 200
    assert admin_client.post("/api/stoliki", json={"nazwa": "S", "pojemnosc": 2}).status_code == 402


# ── trial ────────────────────────────────────────────────────────────────────
def test_trial_daje_pelny_dostep_mimo_tier_free(admin_client):
    admin_client.put("/api/subskrypcja", json={
        "tier": "free", "status": "trial",
        "data_do": (date.today() + timedelta(days=14)).isoformat()})
    s = admin_client.get("/api/subskrypcja").json()
    assert s["status"] == "trial" and s["trial_dni"] == 14
    assert set(s["dostepne_moduly"]) == set(cennik.WSZYSTKIE_MODULY)   # trial = pełny Premium
    assert admin_client.get("/api/imprezy?start=2026-01-01&end=2026-12-31").status_code == 200        # moduł Premium działa


def test_trial_wygasa_do_free_automatycznie(admin_client):
    admin_client.put("/api/subskrypcja", json={
        "tier": "premium", "status": "trial",
        "data_do": (date.today() - timedelta(days=1)).isoformat()})   # trial minął wczoraj
    s = admin_client.get("/api/subskrypcja").json()                   # odczyt synchronizuje
    assert s["status"] == "aktywna" and s["tier"] == "free"
    assert s["trial_dni"] is None and s["dostepne_moduly"] == []
    assert s["aktywna"] is True                                       # Free dalej zapisywalny (nie read-only)
    assert admin_client.get("/api/imprezy?start=2026-01-01&end=2026-12-31").status_code == 403        # moduł Premium już zablokowany


# ── limit pracowników Free ───────────────────────────────────────────────────
def test_free_limit_pracownikow_i_zdjecie_przez_basic(admin_client):
    admin_client.put("/api/subskrypcja", json={"tier": "free", "status": "aktywna"})
    for _ in range(cennik.FREE_LIMIT_PRACOWNIKOW):
        factories.PracownikFactory(aktywny=True)                      # fabryka omija endpoint
    r = admin_client.post("/api/pracownicy", json={"imie": "Nowy", "nazwisko": "Ponad", "aktywny": True})
    assert r.status_code == 402 and "Basic" in r.json()["detail"]
    admin_client.put("/api/subskrypcja", json={"tier": "basic"})      # Basic = bez limitu
    assert admin_client.post("/api/pracownicy",
                             json={"imie": "Nowy", "nazwisko": "Wchodzi", "aktywny": True}).status_code == 201
