"""Status integracji per instancja („secret store").

W modelu instance-per-tenant sekrety integracji trzymane są w zmiennych środowiskowych
instancji (.env). Ten moduł CENTRALNIE wie, które integracje są skonfigurowane — bez
ujawniania wartości sekretów. Wzorzec spójny z fail-fast settings.py:
    brak / niepełny sekret  =>  integracja WYŁĄCZONA (nie crash aplikacji).

Konsumenci (np. wysyłka e-mail, SMS, płatności) pytają `skonfigurowane("email")` zanim
spróbują użyć integracji.
"""

import os


def _ma(*klucze: str) -> bool:
    """True, gdy WSZYSTKIE wskazane zmienne środowiskowe są ustawione (niepuste)."""
    return all(bool((os.environ.get(k) or "").strip()) for k in klucze)


# Rejestr integracji: klucz, czytelna nazwa, wymagane zmienne środowiskowe.
INTEGRACJE = [
    {"klucz": "push",       "nazwa": "Powiadomienia push (VAPID)",        "env": ["VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY"]},
    {"klucz": "pos",        "nazwa": "Agent POS / RCP (Gastro)",          "env": ["RCP_INGEST_TOKEN"]},
    {"klucz": "email",      "nazwa": "E-mail (SMTP) — potwierdzenia",     "env": ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"]},
    {"klucz": "sms",        "nazwa": "SMS (bramka)",                      "env": ["SMS_API_TOKEN", "SMS_API_URL"]},
    {"klucz": "platnosci",  "nazwa": "Płatności online (zadatki)",        "env": ["PAYMENTS_API_KEY"]},
]

_WG_KLUCZA = {i["klucz"]: i for i in INTEGRACJE}


def skonfigurowane(klucz: str) -> bool:
    """Czy integracja o danym kluczu ma komplet sekretów (jest aktywna)."""
    i = _WG_KLUCZA.get(klucz)
    return bool(i and _ma(*i["env"]))


def status() -> list[dict]:
    """Lista integracji ze statusem (bez wartości sekretów — tylko nazwy zmiennych)."""
    return [{"klucz": i["klucz"], "nazwa": i["nazwa"],
             "skonfigurowane": _ma(*i["env"]), "wymaga": list(i["env"])}
            for i in INTEGRACJE]
