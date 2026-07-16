"""Wysyłka SMS przez generyczną bramkę HTTP — best-effort (wzór jak mailer.py).

Konfiguracja przez .env (integracja "sms" w integracje.py):
  SMS_API_URL    – endpoint bramki (POST JSON),
  SMS_API_TOKEN  – token (nagłówek Authorization: Bearer),
  SMS_SENDER     – opcjonalny nadawca (nazwa/numer).

Bramka GENERYCZNA (nie konkretny vendor): wysyła POST JSON {"to","message","from"}.
Dla wybranej bramki (np. SMSAPI, Twilio) dostosuj payload/nagłówki w `_wyslij_http`.

Gdy integracja wyłączona / brak numeru / błąd → zwraca False (no-op) i NIGDY nie rzuca —
SMS nie może wywrócić żądania (np. utworzenia rezerwacji).
"""

from __future__ import annotations

import json
import ipaddress
import os
import re
import urllib.error
import urllib.request
from urllib.parse import urlsplit

import integracje
import settings as app_settings
from delivery_result import DeliveryResult

_TRUE_VALUES = frozenset({"1", "true", "yes", "on", "tak"})
_HTTP_HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_E164 = re.compile(r"^\+[1-9]\d{7,14}$")
SMS_IDEMPOTENCY_HEADER = "Idempotency-Key"


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Never forward the bearer token or message body to a redirect target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open_no_redirect(request, *, timeout: int = 10):
    opener = urllib.request.build_opener(_NoRedirectHandler())
    return opener.open(request, timeout=timeout)


def _validated_api_url(value: str) -> str | None:
    """Accept HTTPS, plus explicit loopback HTTP in development/test only."""
    try:
        parsed = urlsplit(value)
        _ = parsed.port  # validates the optional port eagerly
    except (TypeError, ValueError):
        return None
    if (
        not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        return None
    if parsed.scheme.casefold() == "https":
        return value
    if parsed.scheme.casefold() != "http" or not app_settings.IS_DEV:
        return None
    hostname = parsed.hostname.casefold()
    if hostname == "localhost":
        return value
    try:
        return value if ipaddress.ip_address(hostname).is_loopback else None
    except ValueError:
        return None


def provider_supports_idempotency() -> bool:
    """Czy skonfigurowana bramka honoruje klucz idempotencji HTTP."""
    return (os.environ.get("SMS_SUPPORTS_IDEMPOTENCY") or "").strip().casefold() in _TRUE_VALUES


def provider_idempotency_header() -> str | None:
    """Zwraca zweryfikowaną nazwę nagłówka, którą można zamrozić w outboxie."""
    header = (
        os.environ.get("SMS_IDEMPOTENCY_HEADER") or SMS_IDEMPOTENCY_HEADER
    ).strip()
    return header if 1 <= len(header) <= 128 and _HTTP_HEADER_NAME.fullmatch(header) else None


def _normalizuj_numer(numer: str) -> str:
    """Numer telefonu → E.164 (best-effort, domyślnie PL +48). '' dla pustego/niepoprawnego."""
    if not numer:
        return ""
    n = re.sub(r"[\s\-()]", "", str(numer))
    if n.startswith("+"):
        return n
    if n.startswith("00"):
        return "+" + n[2:]
    if n.startswith("0"):
        n = n[1:]
    if n.isdigit() and len(n) == 9:      # krajowy PL bez prefiksu
        return "+48" + n
    return "+" + n if n.isdigit() else ""


def _wyslij_http_status(
    url: str,
    token: str,
    numer: str,
    tresc: str,
    sender: str,
    *,
    idempotency_key: str | None = None,
    idempotency_header: str | None = None,
) -> int:
    payload = json.dumps({"to": numer, "message": tresc, "from": sender or None}).encode("utf-8")
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    if idempotency_key and idempotency_header:
        headers[idempotency_header] = idempotency_key
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers=headers,
    )
    with _open_no_redirect(req, timeout=10) as resp:
        return int(resp.status)


