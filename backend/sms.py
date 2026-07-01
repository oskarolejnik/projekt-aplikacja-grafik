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
import logging
import os
import re
import urllib.request

import integracje

logger = logging.getLogger(__name__)


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


def _wyslij_http(url: str, token: str, numer: str, tresc: str, sender: str) -> bool:
    payload = json.dumps({"to": numer, "message": tresc, "from": sender or None}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return 200 <= resp.status < 300


def wyslij_sms(numer: str, tresc: str) -> bool:
    """Wysyła SMS. True przy sukcesie; False gdy integracja off / brak numeru / błąd (bez rzucania)."""
    numer = _normalizuj_numer(numer)
    if not numer or not integracje.skonfigurowane("sms"):
        return False
    url = (os.environ.get("SMS_API_URL") or "").strip()
    token = (os.environ.get("SMS_API_TOKEN") or "").strip()
    sender = (os.environ.get("SMS_SENDER") or "").strip()
    if not url:
        return False
    try:
        return _wyslij_http(url, token, numer, tresc, sender)
    except Exception as e:  # noqa: BLE001 — SMS nigdy nie wywraca żądania
        logger.warning("Błąd wysyłki SMS: %s", e)
        return False
