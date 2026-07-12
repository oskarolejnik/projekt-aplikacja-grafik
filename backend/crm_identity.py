"""Kanoniczna, wewnetrzna tozsamosc profilu goscia.

Klucz kontaktowy nigdy nie jest zwracany klientowi. Dla rezerwacji bez telefonu
i e-maila uzywamy zakresu pojedynczego rekordu, zamiast laczyc obce osoby po
nazwisku.
"""

from __future__ import annotations

import hashlib

from sms import _normalizuj_numer


def reservation_fallback_key(reservation_id) -> str:
    if isinstance(reservation_id, bool) or not isinstance(reservation_id, int):
        return ""
    if reservation_id <= 0:
        return ""
    return f"reservation:{reservation_id}"


def identity_parts(termin) -> tuple[str, dict]:
    """Zwraca wewnetrzny klucz i bezpieczny opis jakosci dopasowania."""
    telefon = _normalizuj_numer(getattr(termin, "telefon", None) or "")
    if telefon:
        return telefon, {"source": "telefon", "confident": True}
    email = (getattr(termin, "email", None) or "").strip().lower()
    if email:
        return email, {"source": "email", "confident": True}
    return reservation_fallback_key(getattr(termin, "id", None)), {
        "source": "reservation",
        "confident": False,
    }


def identity_key(termin) -> str:
    return identity_parts(termin)[0]


def hash_key(key: str) -> str:
    return hashlib.sha256((key or "").strip().encode("utf-8")).hexdigest()


def identity_hash(termin) -> str:
    return hash_key(identity_key(termin))


def reservation_fallback_hash(reservation_id) -> str | None:
    key = reservation_fallback_key(reservation_id)
    return hash_key(key) if key else None
