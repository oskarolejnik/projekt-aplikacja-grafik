"""Provisioning instancji klienta (new_client.py) — „drugi klient jednym poleceniem"."""

import pytest

import models
import settings
import new_client as nc


# ── slug ──────────────────────────────────────────────────────────────────────
def test_waliduj_slug_ok():
    assert nc.waliduj_slug("Restauracja-Pod-Lipa") == "restauracja-pod-lipa"
    assert nc.waliduj_slug("  bistro-verde  ") == "bistro-verde"


@pytest.mark.parametrize("zly", ["", "ab", "-bistro", "bistro-", "ma spacje", "kawiarnia_pod", "ą-cafe"])
def test_waliduj_slug_odrzuca(zly):
    with pytest.raises(ValueError):
        nc.waliduj_slug(zly)


# ── sekrety ───────────────────────────────────────────────────────────────────
def test_generuj_sekrety_bezpieczne_i_unikalne():
    a, b = nc.generuj_sekrety(), nc.generuj_sekrety()
    assert set(a) == {"SECRET_KEY", "RCP_INGEST_TOKEN", "ENCRYPTION_KEY"}
    assert a["SECRET_KEY"] != b["SECRET_KEY"]            # losowe przy każdym wywołaniu
    assert a["RCP_INGEST_TOKEN"] != b["RCP_INGEST_TOKEN"]
    assert a["ENCRYPTION_KEY"] != b["ENCRYPTION_KEY"] and len(a["ENCRYPTION_KEY"]) >= 32
    assert len(a["SECRET_KEY"]) >= 32
    # Wygenerowane sekrety NIE mogą trafić na listę niebezpiecznych z settings (fail-fast by je odrzucił).
    assert a["SECRET_KEY"] not in settings._INSECURE_SECRET_KEYS
    assert a["RCP_INGEST_TOKEN"] not in settings._INSECURE_RCP_TOKENS


def test_domyslne_haslo_przechodzi_walidacje():
    from validators import sprawdz_haslo
    for _ in range(20):
        sprawdz_haslo(nc.domyslne_haslo())  # nie rzuca = spełnia reguły (litera+cyfra+specjalny, ASCII)


# ── render .env ───────────────────────────────────────────────────────────────
def test_renderuj_env_produkcyjny_i_z_sekretami():
    sek = {"SECRET_KEY": "AAAA-bardzo-dlugi-sekret-instancji-xyz", "RCP_INGEST_TOKEN": "RCP-token-instancji-123",
           "ENCRYPTION_KEY": "ENC-klucz-szyfrowania-instancji-xyz"}
    env = nc.renderuj_env("bistro-verde", nazwa="Bistro Verde", domena="bistroverde.pl",
                          db_url="sqlite:///./x.db", sekrety=sek)
    assert "APP_ENV=production" in env
    assert f"SECRET_KEY={sek['SECRET_KEY']}" in env
    assert f"RCP_INGEST_TOKEN={sek['RCP_INGEST_TOKEN']}" in env
    assert f"ENCRYPTION_KEY={sek['ENCRYPTION_KEY']}" in env    # PII szyfrowane at-rest od startu
    assert "DATABASE_URL=sqlite:///./x.db" in env
    assert "bistroverde.pl" in env
    # Żadnych niebezpiecznych placeholderów z .env.example.
    for zly in settings._INSECURE_SECRET_KEYS | settings._INSECURE_RCP_TOKENS:
        if zly:
            assert zly not in env


# ── zapis .env (idempotencja) ─────────────────────────────────────────────────
def test_zapisz_env_pisze_i_chroni_przed_nadpisaniem(tmp_path):
    kat = tmp_path / "bistro-verde"
    plik = nc.zapisz_env(kat, "TRESC=1\n")
    assert plik.exists() and plik.read_text(encoding="utf-8") == "TRESC=1\n"
    # Drugi zapis bez force = ochrona istniejących sekretów.
    with pytest.raises(FileExistsError):
        nc.zapisz_env(kat, "TRESC=2\n")
    # force nadpisuje.
    nc.zapisz_env(kat, "TRESC=2\n", force=True)
    assert plik.read_text(encoding="utf-8") == "TRESC=2\n"


# ── inicjalizacja bazy (na współdzielonej sesji testowej) ─────────────────────
def test_zaloz_admina_tworzy_i_awansuje(db):
    u = nc.zaloz_admina(db, "ownerklienta", "Mocn3-Haslo!")
    assert u.rola == "admin" and u.aktywny and u.haslo_hash
    # Ponowne wywołanie z istniejącym loginem = awans/reset (idempotentne).
    u2 = nc.zaloz_admina(db, "ownerklienta", "Inn3-Haslo!")
    assert u2.id == u.id and u2.rola == "admin"
    assert db.query(models.User).filter_by(login="ownerklienta").count() == 1


