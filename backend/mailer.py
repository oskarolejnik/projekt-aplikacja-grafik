"""Wysyłka e-mail (SMTP) — best-effort.

Integracja „email" konfigurowana zmiennymi SMTP_* (patrz integracje.py). Gdy integracja
nieskonfigurowana lub wystąpi błąd → zwraca False (no-op) i NIE rzuca wyjątku — nie wolno
wywrócić żądania (np. utworzenia rezerwacji) z powodu problemu z pocztą.

Zmienne: SMTP_HOST, SMTP_PORT (domyślnie 587), SMTP_USER, SMTP_PASSWORD, SMTP_FROM (opc.).
"""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage

import integracje
from delivery_result import DeliveryResult


def _prawidlowy_adres(adres: str) -> bool:
    if not isinstance(adres, str):
        return False
    adres = adres.strip()
    if not adres or any(znak.isspace() for znak in adres):
        return False
    if adres.count("@") != 1 or "\r" in adres or "\n" in adres:
        return False
    lokalna, domena = adres.rsplit("@", 1)
    return bool(lokalna and domena and not domena.startswith("."))


def _wynik_bledu_smtp(exc: Exception, *, podczas_wysylki: bool) -> DeliveryResult:
    """Klasyfikuje SMTP bez kopiowania komunikatu wyjatku, ktory moze zawierac PII."""
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return DeliveryResult(
            "failed", "smtp_auth_failed", status_code=int(exc.smtp_code),
        )
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        # Nie utrwalamy adresow ani odpowiedzi serwera. Dla wielu odbiorcow wybieramy
        # najbezpieczniejszy wspolny wynik; ten adapter wysyla obecnie do jednego adresu.
        codes = [
            int(value[0])
            for value in exc.recipients.values()
            if isinstance(value, tuple) and value and str(value[0]).isdigit()
        ]
        status = codes[0] if len(set(codes)) == 1 and codes else None
        if codes and all(400 <= code < 500 for code in codes):
            return DeliveryResult("retry", "smtp_recipient_temporary", status_code=status)
        return DeliveryResult("failed", "smtp_recipient_rejected", status_code=status)
    if isinstance(exc, smtplib.SMTPResponseException):
        status = int(exc.smtp_code)
        if 400 <= status < 500:
            return DeliveryResult("retry", "smtp_temporary_rejection", status_code=status)
        if 500 <= status < 600:
            return DeliveryResult("failed", "smtp_permanent_rejection", status_code=status)
    if podczas_wysylki:
        return DeliveryResult("uncertain", "smtp_delivery_uncertain")
    return DeliveryResult("retry", "smtp_connection_error")


def dostarcz_email(
    do: str,
    temat: str,
    tresc: str,
    idempotency_key: str | None = None,
) -> DeliveryResult:
    """Dostarcza e-mail i zwraca wynik R5b; SMTP pozostaje nieidempotentny."""
    del idempotency_key  # SMTP nie oferuje klucza idempotencji.
    if not _prawidlowy_adres(do):
        return DeliveryResult("failed", "invalid_recipient")
    if not integracje.skonfigurowane("email"):
        return DeliveryResult("failed", "email_not_configured")

    host = (os.environ.get("SMTP_HOST") or "").strip()
    user = (os.environ.get("SMTP_USER") or "").strip()
    haslo = os.environ.get("SMTP_PASSWORD") or ""
    nadawca = (os.environ.get("SMTP_FROM") or user).strip()
    try:
        port = int(os.environ.get("SMTP_PORT") or 587)
    except (TypeError, ValueError):
        return DeliveryResult("failed", "invalid_configuration")
    if not host or not user or not haslo or not _prawidlowy_adres(nadawca) or not 1 <= port <= 65535:
        return DeliveryResult("failed", "invalid_configuration")

    try:
        msg = EmailMessage()
        msg["From"] = nadawca
        msg["To"] = do.strip()
        msg["Subject"] = temat
        msg.set_content(tresc)
    except Exception:  # noqa: BLE001 - nieprawidlowa tresc nie moze opuscic adaptera
        return DeliveryResult("failed", "invalid_message")

    etap = "connect"
    zaakceptowano = False
    try:
        with smtplib.SMTP(host, port, timeout=10) as s:
            etap = "starttls"
            s.starttls(context=ssl.create_default_context())
            etap = "login"
            s.login(user, haslo)
            etap = "send_message"
            s.send_message(msg)
            zaakceptowano = True
            etap = "accepted"
        return DeliveryResult("sent", "smtp_accepted")
    except Exception as exc:  # noqa: BLE001 - adapter zwraca kontrolowany wynik
        if zaakceptowano or etap == "accepted":
            return DeliveryResult("sent", "smtp_accepted")
        return _wynik_bledu_smtp(exc, podczas_wysylki=etap == "send_message")


def wyslij_email(do: str, temat: str, tresc: str) -> bool:
    """Kompatybilny wrapper: True wyłącznie po potwierdzeniu przyjęcia przez SMTP."""
    return dostarcz_email(do, temat, tresc).outcome == "sent"
