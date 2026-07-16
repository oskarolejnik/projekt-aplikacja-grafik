"""Minimalny, fail-closed adapter Stripe dla platnosci rezerwacji R5c.

Modul celowo nie zalezy od modeli ani routerow. Warstwa domenowa przechowuje
trwale identyfikatory operacji, a ten adapter mapuje je na stabilne klucze
idempotencji Stripe. SDK jest importowane dopiero przy pierwszym wywolaniu,
wiec brak opcjonalnej zaleznosci nie blokuje uruchomienia aplikacji bez Stripe.
"""

from __future__ import annotations

from hashlib import sha256
from importlib import import_module
import os
import re
from typing import Any, Literal, Mapping
from urllib.parse import urlsplit, urlunsplit


STRIPE_API_VERSION = "2026-06-24.dahlia"
STRIPE_WEBHOOK_TOLERANCE_SECONDS = 300
STRIPE_NETWORK_RETRIES = 2

CheckoutKind = Literal["deposit", "preauthorization"]

_OPAQUE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$")
_PROVIDER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_:-]{1,254}$")
_OPERATIONS = frozenset({"checkout", "expire", "capture", "cancel", "refund"})
_CANCEL_REASONS = frozenset(
    {"duplicate", "fraudulent", "requested_by_customer", "abandoned"}
)
_REFUND_REASONS = frozenset(
    {"duplicate", "fraudulent", "requested_by_customer"}
)
_MIN_PLN_AMOUNT_MINOR = 200
_MAX_PLN_AMOUNT_MINOR = 99_999_999
_STRIPE_KEY = re.compile(r"^rk_(test|live)_[A-Za-z0-9]{8,}$")
_STRIPE_WEBHOOK_SECRET = re.compile(r"^whsec_[A-Za-z0-9]{8,}$")
_DEV_APP_ENVS = frozenset({"development", "dev", "local", "test"})


class StripePaymentsError(RuntimeError):
    """Bazowy blad lokalnego kontraktu adaptera Stripe."""


class StripeSDKUnavailable(StripePaymentsError):
    """Opcjonalne SDK Stripe nie jest dostepne lub ma zly kontrakt."""


class StripeWebhookContractError(StripePaymentsError):
    """Podpisane zdarzenie nie pasuje do wersji/trybu tej instancji."""


def _load_stripe() -> Any:
    try:
        stripe = import_module("stripe")
    except (ImportError, ModuleNotFoundError) as exc:
        raise StripeSDKUnavailable("Stripe SDK is unavailable.") from exc
    if not hasattr(stripe, "StripeClient") or not hasattr(stripe, "Webhook"):
        raise StripeSDKUnavailable("Stripe SDK has an unsupported contract.")
    return stripe


def _require_opaque_ref(value: str, field: str) -> str:
    if not isinstance(value, str) or not _OPAQUE_REF.fullmatch(value):
        raise ValueError(f"{field} must be an opaque identifier.")
    return value


def _require_provider_id(value: str, field: str, prefix: str) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith(prefix)
        or not _PROVIDER_ID.fullmatch(value)
    ):
        raise ValueError(f"{field} has an invalid provider identifier.")
    return value


def _require_amount_minor(value: int, field: str = "amount_minor") -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < _MIN_PLN_AMOUNT_MINOR
        or value > _MAX_PLN_AMOUNT_MINOR
    ):
        raise ValueError(f"{field} must be a supported positive PLN minor amount.")
    return value


def _require_api_key(value: str) -> str:
    if (
        not isinstance(value, str)
        or _STRIPE_KEY.fullmatch(value) is None
    ):
        raise ValueError("A valid restricted Stripe API key (rk_test_*/rk_live_*) is required.")
    return value


def _require_webhook_secret(value: str) -> str:
    if (
        not isinstance(value, str)
        or _STRIPE_WEBHOOK_SECRET.fullmatch(value) is None
    ):
        raise ValueError("A valid Stripe webhook signing secret (whsec_*) is required.")
    return value


