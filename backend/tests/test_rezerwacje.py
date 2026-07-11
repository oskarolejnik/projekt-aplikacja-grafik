"""PII-safe agregat rezerwacji: legacy Google, shadow-read i kanoniczny Termin."""

import logging
from datetime import date, time, timedelta

import factories
import models
import pytest
import rezerwacje
from auth import create_access_token


def _h(u):
    return {"Authorization": f"Bearer {create_access_token(u)}"}


def _ev(start_dt, osoby):
    return {
        "start": {"dateTime": start_dt},
        "description": f"REZERWACJA STOLIKA\nLiczba osób: {osoby}\nTelefon: x",
    }


def _termin(db, data_rezerwacji, *, godz_od=time(18, 0), osoby=4,
            status="rezerwacja", rodzaj="stolik", nazwisko="Klient Sekretny"):
    termin = models.Termin(
        data=data_rezerwacji,
        godz_od=godz_od,
        liczba_osob=osoby,
        status=status,
        rodzaj=rodzaj,
        nazwisko=nazwisko,
        telefon="+48 999 888 777",
        email="sekretny@example.test",
        notatka="ALERGIA-PII-NIE-LOGUJ",
        kanal="reczna",
        zadatek=0,
    )
    db.add(termin)
    db.commit()
    return termin


def test_parsuj_agreguje_dzien_i_godzine():
    events = [
        _ev("2026-06-13T14:00:00+02:00", 5),
        _ev("2026-06-13T14:00:00+02:00", 2),
        _ev("2026-06-13T18:00:00+02:00", 4),
        _ev("2026-06-14T12:00:00+02:00", 3),
    ]
    dni = rezerwacje.parsuj(events)
    d13 = next(d for d in dni if d["data"] == "2026-06-13")
    assert d13["liczba"] == 3 and d13["osoby"] == 11
    godz = {g["godzina"]: g for g in d13["godziny"]}
    assert godz["14:00"]["liczba"] == 2 and godz["14:00"]["osoby"] == 7
    assert godz["18:00"]["liczba"] == 1 and godz["18:00"]["osoby"] == 4


def test_parsuj_bez_liczby_osob_daje_zero():
    dni = rezerwacje.parsuj([
        {"start": {"dateTime": "2026-06-13T10:00:00+02:00"}, "description": "Brak pola osob"},
    ])
    assert dni[0]["liczba"] == 1 and dni[0]["osoby"] == 0


def test_kanoniczny_agregat_filtruje_zakres_status_i_rodzaj_bez_pii(db):
    start = date(2026, 7, 10)
    _termin(db, start - timedelta(days=1))
    _termin(db, start, godz_od=time(18, 0), osoby=5, status="rezerwacja")
    _termin(db, start, godz_od=time(18, 0), osoby=2, status="potwierdzona")
    _termin(db, start, godz_od=None, osoby=None, status="odbyla")
    _termin(db, start + timedelta(days=1), status="odwolana")
    _termin(db, start + timedelta(days=1), status="no_show")
    _termin(db, start + timedelta(days=1), rodzaj="impreza")
    _termin(db, start + timedelta(days=3))  # prawy koniec zakresu jest wyłączny

    wynik = rezerwacje.rezerwacje_z_terminow(db, dni_naprzod=3, start=start)

    assert wynik == [{
        "data": "2026-07-10",
        "liczba": 3,
        "osoby": 7,
        "godziny": [
            {"godzina": "18:00", "liczba": 2, "osoby": 7},
            {"godzina": "—", "liczba": 1, "osoby": 0},
        ],
    }]
    serialized = repr(wynik)
    assert "Klient Sekretny" not in serialized
    assert "+48 999 888 777" not in serialized
    assert "sekretny@example.test" not in serialized
    assert "ALERGIA-PII-NIE-LOGUJ" not in serialized


