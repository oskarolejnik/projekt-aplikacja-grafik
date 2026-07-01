"""Eksport wypłat do Excela — GET /api/eksport/wyplaty (.xlsx dla księgowej)."""

import io
from datetime import date, datetime, time

import openpyxl
import pytest

import factories
import models
import raporty


@pytest.fixture(autouse=True)
def _przycinanie_od_zawsze(monkeypatch):
    monkeypatch.setattr(raporty, "PRZYCINANIE_OD", date(2000, 1, 1))


def test_eksport_wyplaty_xlsx_zawiera_dane(admin_client, db):
    sala = factories.StanowiskoFactory(nazwa="Sala")
    p = factories.PracownikFactory(imie="Jan", nazwisko="Kowalski")
    db.add(models.StawkaPracownika(pracownik_id=p.id, stanowisko_id=sala.id, stawka=30))
    db.add(models.PrzydzialZmiany(data=date(2026, 6, 1), stanowisko_id=sala.id, pracownik_id=p.id, godz_od=time(10, 0)))
    db.add(models.PublikacjaGrafiku(start=date(2026, 6, 1), koniec=date(2026, 6, 30), opublikowano_at=datetime(2026, 6, 1)))
    db.add(models.OdbicieRcp(rcp_id="x1", imie_nazwisko="Jan Kowalski", pracownik_id=p.id, data=date(2026, 6, 1),
                             wejscie=datetime(2026, 6, 1, 10, 0), wyjscie=datetime(2026, 6, 1, 18, 0), godziny=8.0))
    db.commit()

    r = admin_client.get("/api/eksport/wyplaty?rok=2026&miesiac=6")
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]
    assert "wyplaty_2026_06.xlsx" in r.headers.get("content-disposition", "")

    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    rows = [tuple(x) for x in wb.active.iter_rows(values_only=True)]
    assert rows[0][0] == "Pracownik"
    plaskie = [c for row in rows for c in row if c is not None]
    assert "Jan Kowalski" in plaskie
    assert "WSZYSCY RAZEM" in plaskie
    assert 240.0 in plaskie          # 8 h × 30 zł/h


def test_eksport_wyplaty_waliduje_miesiac(admin_client):
    assert admin_client.get("/api/eksport/wyplaty?rok=2026&miesiac=13").status_code == 422


def test_eksport_wyplaty_tylko_admin(make_employee_client, db):
    p = factories.PracownikFactory()
    ce, _ = make_employee_client(p)
    assert ce.get("/api/eksport/wyplaty?rok=2026&miesiac=6").status_code == 403
