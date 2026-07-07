"""Samoobsługa: kreator → provisioning (instancja-matka). Plan PŁATNY wymaga karty i zaczyna
14-dniowy trial z auto-obciążeniem po nim; plan DARMOWY staje się od razu bez karty. Jedna karta
= jeden trial (dedup). Realne procesy NIE są uruchamiane — provisioning.utworz_instancje mock."""

import models
import provisioning
from auth import verify_password
from deps import utcnow_naive

KARTA = {"numer": "4242 4242 4242 4242", "exp_miesiac": 12, "exp_rok": 2030, "cvc": "123"}


def _wlacz(monkeypatch, wywolania):
    """Włącza provisioning i podmienia utworz_instancje na atrapę zapisującą wywołania."""
    monkeypatch.setenv("PROVISIONING_ENABLED", "1")

    def fake_utworz(nazwa, **kw):
        wywolania.append({"nazwa": nazwa, **kw})
        return {"slug": "moja-knajpa", "nazwa": nazwa,
                "url": f"http://{kw.get('host', 'h')}:8100/?login"}

    monkeypatch.setattr(provisioning, "utworz_instancje", fake_utworz)
    monkeypatch.setattr(provisioning, "wczytaj_rejestr", lambda: [])


def test_plan_platny_z_karta_stawia_trial(client, db, monkeypatch):
    wyw = []
    _wlacz(monkeypatch, wyw)
    r = client.post("/api/online/rejestracja", json={
        "email": "Wlasciciel@Knajpa.PL", "haslo": "Haslo123!", "nazwa_lokalu": "Moja Knajpa",
        "plan": "pro", "typ_lokalu": "pizzeria", "moduly": {"modul_rezerwacje": True}, "karta": KARTA})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["tryb"] == "trial-karta" and body["status"] == "zrealizowana"
    assert body["plan"] == "pro" and body["karta_ostatnie4"] == "4242"
    assert "/?login" in body["url"]
    # Provisioning: trial=True, tier=pro, admin=email, hasło jako bcrypt (nie plaintext),
    # token karty (NIE numer) + ostatnie 4 cyfry.
    assert len(wyw) == 1
    call = wyw[0]
    assert call["trial"] is True and call["tier"] == "pro"
    assert call["admin_email"] == "wlasciciel@knajpa.pl"          # znormalizowany
    assert call["karta_ostatnie4"] == "4242" and call["karta_token"].startswith("sandbox_")
    assert call["konfiguracja"]["typ_lokalu"] == "pizzeria"
    assert verify_password("Haslo123!", call["admin_haslo_hash"])
    # PAN nie jest przechowywany; fingerprint (dedup) + ostatnie 4 cyfry — tak.
    rej = db.query(models.RejestracjaLokalu).first()
    assert rej.karta_fingerprint and rej.karta_ostatnie4 == "4242"
    assert "4242424242424242" not in ((rej.karta_token or "") + (rej.karta_fingerprint or ""))


def test_plan_platny_bez_karty_400(client, monkeypatch):
    _wlacz(monkeypatch, [])
    r = client.post("/api/online/rejestracja", json={
        "email": "a@b.pl", "haslo": "Haslo123!", "nazwa_lokalu": "Bez Karty", "plan": "pro"})
    assert r.status_code == 400


def test_dedup_jedna_karta_jeden_trial(client, monkeypatch):
    wyw = []
    _wlacz(monkeypatch, wyw)
    baza = {"haslo": "Haslo123!", "plan": "basic", "karta": KARTA}
    r1 = client.post("/api/online/rejestracja", json={**baza, "email": "a@b.pl", "nazwa_lokalu": "Pierwsza"})
    assert r1.status_code == 201, r1.text
    # Ta sama karta → drugi trial zablokowany (koniec wykorzystywania triala dwa razy).
    r2 = client.post("/api/online/rejestracja", json={**baza, "email": "b@b.pl", "nazwa_lokalu": "Druga"})
    assert r2.status_code == 409
    assert len(wyw) == 1   # instancja postawiona tylko raz


