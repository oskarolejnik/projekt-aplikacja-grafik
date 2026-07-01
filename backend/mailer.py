"""Wysyłka e-mail (SMTP) — best-effort.

Integracja „email" konfigurowana zmiennymi SMTP_* (patrz integracje.py). Gdy integracja
nieskonfigurowana lub wystąpi błąd → zwraca False (no-op) i NIE rzuca wyjątku — nie wolno
wywrócić żądania (np. utworzenia rezerwacji) z powodu problemu z pocztą.

Zmienne: SMTP_HOST, SMTP_PORT (domyślnie 587), SMTP_USER, SMTP_PASSWORD, SMTP_FROM (opc.).
"""

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

import integracje

logger = logging.getLogger(__name__)


def wyslij_email(do: str, temat: str, tresc: str) -> bool:
    """Wysyła e-mail. Zwraca True przy sukcesie, False gdy integracja off / brak adresu / błąd."""
    if not do or not integracje.skonfigurowane("email"):
        return False
    host = (os.environ.get("SMTP_HOST") or "").strip()
    port = int(os.environ.get("SMTP_PORT") or 587)
    user = os.environ.get("SMTP_USER") or ""
    haslo = os.environ.get("SMTP_PASSWORD") or ""
    nadawca = os.environ.get("SMTP_FROM") or user
    try:
        msg = EmailMessage()
        msg["From"] = nadawca
        msg["To"] = do
        msg["Subject"] = temat
        msg.set_content(tresc)
        with smtplib.SMTP(host, port, timeout=10) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(user, haslo)
            s.send_message(msg)
        return True
    except Exception as e:  # noqa: BLE001 — poczta nigdy nie wywraca żądania
        logger.warning("Błąd wysyłki e-mail: %s", e)
        return False
