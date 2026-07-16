"""Fail-closed provider selection for required R5c payments."""

from __future__ import annotations

import pytest

import integracje
import settings
import stripe_payments


PAYMENT_ENV = (
    "PAYMENTS_PROVIDER",
    "STRIPE_RESTRICTED_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "PUBLIC_APP_URL",
    "STRIPE_API_VERSION",
    "STRIPE_EXPECTED_LIVEMODE",
    "STRIPE_PAYMENT_METHOD_CONFIGURATION",
)


@pytest.fixture(autouse=True)
def _clean_payment_environment(monkeypatch):
    for name in PAYMENT_ENV:
        monkeypatch.delenv(name, raising=False)


def _stripe_environment(monkeypatch, *, live: bool = False) -> None:
    mode = "live" if live else "test"
    monkeypatch.setenv("PAYMENTS_PROVIDER", "stripe")
    monkeypatch.setenv(
        "STRIPE_RESTRICTED_KEY",
        f"rk_{mode}_IntegrationContract123456789",
    )
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_IntegrationContract123456789")
    monkeypatch.setenv("PUBLIC_APP_URL", "https://reservations.example.com")
    monkeypatch.setenv("STRIPE_API_VERSION", stripe_payments.STRIPE_API_VERSION)
    monkeypatch.setenv("STRIPE_EXPECTED_LIVEMODE", "true" if live else "false")


def test_development_keeps_explicit_demo_without_calling_it_configured(monkeypatch):
    monkeypatch.setattr(settings, "IS_DEV", True)

    assert integracje.provider_platnosci_wymaganej() == "sandbox"
    assert integracje.skonfigurowane("platnosci") is False

    monkeypatch.setenv("PAYMENTS_PROVIDER", "sandbox")
    assert integracje.provider_platnosci_wymaganej() == "sandbox"


def test_production_never_falls_back_to_sandbox(monkeypatch):
    monkeypatch.setattr(settings, "IS_DEV", False)
    monkeypatch.setenv("PAYMENTS_PROVIDER", "sandbox")

    with pytest.raises(integracje.PaymentProviderConfigurationError) as exc:
        integracje.provider_platnosci_wymaganej()

    assert exc.value.code == "PAYMENT_PROVIDER_CONFIGURATION_INVALID"
    assert "produkcja" in exc.value.message


def test_explicit_broken_stripe_never_degrades_to_demo(monkeypatch):
    monkeypatch.setattr(settings, "IS_DEV", True)
    _stripe_environment(monkeypatch)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "not-a-webhook-secret")

    assert integracje.skonfigurowane("platnosci") is False
    with pytest.raises(integracje.PaymentProviderConfigurationError) as exc:
        integracje.provider_platnosci_wymaganej()
    assert "konfiguracja Stripe" in exc.value.message


@pytest.mark.parametrize(
    ("field", "value"),
    [
        (
            "STRIPE_RESTRICTED_KEY",
            "".join(("sk", "_test_", "SecretKeysAreRejected123")),
        ),
        ("STRIPE_RESTRICTED_KEY", "rk_test_short"),
        ("STRIPE_WEBHOOK_SECRET", "whsec_short"),
        ("PUBLIC_APP_URL", "http://reservations.example.com"),
        ("STRIPE_EXPECTED_LIVEMODE", "true"),
        ("STRIPE_EXPECTED_LIVEMODE", "auto"),
        ("STRIPE_API_VERSION", "latest"),
    ],
)
def test_full_test_mode_contract_is_validated(monkeypatch, field, value):
    monkeypatch.setattr(settings, "IS_DEV", True)
    _stripe_environment(monkeypatch)
    monkeypatch.setenv(field, value)

    assert integracje.skonfigurowane("platnosci") is False
    with pytest.raises(integracje.PaymentProviderConfigurationError):
        integracje.provider_platnosci_wymaganej()


def test_valid_test_and_live_contracts_are_environment_scoped(monkeypatch):
    monkeypatch.setattr(settings, "IS_DEV", True)
    _stripe_environment(monkeypatch)
    assert integracje.skonfigurowane("platnosci") is True
    assert integracje.provider_platnosci_wymaganej() == "stripe"

    monkeypatch.setattr(settings, "IS_DEV", False)
    assert integracje.skonfigurowane("platnosci") is False

    _stripe_environment(monkeypatch, live=True)
    assert integracje.skonfigurowane("platnosci") is True
    assert integracje.provider_platnosci_wymaganej() == "stripe"


def test_production_rejects_loopback_even_over_https(monkeypatch):
    monkeypatch.setattr(settings, "IS_DEV", False)
    _stripe_environment(monkeypatch, live=True)
    monkeypatch.setenv("PUBLIC_APP_URL", "https://127.0.0.1:5174")

    assert integracje.skonfigurowane("platnosci") is False
    with pytest.raises(integracje.PaymentProviderConfigurationError):
        integracje.provider_platnosci_wymaganej()