def _wyslij_http(url: str, token: str, numer: str, tresc: str, sender: str) -> bool:
    """Historyczny helper pozostaje kompatybilny dla lokalnych integracji."""
    return 200 <= _wyslij_http_status(url, token, numer, tresc, sender) < 300


def _wynik_statusu_http(status: int, *, safe_to_retry: bool) -> DeliveryResult:
    if 200 <= status < 300:
        return DeliveryResult("sent", "sms_accepted", status_code=status)
    if status in {408, 429} or 500 <= status < 600:
        code = "sms_rate_limited" if status == 429 else (
            "sms_request_timeout" if status == 408 else "sms_provider_unavailable"
        )
        return DeliveryResult(
            "retry" if safe_to_retry else "uncertain",
            code if safe_to_retry else "sms_delivery_uncertain",
            status_code=status,
        )
    if 400 <= status < 500:
        return DeliveryResult("failed", "sms_request_rejected", status_code=status)
    return DeliveryResult("failed", "sms_unexpected_status", status_code=status)


def dostarcz_sms(
    numer: str,
    tresc: str,
    idempotency_key: str | None = None,
    *,
    force_supports_idempotency: bool | None = None,
    force_idempotency_header: str | None = None,
) -> DeliveryResult:
    """Dostarcza SMS z jawną semantyką retry/uncertain dla workera outboxa."""
    numer = _normalizuj_numer(numer)
    if not numer or not _E164.fullmatch(numer):
        return DeliveryResult("failed", "invalid_recipient")
    if not isinstance(tresc, str) or not tresc.strip():
        return DeliveryResult("failed", "invalid_message")
    if not integracje.skonfigurowane("sms"):
        return DeliveryResult("failed", "sms_not_configured")

    url = _validated_api_url((os.environ.get("SMS_API_URL") or "").strip())
    token = (os.environ.get("SMS_API_TOKEN") or "").strip()
    sender = (os.environ.get("SMS_SENDER") or "").strip()
    if not url or not token:
        return DeliveryResult("failed", "invalid_configuration")

    supports_idempotency = (
        provider_supports_idempotency()
        if force_supports_idempotency is None
        else bool(force_supports_idempotency)
    )
    effective_key = idempotency_key.strip() if isinstance(idempotency_key, str) else ""
    idempotent_attempt = bool(supports_idempotency and effective_key)
    header_name = None
    if supports_idempotency:
        header_name = force_idempotency_header or provider_idempotency_header()
        if (
            not header_name
            or len(header_name) > 128
            or not _HTTP_HEADER_NAME.fullmatch(header_name)
        ):
            return DeliveryResult("failed", "invalid_configuration")

    try:
        status = _wyslij_http_status(
            url,
            token,
            numer,
            tresc,
            sender,
            idempotency_key=effective_key if idempotent_attempt else None,
            idempotency_header=header_name if idempotent_attempt else None,
        )
        return _wynik_statusu_http(status, safe_to_retry=idempotent_attempt)
    except urllib.error.HTTPError as exc:
        # Celowo nie czytamy body ani komunikatu wyjątku: mogą zawierać PII.
        try:
            status = int(exc.code)
        finally:
            exc.close()
        return _wynik_statusu_http(status, safe_to_retry=idempotent_attempt)
    except Exception:  # noqa: BLE001 - wynik sieci nie może wywrócić workera
        if idempotent_attempt:
            return DeliveryResult("retry", "sms_network_error")
        return DeliveryResult("uncertain", "sms_delivery_uncertain")


def wyslij_sms(numer: str, tresc: str) -> bool:
    """Wysyła SMS. True przy sukcesie; False gdy integracja off / brak numeru / błąd (bez rzucania)."""
    return dostarcz_sms(numer, tresc).outcome == "sent"
