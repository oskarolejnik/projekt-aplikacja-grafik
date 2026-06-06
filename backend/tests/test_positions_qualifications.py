"""CEL 2 — Definiowanie stanowisk i kwalifikacji.

System stanowisk (obsługa sali, kuchnia, zarządzanie, ...) z flagą weekend-only
(de-facto priorytet/ograniczenie w tej aplikacji — brak osobnego pola „priorytet"),
podkategorie/rewiry oraz przypisanie pracowników do jednego lub wielu stanowisk
(relacja wiele-do-wielu w obie strony).
"""

import pytest

import models
import factories


# ── Tworzenie stanowisk przez API ────────────────────────────────────────────
def test_admin_tworzy_stanowiska(admin_client):
    for nazwa in ["Obsługa sali", "Kuchnia", "Zarządzanie"]:
        r = admin_client.post("/api/stanowiska", json={"nazwa": nazwa, "tylko_weekend": False})
        assert r.status_code == 201, r.text
        assert r.json()["nazwa"] == nazwa


def test_stanowisko_weekendowe_ma_flage(admin_client):
    r = admin_client.post("/api/stanowiska", json={"nazwa": "Eventy", "tylko_weekend": True})
    assert r.status_code == 201
    assert r.json()["tylko_weekend"] is True


def test_duplikat_nazwy_stanowiska_odrzucony(admin_client):
    admin_client.post("/api/stanowiska", json={"nazwa": "Bar", "tylko_weekend": False})
    r = admin_client.post("/api/stanowiska", json={"nazwa": "Bar", "tylko_weekend": False})
    assert r.status_code == 400
    assert "już istnieje" in r.json()["detail"]


def test_unikalnosc_nazwy_na_poziomie_bazy(db):
    factories.StanowiskoFactory(nazwa="Kasa")
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        # Druga taka sama nazwa łamie UNIQUE constraint kolumny `nazwa`.
        db.add(models.Stanowisko(nazwa="Kasa"))
        db.commit()
    db.rollback()


# ── Podkategorie / rewiry ─────────────────────────────────────────────────────
def test_podkategorie_rewiry_z_godzina(admin_client):
    sid = admin_client.post("/api/stanowiska", json={"nazwa": "Obsługa sali"}).json()["id"]
    r = admin_client.post(
        f"/api/stanowiska/{sid}/podkategorie",
        json={"nazwa": "Sala A", "godz_od": "12:00"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["nazwa"] == "Sala A"
    # Stanowisko zwraca swoje podkategorie
    stan = next(s for s in admin_client.get("/api/stanowiska").json() if s["id"] == sid)
    assert any(p["nazwa"] == "Sala A" for p in stan["podkategorie"])


# ── Kwalifikacje: jeden i wiele ───────────────────────────────────────────────
def test_pracownik_z_jedna_kwalifikacja(admin_client):
    sid = admin_client.post("/api/stanowiska", json={"nazwa": "Kuchnia"}).json()["id"]
    r = admin_client.post(
        "/api/pracownicy",
        json={"imie": "Jan", "nazwisko": "Kowalski", "aktywny": True, "kwalifikacje_ids": [sid]},
    )
    assert r.status_code == 201, r.text
    assert [k["id"] for k in r.json()["kwalifikacje"]] == [sid]


def test_pracownik_z_wieloma_kwalifikacjami(admin_client):
    ids = [
        admin_client.post("/api/stanowiska", json={"nazwa": n}).json()["id"]
        for n in ["Sala", "Bar", "Kasa"]
    ]
    r = admin_client.post(
        "/api/pracownicy",
        json={"imie": "Anna", "nazwisko": "Nowak", "aktywny": True, "kwalifikacje_ids": ids},
    )
    assert r.status_code == 201
    assert sorted(k["id"] for k in r.json()["kwalifikacje"]) == sorted(ids)


def test_relacja_jest_dwukierunkowa(company, db):
    """Stanowisko widzi swoich uprawnionych, pracownik swoje kwalifikacje."""
    sala = company["stanowiska"]["sala"]
    db.expire_all()
    sala_db = db.get(models.Stanowisko, sala.id)
    assert len(sala_db.uprawnieni) >= 1
    for prac in sala_db.uprawnieni:
        assert sala_db in prac.kwalifikacje


def test_aktualizacja_kwalifikacji(admin_client):
    s1 = admin_client.post("/api/stanowiska", json={"nazwa": "Sala"}).json()["id"]
    s2 = admin_client.post("/api/stanowiska", json={"nazwa": "Bar"}).json()["id"]
    pid = admin_client.post(
        "/api/pracownicy",
        json={"imie": "Ewa", "nazwisko": "Lis", "aktywny": True, "kwalifikacje_ids": [s1]},
    ).json()["id"]
    # Zmiana kwalifikacji na inne stanowisko
    r = admin_client.put(
        f"/api/pracownicy/{pid}",
        json={"imie": "Ewa", "nazwisko": "Lis", "aktywny": True, "kwalifikacje_ids": [s2]},
    )
    assert r.status_code == 200
    assert [k["id"] for k in r.json()["kwalifikacje"]] == [s2]


def test_managerowie_pokrywaja_zarzadzanie(company):
    """Tylko managerowie powinni mieć kwalifikację 'Zarządzanie' (stanowisko krytyczne)."""
    zarz = company["stanowiska"]["zarzadzanie"]
    znajacy = [w for w in company["pracownicy"] if zarz in w["obj"].kwalifikacje]
    assert len(znajacy) >= 2
    assert all(w["profile"] == factories.PROFILE_MANAGER for w in znajacy)
