"""Provisioning nowej instancji klienta (model instance-per-tenant) — „drugi klient jednym poleceniem".

Jedno uruchomienie:
  1. generuje świeże, bezpieczne sekrety (SECRET_KEY, RCP_INGEST_TOKEN),
  2. renderuje gotowy do produkcji plik `.env` instancji (APP_ENV=production, własna baza),
  3. zapisuje go w `instances/<slug>/.env` (katalog runtime, poza repo),
  4. (z flagą --init) inicjuje bazę instancji, zakłada administratora i ustawia nazwę lokalu.

Przykład:
    python new_client.py restauracja-pod-lipa --nazwa "Restauracja Pod Lipą" \
        --admin szefowa --domena podlipa.pl --init

Bez --init skrypt tylko przygotowuje katalog i `.env` (operator inicjuje bazę później).
Plik `.env` zawiera prawdziwe sekrety — NIGDY nie jest commitowany (katalog `instances/` w .gitignore).

Funkcje są rozbite tak, by dało się je testować bez efektów ubocznych:
  generuj_sekrety / renderuj_env / waliduj_slug / zapisz_env — czyste,
  zaloz_admina / ustaw_nazwe_lokalu — operują na przekazanej sesji bazy.
"""

from __future__ import annotations

import argparse
import os
import re
import secrets
import string
import sys
from pathlib import Path

from fastapi import HTTPException

from validators import sprawdz_haslo, sprawdz_login

# UWAGA: `models`/`auth`/`database` importujemy LENIWIE (w funkcjach), bo `database.py`
# czyta DATABASE_URL i tworzy silnik już przy imporcie. Tor --init musi najpierw ustawić
# środowisko instancji, a dopiero potem zaimportować bazę — inaczej init trafiłby do złej bazy.

# Slug instancji: małe litery/cyfry/myślnik, 3–40 znaków, bez myślnika na brzegach.
_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,38}[a-z0-9])$")
_HASLO_ALFABET = string.ascii_letters + string.digits + "!@#$%^&*-_+"


def waliduj_slug(slug: str) -> str:
    """Normalizuje i sprawdza slug instancji (używany w nazwie katalogu, bazy, subdomeny)."""
    slug = (slug or "").strip().lower()
    if not _SLUG_RE.match(slug):
        raise ValueError(
            "Slug musi mieć 3–40 znaków: małe litery, cyfry i myślniki "
            "(bez myślnika na początku/końcu). Przykład: restauracja-pod-lipa"
        )
    return slug


def generuj_sekrety() -> dict:
    """Świeże, kryptograficznie losowe sekrety instancji (każde wywołanie inne)."""
    return {
        "SECRET_KEY": secrets.token_urlsafe(48),       # 64 znaki — daleko ponad próg bezpieczeństwa
        "RCP_INGEST_TOKEN": secrets.token_urlsafe(32),  # token agenta POS (ten sam po stronie agenta)
    }


def domyslne_haslo(n: int = 18) -> str:
    """Losowe hasło spełniające reguły validators.sprawdz_haslo (litera+cyfra+znak specjalny)."""
    for _ in range(100):
        h = "".join(secrets.choice(_HASLO_ALFABET) for _ in range(n))
        try:
            sprawdz_haslo(h)
            return h
        except HTTPException:
            continue
    raise RuntimeError("Nie udało się wygenerować poprawnego hasła.")  # praktycznie nieosiągalne


def renderuj_env(slug: str, *, nazwa: str, domena: str | None, db_url: str, sekrety: dict,
                 smtp_from: str = "") -> str:
    """Zwraca treść produkcyjnego pliku `.env` instancji (bez zapisu na dysk)."""
    poczta = domena or "twojadomena.pl"
    return f"""# ─────────────────────────────────────────────────────────────────────────────
# Instancja: {slug}   ({nazwa})
# Wygenerowano przez new_client.py — NIE COMMITUJ (zawiera sekrety instancji).
# Domena docelowa: {domena or '(ustaw przy wdrożeniu)'}
# ─────────────────────────────────────────────────────────────────────────────

# Produkcja: fail-fast na niebezpiecznych sekretach (settings.py).
APP_ENV=production

# Własna baza instancji (izolacja danych per klient).
DATABASE_URL={db_url}

# Sekret JWT — unikalny dla tej instancji.
SECRET_KEY={sekrety['SECRET_KEY']}
TOKEN_TTL_MINUTES=720

# Puste = tylko same-origin (backend serwuje frontend spod tej samej domeny).
CORS_ORIGINS=

# Token ingestu agenta POS/RCP — ustaw ten sam po stronie agenta lokalnego.
RCP_INGEST_TOKEN={sekrety['RCP_INGEST_TOKEN']}
RCP_POWIADOM_OKNO_MIN=60

# Web Push (PWA) — wygeneruj raz: python generate_vapid.py
VAPID_PUBLIC_KEY=
VAPID_PRIVATE_KEY=
VAPID_SUBJECT=mailto:admin@{poczta}

# E-mail (SMTP) — opcjonalne potwierdzenia rezerwacji (brak kompletu = wyłączone).
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM={smtp_from}
"""


