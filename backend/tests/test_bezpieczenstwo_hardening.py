"""Regresje utwardzenia bezpieczeństwa (audyt 2026-07-07): H1 ENCRYPTION_KEY wymagany w prod,
H2 role_guard egzekwuje bieżący stan konta z bazy (dezaktywacja działa natychmiast)."""

import models
import settings
from auth import create_access_token
from fastapi.testclient import TestClient
import main


def test_encryption_key_wymagany_w_produkcji(monkeypatch):
    """H1: brak ENCRYPTION_KEY figuruje jako błąd KRYTYCZNY (w produkcji → fail-fast startu,
    w dev → głośne ostrzeżenie). Sprawdzamy listę błędów niezależnie od trybu."""
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    errors, _ = settings._problems()
    assert any("ENCRYPTION_KEY" in e for e in errors)


def test_workstation_pin_pepper_musi_byc_osobnym_mocnym_sekretem(monkeypatch):
    monkeypatch.setenv("WORKSTATION_PIN_PEPPER", "krotki")
    errors, _ = settings._problems()
    assert any("WORKSTATION_PIN_PEPPER jest za krótki" in e for e in errors)

    shared = "wspolny-sekret-testowy-0123456789abcdef"
    monkeypatch.setenv("SECRET_KEY", shared)
    monkeypatch.setenv("WORKSTATION_PIN_PEPPER", shared)
    errors, _ = settings._problems()
    assert any("musi być osobnym sekretem" in e for e in errors)


def test_dezaktywacja_konta_uniewaznia_token_natychmiast(admin, db):
    """H2: ten sam, wciąż ważny token po dezaktywacji konta musi zostać odrzucony (401) —
    middleware czyta User.aktywny z bazy, nie ufa roli/statusowi wmrożonym w JWT."""
    tok = {"Authorization": f"Bearer {create_access_token(admin)}"}
    c = TestClient(main.app)
    assert c.get("/api/subskrypcja", headers=tok).status_code == 200   # aktywny admin
    u = db.get(models.User, admin.id)
    u.aktywny = False
    db.commit()
    assert c.get("/api/subskrypcja", headers=tok).status_code == 401   # dezaktywowany → odmowa


def test_naglowki_bezpieczenstwa_na_kazdej_odpowiedzi(client):
    """M3: X-Frame-Options / nosniff / Referrer-Policy na każdej odpowiedzi (też publicznej)."""
    r = client.get("/api/health")
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("Referrer-Policy") == "no-referrer"


def test_degradacja_roli_dziala_natychmiast(admin, db):
    """H2: obniżenie roli admin→employee natychmiast odbiera dostęp do endpointów admina."""
    tok = {"Authorization": f"Bearer {create_access_token(admin)}"}
    c = TestClient(main.app)
    assert c.get("/api/subskrypcja", headers=tok).status_code == 200
    u = db.get(models.User, admin.id)
    u.rola = "employee"
    db.commit()
    # employee nie ma dostępu do /api/subskrypcja (nie /api/me/, nie oversight) → 403
    assert c.get("/api/subskrypcja", headers=tok).status_code == 403