def test_canonical_nigdy_nie_wola_google_ani_nie_fallbackuje(db, monkeypatch):
    start = date(2026, 7, 10)
    _termin(db, start, osoby=6)
    monkeypatch.setattr(rezerwacje, "_tryb_odczytu", lambda: "canonical")

    def google_nie_moze_byc_wolane(*_args, **_kwargs):
        raise AssertionError("canonical nie może wywołać Google")

    monkeypatch.setattr(rezerwacje, "_rezerwacje_per_dzien_status", google_nie_moze_byc_wolane)
    wynik = rezerwacje.czytaj_rezerwacje(db, dni_naprzod=1, start=start)
    assert wynik[0]["liczba"] == 1 and wynik[0]["osoby"] == 6


def test_legacy_zwraca_google_i_nie_liczy_canonical(db, monkeypatch):
    legacy = [{"data": "2026-07-10", "liczba": 2, "osoby": 7, "godziny": []}]
    monkeypatch.setattr(rezerwacje, "_tryb_odczytu", lambda: "legacy")
    monkeypatch.setattr(rezerwacje, "_rezerwacje_per_dzien_status", lambda _dni: (legacy, "ok"))

    def canonical_nie_moze_byc_wolany(*_args, **_kwargs):
        raise AssertionError("legacy nie powinien liczyć canonical")

    monkeypatch.setattr(rezerwacje, "rezerwacje_z_terminow", canonical_nie_moze_byc_wolany)
    assert rezerwacje.czytaj_rezerwacje(db) is legacy


def test_shadow_zwraca_legacy_i_loguje_wylacznie_pii_free_delta(db, monkeypatch, caplog):
    start = date(2026, 7, 10)
    _termin(db, start, osoby=9, nazwisko="TAJNE-NAZWISKO-SHADOW")
    legacy = [{
        "data": "2026-07-10", "liczba": 2, "osoby": 5,
        "godziny": [{"godzina": "18:00", "liczba": 2, "osoby": 5}],
    }]
    monkeypatch.setenv("REZERWACJE_READ_MODE", "shadow")
    monkeypatch.setenv("REZERWACJE_CUTOVER_DATE", "2026-07-01")
    monkeypatch.setattr(rezerwacje, "_rezerwacje_per_dzien_status", lambda _dni: (legacy, "ok"))
    caplog.set_level(logging.INFO, logger="rezerwacje")

    wynik = rezerwacje.czytaj_rezerwacje(db, dni_naprzod=1, start=start)

    assert wynik is legacy
    assert "rezerwacje_shadow_delta" in caplog.text
    assert '"delta_rezerwacje":-1' in caplog.text
    assert '"delta_osoby":4' in caplog.text
    assert '"cutover_date":"2026-07-01"' in caplog.text
    assert '"data":"2026-07-10"' in caplog.text
    assert '"godzina":"18:00"' in caplog.text
    assert '"delta_liczba":-1' in caplog.text
    assert "TAJNE-NAZWISKO-SHADOW" not in caplog.text
    assert "+48 999 888 777" not in caplog.text
    assert "sekretny@example.test" not in caplog.text
    assert "ALERGIA-PII-NIE-LOGUJ" not in caplog.text


@pytest.mark.parametrize("status", ["unconfigured", "error"])
def test_shadow_pomija_delta_gdy_legacy_niewiarygodne(db, monkeypatch, caplog, status):
    start = date(2026, 7, 10)
    _termin(db, start)
    monkeypatch.setattr(rezerwacje, "_tryb_odczytu", lambda: "shadow")
    monkeypatch.setattr(rezerwacje, "_rezerwacje_per_dzien_status", lambda _dni: ([], status))
    caplog.set_level(logging.INFO, logger="rezerwacje")

    assert rezerwacje.czytaj_rezerwacje(db, dni_naprzod=1, start=start) == []
    assert f"rezerwacje_shadow_unavailable legacy_status={status}" in caplog.text
    assert "rezerwacje_shadow_delta" not in caplog.text


