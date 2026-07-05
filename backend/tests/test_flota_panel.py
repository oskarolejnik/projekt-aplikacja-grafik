"""Panel operatora „Flota" (instancja-matka): endpoint pulsu instancji (FLEET_TOKEN)
+ agregacja subskrypcji wszystkich lokali z licznikami wg pakietu/statusu."""

import provisioning


def test_puls_wymaga_fleet_tokenu(client, monkeypatch):
    monkeypatch.delenv("FLEET_TOKEN", raising=False)
    assert client.get("/api/instancja/puls").status_code == 403      # brak tokenu w env
    monkeypatch.setenv("FLEET_TOKEN", "sekret-floty")
    assert client.get("/api/instancja/puls").status_code == 403      # brak nagłówka
    assert client.get("/api/instancja/puls",
                      headers={"X-Fleet-Token": "zly"}).status_code == 403


def test_puls_zwraca_podsumowanie(client, monkeypatch):
    monkeypatch.setenv("FLEET_TOKEN", "sekret-floty")
    r = client.get("/api/instancja/puls", headers={"X-Fleet-Token": "sekret-floty"})
    assert r.status_code == 200
    b = r.json()
    # niewrażliwe podsumowanie — bez PII/płac
    assert set(b) == {"nazwa_lokalu", "tier", "status", "aktywna", "data_do",
                      "liczba_uzytkownikow", "liczba_pracownikow"}
    assert b["tier"] == "free" and b["aktywna"] is True             # domyślna subskrypcja


def test_flota_agreguje_subskrypcje(admin_client, monkeypatch):
    monkeypatch.setenv("PROVISIONING_ENABLED", "1")
    monkeypatch.setenv("FLEET_TOKEN", "sekret-floty")
    monkeypatch.setattr(provisioning, "status_floty", lambda: [
        {"slug": "a", "nazwa": "Bar A", "port": 8100, "tier": "pro", "dziala": True,
         "email": "a@x.pl", "utworzono_at": "2026-07-01T10:00:00"},
        {"slug": "b", "nazwa": "Bar B", "port": 8101, "tier": "free", "dziala": True,
         "utworzono_at": "2026-07-02T10:00:00"},
        {"slug": "c", "nazwa": "Bar C", "port": 8102, "tier": "pro", "dziala": False,
         "utworzono_at": "2026-07-03T10:00:00"},
    ])
    # żywe pulsy: A pro/aktywna, B free/trial, C nie odpowiada (None)
    pulsy = {8100: {"nazwa_lokalu": "Bar A", "tier": "pro", "status": "aktywna", "aktywna": True,
                    "data_do": None, "liczba_uzytkownikow": 5},
             8101: {"nazwa_lokalu": "Bar B", "tier": "free", "status": "trial", "aktywna": True,
                    "data_do": "2026-08-01", "liczba_uzytkownikow": 2}}
    monkeypatch.setattr(provisioning, "puls_instancji", lambda port, token, **k: pulsy.get(port))

    b = admin_client.get("/api/flota").json()
    assert b["enabled"] is True and b["puls_dostepny"] is True
    p = b["podsumowanie"]
    assert p["instancji"] == 3
    assert p["aktywnych"] == 2                                       # A i B; C bez pulsu
    assert p["wg_pakietu"] == {"pro": 2, "free": 1}                 # C fallback na tier z rejestru
    assert p["wg_statusu"] == {"aktywna": 1, "trial": 1}            # tylko z żywych pulsów
    inst_c = next(i for i in b["instancje"] if i["slug"] == "c")
    assert inst_c["puls"] is None                                    # nieodpowiadająca instancja


def test_flota_bez_fleet_tokenu_sam_rejestr(admin_client, monkeypatch):
    monkeypatch.setenv("PROVISIONING_ENABLED", "1")
    monkeypatch.delenv("FLEET_TOKEN", raising=False)
    monkeypatch.setattr(provisioning, "status_floty", lambda: [
        {"slug": "a", "nazwa": "Bar A", "port": 8100, "tier": "basic", "dziala": True,
         "utworzono_at": "2026-07-01T10:00:00"}])
    b = admin_client.get("/api/flota").json()
    assert b["puls_dostepny"] is False
    assert b["podsumowanie"]["wg_pakietu"] == {"basic": 1}          # z rejestru
    assert b["podsumowanie"]["wg_statusu"] == {}                    # brak pulsów → brak statusów