def zapisz_env(katalog: Path, tresc: str, *, force: bool = False) -> Path:
    """Zapisuje `.env` w katalogu instancji. Idempotentny: bez force NIE nadpisuje
    istniejącego pliku (chroni przed przypadkową utratą sekretów działającej instancji)."""
    katalog = Path(katalog)
    katalog.mkdir(parents=True, exist_ok=True)
    plik = katalog / ".env"
    if plik.exists() and not force:
        raise FileExistsError(
            f"{plik} już istnieje — użyj --force, by nadpisać (uwaga: zmienia sekrety instancji)."
        )
    plik.write_text(tresc, encoding="utf-8")
    try:
        os.chmod(plik, 0o600)  # tylko właściciel (bez efektu na Windows — best-effort)
    except OSError:
        pass
    return plik


def zaloz_admina(db, login: str = None, haslo: str = None, *, email: str = None, haslo_hash: str = None):
    """Tworzy lub awansuje konto administratora w bazie instancji.
    Dwa tory:
      • e-mail (samoobsługa z checkoutu): `email` + gotowy `haslo_hash` (bcrypt policzony na matce,
        bez plaintextu). Wewnętrzny `login` syntetyzowany z adresu. Logowanie e-mailem.
      • login (operator/CLI): `login` + `haslo` (walidacja + hash lokalnie)."""
    import models
    from auth import hash_password
    from deps import unikalny_login_z_emaila

    if email:
        email = email.strip().lower()
        if haslo_hash:
            hh = haslo_hash
        else:
            sprawdz_haslo(haslo)
            hh = hash_password(haslo)
        u = db.query(models.User).filter(models.User.email == email).first()
        if u:
            u.rola, u.aktywny, u.haslo_hash = "admin", True, hh
            u.login = u.login or unikalny_login_z_emaila(db, email)
        else:
            u = models.User(login=unikalny_login_z_emaila(db, email), email=email,
                            haslo_hash=hh, rola="admin")
            db.add(u)
    else:
        login = sprawdz_login(login)
        sprawdz_haslo(haslo)
        u = db.query(models.User).filter(models.User.login == login).first()
        if u:
            u.rola, u.aktywny, u.haslo_hash = "admin", True, hash_password(haslo)
        else:
            u = models.User(login=login, haslo_hash=hash_password(haslo), rola="admin")
            db.add(u)
    db.commit()
    db.refresh(u)
    return u


TIERY = ("free", "basic", "pro", "premium", "enterprise")


def ustaw_tier(db, tier: str, *, oplacony: bool = False, dni: int = 30):
    """Ustawia pakiet (tier) subskrypcji instancji — np. wybór z cennika przy samoobsłudze.
    `oplacony=True` (tor z checkoutu): oznacza subskrypcję jako aktywną i opłaconą na `dni` dni
    (data_od=dziś, data_do=dziś+dni) — instancja startuje bez trybu tylko-do-odczytu."""
    import models

    if tier not in TIERY:
        raise ValueError(f"Nieznany tier '{tier}' (dozwolone: {', '.join(TIERY)}).")
    s = db.get(models.Subskrypcja, 1)
    if s is None:
        s = models.Subskrypcja(id=1)
        db.add(s)
    s.tier = tier
    if oplacony:
        from datetime import date, timedelta
        s.status = "aktywna"
        s.data_od = date.today()
        s.data_do = date.today() + timedelta(days=dni)
    db.commit()
    db.refresh(s)
    return s


