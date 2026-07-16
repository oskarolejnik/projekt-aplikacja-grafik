"""Focused contract tests for the R5b e-mail and SMS provider adapters."""

from dataclasses import FrozenInstanceError
import smtplib
import urllib.error

import pytest

from delivery_result import DeliveryResult
import mailer
import sms


class FakeResponse:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeSMTP:
    login_error = None
    send_error = None
    exit_error = None
    sent_message = None

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if self.exit_error:
            raise self.exit_error
        return False

    def starttls(self, *args, **kwargs):
        return None

    def login(self, *args, **kwargs):
        if self.login_error:
            raise self.login_error

    def send_message(self, message):
        type(self).sent_message = message
        if self.send_error:
            raise self.send_error


def _smtp_config(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "sender@example.test")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.delenv("SMTP_FROM", raising=False)


def _sms_config(monkeypatch, *, idempotent=False):
    monkeypatch.setenv("SMS_API_URL", "https://sms.example.test/messages")
    monkeypatch.setenv("SMS_API_TOKEN", "secret")
    monkeypatch.setenv("SMS_SUPPORTS_IDEMPOTENCY", "true" if idempotent else "false")
    monkeypatch.delenv("SMS_IDEMPOTENCY_HEADER", raising=False)


def _request_headers(request):
    return {name.casefold(): value for name, value in request.header_items()}


def test_delivery_result_is_immutable():
    result = DeliveryResult("sent", "accepted", status_code=202)

    with pytest.raises(FrozenInstanceError):
        result.outcome = "failed"


def test_email_invalid_recipient_and_configuration_are_terminal(monkeypatch):
    _smtp_config(monkeypatch)
    assert mailer.dostarcz_email("not-an-email", "Subject", "Body") == DeliveryResult(
        "failed", "invalid_recipient",
    )

    monkeypatch.setenv("SMTP_PORT", "not-a-port")
    assert mailer.dostarcz_email("guest@example.test", "Subject", "Body") == DeliveryResult(
        "failed", "invalid_configuration",
    )


def test_email_success_keeps_smtp_non_idempotent(monkeypatch):
    _smtp_config(monkeypatch)
    FakeSMTP.sent_message = None
    FakeSMTP.login_error = None
    FakeSMTP.send_error = None
    FakeSMTP.exit_error = None
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)

    result = mailer.dostarcz_email(
        "guest@example.test", "Subject", "Body", idempotency_key="r5b-email-1",
    )

    assert result == DeliveryResult("sent", "smtp_accepted")
    assert FakeSMTP.sent_message["To"] == "guest@example.test"
    assert "Idempotency-Key" not in FakeSMTP.sent_message
    assert mailer.wyslij_email("guest@example.test", "Subject", "Body") is True


def test_email_error_before_send_is_retry(monkeypatch):
    _smtp_config(monkeypatch)

    def connection_failure(*args, **kwargs):
        raise OSError("recipient=guest@example.test")

    monkeypatch.setattr(mailer.smtplib, "SMTP", connection_failure)
    result = mailer.dostarcz_email("guest@example.test", "Subject", "Body")

    assert result == DeliveryResult("retry", "smtp_connection_error")
    assert "guest@example.test" not in result.code


def test_email_auth_and_smtp_response_codes_are_classified(monkeypatch):
    _smtp_config(monkeypatch)
    FakeSMTP.sent_message = None
    FakeSMTP.exit_error = None
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)

    FakeSMTP.login_error = smtplib.SMTPAuthenticationError(535, b"guest@example.test")
    FakeSMTP.send_error = None
    assert mailer.dostarcz_email("guest@example.test", "Subject", "Body") == DeliveryResult(
        "failed", "smtp_auth_failed", status_code=535,
    )

    FakeSMTP.login_error = None
    FakeSMTP.send_error = smtplib.SMTPDataError(451, b"guest@example.test")
    assert mailer.dostarcz_email("guest@example.test", "Subject", "Body") == DeliveryResult(
        "retry", "smtp_temporary_rejection", status_code=451,
    )

    FakeSMTP.send_error = smtplib.SMTPDataError(550, b"guest@example.test")
    assert mailer.dostarcz_email("guest@example.test", "Subject", "Body") == DeliveryResult(
        "failed", "smtp_permanent_rejection", status_code=550,
    )


