"""Szyfrowanie danych wrażliwych at-rest (szyfrowanie.py + EncryptedString) — RODO."""

import datetime as dt

import pytest
from sqlalchemy import text

import models
import szyfrowanie as sz

KLUCZ = "testowy-bardzo-dlugi-klucz-szyfrujacy-instancji"


@pytest.fixture
def z_kluczem(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", KLUCZ)
    return KLUCZ


@pytest.fixture
def bez_klucza(monkeypatch):
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)


# ── jednostkowe: szyfruj / odszyfruj ──────────────────────────────────────────
def test_round_trip_z_kluczem(z_kluczem):
    szyfr = sz.szyfruj("609 228 774")
    assert szyfr.startswith("enc:v1:")
    assert "609 228 774" not in szyfr                  # jawny tekst nie przecieka
    assert sz.odszyfruj(szyfr) == "609 228 774"
    assert sz.aktywne() is True


def test_passthrough_bez_klucza(bez_klucza):
    assert sz.aktywne() is False
    assert sz.szyfruj("jan@example.com") == "jan@example.com"   # brak klucza = plaintext
    assert sz.odszyfruj("jan@example.com") == "jan@example.com"


def test_legacy_plaintext_odczyt(z_kluczem):
    # Wartość bez prefiksu (dane sprzed włączenia szyfrowania) — zwracana bez zmian.
    assert sz.odszyfruj("500 100 200") == "500 100 200"


def test_nie_podwaja_szyfrowania(z_kluczem):
    raz = sz.szyfruj("x@y.pl")
    assert sz.szyfruj(raz) == raz                       # już zaszyfrowane -> bez zmian


def test_none_bez_zmian(z_kluczem):
    assert sz.szyfruj(None) is None
    assert sz.odszyfruj(None) is None


def test_rozne_szyfrogramy_ten_sam_tekst(z_kluczem):
    # Fernet jest niedeterministyczny — dwa szyfrogramy tego samego tekstu są różne,
    # ale oba odszyfrowują się do oryginału (dlatego nie wolno filtrować po tych polach w SQL).
    a, b = sz.szyfruj("tel"), sz.szyfruj("tel")
    assert a != b
    assert sz.odszyfruj(a) == sz.odszyfruj(b) == "tel"


# ── ORM: EncryptedString szyfruje w bazie, odszyfrowuje przy odczycie ──────────
def test_orm_szyfruje_at_rest(db, z_kluczem):
    lo = models.ListaOczekujacych(
        data=dt.date(2026, 7, 1), nazwisko="Gość Testowy",
        telefon="609 228 774", email="gosc@example.com",
        status="oczekuje", utworzono_at=dt.datetime(2026, 7, 1, 12, 0),
    )
    db.add(lo); db.commit()
    lo_id = lo.id

    # W bazie leży szyfrogram (surowy odczyt SQL pomija TypeDecorator).
    surowy = db.execute(text("SELECT telefon, email FROM lista_oczekujacych WHERE id=:i"),
                        {"i": lo_id}).one()
    assert surowy[0].startswith("enc:v1:") and "609 228 774" not in surowy[0]
    assert surowy[1].startswith("enc:v1:") and "gosc@example.com" not in surowy[1]

    # Odczyt przez ORM (świeży) zwraca jawny tekst.
    db.expire_all()
    znaleziony = db.get(models.ListaOczekujacych, lo_id)
    assert znaleziony.telefon == "609 228 774"
    assert znaleziony.email == "gosc@example.com"


def test_orm_passthrough_bez_klucza(db, bez_klucza):
    lo = models.ListaOczekujacych(
        data=dt.date(2026, 7, 1), nazwisko="Bez Szyfru", telefon="111 222 333",
        status="oczekuje", utworzono_at=dt.datetime(2026, 7, 1, 12, 0),
    )
    db.add(lo); db.commit()
    surowy = db.execute(text("SELECT telefon FROM lista_oczekujacych WHERE id=:i"),
                        {"i": lo.id}).scalar()
    assert surowy == "111 222 333"                      # bez klucza -> plaintext w bazie
