"""Regresje walidacji wejścia (audyt runda 3): niewalidowane parametry dawały 500 zamiast 4xx."""

import factories
from auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(u)}"}


def test_me_godziny_waliduje_rok_miesiac(client, db):
    """/api/me/godziny: niewalidowany miesiąc/rok dawał 500 (date(rok, miesiac, 1) → ValueError).
    Teraz Query z zakresem → 422 (błąd klienta), nie crash. Endpoint dostępny dla employee."""
    p = factories.PracownikFactory()
    emp = factories.UserFactory(login="jan_val", rola="employee", pracownik=p)
    assert client.get("/api/me/godziny", headers=_h(emp), params={"rok": 2026, "miesiac": 13}).status_code == 422
    assert client.get("/api/me/godziny", headers=_h(emp), params={"rok": 2026, "miesiac": 0}).status_code == 422
    assert client.get("/api/me/godziny", headers=_h(emp), params={"rok": 0, "miesiac": 1}).status_code == 422
    # poprawne parametry nadal działają (200)
    assert client.get("/api/me/godziny", headers=_h(emp), params={"rok": 2026, "miesiac": 6}).status_code == 200


def test_raporty_godziny_waliduje_miesiac(admin_client):
    """/api/raporty/godziny (admin): ten sam zakres walidacji → 422 zamiast 500."""
    assert admin_client.get("/api/raporty/godziny", params={"rok": 2026, "miesiac": 13}).status_code == 422


def test_kopiuj_wymagania_zle_body_400(admin_client):
    """/api/wymagania/kopiuj: brak klucza lub zła data w surowym body dawały 500 (KeyError/ValueError).
    Teraz czytelne 400."""
    assert admin_client.post("/api/wymagania/kopiuj", json={}).status_code == 400
    assert admin_client.post("/api/wymagania/kopiuj", json={
        "source_date": "2026-13-01", "start_date": "2026-01-01", "end_date": "2026-01-07"}).status_code == 400


def test_kopiuj_wymagania_tydzien_zle_body_400(admin_client):
    assert admin_client.post("/api/wymagania/kopiuj-tydzien", json={}).status_code == 400
    assert admin_client.post("/api/wymagania/kopiuj-tydzien", json={
        "source_start": "nie-data", "target_start": "2026-01-01"}).status_code == 400