def test_darmowy_stawia_od_razu_bez_karty(client, monkeypatch):
    wyw = []
    _wlacz(monkeypatch, wyw)
    r = client.post("/api/online/rejestracja", json={
        "email": "free@lokal.pl", "haslo": "Haslo123!", "nazwa_lokalu": "Darmowa Knajpa", "plan": "darmowy"})
    assert r.status_code == 201, r.text
    assert r.json()["tryb"] == "darmowy" and r.json()["plan"] == "free"
    assert "/?login" in r.json()["url"]
    call = wyw[0]
    assert call["tier"] == "free" and not call.get("trial") and "karta_token" not in call


def test_trial_legacy_operatorski_bez_karty(client, monkeypatch):
    wyw = []
    _wlacz(monkeypatch, wyw)
    r = client.post("/api/online/rejestracja", json={
        "email": "trial@lokal.pl", "haslo": "Haslo123!", "nazwa_lokalu": "Trial Knajpa",
        "trial": True, "typ_lokalu": "pizzeria", "moduly": {"modul_imprezy": True}})
    assert r.status_code == 201, r.text
    assert r.json()["tryb"] == "trial" and r.json()["status"] == "zrealizowana"
    call = wyw[0]
    assert call["trial"] is True and call["tier"] == "premium" and call.get("karta_token") is None


def test_rejestracja_503_gdy_wylaczona(client):
    r = client.post("/api/online/rejestracja", json={
        "email": "a@b.pl", "haslo": "Haslo123!", "nazwa_lokalu": "Knajpa", "plan": "darmowy"})
    assert r.status_code == 503


def test_rejestracja_limit_ip(client, monkeypatch):
    _wlacz(monkeypatch, [])
    for i in range(3):
        assert client.post("/api/online/rejestracja", json={
            "email": f"a{i}@b.pl", "haslo": "Haslo123!", "nazwa_lokalu": f"Knajpa {i}", "plan": "darmowy"}).status_code == 201
    assert client.post("/api/online/rejestracja", json={
        "email": "x@b.pl", "haslo": "Haslo123!", "nazwa_lokalu": "Za duzo", "plan": "darmowy"}).status_code == 429


def test_rejestracja_walidacja(client, monkeypatch):
    _wlacz(monkeypatch, [])
    baza = {"email": "ok@lokal.pl", "haslo": "Haslo123!", "nazwa_lokalu": "Dobra Knajpa", "plan": "darmowy"}
    assert client.post("/api/online/rejestracja", json={**baza, "email": "zly-email"}).status_code == 400
    assert client.post("/api/online/rejestracja", json={**baza, "haslo": "slabe"}).status_code == 400
    assert client.post("/api/online/rejestracja", json={**baza, "nazwa_lokalu": "ab"}).status_code == 400
    assert client.post("/api/online/rejestracja", json={**baza, "plan": "kosmiczny"}).status_code == 400
    # Karta z błędną datą/CVC → 400 (walidacja karty).
    zla_karta = {"numer": "4242424242424242", "exp_miesiac": 13, "exp_rok": 2030, "cvc": "12"}
    assert client.post("/api/online/rejestracja", json={
        "email": "k@b.pl", "haslo": "Haslo123!", "nazwa_lokalu": "Zla Karta", "plan": "pro", "karta": zla_karta}).status_code == 400


def test_oplac_legacy_idempotentny(client, db, monkeypatch):
    """Tor legacy /oplac (operatorski checkout): ręczna rejestracja 'oczekuje' → opłacenie stawia
    instancję raz (idempotencja podwójnego kliknięcia) i wystawia GET status/polling + 404."""
    wyw = []
    _wlacz(monkeypatch, wyw)
    rej = models.RejestracjaLokalu(
        email="legacy@b.pl", haslo_hash="x", nazwa="Legacy Knajpa", tier="basic", netto=99.0,
        status="oczekuje", external_id="ext-legacy", utworzono_at=utcnow_naive())
    db.add(rej); db.commit()
    u1 = client.post("/api/online/rejestracja/ext-legacy/oplac").json()["url"]
    u2 = client.post("/api/online/rejestracja/ext-legacy/oplac").json()["url"]   # podwójny klik
    assert u1 == u2 and len(wyw) == 1
    assert client.get("/api/online/rejestracja/ext-legacy").json()["status"] == "zrealizowana"
    assert client.get("/api/online/rejestracja/nieistnieje").status_code == 404