def ustaw_trial(db, tier: str = "premium", dni: int = 14):
    """Uruchamia trial: status=trial + pełny dostęp (tier=premium → wszystkie moduły przez
    override w deps.moduly_efektywne_dla_sub). Po `dni` dniach instancja sama spada do Free."""
    import models
    from datetime import date, timedelta

    s = db.get(models.Subskrypcja, 1)
    if s is None:
        s = models.Subskrypcja(id=1)
        db.add(s)
    s.tier = tier
    s.status = "trial"
    s.data_od = date.today()
    s.data_do = date.today() + timedelta(days=dni)
    db.commit()
    db.refresh(s)
    return s


def ustaw_nazwe_lokalu(db, nazwa: str):
    """Ustawia nazwę lokalu w singletonie LokalConfig (id=1), tworząc go w razie potrzeby."""
    import models

    cfg = db.get(models.LokalConfig, 1)
    if cfg is None:
        cfg = models.LokalConfig(id=1)
        db.add(cfg)
    if nazwa:
        cfg.nazwa_lokalu = nazwa
    db.commit()
    db.refresh(cfg)
    return cfg


_POLA_KONFIGURACJI = ("typ_lokalu", "modul_rezerwacje", "modul_imprezy", "modul_rozliczenia",
                      "modul_pos", "modul_sprzatanie", "rezerwacje_online")


def ustaw_konfiguracje(db, dane: dict):
    """Ustawia typ lokalu + moduły w LokalConfig (id=1) z presetu kreatora (tor samoobsługi).
    Best-effort: nieznane/None pola pomijamy. Bez kroku onboardingu w instancji — konfiguracja
    z kreatora na matce jedzie tu razem z provisioningiem."""
    import models

    if not dane:
        return None
    cfg = db.get(models.LokalConfig, 1)
    if cfg is None:
        cfg = models.LokalConfig(id=1)
        db.add(cfg)
    for k in _POLA_KONFIGURACJI:
        if k in dane and dane[k] is not None:
            setattr(cfg, k, dane[k])
    db.commit()
    db.refresh(cfg)
    return cfg


