"""Izolowane testy kontraktu drivera Stripe R5c bez instalowania SDK."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import stripe_payments


class FakeService:
    def __init__(self):
        self.calls = []

    def _record(self, method, *args, **kwargs):
        call = {"method": method, "args": args, "kwargs": kwargs}
        self.calls.append(call)
        return call

    def create(self, *args, **kwargs):
        return self._record("create", *args, **kwargs)

    def retrieve(self, *args, **kwargs):
        return self._record("retrieve", *args, **kwargs)

    def expire(self, *args, **kwargs):
        return self._record("expire", *args, **kwargs)

    def capture(self, *args, **kwargs):
        return self._record("capture", *args, **kwargs)

    def cancel(self, *args, **kwargs):
        return self._record("cancel", *args, **kwargs)


class FakeStripeClient:
    instances = []

    def __init__(self, api_key, **kwargs):
        self.api_key = api_key
        self.kwargs = kwargs
        self.v1 = SimpleNamespace(
            checkout=SimpleNamespace(sessions=FakeService()),
            payment_intents=FakeService(),
            refunds=FakeService(),
        )
        type(self).instances.append(self)


class FakeWebhook:
    event = {
        "api_version": stripe_payments.STRIPE_API_VERSION,
        "livemode": False,
        "id": "evt_test",
    }
    calls = []

    @classmethod
    def construct_event(cls, *args, **kwargs):
        cls.calls.append((args, kwargs))
        return cls.event


@pytest.fixture
def fake_stripe(monkeypatch):
    FakeStripeClient.instances = []
    FakeWebhook.calls = []
    FakeWebhook.event = {
        "api_version": stripe_payments.STRIPE_API_VERSION,
        "livemode": False,
        "id": "evt_test",
    }
    module = SimpleNamespace(StripeClient=FakeStripeClient, Webhook=FakeWebhook)
    monkeypatch.setattr(stripe_payments, "_load_stripe", lambda: module)
    return module


@pytest.fixture
def driver(fake_stripe):
    return stripe_payments.StripePaymentDriver(
        api_key="rk_test_DriverContract123456",
        webhook_secret="whsec_DriverContract123456",
        public_app_url="https://app.example.test",
        payment_method_configuration="pmc_lokalo_deposit",
    )


def _checkout(driver, **overrides):
    params = {
        "payment_ref": "pay_018f",
        "reservation_ref": "reservation_18f:incarnation_2",
        "reservation_revision": 3,
        "policy_version": "policy_7",
        "amount_minor": 12_500,
        "kind": "deposit",
        "attempt_ref": "attempt_1",
        "expires_at": 1_800_000_000,
    }
    params.update(overrides)
    return driver.create_checkout_session(**params)


def test_sdk_is_lazy_and_missing_sdk_fails_only_on_first_io(monkeypatch):
    driver = stripe_payments.StripePaymentDriver(
        api_key="rk_test_DriverContract123456",
        webhook_secret="whsec_DriverContract123456",
        public_app_url="https://app.example.test",
    )

    def unavailable():
        raise stripe_payments.StripeSDKUnavailable("missing")

    monkeypatch.setattr(stripe_payments, "_load_stripe", unavailable)
    with pytest.raises(stripe_payments.StripeSDKUnavailable):
        driver.retrieve_payment_intent("pi_test_123")


def test_deposit_checkout_uses_dahlia_hosted_dynamic_methods(driver):
    call = _checkout(driver)
    params = call["args"][0]
    options = call["kwargs"]["options"]

    assert params["ui_mode"] == "hosted"
    assert params["mode"] == "payment"
    assert params["locale"] == "pl"
    assert params["success_url"] == "https://app.example.test/?rezerwuj&platnosc=powrot"
    assert params["cancel_url"] == (
        "https://app.example.test/?rezerwuj&platnosc=anulowana"
    )
    assert "session_id" not in params["success_url"]
    assert "CHECKOUT_SESSION_ID" not in params["success_url"]
    assert "payment_method_types" not in params
    assert params["payment_method_configuration"] == "pmc_lokalo_deposit"
    assert params["line_items"][0]["price_data"]["currency"] == "pln"
    assert params["line_items"][0]["price_data"]["unit_amount"] == 12_500
    assert params["payment_intent_data"]["capture_method"] == "automatic_async"
    assert params["metadata"] == params["payment_intent_data"]["metadata"]
    assert params["metadata"]["lokalo_payment_ref"] == "pay_018f"
    assert options["stripe_version"] == "2026-06-24.dahlia"
    assert options["idempotency_key"] == stripe_payments.stable_idempotency_key(
        "checkout", "attempt_1"
    )
    client = FakeStripeClient.instances[0]
    assert client.api_key == "rk_test_DriverContract123456"
    assert client.kwargs == {"max_network_retries": 2}


def test_preauthorization_uses_manual_capture_without_method_allowlist(driver):
    call = _checkout(driver, kind="preauthorization", attempt_ref="attempt_2")
    params = call["args"][0]

    assert params["payment_intent_data"]["capture_method"] == "manual"
    assert "payment_method_types" not in params
    assert params["metadata"]["lokalo_payment_kind"] == "preauthorization"


def test_stable_idempotency_key_is_retry_stable_and_operation_scoped():
    first = stripe_payments.stable_idempotency_key("checkout", "attempt_1")
    assert first == stripe_payments.stable_idempotency_key(
        "checkout", "attempt_1"
    )
    assert first != stripe_payments.stable_idempotency_key(
        "checkout", "attempt_2"
    )
    assert first != stripe_payments.stable_idempotency_key(
        "refund", "attempt_1"
    )
    assert len(first) <= 255
    assert "attempt_1" not in first


@pytest.mark.parametrize("amount", [True, 0, 199, 100_000_000, 12.5])
def test_checkout_rejects_unsupported_pln_amount_before_sdk_io(driver, amount):
    with pytest.raises(ValueError):
        _checkout(driver, amount_minor=amount)
    assert FakeStripeClient.instances == []


@pytest.mark.parametrize(
    "url",
    [
        "http://app.example.test",
        "https://user:password@app.example.test",
        "https://app.example.test/?redirect=https://evil.example",
        "https://app.example.test/#fragment",
    ],
)
def test_public_app_url_is_fail_closed(url):
    with pytest.raises(ValueError):
        stripe_payments.StripePaymentDriver(
            api_key="rk_test_DriverContract123456",
            webhook_secret="whsec_DriverContract123456",
            public_app_url=url,
        )


def test_loopback_http_is_available_only_for_local_stripe_cli(fake_stripe):
    success, cancel = stripe_payments.checkout_return_urls(
        "http://127.0.0.1:5174/"
    )
    assert success.startswith("http://127.0.0.1:5174/?rezerwuj")
    assert cancel.endswith("?rezerwuj&platnosc=anulowana")


def test_checkout_capture_cancel_refund_and_retrieve_contract(driver):
    driver.retrieve_checkout_session("cs_test_123")
    driver.expire_checkout_session("cs_test_123", operation_ref="expire_1")
    driver.retrieve_payment_intent("pi_test_123")
    driver.capture_payment_intent(
        "pi_test_123", operation_ref="capture_1", amount_minor=5_000
    )
    driver.cancel_payment_intent(
        "pi_test_123", operation_ref="cancel_1", reason="abandoned"
    )
    refund_call = driver.create_full_refund(
        "pi_test_123",
        payment_ref="pay_018f",
        operation_ref="refund_1",
    )
    driver.retrieve_refund("re_test_123")

    client = FakeStripeClient.instances[0]
    session_calls = client.v1.checkout.sessions.calls
    assert session_calls[0]["args"] == (
        "cs_test_123",
        {"expand": ["payment_intent.latest_charge"]},
    )
    assert session_calls[0]["kwargs"]["options"] == {
        "stripe_version": stripe_payments.STRIPE_API_VERSION
    }
    assert session_calls[1]["method"] == "expire"
    assert "idempotency_key" in session_calls[1]["kwargs"]["options"]

    intent_calls = client.v1.payment_intents.calls
    assert intent_calls[0]["args"] == (
        "pi_test_123",
        {"expand": ["latest_charge"]},
    )
    assert intent_calls[1]["args"][1] == {"amount_to_capture": 5_000}
    assert intent_calls[2]["args"][1] == {"cancellation_reason": "abandoned"}
    assert all(
        call["kwargs"]["options"]["stripe_version"]
        == stripe_payments.STRIPE_API_VERSION
        for call in intent_calls
    )

    refund_params = refund_call["args"][0]
    assert refund_params["payment_intent"] == "pi_test_123"
    assert "amount" not in refund_params
    assert refund_params["reason"] == "requested_by_customer"
    assert client.v1.refunds.calls[1]["method"] == "retrieve"


def test_webhook_uses_raw_body_signature_tolerance_version_and_mode(driver):
    raw = b'{"id":"evt_test"}'
    event = driver.construct_webhook_event(raw, "t=123,v1=signature")

    assert event["id"] == "evt_test"
    args, kwargs = FakeWebhook.calls[0]
    assert args == (raw, "t=123,v1=signature", "whsec_DriverContract123456")
    assert kwargs == {"tolerance": 300}


def test_webhook_rejects_parsed_body_wrong_version_and_wrong_mode(
    driver, fake_stripe
):
    with pytest.raises(TypeError):
        driver.construct_webhook_event('{"id":"evt_test"}', "sig")
    assert FakeWebhook.calls == []

    FakeWebhook.event = {"api_version": "2026-03-25.dahlia", "livemode": False}
    with pytest.raises(stripe_payments.StripeWebhookContractError):
        driver.construct_webhook_event(b"{}", "sig")

    FakeWebhook.event = {
        "api_version": stripe_payments.STRIPE_API_VERSION,
        "livemode": True,
    }
    with pytest.raises(stripe_payments.StripeWebhookContractError):
        driver.construct_webhook_event(b"{}", "sig")


def test_environment_contract_pins_api_version(monkeypatch, fake_stripe):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("STRIPE_RESTRICTED_KEY", "rk_test_DriverContract123456")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_DriverContract123456")
    monkeypatch.setenv("PUBLIC_APP_URL", "https://app.example.test")
    monkeypatch.setenv("STRIPE_EXPECTED_LIVEMODE", "false")
    monkeypatch.setenv("STRIPE_API_VERSION", "2026-06-24.dahlia")
    driver = stripe_payments.StripePaymentDriver.from_environment(production=False)
    assert driver.construct_webhook_event(b"{}", "sig")["id"] == "evt_test"

    monkeypatch.setenv("STRIPE_API_VERSION", "latest")
    with pytest.raises(ValueError, match="STRIPE_API_VERSION"):
        stripe_payments.StripePaymentDriver.from_environment(production=False)
