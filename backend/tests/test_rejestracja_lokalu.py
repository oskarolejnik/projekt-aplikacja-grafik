"""Tor z płatnością: kreator → checkout → auto-provision konta + instancji (instancja-matka).
Realne procesy NIE są uruchamiane — provisioning.utworz_instancje jest mockowany."""

import models
import provisioning
from auth import verify_password


def _wlacz(monkeypatch, wywolania):
    """Włącza provisioning i podmienia utworz_instancje na atrapę zapisującą wywołania."""
    monkeypatch.setenv("PROVISIONING_ENABLED", "1")

    def fake_utworz(nazwa, **kw):
        wywolania.append({"nazwa": nazwa, **kw})
        return {"slug": "moja-knajpa", "nazwa": nazwa,
                "url": f"http://{kw.get('host', 'h')}:8100/?login"}

    monkeypatch.setattr(provisioning, "utworz_instancje", fake_utworz)
    monkeypatch.setattr(provisioning, "wczytaj_rejestr", lambda: [])


def test_rejestracja_oplac_stawia_konto_i_instancje(client, db, monkeypatch):
    wyw = []
    _wlacz(monkeypatch, wyw)

    # 1) Kreator zapisuje rejestrację oczekującą na płatność.
    r = client.post("/api/online/rejestracja", json={
        "email": "Wlasciciel@Knajpa.PL", "haslo": "Haslo123!", "nazwa_lokalu": "Moja Knajpa",
        "plan": "pro", "typ_lokalu": "pizzeria", "moduly": {"modul_rezerwacje": True}})
    assert r.status_code == 201, r.text
    body = r.json()
    ext = body["external_id"]
    assert body["plan"] == "pro" and body["brutto"] > 0
    assert body["link"] == f"/?rejestracja-oplac={ext}"
    # Nic jeszcze nie postawione (czeka na płatność).
    assert wyw == []
    assert db.query(models.RejestracjaLokalu).count() == 1

    # 2) Opłacenie (sandbox) → provisioning z gotowym adminem.
    o = client.post(f"/api/online/rejestracja/{ext}/oplac")
    assert o.status_code == 200, o.text
    assert o.json()["status"] == "zrealizowana"
    assert "/?login" in o.json()["url"]
    # Provisioning dostał e-mail admina, tier i konfigurację — HASŁO jako bcrypt, nie plaintext.
    assert len(wyw) == 1
    call = wyw[0]
    assert call["admin_email"] == "wlasciciel@knajpa.pl"   # znormalizowany
    assert call["tier"] == "pro"
    assert call["konfiguracja"]["typ_lokalu"] == "pizzeria"
    assert call["admin_haslo_hash"] != "Haslo123!"
    assert verify_password("Haslo123!", call["admin_haslo_hash"])


def test_oplac_idempotentne_nie_stawia_drugiej_instancji(client, monkeypatch):
    wyw = []
    _wlacz(monkeypatch, wyw)
    ext = client.post("/api/online/rejestracja", json={
        "email": "a@b.pl", "haslo": "Haslo123!", "nazwa_lokalu": "Knajpa Dwa", "plan": "basic"}).json()["external_id"]
    u1 = client.post(f"/api/online/rejestracja/{ext}/oplac").json()["url"]
    u2 = client.post(f"/api/online/rejestracja/{ext}/oplac").json()["url"]   # podwójny klik
    assert u1 == u2
    assert len(wyw) == 1   # instancja postawiona TYLKO raz


def test_rejestracja_trial_stawia_od_razu_bez_platnosci(client, monkeypatch):
    wyw = []
    _wlacz(monkeypatch, wyw)
    r = client.post("/api/online/rejestracja", json={
        "email": "trial@lokal.pl", "haslo": "Haslo123!", "nazwa_lokalu": "Trial Knajpa",
        "trial": True, "typ_lokalu": "pizzeria", "moduly": {"modul_imprezy": True}})
    assert r.status_code == 201, r.text
    assert r.json()["tryb"] == "trial" and r.json()["status"] == "zrealizowana"
    assert "/?login" in r.json()["url"]
    # provisioning wywołany OD RAZU z trial=True + adminem (bez kroku płatności)
    assert len(wyw) == 1
    call = wyw[0]
    assert call["trial"] is True and call["admin_email"] == "trial@lokal.pl" and call["tier"] == "premium"
    assert call["konfiguracja"]["typ_lokalu"] == "pizzeria"


def test_checkout_zero_zl_dla_darmowego(client, monkeypatch):
    wyw = []
    _wlacz(monkeypatch, wyw)
    r = client.post("/api/online/rejestracja", json={
        "email": "free@lokal.pl", "haslo": "Haslo123!", "nazwa_lokalu": "Darmowa Knajpa", "plan": "darmowy"})
    assert r.status_code == 201
    assert r.json()["plan"] == "free" and r.json()["brutto"] == 0
    o = client.post(f"/api/online/rejestracja/{r.json()['external_id']}/oplac")
    assert o.status_code == 200 and o.json()["status"] == "zrealizowana"
    assert wyw[0]["tier"] == "free"


def test_rejestracja_503_gdy_wylaczona(client):
    r = client.post("/api/online/rejestracja", json={
        "email": "a@b.pl", "haslo": "Haslo123!", "nazwa_lokalu": "Knajpa", "plan": "pro"})
    assert r.status_code == 503


def test_rejestracja_limit_ip(client, monkeypatch):
    _wlacz(monkeypatch, [])
    for i in range(3):
        assert client.post("/api/online/rejestracja", json={
            "email": f"a{i}@b.pl", "haslo": "Haslo123!", "nazwa_lokalu": f"Knajpa {i}", "plan": "pro"}).status_code == 201
    assert client.post("/api/online/rejestracja", json={
        "email": "x@b.pl", "haslo": "Haslo123!", "nazwa_lokalu": "Za duzo", "plan": "pro"}).status_code == 429


def test_rejestracja_walidacja(client, monkeypatch):
    _wlacz(monkeypatch, [])
    baza = {"email": "ok@lokal.pl", "haslo": "Haslo123!", "nazwa_lokalu": "Dobra Knajpa", "plan": "pro"}
    assert client.post("/api/online/rejestracja", json={**baza, "email": "zly-email"}).status_code == 400
    assert client.post("/api/online/rejestracja", json={**baza, "haslo": "slabe"}).status_code == 400
    assert client.post("/api/online/rejestracja", json={**baza, "nazwa_lokalu": "ab"}).status_code == 400
    assert client.post("/api/online/rejestracja", json={**baza, "plan": "kosmiczny"}).status_code == 400


def test_status_polling(client, monkeypatch):
    wyw = []
    _wlacz(monkeypatch, wyw)
    ext = client.post("/api/online/rejestracja", json={
        "email": "poll@lokal.pl", "haslo": "Haslo123!", "nazwa_lokalu": "Poll Knajpa", "plan": "pro"}).json()["external_id"]
    assert client.get(f"/api/online/rejestracja/{ext}").json()["status"] == "oczekuje"
    client.post(f"/api/online/rejestracja/{ext}/oplac")
    stan = client.get(f"/api/online/rejestracja/{ext}").json()
    assert stan["status"] == "zrealizowana" and "/?login" in stan["url"]
    assert client.get("/api/online/rejestracja/nieistnieje").status_code == 404
