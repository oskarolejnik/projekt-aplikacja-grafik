"""Płatności zadatków online (platnosci.py + /api/platnosci) — Rec#7, tryb sandbox."""

import integracje
import platnosci


# ── warstwa domenowa (sandbox) ────────────────────────────────────────────────
def test_utworz_platnosc_sandbox(db, monkeypatch):
    monkeypatch.setattr(integracje, "skonfigurowane", lambda k: False)  # brak bramki → sandbox
    p = platnosci.utworz_platnosc(db, termin_id=None, kwota=150.0)
    assert p.id and p.status == "oczekuje" and p.provider == "sandbox"
    assert p.external_id and p.link and str(p.external_id) in p.link
    assert p.kwota == 150.0
    assert p.oplacono_at is None


def test_oznacz_oplacona_idempotentne(db, monkeypatch):
    monkeypatch.setattr(integracje, "skonfigurowane", lambda k: False)
    ext = platnosci.utworz_platnosc(db, None, 100).external_id
    p2 = platnosci.oznacz_oplacona(db, ext)
    assert p2.status == "oplacona" and p2.oplacono_at is not None
    stamp = p2.oplacono_at
    p3 = platnosci.oznacz_oplacona(db, ext)          # ponownie — bez zmiany znacznika
    assert p3.status == "oplacona" and p3.oplacono_at == stamp


def test_oznacz_oplacona_brak_zwraca_none(db):
    assert platnosci.oznacz_oplacona(db, "token-ktorego-nie-ma") is None


# ── endpointy (admin) ─────────────────────────────────────────────────────────
def test_endpoint_utworz_i_lista(admin_client):
    r = admin_client.post("/api/platnosci", json={"termin_id": None, "kwota": 200})
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["status"] == "oczekuje" and b["link"] and b["kwota"] == 200
    lst = admin_client.get("/api/platnosci").json()
    assert any(x["id"] == b["id"] for x in lst)


def test_endpoint_kwota_niedodatnia_400(admin_client):
    assert admin_client.post("/api/platnosci", json={"kwota": 0}).status_code == 400
    assert admin_client.post("/api/platnosci", json={"kwota": -5}).status_code == 400


def test_endpoint_oznacz_oplacona(admin_client):
    b = admin_client.post("/api/platnosci", json={"kwota": 50}).json()
    r = admin_client.post(f"/api/platnosci/{b['id']}/oplacona")
    assert r.status_code == 200 and r.json()["status"] == "oplacona"
    assert admin_client.post("/api/platnosci/999999/oplacona").status_code == 404


def test_platnosci_tylko_admin(client):
    tok = client.post("/api/auth/register",
                      json={"email": "kelnerx@lokal.pl", "haslo": "Haslo123!", "imie": "A", "nazwisko": "B"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {tok}"})
    assert client.post("/api/platnosci", json={"kwota": 10}).status_code == 403
    assert client.get("/api/platnosci").status_code == 403
