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


def zaloz_admina(db, login: str, haslo: str):
    """Tworzy lub awansuje konto administratora w bazie instancji (jak create_admin, ale na sesji)."""
    import models
    from auth import hash_password

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


def _domyslny_db_url(katalog: Path) -> str:
    """Domyślnie SQLite w katalogu instancji (działa od ręki). Produkcyjnie zaleca się
    Postgres per instancja: --db-url postgresql+psycopg2://user:haslo@host:5432/grafik_<slug>"""
    return f"sqlite:///{(katalog / 'grafik.db').as_posix()}"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Provisioning nowej instancji klienta (instance-per-tenant).")
    p.add_argument("slug", help="identyfikator instancji, np. restauracja-pod-lipa")
    p.add_argument("--nazwa", default="", help="nazwa lokalu (white-label), np. \"Restauracja Pod Lipą\"")
    p.add_argument("--admin", default="", help="login administratora (min. 5 znaków alfanumerycznych)")
    p.add_argument("--haslo", default="", help="hasło administratora (puste = wygenerowane losowo)")
    p.add_argument("--domena", default=None, help="docelowa domena/subdomena instancji")
    p.add_argument("--db-url", default=None, help="DATABASE_URL (domyślnie SQLite w katalogu instancji)")
    p.add_argument("--base-dir", default=None, help="katalog na instancje (domyślnie backend/instances)")
    p.add_argument("--init", action="store_true", help="zainicjuj bazę, załóż admina i ustaw nazwę lokalu")
    p.add_argument("--bez-admina", action="store_true",
                   help="z --init: zainicjuj bazę BEZ konta administratora — świeża instancja "
                        "pokaże kreator (onboarding), w którym klient sam założy konto właściciela "
                        "(tor samoobsługowego provisioningu)")
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
    try:
        if args.bez_admina:
            # Tor samoobsługi: baza gotowa, zero kont → instancja przy pierwszym wejściu
            # pokaże kreator (bootstrap 0-userów), gdzie klient założy konto właściciela.
            ustaw_nazwe_lokalu(db, nazwa)
        else:
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
    if args.bez_admina:
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
