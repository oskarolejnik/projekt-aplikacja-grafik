"""Samoobsługowy onboarding instancji (/api/onboarding/*) — Rec#2 audytu, druga część."""

import models


def test_status_pusta_baza_potrzebny(client):
    r = client.get("/api/onboarding/status")
    assert r.status_code == 200
    assert r.json()["potrzebny"] is True


def test_bootstrap_tworzy_admina_ustawia_nazwe_i_loguje(client, db):
    r = client.post("/api/onboarding/bootstrap",
                    json={"email": "wlasciciel@knajpa.pl", "haslo": "Mocn3-Haslo!", "nazwa_lokalu": "Moja Knajpa"})
    assert r.status_code == 201, r.text
    assert "access_token" in r.json()
    assert r.json()["user"]["rola"] == "admin"
    assert r.json()["user"]["email"] == "wlasciciel@knajpa.pl"
    # Admin w bazie (logowanie e-mailem).
    assert db.query(models.User).filter_by(email="wlasciciel@knajpa.pl").count() == 1
    # Logowanie tym kontem działa — e-mailem.
    assert client.post("/api/auth/login",
                       json={"email": "wlasciciel@knajpa.pl", "haslo": "Mocn3-Haslo!"}).status_code == 200
    # Onboarding już niepotrzebny; nazwa lokalu ustawiona (publiczny branding).
    assert client.get("/api/onboarding/status").json()["potrzebny"] is False
    assert client.get("/api/lokal/branding").json()["nazwa_lokalu"] == "Moja Knajpa"


def test_drugi_bootstrap_odrzucony_409(client):
    assert client.post("/api/onboarding/bootstrap",
                       json={"email": "pierwszy@lokal.pl", "haslo": "Mocn3-Haslo!"}).status_code == 201
    # Instancja ma już administratora — brak przejęcia.
    r = client.post("/api/onboarding/bootstrap", json={"email": "drugi@lokal.pl", "haslo": "Mocn3-Haslo!"})
    assert r.status_code == 409


def test_bootstrap_waliduje_dane(client):
    assert client.post("/api/onboarding/bootstrap",
                       json={"email": "bezmalpy", "haslo": "Mocn3-Haslo!"}).status_code == 400   # zły e-mail
    assert client.post("/api/onboarding/bootstrap",
                       json={"email": "admin@lokal.pl", "haslo": "slabe"}).status_code == 400    # hasło za słabe
    # Żadna nieudana walidacja nie utworzyła użytkownika.
    assert client.get("/api/onboarding/status").json()["potrzebny"] is True