def _normalize_public_app_url(
    value: str,
    *,
    allow_loopback_http: bool = True,
) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 2048:
        raise ValueError("PUBLIC_APP_URL is invalid.")
    parsed = urlsplit(value.strip())
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("PUBLIC_APP_URL is invalid.") from exc
    host = (parsed.hostname or "").casefold()
    loopback = host in {"localhost", "127.0.0.1", "::1"}
    if (
        not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or (loopback and not allow_loopback_http)
        or (
            parsed.scheme != "https"
            and not (allow_loopback_http and parsed.scheme == "http" and loopback)
        )
    ):
        raise ValueError("PUBLIC_APP_URL must be a safe HTTPS URL.")
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def checkout_return_urls(public_app_url: str) -> tuple[str, str]:
    """Buduje stałe powroty UI bez identyfikatora obiektu providera w URL."""

    base = _normalize_public_app_url(public_app_url)
    success_url = f"{base}/?rezerwuj&platnosc=powrot"
    cancel_url = f"{base}/?rezerwuj&platnosc=anulowana"
    return success_url, cancel_url


def stable_idempotency_key(operation: str, operation_ref: str) -> str:
    """Tworzy nieodwracalny, stabilny klucz z trwalego ID lokalnej operacji.

    ``operation_ref`` musi identyfikowac jedna niemutowalna operacje w bazie.
    Ponowienie tej samej operacji daje ten sam klucz; nowa proba musi miec nowe ID.
    """

    if operation not in _OPERATIONS:
        raise ValueError("Unsupported Stripe operation.")
    reference = _require_opaque_ref(operation_ref, "operation_ref")
    digest = sha256(
        f"lokalo-r5c-v1\0{operation}\0{reference}".encode("utf-8")
    ).hexdigest()
    return f"lokalo:r5c:{operation}:v1:{digest}"


def _event_value(event: Any, key: str) -> Any:
    if isinstance(event, Mapping):
        return event.get(key)
    return getattr(event, key, None)


def construct_webhook_event(
    raw_body: bytes,
    stripe_signature: str,
    webhook_secret: str,
    *,
    expected_livemode: bool | None = None,
) -> Any:
    """Weryfikuje podpis na surowym body i fail-closed sprawdza kontrakt eventu."""

    if not isinstance(raw_body, bytes):
        raise TypeError("Stripe webhook body must be raw bytes.")
    if not isinstance(stripe_signature, str) or not stripe_signature.strip():
        raise ValueError("Stripe-Signature header is required.")
    secret = _require_webhook_secret(webhook_secret)
    stripe = _load_stripe()
    event = stripe.Webhook.construct_event(
        raw_body,
        stripe_signature,
        secret,
        tolerance=STRIPE_WEBHOOK_TOLERANCE_SECONDS,
    )
    if _event_value(event, "api_version") != STRIPE_API_VERSION:
        raise StripeWebhookContractError("Unexpected Stripe event API version.")
    livemode = _event_value(event, "livemode")
    if not isinstance(livemode, bool):
        raise StripeWebhookContractError("Stripe event livemode is missing.")
    if expected_livemode is not None and livemode is not expected_livemode:
        raise StripeWebhookContractError("Unexpected Stripe event mode.")
    return event


