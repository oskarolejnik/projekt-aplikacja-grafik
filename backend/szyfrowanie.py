"""Szyfrowanie danych wrażliwych at-rest (RODO) — field-level, transparentne dla ORM.

Chroni dane osobowe (np. kontakt gościa rezerwacji) w spoczynku: w bazie leży szyfrogram,
a aplikacja operuje na jawnym tekście. Używa Fernet (AES-128-CBC + HMAC) z biblioteki
`cryptography`. Klucz pochodzi z sekretu `ENCRYPTION_KEY` (dowolny długi, losowy ciąg —
derywowany do klucza Fernet przez SHA-256).

Zasady bezpiecznego wdrożenia bez migracji danych:
  • BRAK ENCRYPTION_KEY → passthrough (jawny tekst). Ułatwia dev i nie psuje istniejących instalacji.
  • Szyfrogram ma prefiks `enc:v1:` — po nim rozpoznajemy, czy wartość szyfrować/odszyfrowywać.
  • Odczyt legacy jawnego tekstu (bez prefiksu) zwraca wartość bez zmian → stopniowa migracja:
    nowe/zmienione zapisy są szyfrowane, stare działają dalej i zostaną zaszyfrowane przy edycji.

UWAGA: Fernet jest niedeterministyczny (ten sam tekst → różne szyfrogramy), więc pól szyfrowanych
NIE wolno używać w zapytaniach equality/LIKE po stronie SQL — porównuj po odszyfrowaniu w Pythonie.
"""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.types import String, TypeDecorator

_PREFIX = "enc:v1:"
_cache: dict = {}          # raw klucz -> instancja Fernet (memoizacja)


def _fernet():
    """Zwraca Fernet dla bieżącego ENCRYPTION_KEY albo None (brak klucza = passthrough)."""
    raw = os.environ.get("ENCRYPTION_KEY", "").strip()
    if not raw:
        return None
    f = _cache.get(raw)
    if f is None:
        klucz = base64.urlsafe_b64encode(hashlib.sha256(raw.encode("utf-8")).digest())
        f = Fernet(klucz)
        _cache[raw] = f
    return f


def aktywne() -> bool:
    """Czy szyfrowanie jest włączone (ustawiony ENCRYPTION_KEY)."""
    return _fernet() is not None


def szyfruj(tekst):
    """Jawny tekst → szyfrogram z prefiksem. None i już-zaszyfrowane zwraca bez zmian;
    bez klucza zwraca jawny tekst (passthrough)."""
    if tekst is None:
        return None
    if isinstance(tekst, str) and tekst.startswith(_PREFIX):
        return tekst
    f = _fernet()
    if f is None:
        return tekst
    token = f.encrypt(str(tekst).encode("utf-8")).decode("ascii")
    return _PREFIX + token


def odszyfruj(wartosc):
    """Szyfrogram (z prefiksem) → jawny tekst. Wartość bez prefiksu (legacy plaintext)
    albo brak klucza → zwraca bez zmian. Nieudane odszyfrowanie → zwraca jak jest (fallback)."""
    if not isinstance(wartosc, str) or not wartosc.startswith(_PREFIX):
        return wartosc
    f = _fernet()
    if f is None:
        return wartosc
    try:
        return f.decrypt(wartosc[len(_PREFIX):].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return wartosc


class EncryptedString(TypeDecorator):
    """Kolumna String szyfrowana at-rest. Zapis → szyfruj, odczyt → odszyfruj (transparentnie).
    Bez ENCRYPTION_KEY działa jak zwykły String (passthrough)."""
    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return szyfruj(value)

    def process_result_value(self, value, dialect):
        return odszyfruj(value)
