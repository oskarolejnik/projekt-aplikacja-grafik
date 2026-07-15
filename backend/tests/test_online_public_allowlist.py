"""Fail-closed granica autoryzacji publicznych tras ``/api/online``."""

import re

import pytest

import main


def _concrete_path(template: str) -> str:
    return re.sub(r"\{[A-Za-z_][A-Za-z0-9_]*\}", "wartosc-123", template)


def test_allowlista_odzwierciedla_wszystkie_istniejace_handlery_online():
    actual = {
        (method, route.path)
        for route in main.app.routes
        if (route.path == "/api/online" or route.path.startswith("/api/online/"))
        for method in (getattr(route, "methods", None) or ())
        if method not in {"HEAD", "OPTIONS"}
    }

    assert set(main.ONLINE_PUBLIC_ROUTE_TEMPLATES) == actual


@pytest.mark.parametrize("method,template", main.ONLINE_PUBLIC_ROUTE_TEMPLATES)
def test_kazda_jawna_para_online_jest_publiczna(method, template):
    assert main._trasa_publiczna(_concrete_path(template), method) is True


@pytest.mark.parametrize(
    "method,path",
    (
        ("GET", "/api/online/nieznana-trasa"),
        ("POST", "/api/online/dostepnosc"),
        ("DELETE", "/api/online/rezerwacja/wartosc-123"),
        ("GET", "/api/online/rezerwacja/wartosc-123/odwolaj"),
        ("POST", "/api/online/rezerwacja/wartosc-123/odwolaj/dalej"),
        ("GET", "/api/online/rezerwacja/"),
        ("GET", "/api/online/rezerwacja/sekret-capability"),
        ("POST", "/api/online/rezerwacja/sekret-capability/potwierdz"),
        ("POST", "/api/online/rezerwacja/sekret-capability/odwolaj"),
        ("POST", "/api/online/rezerwacja/sekret-capability/edytuj"),
        ("DELETE", "/api/online/hold/sekret-capability"),
        ("GET", "/api/online-cokolwiek/dostepnosc"),
    ),
)
def test_nieznana_sciezka_lub_metoda_online_nie_jest_publiczna(method, path):
    assert main._trasa_publiczna(path, method) is False


def test_middleware_wymaga_logowania_dla_nieznanej_trasy_online(client):
    response = client.get("/api/online/nieznana-trasa")

    assert response.status_code == 401
    assert response.json() == {"detail": "Wymagane logowanie."}


def test_middleware_wymaga_logowania_dla_zlej_metody_online(client):
    response = client.post("/api/online/dostepnosc")

    assert response.status_code == 401
    assert response.json() == {"detail": "Wymagane logowanie."}


def test_odpowiedzi_online_sa_no_store(client):
    response = client.get("/api/online/nowy-lokal/status")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
