"""Samoobsługowy provisioning (flota): bramka env, limity, slug/port/rejestr.
Realne procesy NIE są uruchamiane — tor subprocess/health mockowany."""

import provisioning


def test_status_wylaczony_domyslnie(client):
    r = client.get("/api/online/nowy-lokal/status")
    assert r.status_code == 200
    assert r.json() == {"enabled": False}


def test_nowy_lokal_503_gdy_wylaczony(client):
    r = client.post("/api/online/nowy-lokal", json={"nazwa_lokalu": "Testowa Knajpa"})
    assert r.status_code == 503


def test_nowy_lokal_tor_wlaczony(client, monkeypatch):
    monkeypatch.setenv("PROVISIONING_ENABLED", "1")
    wywolania = []

    def fake_utworz(nazwa, email, host, tier=None):
        wywolania.append({"nazwa": nazwa, "email": email, "tier": tier})
        return {"slug": "testowa-knajpa", "nazwa": nazwa, "url": f"http://{host}:8100/?start"}

    monkeypatch.setattr(provisioning, "utworz_instancje", fake_utworz)
    # status raportuje dostępność i wolne miejsca
    monkeypatch.setattr(provisioning, "wczytaj_rejestr", lambda: [])
    s = client.get("/api/online/nowy-lokal/status").json()
    assert s["enabled"] is True and s["wolne_miejsca"] == provisioning.LIMIT_FLOTY

    r = client.post("/api/online/nowy-lokal", json={"nazwa_lokalu": "Testowa Knajpa", "email": "a@b.pl"})
    assert r.status_code == 201
    assert r.json()["slug"] == "testowa-knajpa" and "/?start" in r.json()["url"]
    assert wywolania[-1]["tier"] is None   # bez planu — tier zostaje domyślny

    # pakiet z cennika → tier subskrypcji instancji (darmowy→free, pro→pro)
    client.post("/api/online/nowy-lokal", json={"nazwa_lokalu": "Knajpa Pro", "plan": "pro"})
    assert wywolania[-1]["tier"] == "pro"
    client.post("/api/online/nowy-lokal", json={"nazwa_lokalu": "Knajpa Free", "plan": "Darmowy"})
    assert wywolania[-1]["tier"] == "free"

    # walidacja nazwy
    assert client.post("/api/online/nowy-lokal", json={"nazwa_lokalu": "ab"}).status_code == 400


def test_nowy_lokal_limit_ip(client, monkeypatch):
    monkeypatch.setenv("PROVISIONING_ENABLED", "1")
    monkeypatch.setattr(provisioning, "utworz_instancje",
                        lambda nazwa, email, host, tier=None: {"slug": "x", "nazwa": nazwa, "url": "http://h:1/?start"})
    for i in range(3):
        assert client.post("/api/online/nowy-lokal", json={"nazwa_lokalu": f"Lokal {i} abc"}).status_code == 201
    assert client.post("/api/online/nowy-lokal", json={"nazwa_lokalu": "Za duzo"}).status_code == 429


def test_flota_tylko_admin(admin_client, monkeypatch):
    # UWAGA: fixture admin_client MUTUJE nagłówki współdzielonego clienta —
    # anonimowe wywołanie musi iść świeżym TestClientem (gotcha z conftest).
    from fastapi.testclient import TestClient
    import main
    monkeypatch.setattr(provisioning, "status_floty", lambda: [{"slug": "a", "port": 8100, "dziala": True}])
    with TestClient(main.app) as anon:
        assert anon.get("/api/flota").status_code == 401
    r = admin_client.get("/api/flota")
    assert r.status_code == 200
    body = r.json()
    assert body["limit"] == provisioning.LIMIT_FLOTY and body["instancje"][0]["slug"] == "a"


def test_slug_z_nazwy_polskie_znaki_i_kolizje():
    assert provisioning.slug_z_nazwy("Restauracja Pod Lipą", set()) == "restauracja-pod-lipa"
    zajete = {"restauracja-pod-lipa"}
    assert provisioning.slug_z_nazwy("Restauracja Pod Lipą", zajete) == "restauracja-pod-lipa-2"
    assert provisioning.slug_z_nazwy("źdźbło & Co!!!", set()) == "zdzblo-co"
    assert len(provisioning.slug_z_nazwy("x" * 100, set())) <= 40


def test_przydziel_port_omija_zajete(monkeypatch):
    monkeypatch.setattr(provisioning, "_port_wolny", lambda p: p != provisioning.PORT_OD)
    rejestr = [{"port": provisioning.PORT_OD + 1}]
    assert provisioning.przydziel_port(rejestr) == provisioning.PORT_OD + 2


def test_rejestr_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(provisioning, "INSTANCES_DIR", tmp_path)
    monkeypatch.setattr(provisioning, "REGISTRY", tmp_path / "registry.json")
    assert provisioning.wczytaj_rejestr() == []
    provisioning.zapisz_rejestr([{"slug": "a", "port": 8100}])
    assert provisioning.wczytaj_rejestr() == [{"slug": "a", "port": 8100}]
