"""Kontrakt konfiguracji kontrolowanego cutoveru rezerwacji."""

from datetime import date, timedelta
from pathlib import Path

import pytest

import settings

ROOT = Path(__file__).resolve().parents[2]


def test_domyslny_tryb_legacy_nie_wymaga_daty(monkeypatch):
    monkeypatch.delenv("REZERWACJE_READ_MODE", raising=False)
    monkeypatch.delenv("REZERWACJE_CUTOVER_DATE", raising=False)
    assert settings.rezerwacje_read_mode() == "legacy"
    assert settings.rezerwacje_cutover_date() is None


@pytest.mark.parametrize("mode", ["shadow", "canonical"])
def test_tryb_cutover_wymaga_jawnej_daty(monkeypatch, mode):
    monkeypatch.setenv("REZERWACJE_READ_MODE", mode)
    monkeypatch.delenv("REZERWACJE_CUTOVER_DATE", raising=False)
    with pytest.raises(ValueError):
        settings.rezerwacje_cutover_date()


def test_nieznany_tryb_jest_bledem(monkeypatch):
    monkeypatch.setenv("REZERWACJE_READ_MODE", "automatic")
    with pytest.raises(ValueError):
        settings.rezerwacje_read_mode()


def test_canonical_nie_moze_wystartowac_przed_data_cutoveru(monkeypatch):
    dzis = date(2035, 7, 13)
    monkeypatch.setattr(settings, "_dzis_warszawa", lambda: dzis)
    monkeypatch.setenv("REZERWACJE_READ_MODE", "canonical")
    monkeypatch.setenv("REZERWACJE_CUTOVER_DATE", (dzis + timedelta(days=1)).isoformat())
    with pytest.raises(ValueError):
        settings.rezerwacje_cutover_date()


def test_canonical_przyjmuje_dzisiejsza_date(monkeypatch):
    dzis = date(2035, 7, 13)
    monkeypatch.setattr(settings, "_dzis_warszawa", lambda: dzis)
    monkeypatch.setenv("REZERWACJE_READ_MODE", "canonical")
    monkeypatch.setenv("REZERWACJE_CUTOVER_DATE", dzis.isoformat())
    assert settings.rezerwacje_cutover_date() == dzis


def test_produkcyjny_compose_przekazuje_cutover_i_google():
    compose = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    for variable in (
        "REZERWACJE_READ_MODE",
        "REZERWACJE_CUTOVER_DATE",
        "GOOGLE_CALENDAR_ID",
        "GOOGLE_SA_JSON",
    ):
        assert f"{variable}:" in compose
    assert "./secrets:/run/secrets/lokalo:ro" in compose


def test_runtime_deklaruje_baze_stref_czasowych():
    requirements = (ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8")
    assert "tzdata==" in requirements
