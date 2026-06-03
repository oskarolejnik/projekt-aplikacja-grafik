"""Walidacja danych rejestracji.

Reguły (interpretacja wymagań):
  - LOGIN: min. 5 znaków, wyłącznie ASCII alfanumeryczne [A-Za-z0-9]
           (brak spacji, polskich liter i znaków specjalnych -> brak problemów z kodowaniem).
  - HASŁO: min. 8 znaków, >=1 litera, >=1 cyfra, >=1 znak specjalny,
           wyłącznie drukowalne znaki ASCII (33-126) -> bez spacji i Unicode.

Walidatory zgłaszają HTTPException(400) z czytelnym komunikatem, więc nadają się
zarówno do endpointów FastAPI, jak i do skryptu CLI (tam komunikat jest łapany).
"""

import re

from fastapi import HTTPException

_LOGIN_RE = re.compile(r"^[A-Za-z0-9]{5,}$")
# Znak specjalny = drukowalny ASCII spoza liter/cyfr (zakresy interpunkcji).
_SPECIAL_RE = re.compile(r"[!-/:-@\[-`{-~]")


def sprawdz_login(login: str) -> str:
    login = (login or "").strip()
    if len(login) < 5:
        raise HTTPException(400, "Login musi mieć co najmniej 5 znaków.")
    if not _LOGIN_RE.match(login):
        raise HTTPException(
            400,
            "Login może zawierać wyłącznie litery i cyfry (bez spacji, polskich znaków i znaków specjalnych).",
        )
    return login


def sprawdz_haslo(haslo: str) -> None:
    if not isinstance(haslo, str) or len(haslo) < 8:
        raise HTTPException(400, "Hasło musi mieć co najmniej 8 znaków.")
    if any(ord(c) < 33 or ord(c) > 126 for c in haslo):
        raise HTTPException(
            400,
            "Hasło może zawierać tylko drukowalne znaki ASCII (bez spacji i polskich liter).",
        )
    if not re.search(r"[A-Za-z]", haslo):
        raise HTTPException(400, "Hasło musi zawierać co najmniej jedną literę.")
    if not re.search(r"\d", haslo):
        raise HTTPException(400, "Hasło musi zawierać co najmniej jedną cyfrę.")
    if not _SPECIAL_RE.search(haslo):
        raise HTTPException(400, "Hasło musi zawierać co najmniej jeden znak specjalny (np. ! @ # $ %).")
