"""Moduł SMS (sms.py) — best-effort przez bramkę HTTP, no-op gdy nieskonfigurowany (Rec#7)."""

import integracje
import sms


class FakeResp:
    def __init__(self, status=200):
        self.status = status
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


# ── normalizacja numeru ───────────────────────────────────────────────────────
def test_normalizuj_numer():
    assert sms._normalizuj_numer("600 100 200") == "+48600100200"      # krajowy PL
    assert sms._normalizuj_numer("+48600100200") == "+48600100200"     # już E.164
    assert sms._normalizuj_numer("0600100200") == "+48600100200"       # z zerem wiodącym
    assert sms._normalizuj_numer("00420123456789") == "+420123456789"  # 00 → +
    assert sms._normalizuj_numer("") == ""
    assert sms._normalizuj_numer("abc") == ""                          # śmieci → pusty


# ── best-effort: no-op gdy integracja wyłączona ───────────────────────────────
def test_noop_gdy_nieskonfigurowany(monkeypatch):
    monkeypatch.delenv("SMS_API_TOKEN", raising=False)
    monkeypatch.delenv("SMS_API_URL", raising=False)
    assert integracje.skonfigurowane("sms") is False
    assert sms.wyslij_sms("600100200", "Przypomnienie") is False       # no-op, nie rzuca


def test_pusty_numer_false(monkeypatch):
    monkeypatch.setattr(integracje, "skonfigurowane", lambda k: True)
    assert sms.wyslij_sms("", "x") is False


# ── wysyłka gdy skonfigurowany ────────────────────────────────────────────────
def test_wyslij_sms_sukces(monkeypatch):
    monkeypatch.setattr(integracje, "skonfigurowane", lambda k: True)
    monkeypatch.setenv("SMS_API_URL", "https://bramka.example/send")
    monkeypatch.setenv("SMS_API_TOKEN", "tajny-token")
    wyslane = {}
    def fake_open_no_redirect(req, timeout=10):
        wyslane["url"] = req.full_url
        wyslane["auth"] = req.headers.get("Authorization")
        return FakeResp(200)
    monkeypatch.setattr(sms, "_open_no_redirect", fake_open_no_redirect)
    assert sms.wyslij_sms("600 100 200", "Przypomnienie o rezerwacji") is True
    assert wyslane["url"] == "https://bramka.example/send"
    assert wyslane["auth"] == "Bearer tajny-token"


def test_blad_sieci_nie_rzuca(monkeypatch):
    monkeypatch.setattr(integracje, "skonfigurowane", lambda k: True)
    monkeypatch.setenv("SMS_API_URL", "https://bramka.example/send")
    def boom(*a, **k):
        raise OSError("brak sieci")
    monkeypatch.setattr(sms, "_open_no_redirect", boom)
    assert sms.wyslij_sms("600100200", "x") is False                   # błąd → False, bez wyjątku


def test_status_5xx_false(monkeypatch):
    monkeypatch.setattr(integracje, "skonfigurowane", lambda k: True)
    monkeypatch.setenv("SMS_API_URL", "https://bramka.example/send")
    monkeypatch.setattr(sms, "_open_no_redirect", lambda *a, **k: FakeResp(500))
    assert sms.wyslij_sms("600100200", "x") is False
