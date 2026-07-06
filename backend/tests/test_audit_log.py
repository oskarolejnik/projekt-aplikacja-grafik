"""Dziennik audytu dostępu do danych płacowych (AuditLog + /api/audit-log) — RODO."""

import models


def test_raport_godzin_zapisuje_audyt(admin_client, db):
    r = admin_client.get("/api/raporty/godziny?rok=2026&miesiac=7")
    assert r.status_code == 200, r.text
    wpisy = db.query(models.AuditLog).all()
    assert len(wpisy) == 1
    w = wpisy[0]
    assert w.akcja == "raport_godzin"
    assert w.zasob == "2026-07"
    assert w.login == "admin_test"        # denormalizacja aktora
    assert w.ts is not None


def test_audit_log_lista_i_filtry(admin_client):
    admin_client.get("/api/raporty/godziny?rok=2026&miesiac=7")
    admin_client.get("/api/raporty/godziny?rok=2026&miesiac=8")

    wszystko = admin_client.get("/api/audit-log").json()
    assert len(wszystko) == 2
    assert wszystko[0]["id"] > wszystko[1]["id"]          # najnowsze najpierw

    assert len(admin_client.get("/api/audit-log?akcja=raport_godzin").json()) == 2
    assert admin_client.get("/api/audit-log?akcja=nieistnieje").json() == []
    assert admin_client.get("/api/audit-log?login=nikt").json() == []
    assert len(admin_client.get("/api/audit-log?login=admin_test").json()) == 2


def test_audit_log_filtruje_zakres_dat(admin_client):
    admin_client.get("/api/raporty/godziny?rok=2026&miesiac=7")
    # Wpis powstał „dziś" (UTC) — zakres w odległej przeszłości nie obejmie go.
    assert admin_client.get("/api/audit-log?od=2000-01-01&do=2000-12-31").json() == []
    assert len(admin_client.get("/api/audit-log?od=2020-01-01").json()) == 1


def test_audit_log_tylko_admin(client):
    # Zwykły pracownik nie ma wglądu w dziennik audytu ani w raport płac.
    r = client.post("/api/auth/register",
                    json={"email": "szeregowy@lokal.pl", "haslo": "Haslo123!", "imie": "A", "nazwisko": "B"})
    token = r.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    assert client.get("/api/audit-log").status_code == 403
    assert client.get("/api/raporty/godziny?rok=2026&miesiac=7").status_code == 403