def test_shadow_awaria_canonical_nie_przerywa_legacy_i_nie_loguje_tresci_bledu(
    db, monkeypatch, caplog,
):
    legacy = [{"data": "2026-07-10", "liczba": 1, "osoby": 2, "godziny": []}]
    monkeypatch.setattr(rezerwacje, "_tryb_odczytu", lambda: "shadow")
    monkeypatch.setattr(rezerwacje, "_rezerwacje_per_dzien_status", lambda _dni: (legacy, "ok"))

    def awaria_canonical(*_args, **_kwargs):
        raise RuntimeError("TAJNA-TRESC-NIE-LOGUJ")

    monkeypatch.setattr(rezerwacje, "rezerwacje_z_terminow", awaria_canonical)
    caplog.set_level(logging.INFO, logger="rezerwacje")

    assert rezerwacje.czytaj_rezerwacje(db) is legacy
    assert "rezerwacje_shadow_unavailable canonical_status=error error_type=RuntimeError" in caplog.text
    assert "TAJNA-TRESC-NIE-LOGUJ" not in caplog.text
    assert "rezerwacje_shadow_delta" not in caplog.text


def test_legacy_status_odroznia_poprawnie_pusto_brak_konfiguracji_i_blad(monkeypatch, caplog):
    monkeypatch.setattr(rezerwacje, "_cache", {"ts": 0.0, "dane": None})
    monkeypatch.setattr(rezerwacje, "skonfigurowane", lambda: True)
    monkeypatch.setattr(rezerwacje, "_pobierz_wydarzenia", lambda *_args: [])
    assert rezerwacje._rezerwacje_per_dzien_status(30) == ([], "ok")

    monkeypatch.setattr(rezerwacje, "_cache", {"ts": 0.0, "dane": None})
    monkeypatch.setattr(rezerwacje, "skonfigurowane", lambda: False)
    assert rezerwacje._rezerwacje_per_dzien_status(30) == ([], "unconfigured")

    monkeypatch.setattr(rezerwacje, "_cache", {"ts": 0.0, "dane": None})
    monkeypatch.setattr(rezerwacje, "skonfigurowane", lambda: True)

    def awaria(*_args):
        raise RuntimeError("TAJNA-TRESC-GOOGLE-NIE-LOGUJ")

    monkeypatch.setattr(rezerwacje, "_pobierz_wydarzenia", awaria)
    caplog.set_level(logging.INFO, logger="rezerwacje")
    assert rezerwacje._rezerwacje_per_dzien_status(30) == ([], "error")
    assert "rezerwacje_legacy_unavailable error_type=RuntimeError" in caplog.text
    assert "TAJNA-TRESC-GOOGLE-NIE-LOGUJ" not in caplog.text


def test_endpointy_uzywaja_kanonicznego_agregatu_i_redaguja_pracownika(
    client, admin_client, db, monkeypatch,
):
    dzien = rezerwacje._dzis_lokalnie() + timedelta(days=1)
    _termin(db, dzien, godz_od=time(14, 0), osoby=7)
    monkeypatch.setattr(rezerwacje, "_tryb_odczytu", lambda: "canonical")

    def google_nie_moze_byc_wolane(*_args, **_kwargs):
        raise AssertionError("endpoint canonical nie może wywołać Google")

    monkeypatch.setattr(rezerwacje, "_rezerwacje_per_dzien_status", google_nie_moze_byc_wolane)

    admin_response = admin_client.get("/api/rezerwacje")
    assert admin_response.status_code == 200
    assert admin_response.json()["dni"][0]["godziny"][0]["godzina"] == "14:00"

    pracownik = factories.PracownikFactory()
    employee = factories.UserFactory(login="obsrez", rola="employee", pracownik=pracownik)
    employee_full = client.get("/api/rezerwacje", headers=_h(employee))
    assert employee_full.status_code == 200
    assert employee_full.json()["dni"][0]["godziny"][0]["godzina"] == "14:00"

    employee_safe = client.get("/api/me/rezerwacje", headers=_h(employee))
    assert employee_safe.status_code == 200
    assert employee_safe.json()["dni"] == [{
        "data": dzien.isoformat(), "liczba": 1, "osoby": 7,
    }]

    for response in (admin_response, employee_full, employee_safe):
        body = response.text
        assert "Klient Sekretny" not in body
        assert "+48 999 888 777" not in body
        assert "sekretny@example.test" not in body
        assert "ALERGIA-PII-NIE-LOGUJ" not in body

    szef = factories.UserFactory(login="szefrez", rola="szef")
    assert client.get("/api/rezerwacje", headers=_h(szef)).status_code == 200
    assert client.get("/api/pracownicy", headers=_h(employee)).status_code == 403