def test_email_network_failure_during_send_is_uncertain(monkeypatch):
    _smtp_config(monkeypatch)
    FakeSMTP.login_error = None
    FakeSMTP.exit_error = None
    FakeSMTP.send_error = OSError("guest@example.test")
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)

    result = mailer.dostarcz_email("guest@example.test", "Subject", "Body")

    assert result == DeliveryResult("uncertain", "smtp_delivery_uncertain")
    assert "guest@example.test" not in result.code


def test_email_failure_after_acceptance_stays_sent(monkeypatch):
    _smtp_config(monkeypatch)
    FakeSMTP.login_error = None
    FakeSMTP.send_error = None
    FakeSMTP.exit_error = OSError("connection closed during quit")
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)

    assert mailer.dostarcz_email(
        "guest@example.test", "Subject", "Body",
    ) == DeliveryResult("sent", "smtp_accepted")
    FakeSMTP.exit_error = None


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (202, DeliveryResult("sent", "sms_accepted", status_code=202)),
        (400, DeliveryResult("failed", "sms_request_rejected", status_code=400)),
        (429, DeliveryResult("uncertain", "sms_delivery_uncertain", status_code=429)),
        (503, DeliveryResult("uncertain", "sms_delivery_uncertain", status_code=503)),
    ],
)
def test_sms_classifies_http_statuses(monkeypatch, status, expected):
    _sms_config(monkeypatch)
    monkeypatch.setattr(
        sms, "_open_no_redirect", lambda *args, **kwargs: FakeResponse(status),
    )

    assert sms.dostarcz_sms("600100200", "Reservation update") == expected


def test_sms_adds_default_idempotency_header_only_when_supported(monkeypatch):
    _sms_config(monkeypatch, idempotent=True)
    requests = []

    def capture(request, timeout=10):
        requests.append(request)
        return FakeResponse(200)

    monkeypatch.setattr(sms, "_open_no_redirect", capture)
    result = sms.dostarcz_sms(
        "600100200", "Reservation update", idempotency_key="r5b-sms-1",
    )

    assert result == DeliveryResult("sent", "sms_accepted", status_code=200)
    assert _request_headers(requests[0])["idempotency-key"] == "r5b-sms-1"

    monkeypatch.setenv("SMS_SUPPORTS_IDEMPOTENCY", "false")
    sms.dostarcz_sms("600100200", "Reservation update", idempotency_key="r5b-sms-2")
    assert "idempotency-key" not in _request_headers(requests[1])


def test_sms_uses_configured_idempotency_header(monkeypatch):
    _sms_config(monkeypatch, idempotent=True)
    monkeypatch.setenv("SMS_IDEMPOTENCY_HEADER", "X-Provider-Request-ID")
    captured = {}

    def capture(request, timeout=10):
        captured.update(_request_headers(request))
        return FakeResponse(200)

    monkeypatch.setattr(sms, "_open_no_redirect", capture)
    sms.dostarcz_sms("600100200", "Reservation update", idempotency_key="r5b-sms-3")

    assert captured["x-provider-request-id"] == "r5b-sms-3"


def test_sms_rejects_an_unsafe_idempotency_header_contract(monkeypatch):
    _sms_config(monkeypatch, idempotent=True)
    monkeypatch.setenv("SMS_IDEMPOTENCY_HEADER", "X" * 129)

    assert sms.provider_idempotency_header() is None
    assert sms.dostarcz_sms(
        "600100200", "Reservation update", idempotency_key="r5b-sms-invalid",
    ) == DeliveryResult("failed", "invalid_configuration")


@pytest.mark.parametrize(
    "api_url",
    [
        "http://sms.example.test/messages",
        "https://provider-user:provider-password@sms.example.test/messages",
    ],
)
def test_sms_rejects_unsafe_provider_urls_before_network_io(monkeypatch, api_url):
    _sms_config(monkeypatch)
    monkeypatch.setenv("SMS_API_URL", api_url)
    # Nawet tryb developerski nie zezwala na zwykĹ‚y HTTP poza loopbackiem.
    monkeypatch.setattr(sms.app_settings, "IS_DEV", True)
    opened = []
    monkeypatch.setattr(
        sms,
        "_open_no_redirect",
        lambda *args, **kwargs: opened.append((args, kwargs)),
    )

    assert sms.dostarcz_sms("600100200", "Reservation update") == DeliveryResult(
        "failed", "invalid_configuration",
    )
    assert opened == []


