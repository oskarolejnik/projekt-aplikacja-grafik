"""Rate-limit + lockout logowania (ratelimit.py + /api/auth/login) — ochrona przed brute-force."""

import pytest

import ratelimit


class FakeZegar:
    """Sterowalny zegar — pozwala testować lockout/okno bez realnego sleep."""
    def __init__(self, t=1000.0):
        self.t = t
    def __call__(self):
        return self.t
    def plus(self, s):
        self.t += s


@pytest.fixture
def zegar(monkeypatch):
    z = FakeZegar()
    monkeypatch.setattr(ratelimit, "_zegar", z)
    return z


# ── jednostkowe (moduł) ───────────────────────────────────────────────────────
def test_ponizej_progu_bez_blokady(zegar):
    for _ in range(ratelimit.MAX_PROBY - 1):
        assert ratelimit.zarejestruj_porazke("k") == 0
    assert ratelimit.pozostala_blokada("k") == 0          # jeszcze nie zablokowany


def test_lockout_po_przekroczeniu_progu(zegar):
    blok = 0
    for _ in range(ratelimit.MAX_PROBY):
        blok = ratelimit.zarejestruj_porazke("k")
    assert blok == ratelimit.LOCKOUT_SEKUNDY               # próg -> nałożona blokada
    assert ratelimit.pozostala_blokada("k") == ratelimit.LOCKOUT_SEKUNDY


def test_blokada_wygasa_po_czasie(zegar):
    for _ in range(ratelimit.MAX_PROBY):
        ratelimit.zarejestruj_porazke("k")
    zegar.plus(ratelimit.LOCKOUT_SEKUNDY - 1)
    assert ratelimit.pozostala_blokada("k") == 1
    zegar.plus(2)                                          # po wygaśnięciu
    assert ratelimit.pozostala_blokada("k") == 0
    # Po wygaśnięciu licznik startuje od zera — jedna porażka nie blokuje.
    assert ratelimit.zarejestruj_porazke("k") == 0


def test_sukces_kasuje_licznik(zegar):
    for _ in range(ratelimit.MAX_PROBY - 1):
        ratelimit.zarejestruj_porazke("k")
    ratelimit.zarejestruj_sukces("k")
    assert ratelimit.pozostala_blokada("k") == 0
    assert ratelimit.zarejestruj_porazke("k") == 0         # liczy od nowa


def test_okno_akumulacji_wygasa(zegar):
    for _ in range(ratelimit.MAX_PROBY - 1):
        ratelimit.zarejestruj_porazke("k")
    zegar.plus(ratelimit.OKNO_SEKUNDY + 1)                 # poza oknem
    # Kolejna porażka liczy się jako pierwsza — brak blokady mimo (MAX-1) wcześniej.
    assert ratelimit.zarejestruj_porazke("k") == 0


def test_klucze_niezalezne(zegar):
    for _ in range(ratelimit.MAX_PROBY):
        ratelimit.zarejestruj_porazke("a")
    assert ratelimit.pozostala_blokada("a") > 0
    assert ratelimit.pozostala_blokada("b") == 0           # inny klucz nietknięty


# ── integracyjne (endpoint /api/auth/login) ───────────────────────────────────
def _zarejestruj(client, ident):
    return client.post("/api/auth/register",
                       json={"email": f"{ident}@lokal.pl", "haslo": "Haslo123!", "imie": "T", "nazwisko": "U"})


def test_login_blokuje_po_serii_bledow(client):
    _zarejestruj(client, "brutalny")
    # MAX nieudanych prób -> wszystkie 401 (blokada sprawdzana przed weryfikacją).
    for _ in range(ratelimit.MAX_PROBY):
        assert client.post("/api/auth/login", json={"email": "brutalny@lokal.pl", "haslo": "Zle1!zle"}).status_code == 401
    # Kolejna próba (nawet z poprawnym hasłem) -> 429 z nagłówkiem Retry-After.
    r = client.post("/api/auth/login", json={"email": "brutalny@lokal.pl", "haslo": "Haslo123!"})
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0


def test_login_sukces_resetuje_licznik(client):
    _zarejestruj(client, "resetowy")
    for _ in range(ratelimit.MAX_PROBY - 1):
        assert client.post("/api/auth/login", json={"email": "resetowy@lokal.pl", "haslo": "Zle1!zle"}).status_code == 401
    # Poprawne logowanie tuż poniżej progu -> 200 i kasuje licznik.
    assert client.post("/api/auth/login", json={"email": "resetowy@lokal.pl", "haslo": "Haslo123!"}).status_code == 200
    # Po resecie znów wolno próbować (401, nie 429).
    assert client.post("/api/auth/login", json={"email": "resetowy@lokal.pl", "haslo": "Zle1!zle"}).status_code == 401