class StripePaymentDriver:
    """Izolowany klient Stripe Checkout/PaymentIntent/Refund dla R5c."""

    def __init__(
        self,
        *,
        api_key: str,
        webhook_secret: str,
        public_app_url: str,
        expected_livemode: bool | None = None,
        payment_method_configuration: str | None = None,
        allow_loopback_http: bool = True,
    ) -> None:
        self._api_key = _require_api_key(api_key)
        self._webhook_secret = _require_webhook_secret(webhook_secret)
        self._public_app_url = _normalize_public_app_url(
            public_app_url,
            allow_loopback_http=allow_loopback_http,
        )
        key_livemode = "_live_" in self._api_key
        if expected_livemode is None:
            expected_livemode = key_livemode
        if not isinstance(expected_livemode, bool):
            raise ValueError("expected_livemode must be boolean.")
        if expected_livemode is not key_livemode:
            raise ValueError("Stripe key mode and expected livemode must match.")
        self._expected_livemode = expected_livemode
        self._payment_method_configuration = (
            _require_opaque_ref(
                payment_method_configuration, "payment_method_configuration"
            )
            if payment_method_configuration
            else None
        )
        self._client_instance: Any | None = None

    @classmethod
    def from_environment(
        cls,
        *,
        production: bool | None = None,
    ) -> "StripePaymentDriver":
        """Build a driver only when the complete environment contract is coherent.

        Production is deliberately live-only and rejects loopback return URLs.  A
        development/test process is test-mode-only, preventing accidental real charges
        while running a local demo.  Callers may pass ``production`` explicitly; the
        default follows the same ``APP_ENV`` vocabulary as ``settings.py``.
        """

        if production is None:
            app_env = (os.environ.get("APP_ENV") or "production").strip().casefold()
            production = app_env not in _DEV_APP_ENVS
        if not isinstance(production, bool):
            raise TypeError("production must be boolean.")
        configured_version = (
            os.environ.get("STRIPE_API_VERSION") or STRIPE_API_VERSION
        ).strip()
        if configured_version != STRIPE_API_VERSION:
            raise ValueError("Unsupported STRIPE_API_VERSION.")
        raw_livemode = (os.environ.get("STRIPE_EXPECTED_LIVEMODE") or "").strip().casefold()
        if raw_livemode not in {"true", "false"}:
            raise ValueError("STRIPE_EXPECTED_LIVEMODE must be explicitly true or false.")
        expected_livemode = raw_livemode == "true"
        if production is not expected_livemode:
            raise ValueError(
                "Production requires Stripe live mode; development/test requires Stripe test mode."
            )
        return cls(
            api_key=os.environ.get("STRIPE_RESTRICTED_KEY", ""),
            webhook_secret=os.environ.get("STRIPE_WEBHOOK_SECRET", ""),
            public_app_url=os.environ.get("PUBLIC_APP_URL", ""),
            expected_livemode=expected_livemode,
            payment_method_configuration=(
                os.environ.get("STRIPE_PAYMENT_METHOD_CONFIGURATION") or None
            ),
            allow_loopback_http=not production,
        )

    def _client(self) -> Any:
        if self._client_instance is None:
            stripe = _load_stripe()
            self._client_instance = stripe.StripeClient(
                self._api_key,
                max_network_retries=STRIPE_NETWORK_RETRIES,
            )
        return self._client_instance

    @staticmethod
    def _options(idempotency_key: str | None = None) -> dict[str, Any]:
        options: dict[str, Any] = {"stripe_version": STRIPE_API_VERSION}
        if idempotency_key is not None:
            options["idempotency_key"] = idempotency_key
        return options

    def create_checkout_session(
        self,
        *,
        payment_ref: str,
        reservation_ref: str,
        reservation_revision: int,
        policy_version: str,
        amount_minor: int,
        kind: CheckoutKind,
        attempt_ref: str,
        expires_at: int | None = None,
    ) -> Any:
        payment_ref = _require_opaque_ref(payment_ref, "payment_ref")
        reservation_ref = _require_opaque_ref(reservation_ref, "reservation_ref")
        policy_version = _require_opaque_ref(policy_version, "policy_version")
        _require_opaque_ref(attempt_ref, "attempt_ref")
        amount_minor = _require_amount_minor(amount_minor)
        if (
            isinstance(reservation_revision, bool)
            or not isinstance(reservation_revision, int)
            or reservation_revision < 0
        ):
            raise ValueError("reservation_revision must be a non-negative integer.")
        if kind not in {"deposit", "preauthorization"}:
            raise ValueError("Unsupported checkout kind.")
        if expires_at is not None and (
            isinstance(expires_at, bool)
            or not isinstance(expires_at, int)
            or expires_at <= 0
        ):
            raise ValueError("expires_at must be an epoch timestamp.")

        metadata = {
            "lokalo_payment_ref": payment_ref,
            "lokalo_reservation_ref": reservation_ref,
            "lokalo_reservation_revision": str(reservation_revision),
            "lokalo_policy_version": policy_version,
            "lokalo_payment_kind": kind,
        }
        success_url, cancel_url = checkout_return_urls(self._public_app_url)
        params: dict[str, Any] = {
            "ui_mode": "hosted",
            "mode": "payment",
            "locale": "pl",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "client_reference_id": payment_ref,
            "line_items": [
                {
                    "price_data": {
                        "currency": "pln",
                        "unit_amount": amount_minor,
                        "product_data": {
                            "name": (
                                "Zadatek za rezerwacje"
                                if kind == "deposit"
                                else "Preautoryzacja rezerwacji"
                            )
                        },
                    },
                    "quantity": 1,
                }
            ],
            "metadata": metadata,
            "payment_intent_data": {
                "capture_method": (
                    "automatic_async" if kind == "deposit" else "manual"
                ),
                "metadata": metadata,
            },
        }
        if expires_at is not None:
            params["expires_at"] = expires_at
        if self._payment_method_configuration is not None:
            params["payment_method_configuration"] = (
                self._payment_method_configuration
            )

        # Brak payment_method_types jest celowy: Stripe dobiera metody dynamicznie.
        return self._client().v1.checkout.sessions.create(
            params,
            options=self._options(
                stable_idempotency_key("checkout", attempt_ref)
            ),
        )

    def retrieve_checkout_session(self, session_id: str) -> Any:
        session_id = _require_provider_id(session_id, "session_id", "cs_")
        return self._client().v1.checkout.sessions.retrieve(
            session_id,
            {"expand": ["payment_intent.latest_charge"]},
            options=self._options(),
        )

    def expire_checkout_session(
        self, session_id: str, *, operation_ref: str
    ) -> Any:
        session_id = _require_provider_id(session_id, "session_id", "cs_")
        return self._client().v1.checkout.sessions.expire(
            session_id,
            {},
            options=self._options(
                stable_idempotency_key("expire", operation_ref)
            ),
        )

    def retrieve_payment_intent(self, payment_intent_id: str) -> Any:
        payment_intent_id = _require_provider_id(
            payment_intent_id, "payment_intent_id", "pi_"
        )
        return self._client().v1.payment_intents.retrieve(
            payment_intent_id,
            {"expand": ["latest_charge"]},
            options=self._options(),
        )

    def capture_payment_intent(
        self,
        payment_intent_id: str,
        *,
        operation_ref: str,
        amount_minor: int | None = None,
    ) -> Any:
        payment_intent_id = _require_provider_id(
            payment_intent_id, "payment_intent_id", "pi_"
        )
        params: dict[str, Any] = {}
        if amount_minor is not None:
            params["amount_to_capture"] = _require_amount_minor(
                amount_minor, "amount_minor"
            )
        return self._client().v1.payment_intents.capture(
            payment_intent_id,
            params,
            options=self._options(
                stable_idempotency_key("capture", operation_ref)
            ),
        )

    def cancel_payment_intent(
        self,
        payment_intent_id: str,
        *,
        operation_ref: str,
        reason: str = "abandoned",
    ) -> Any:
        payment_intent_id = _require_provider_id(
            payment_intent_id, "payment_intent_id", "pi_"
        )
        if reason not in _CANCEL_REASONS:
            raise ValueError("Unsupported PaymentIntent cancellation reason.")
        return self._client().v1.payment_intents.cancel(
            payment_intent_id,
            {"cancellation_reason": reason},
            options=self._options(
                stable_idempotency_key("cancel", operation_ref)
            ),
        )

    def create_full_refund(
        self,
        payment_intent_id: str,
        *,
        payment_ref: str,
        operation_ref: str,
        reason: str = "requested_by_customer",
    ) -> Any:
        payment_intent_id = _require_provider_id(
            payment_intent_id, "payment_intent_id", "pi_"
        )
        payment_ref = _require_opaque_ref(payment_ref, "payment_ref")
        if reason not in _REFUND_REASONS:
            raise ValueError("Unsupported refund reason.")
        params = {
            "payment_intent": payment_intent_id,
            "reason": reason,
            "metadata": {
                "lokalo_payment_ref": payment_ref,
                "lokalo_refund_operation_ref": _require_opaque_ref(
                    operation_ref, "operation_ref"
                ),
            },
        }
        # Brak amount jest celowy: pierwszy zakres R5c obsluguje pelny zwrot.
        return self._client().v1.refunds.create(
            params,
            options=self._options(
                stable_idempotency_key("refund", operation_ref)
            ),
        )

    def retrieve_refund(self, refund_id: str) -> Any:
        refund_id = _require_provider_id(refund_id, "refund_id", "re_")
        return self._client().v1.refunds.retrieve(
            refund_id,
            options=self._options(),
        )

    def construct_webhook_event(
        self, raw_body: bytes, stripe_signature: str
    ) -> Any:
        return construct_webhook_event(
            raw_body,
            stripe_signature,
            self._webhook_secret,
            expected_livemode=self._expected_livemode,
        )