def test_sms_allows_loopback_http_only_in_development(monkeypatch):
    _sms_config(monkeypatch)
    monkeypatch.setenv("SMS_API_URL", "http://127.0.0.1:18080/messages")
    opened = []

    def capture(request, timeout=10):
        opened.append(request.full_url)
        return FakeResponse(202)

    monkeypatch.setattr(sms, "_open_no_redirect", capture)
    monkeypatch.setattr(sms.app_settings, "IS_DEV", False)
    assert sms.dostarcz_sms("600100200", "Reservation update") == DeliveryResult(
        "failed", "invalid_configuration",
    )
    assert opened == []

    monkeypatch.setattr(sms.app_settings, "IS_DEV", True)
    assert sms.dostarcz_sms("600100200", "Reservation update") == DeliveryResult(
        "sent", "sms_accepted", status_code=202,
    )
    assert opened == ["http://127.0.0.1:18080/messages"]


def test_sms_redirect_handler_never_forwards_request_credentials_or_body():
    request = sms.urllib.request.Request(
        "https://sms.example.test/messages",
        data=b'{"message":"private reservation body"}',
        method="POST",
        headers={"Authorization": "Bearer provider-secret"},
    )

    redirected = sms._NoRedirectHandler().redirect_request(
        request,
        None,
        302,
        "Found",
        {"Location": "https://attacker.example.test/collect"},
        "https://attacker.example.test/collect",
    )

    assert redirected is None


def test_sms_302_is_not_followed_or_sent_to_redirect_target(monkeypatch):
    _sms_config(monkeypatch)
    opened = []
    handlers = []

    class RedirectBody:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    body = RedirectBody()

    class RedirectingOpener:
        def open(self, request, timeout=10):
            opened.append(
                {
                    "url": request.full_url,
                    "authorization": request.get_header("Authorization"),
                }
            )
            raise urllib.error.HTTPError(
                request.full_url,
                302,
                "Found",
                {"Location": "https://attacker.example.test/collect"},
                body,
            )

    def fake_build_opener(handler):
        handlers.append(handler)
        return RedirectingOpener()

    monkeypatch.setattr(sms.urllib.request, "build_opener", fake_build_opener)

    result = sms.dostarcz_sms("600100200", "Reservation update")

    assert result == DeliveryResult("failed", "sms_unexpected_status", status_code=302)
    assert len(handlers) == 1
    assert isinstance(handlers[0], sms._NoRedirectHandler)
    assert opened == [
        {
            "url": "https://sms.example.test/messages",
            "authorization": "Bearer secret",
        }
    ]
    assert body.closed is True


def test_sms_network_result_depends_on_effective_idempotency(monkeypatch):
    _sms_config(monkeypatch, idempotent=True)

    def network_failure(*args, **kwargs):
        raise OSError("phone=+48600100200")

    monkeypatch.setattr(sms, "_open_no_redirect", network_failure)
    assert sms.dostarcz_sms(
        "600100200", "Reservation update", idempotency_key="r5b-sms-4",
    ) == DeliveryResult("retry", "sms_network_error")
    assert sms.dostarcz_sms(
        "600100200", "Reservation update",
    ) == DeliveryResult("uncertain", "sms_delivery_uncertain")

    monkeypatch.setenv("SMS_SUPPORTS_IDEMPOTENCY", "false")
    assert sms.dostarcz_sms(
        "600100200", "Reservation update", idempotency_key="ignored",
    ) == DeliveryResult("uncertain", "sms_delivery_uncertain")


def test_sms_http_error_is_classified_without_reading_body(monkeypatch):
    _sms_config(monkeypatch, idempotent=True)

    class PrivateBody:
        def read(self, *args, **kwargs):
            raise AssertionError("response body must not be read")

        def close(self):
            return None

    def rate_limited(*args, **kwargs):
        raise urllib.error.HTTPError(
            "https://sms.example.test/messages",
            429,
            "phone=+48600100200",
            {},
            PrivateBody(),
        )

    monkeypatch.setattr(sms, "_open_no_redirect", rate_limited)
    result = sms.dostarcz_sms(
        "600100200", "Reservation update", idempotency_key="r5b-sms-5",
    )

    assert result == DeliveryResult("retry", "sms_rate_limited", status_code=429)
    assert result.provider_message_id is None


def test_sms_invalid_recipient_and_wrapper(monkeypatch):
    _sms_config(monkeypatch)
    assert sms.dostarcz_sms("+abc", "Reservation update") == DeliveryResult(
        "failed", "invalid_recipient",
    )

    monkeypatch.setattr(
        sms, "_open_no_redirect", lambda *args, **kwargs: FakeResponse(200),
    )
    assert sms.wyslij_sms("600100200", "Reservation update") is True
