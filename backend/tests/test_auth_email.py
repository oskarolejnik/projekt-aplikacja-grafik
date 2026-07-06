"""Logowanie e-mailem (nowy kanał dla wszystkich kont) + wsteczna zgodność loginu.

Nowe konta (właściciel z kreatora, pracownicy z zaproszenia, samodzielna rejestracja) mają
e-mail i logują się nim (case-insensitive). Stare konta bez e-maila (seed/CLI/kadry) logują się
dalej po login — fallback w /api/auth/login."""

import models
from auth import hash_password


def test_bootstrap_i_login_emailem(client):
    r = client.post("/api/onboarding/bootstrap",
                    json={"email": "Wlasciciel@Lokal.PL", "haslo": "Mocn3-Haslo!"})
    assert r.status_code == 201, r.text
    # e-mail znormalizowany (lower) i zwrócony; login syntetyzowany wewnętrznie
    assert r.json()["user"]["email"] == "wlasciciel@lokal.pl"
    assert r.json()["user"]["login"]
    # logowanie e-mailem niezależnie od wielkości liter
    assert client.post("/api/auth/login",
                       json={"email": "WLASCICIEL@lokal.pl", "haslo": "Mocn3-Haslo!"}).status_code == 200


def test_duplikat_emaila_odrzucony(client):
    assert client.post("/api/onboarding/bootstrap",
                       json={"email": "a@lokal.pl", "haslo": "Haslo123!"}).status_code == 201
    # drugie konto z tym samym e-mailem (register) → 400 (a nie 500 z IntegrityError)
    r = client.post("/api/auth/register",
                    json={"email": "A@Lokal.pl", "haslo": "Haslo123!", "imie": "A", "nazwisko": "B"})
    assert r.status_code == 400


def test_email_wymagany_i_walidowany(client):
    assert client.post("/api/onboarding/bootstrap", json={"haslo": "Haslo123!"}).status_code == 422
    assert client.post("/api/onboarding/bootstrap",
                       json={"email": "zly-email", "haslo": "Haslo123!"}).status_code == 400


def test_stare_konto_bez_emaila_loguje_sie_loginem(client, db):
    # konto założone „po staremu" (login, brak e-maila) — np. seed / create_admin / kadry
    db.add(models.User(login="starykonto", email=None,
                       haslo_hash=hash_password("Haslo123!"), rola="admin"))
    db.commit()
    # brak dopasowania po e-mailu, ale login (fallback) działa
    assert client.post("/api/auth/login", json={"email": "starykonto", "haslo": "Haslo123!"}).status_code == 401
    assert client.post("/api/auth/login", json={"login": "starykonto", "haslo": "Haslo123!"}).status_code == 200