def _domyslny_db_url(katalog: Path) -> str:
    """Domyślnie SQLite w katalogu instancji (działa od ręki). Produkcyjnie zaleca się
    Postgres per instancja: --db-url postgresql+psycopg2://user:haslo@host:5432/grafik_<slug>"""
    return f"sqlite:///{(katalog / 'grafik.db').as_posix()}"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Provisioning nowej instancji klienta (instance-per-tenant).")
    p.add_argument("slug", help="identyfikator instancji, np. restauracja-pod-lipa")
    p.add_argument("--nazwa", default="", help="nazwa lokalu (white-label), np. \"Restauracja Pod Lipą\"")
    p.add_argument("--admin", default="", help="login administratora (min. 5 znaków alfanumerycznych)")
    p.add_argument("--email", default="", help="e-mail administratora (tor samoobsługi z checkoutu); "
                   "hasło przekazywane jako bcrypt przez env LOKALO_ADMIN_HASLO_HASH (nie argv)")
    p.add_argument("--haslo", default="", help="hasło administratora (puste = wygenerowane losowo)")
    p.add_argument("--domena", default=None, help="docelowa domena/subdomena instancji")
    p.add_argument("--db-url", default=None, help="DATABASE_URL (domyślnie SQLite w katalogu instancji)")
    p.add_argument("--base-dir", default=None, help="katalog na instancje (domyślnie backend/instances)")
    p.add_argument("--init", action="store_true", help="zainicjuj bazę, załóż admina i ustaw nazwę lokalu")
    p.add_argument("--bez-admina", action="store_true",
                   help="z --init: zainicjuj bazę BEZ konta administratora — świeża instancja "
                        "pokaże kreator (onboarding), w którym klient sam założy konto właściciela "
                        "(tor samoobsługowego provisioningu)")
    p.add_argument("--tier", default=None, choices=list(TIERY),
                   help="z --init: pakiet subskrypcji instancji (np. wybór z cennika)")
    p.add_argument("--trial", action="store_true",
                   help="z --init --email: 14-dniowy trial pełnego dostępu (status=trial, tier=premium) "
                        "zamiast opłaconego planu — bez płatności")
    p.add_argument("--force", action="store_true", help="nadpisz istniejący .env instancji")
    args = p.parse_args(argv)

    try:
        slug = waliduj_slug(args.slug)
    except ValueError as e:
        print(f"Błąd: {e}", file=sys.stderr)
        return 2

    base_dir = Path(args.base_dir) if args.base_dir else Path(__file__).resolve().parent / "instances"
    katalog = base_dir / slug
    nazwa = args.nazwa or slug
    db_url = args.db_url or _domyslny_db_url(katalog)
    sekrety = generuj_sekrety()

    tresc = renderuj_env(slug, nazwa=nazwa, domena=args.domena, db_url=db_url, sekrety=sekrety)
    try:
        plik = zapisz_env(katalog, tresc, force=args.force)
    except FileExistsError as e:
        print(f"Błąd: {e}", file=sys.stderr)
        return 1
    print(f"[OK] Zapisano konfiguracje instancji: {plik}")

    if not args.init:
        print("[i] Pominieto inicjalizacje bazy (bez --init). Aby ja wykonac, uruchom ponownie z --init.")
        return 0

    # Inicjalizacja bazy: ustawiamy środowisko instancji PRZED importem database/aplikacji.
    os.environ["APP_ENV"] = "production"
    os.environ["DATABASE_URL"] = db_url
    os.environ["SECRET_KEY"] = sekrety["SECRET_KEY"]
    os.environ["RCP_INGEST_TOKEN"] = sekrety["RCP_INGEST_TOKEN"]

    import database  # import po ustawieniu env (czyta DATABASE_URL przy starcie)

    database.init_db()

    db = database.SessionLocal()
    admin_login = admin_haslo = None
    try:
        if args.email:
            # Tor samoobsługi z checkoutu: admin zakładany z e-maila (hash przez env, bez plaintextu),
            # a subskrypcja od razu AKTYWNA/OPŁACONA (instancja startuje bez trybu tylko-do-odczytu).
            hh = os.environ.get("LOKALO_ADMIN_HASLO_HASH")
            if not hh:
                print("Błąd: brak LOKALO_ADMIN_HASLO_HASH w środowisku dla toru --email.", file=sys.stderr)
                return 1
            if args.trial:
                ustaw_trial(db)                       # 14 dni pełnego dostępu, bez płatności
            elif args.tier:
                ustaw_tier(db, args.tier, oplacony=True)
            zaloz_admina(db, email=args.email, haslo_hash=hh)
            ustaw_nazwe_lokalu(db, nazwa)
            cfg_json = os.environ.get("LOKALO_CONFIG_JSON")
            if cfg_json:
                import json as _json
                try:
                    ustaw_konfiguracje(db, _json.loads(cfg_json))
                except (ValueError, TypeError):
                    pass  # zła konfiguracja nie blokuje provisioningu
        elif args.bez_admina:
            # Tor operatorski/enterprise: baza gotowa, zero kont → instancja przy pierwszym wejściu
            # pokaże kreator (bootstrap 0-userów), gdzie klient założy konto właściciela.
            if args.tier:
                ustaw_tier(db, args.tier)
            ustaw_nazwe_lokalu(db, nazwa)
        else:
            if args.tier:
                ustaw_tier(db, args.tier)
            admin_login = args.admin or "admin"
            admin_haslo = args.haslo or domyslne_haslo()
            zaloz_admina(db, admin_login, admin_haslo)
            ustaw_nazwe_lokalu(db, nazwa)
    except HTTPException as e:
        print(f"Błąd: {e.detail}", file=sys.stderr)
        return 1
    finally:
        db.close()

    print(f"[OK] Zainicjowano baze instancji: {db_url}")
    if args.email:
        print(f"[OK] Administrator (e-mail): {args.email}")
    elif args.bez_admina:
        print("[OK] Bez konta administratora — konto wlasciciela zalozy kreator (onboarding).")
    else:
        print(f"[OK] Administrator: login='{admin_login}'")
        if not args.haslo:
            print(f"     haslo (wygenerowane, zapisz je): {admin_haslo}")
    print(f"[OK] Nazwa lokalu: {nazwa}")
    print(f"\nNastepny krok: uruchom backend ze srodowiskiem tej instancji (plik {plik}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
