"""Kanoniczne nazwy obiektów konfiguracyjnych modułu rezerwacji."""

from __future__ import annotations

import unicodedata


def normalize_room_name(value: str) -> str:
    """Normalizuje zapis do wyświetlenia bez zmiany znaczenia nazwy."""
    return " ".join(unicodedata.normalize("NFKC", value).split())


def room_name_key(value: str) -> str:
    """Stabilny, Unicode-safe klucz unikalności nazwy sali."""
    return normalize_room_name(value).casefold()
