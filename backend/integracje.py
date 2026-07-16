"""Status integracji per instancja („secret store").

W modelu instance-per-tenant sekrety integracji trzymane są w zmiennych środowiskowych
instancji (.env). Ten moduł CENTRALNIE wie, które integracje są skonfigurowane — bez
ujawniania wartości sekretów. Wzorzec spójny z fail-fast settings.py:
    brak / niepełny sekret  =>  integracja WYŁĄCZONA (nie crash aplikacji).

Konsumenci (np. wysyłka e-mail, SMS, płatności) pytają `skonfigurowane("email")` zanim
spróbują użyć integracji.
"""

import os

import settings


class PaymentProviderConfigurationError(RuntimeError):
    """A required reservation payment has no safe provider configuration."""

    code = "PAYMENT_PROVIDER_CONFIGURATION_INVALID"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _ma(*klucze: str) -> bool:
    """True, gdy WSZYSTKIE wskazane zmienne środowiskowe są ustawione (niepuste)."""
    return all(bool((os.environ.get(k) or "").strip()) for k in klucze)


# Rejestr integracji: klucz, czytelna nazwa, wymagane zmienne środowiskowe.
INTEGRACJE = [
    {"klucz": "push",       "nazwa": "Powiadomienia push (VAPID)",        "env": ["VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY"]},
    {"klucz": "pos",        "nazwa": "Agent POS / RCP (Gastro)",          "env": ["RCP_INGEST_TOKEN"]},
    {"klucz": "email",      "nazwa": "E-mail (SMTP) — potwierdzenia",     "env": ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"]},
    {"klucz": "sms",        "nazwa": "SMS (bramka)",                      "env": ["SMS_API_TOKEN", "SMS_API_URL"]},
    {
        "klucz": "platnosci",
        "nazwa": "Płatności online rezerwacji (Stripe)",
        "env": [
            "PAYMENTS_PROVIDER",
            "STRIPE_RESTRICTED_KEY",
            "STRIPE_WEBHOOK_SECRET",
            "PUBLIC_APP_URL",
            "STRIPE_API_VERSION",
            "STRIPE_EXPECTED_LIVEMODE",
        ],
    },
]

_WG_KLUCZA = {i["klucz"]: i for i in INTEGRACJE}


def skonfigurowane(klucz: str) -> bool:
    """Czy integracja o danym kluczu ma komplet sekretów (jest aktywna)."""
    i = _WG_KLUCZA.get(klucz)
    if not i or not _ma(*i["env"]):
        return False
    if klucz == "platnosci":
        if os.environ.get("PAYMENTS_PROVIDER", "").strip().lower() != "stripe":
            return False
        # Nie wystarcza już obecność czterech napisów. Ten sam kontrakt,
        # który utworzy worker, sprawdza prefiksy rk_/whsec_, bezpieczny URL,
        # zgodność test/live oraz przypiętą wersję API — nadal bez I/O.
        try:
            from stripe_payments import StripePaymentDriver

            StripePaymentDriver.from_environment(production=not settings.IS_DEV)
        except (TypeError, ValueError):
            return False
        return True
    return True


def provider_platnosci_wymaganej() -> str:
    """Select ``stripe`` or an explicitly non-production ``sandbox``.

    Wywołuje to dopiero ścieżka rezerwacji, dla której rozstrzygnięta polityka
    rzeczywiście wymaga płatności. Brak/``sandbox`` pozostaje wygodnym demo w
    development/test, ale nigdy nie jest cichym fallbackiem produkcyjnym.
    Jawnie wybrany, lecz niepełny Stripe także nie degraduje się do demo.
    """

    configured = (os.environ.get("PAYMENTS_PROVIDER") or "").strip().lower()
    if configured == "stripe":
        if skonfigurowane("platnosci"):
            return "stripe"
        raise PaymentProviderConfigurationError(
            "Płatność jest wymagana, ale konfiguracja Stripe jest niepełna lub niespójna. "
            "Sprawdź restricted key rk_*, sekret webhooka whsec_*, PUBLIC_APP_URL oraz "
            "zgodność trybu test/live."
        )
    if configured in {"", "sandbox"}:
        if settings.IS_DEV:
            return "sandbox"
        raise PaymentProviderConfigurationError(
            "Płatność jest wymagana, ale produkcja nie ma aktywnej integracji Stripe. "
            "Sandbox jest dozwolony wyłącznie w development/test."
        )
    raise PaymentProviderConfigurationError(
        "Płatność jest wymagana, ale PAYMENTS_PROVIDER ma nieobsługiwaną wartość. "
        "Użyj 'stripe' albo 'sandbox' wyłącznie w development/test."
    )


def status() -> list[dict]:
    """Lista integracji ze statusem (bez wartości sekretów — tylko nazwy zmiennych)."""
    return [{"klucz": i["klucz"], "nazwa": i["nazwa"],
             "skonfigurowane": skonfigurowane(i["klucz"]), "wymaga": list(i["env"])}
            for i in INTEGRACJE]
