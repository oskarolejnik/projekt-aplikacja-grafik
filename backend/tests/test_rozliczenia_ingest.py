"""Ingest rozliczeń kelnerów z Gastro (agent → /api/gastro/rozliczenia):
token agenta, upsert po poz_id, mapowanie kelnera po imieniu i nazwisku (jak RCP),
podgląd admina. NIE dotyka RCP."""

import models
import factories
from auth import create_access_token

TOKEN = {"X-RCP-Token": "test-rcp-token"}


def _poz(**nadpisz):
    poz = {
        "poz_id": "T-1", "rozliczenie_id": "Z-1",
        "imie_nazwisko": "KAMIL NOCOŃ", "data": "2026-06-11",
        "zamknieto": None, "zamkniete": 0,
        "forma": "GOTÓWKA", "sprzedaz": 623.0, "deklarowane": 0.0,
    }
    poz.update(nadpisz)
    return poz


def test_ingest_wymaga_tokenu(client, db):
    r = client.post("/api/gastro/rozliczenia", json={"pozycje": [_poz()]})
    assert r.status_code == 401
    r = client.post("/api/gastro/rozliczenia", json={"pozycje": [_poz()]},
                    headers={"X-RCP-Token": "zly"})
    assert r.status_code == 401


def test_ingest_upsert_i_mapowanie_pracownika(client, db):
    prac = factories.PracownikFactory(imie="Kamil", nazwisko="Nocoń")
    # 1) zmiana otwarta — system naliczył, deklaracji brak
    r = client.post("/api/gastro/rozliczenia", json={"pozycje": [_poz()]}, headers=TOKEN)
    assert r.status_code == 200 and r.json()["pozycje"] == 1
    rec = db.query(models.RozliczenieGastro).filter_by(poz_id="T-1").first()
    assert rec.pracownik_id == prac.id          # mapowanie „KAMIL NOCOŃ" -> Kamil Nocoń (case/diakrytyki)
    assert rec.zamkniete is False and rec.deklarowane == 0.0
    # 2) kelner się rozliczył — UPSERT tej samej pozycji (zamkniete=1 + kwota deklarowana)
    r = client.post("/api/gastro/rozliczenia", json={"pozycje": [
        _poz(zamkniete=1, zamknieto="2026-06-11T18:34:01", deklarowane=1100.0),
    ]}, headers=TOKEN)
    assert r.status_code == 200
    db.expire_all()
    rows = db.query(models.RozliczenieGastro).filter_by(poz_id="T-1").all()
    assert len(rows) == 1                        # upsert, nie duplikat
    assert rows[0].zamkniete is True
    assert rows[0].deklarowane == 1100.0
    assert rows[0].zamknieto is not None


def test_ingest_bez_pracownika_zapisuje_z_nazwa(client, db):
    """Kelner z Gastro bez konta w aplikacji — pozycja zapisana z samą nazwą (pid NULL)."""
    r = client.post("/api/gastro/rozliczenia", json={"pozycje": [
        _poz(poz_id="T-2", imie_nazwisko="OSOBA NIEZNANA"),
    ]}, headers=TOKEN)
    assert r.status_code == 200
    rec = db.query(models.RozliczenieGastro).filter_by(poz_id="T-2").first()
    assert rec.pracownik_id is None and rec.imie_nazwisko == "OSOBA NIEZNANA"


def test_podglad_admina_i_ochrona(client, admin_client, db):
    factories.PracownikFactory(imie="Kamil", nazwisko="Nocoń")
    admin_client.post("/api/gastro/rozliczenia", json={"pozycje": [
        _poz(zamkniete=1, deklarowane=1100.0),
        _poz(poz_id="T-3", forma="KARTA", sprzedaz=3191.0, deklarowane=2912.0, zamkniete=1),
    ]}, headers=TOKEN)
    r = admin_client.get("/api/gastro/rozliczenia?start=2026-06-11&end=2026-06-11")
    assert r.status_code == 200
    poz = r.json()["pozycje"]
    assert len(poz) == 2
    karta = next(p for p in poz if p["forma"] == "KARTA")
    assert karta["sprzedaz"] == 3191.0 and karta["deklarowane"] == 2912.0
    assert karta["pracownik"] == "Kamil Nocoń"
    # pracownik (employee) nie ma dostępu do podglądu
    prac = factories.PracownikFactory()
    emp = factories.UserFactory(login="emprozl", rola="employee", pracownik=prac)
    r = client.get("/api/gastro/rozliczenia?start=2026-06-11&end=2026-06-11",
                   headers={"Authorization": f"Bearer {create_access_token(emp)}"})
    assert r.status_code == 403
