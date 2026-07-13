"""Centralna walidacja krytycznych sekretów + konfiguracja CORS (secure by default).

Filozofia: bezpieczeństwo domyślnie. W trybie PRODUKCYJNYM (APP_ENV != development)
aplikacja ODMAWIA STARTU, gdy krytyczny sekret ma wartość domyślną/przykładową —
inaczej nowy klient mógłby ruszyć z `SECRET_KEY=dev-secret-change-me` i każdy
podrobiłby token administratora. W trybie deweloperskim te same problemy są tylko
ostrzeżeniami, żeby nie utrudniać lokalnej pracy.

Tryb wybiera zmienna APP_ENV:
  - (brak) / "production"      → produkcja: twarde błędy na niebezpiecznych sekretach.
  - "development"/"dev"/"local"/"test" → ostrzeżenia zamiast błędów.

Aby świadomie uruchomić lokalnie z domyślnymi sekretami:  APP_ENV=development
"""

import os
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo
from typing import Optional

APP_ENV = os.environ.get("APP_ENV", "production").strip().lower()
IS_DEV = APP_ENV in ("development", "dev", "local", "test")

# Próg „za krótki" dla SECRET_KEY (ostrzeżenie, nie błąd).
_MIN_SECRET_LEN = 32

# Znane, niebezpieczne wartości domyślne/przykładowe (z .env.example i kodu).
# UWAGA: świadomie NIE umieszczamy tu "test-secret-key"/"test-rcp-token" używanych
# przez zestaw testów — inaczej testy nie wystartowałyby w trybie produkcyjnym.
_INSECURE_SECRET_KEYS = {
    "",
    "dev-secret-change-me",
    "zmien-mnie-na-dlugi-losowy-sekret",
    "change-me",
    "changeme",
    "secret",
    "changethis",
}
_INSECURE_RCP_TOKENS = {
    "ten-sam-dlugi-sekret-co-w-agencie",
    "zmien-mnie",
    "changeme",
}

# Origins dozwolone domyślnie w trybie deweloperskim (proxy Vite + lokalny backend).
DEV_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

# Origins aplikacji NATYWNEJ (Capacitor). WebView łączy się cross-origin z adresem
# instancji, więc te originy muszą być dozwolone ZAWSZE (także w produkcji). Bezpieczne:
# API autoryzuje bearer-tokenem (nie ciasteczkami), więc CORS nie jest tu granicą bezpieczeństwa.
#   iOS         → capacitor://localhost
#   Android     → https://localhost (Capacitor 6+) oraz http://localhost (starsze / server.androidScheme)
NATIVE_ORIGINS = [
    "capacitor://localhost",
    "https://localhost",
    "http://localhost",
    "ionic://localhost",
]



def cors_origins() -> list[str]:
    """Lista dozwolonych originów dla CORS (secure by default).

    - CORS_ORIGINS ustawione → używamy podanej listy (po przecinku).
    - CORS_ORIGINS puste/niebrak:
        * produkcja → [] (tylko same-origin; backend serwuje frontend z tego samego
          adresu, więc cross-origin nie jest potrzebny),
        * dev       → lista lokalnych adresów (proxy Vite).

    Do wyniku ZAWSZE dokładamy originy aplikacji natywnej (Capacitor) — apka mobilna
    łączy się z instancją cross-origin niezależnie od trybu.
    """
    raw = os.environ.get("CORS_ORIGINS")
    if raw is None or raw.strip() == "":
        base = list(DEV_ORIGINS) if IS_DEV else []
    else:
        base = [o.strip() for o in raw.split(",") if o.strip()]
    for o in NATIVE_ORIGINS:
        if o not in base:
            base.append(o)
    return base


def _problems() -> tuple[list[str], list[str]]:
    """Zwraca (błędy_krytyczne, ostrzeżenia) dla bieżącej konfiguracji."""
    errors: list[str] = []
    warnings: list[str] = []

    secret = os.environ.get("SECRET_KEY", "")
    if secret in _INSECURE_SECRET_KEYS:
        errors.append(
            "SECRET_KEY ma wartość domyślną/pustą — ustaw długi, losowy sekret. "
            'Wygeneruj: python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )
    elif len(secret) < _MIN_SECRET_LEN:
        warnings.append(
            f"SECRET_KEY jest krótki ({len(secret)} znaków) — zalecane min. {_MIN_SECRET_LEN}."
        )

    enc = os.environ.get("ENCRYPTION_KEY", "").strip()
    if not enc:
        errors.append(
            "ENCRYPTION_KEY nie jest ustawiony — PII gości (telefon, e-mail) byłoby zapisywane "
            "JAWNYM TEKSTEM (bez szyfrowania at-rest, RODO art. 32). Ustaw długi, losowy klucz "
            '(np. python -c "import secrets; print(secrets.token_urlsafe(48))") i NIE zmieniaj go '
            "po pierwszym zapisie danych."
        )

    rcp = os.environ.get("RCP_INGEST_TOKEN", "")
    if rcp in _INSECURE_RCP_TOKENS:
        errors.append(
            "RCP_INGEST_TOKEN ma wartość przykładową — ustaw długi, losowy token "
            "(ten sam co w agencie lokalnym) albo zostaw pusty, jeśli nie używasz agenta POS."
        )
    elif rcp == "":
        warnings.append(
            "RCP_INGEST_TOKEN jest pusty — ingest agenta POS (RCP/Gastro) jest wyłączony "
            "(wszystkie żądania /api/rcp/ingest i /api/gastro/* będą odrzucane)."
        )

    db_url = os.environ.get("DATABASE_URL", "")
    if "grafik:grafik@" in db_url:
        warnings.append(
            "DATABASE_URL używa domyślnych danych logowania (grafik:grafik) — "
            "zmień login/hasło bazy w środowisku produkcyjnym."
        )

    raw_cors = os.environ.get("CORS_ORIGINS", "")
    if not IS_DEV and raw_cors.strip() == "*":
        errors.append(
            "CORS_ORIGINS='*' w trybie produkcyjnym jest niedozwolone — ogranicz do adresu frontendu "
            "(albo zostaw puste: backend serwuje frontend z tego samego adresu)."
        )

    return errors, warnings


def validate_critical_secrets() -> None:
    """Sprawdza sekrety przy starcie. W produkcji RZUCA RuntimeError na błędach
    krytycznych (fail-fast → aplikacja nie wstaje). W dev tylko ostrzega."""
    errors, warnings = _problems()

    for w in warnings:
        print(f"⚠️  [konfiguracja] {w}", file=sys.stderr)

    if not errors:
        return

    header = (
        "BŁĄD KONFIGURACJI BEZPIECZEŃSTWA — aplikacja nie zostanie uruchomiona.\n"
        "Napraw poniższe sekrety (np. w pliku backend/.env):"
    )
    body = "\n".join(f"  • {e}" for e in errors)
    hint = (
        "\nDo świadomego uruchomienia lokalnego z domyślnymi sekretami ustaw: APP_ENV=development"
    )
    message = f"{header}\n{body}{hint}"

    if IS_DEV:
        # W dev nie blokujemy startu — tylko głośno ostrzegamy.
        print(f"⚠️  {message}", file=sys.stderr)
        return

    raise RuntimeError(message)