def test_zaloz_admina_odrzuca_slabe_dane(db):
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        nc.zaloz_admina(db, "abc", "Mocn3-Haslo!")          # login za krótki
    with pytest.raises(HTTPException):
        nc.zaloz_admina(db, "ownerklienta", "slabe")        # hasło za słabe


def test_ustaw_nazwe_lokalu_tworzy_singleton(db):
    cfg = nc.ustaw_nazwe_lokalu(db, "Restauracja Pod Lipą")
    assert cfg.id == 1 and cfg.nazwa_lokalu == "Restauracja Pod Lipą"
    cfg2 = nc.ustaw_nazwe_lokalu(db, "Nowa Nazwa")
    assert cfg2.id == 1 and cfg2.nazwa_lokalu == "Nowa Nazwa"
    assert db.query(models.LokalConfig).count() == 1


def test_nowa_instancja_zasiewa_neutralne_sale(db):
    """De-Rajculizacja: świeża instancja (brak configu) dostaje NEUTRALNĄ salę „Sala", nie sale
    legacy pierwotnego lokalu (Parter/Zielona/Kryształowa…), które sprzątanie podstawia dla NULL."""
    import sprzatanie
    for c in db.query(models.LokalConfig).all():
        db.delete(c)
    db.commit()
    cfg = nc.ustaw_nazwe_lokalu(db, "Bistro Verde")
    assert cfg.sale == ["Sala"]
    assert cfg.sprzatanie_sale_codziennie == ["Sala"]
    assert cfg.sprzatanie_sala_niedziela == ""
    assert cfg.sale != list(sprzatanie.SALE)        # NIE dziedziczy sal legacy


def test_nowa_instancja_nie_nadpisuje_istniejacych_sal(db):
    """Idempotencja: gdy config już istnieje (kreator / ponowny provisioning), zasiew NIE rusza sal."""
    for c in db.query(models.LokalConfig).all():
        db.delete(c)
    db.add(models.LokalConfig(id=1, sale=["Główna", "Ogród"]))
    db.commit()
    cfg = nc.ustaw_nazwe_lokalu(db, "X")
    assert cfg.sale == ["Główna", "Ogród"]          # istniejąca struktura nietknięta


def test_ustaw_tier_singleton_i_walidacja(db):
    s = nc.ustaw_tier(db, "pro")
    assert s.id == 1 and s.tier == "pro"
    s2 = nc.ustaw_tier(db, "free")                 # nadpisuje, nie duplikuje
    assert s2.id == 1 and s2.tier == "free"
    assert db.query(models.Subskrypcja).count() == 1
    with pytest.raises(ValueError):
        nc.ustaw_tier(db, "platinum")


# ── tor samoobsługi z checkoutu: admin e-mailem + subskrypcja opłacona ────────
def test_zaloz_admina_emailem_uzywa_gotowego_hasha(db):
    from auth import hash_password, verify_password
    hh = hash_password("Haslo123!")
    u = nc.zaloz_admina(db, email="Szef@Lokal.PL", haslo_hash=hh)
    assert u.email == "szef@lokal.pl"        # znormalizowany
    assert u.rola == "admin" and u.login     # wewnętrzny login syntetyzowany, niepusty
    assert u.haslo_hash == hh                # hash przekazany gotowy — bez ponownego liczenia
    assert verify_password("Haslo123!", u.haslo_hash)


def test_ustaw_tier_oplacony_aktywuje_subskrypcje(db):
    from datetime import date, timedelta
    s = nc.ustaw_tier(db, "pro", oplacony=True)
    assert s.tier == "pro" and s.status == "aktywna"
    assert s.data_od == date.today() and s.data_do == date.today() + timedelta(days=30)


def test_ustaw_trial_14_dni_pelny_dostep(db):
    from datetime import date, timedelta
    s = nc.ustaw_trial(db)
    assert s.status == "trial" and s.tier == "premium"
    assert s.data_od == date.today() and s.data_do == date.today() + timedelta(days=14)


def test_ustaw_konfiguracje_ustawia_typ_i_moduly(db):
    cfg = nc.ustaw_konfiguracje(db, {"typ_lokalu": "pizzeria", "modul_pos": True, "nieznane": "x"})
    assert cfg.typ_lokalu == "pizzeria" and cfg.modul_pos is True
