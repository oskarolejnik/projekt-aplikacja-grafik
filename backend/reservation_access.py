"""Deklaratywna autoryzacja wewnętrznych tras modułu rezerwacji.

Polityka jest celowo dokładna: nie opiera się na tekstowym ``startswith`` dla
podobnie nazwanych endpointów i nie otwiera nowych tras automatycznie. Nieznana
trasa wewnątrz chronionej przestrzeni pozostaje dostępna wyłącznie adminowi.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

import uprawnienia


@dataclass(frozen=True)
class Requirement:
    all_of: tuple[str, ...] = ()
    any_of: tuple[str, ...] = ()
    admin_only: bool = False


ADMIN_ONLY = Requirement(admin_only=True)

OPERATIONS = "rezerwacje.operacje"
HOST = "rezerwacje.host"
FLOOR = "rezerwacje.sala"
RULES = "rezerwacje.reguly"
ANALYTICS = "rezerwacje.analityka"
CONTACT = "rezerwacje.dane_kontaktowe"


_RESERVATION_ITEM = re.compile(
    r"^/api/rezerwacje-stolik/(?P<id>[1-9]\d*)(?:/(?P<action>auto-przydziel|status|wyslij-potwierdzenie))?$"
)
_WAITLIST_ITEM = re.compile(
    r"^/api/lista-oczekujacych/(?P<id>[1-9]\d*)(?:/(?P<action>odwolaj|zrealizuj|powiadom|hold|zwolnij-hold))?$"
)
_CONFIG_ITEM = re.compile(
    r"^/api/(?P<resource>stoliki|kombinacje|sasiedztwo|godziny-otwarcia|wyjatki-kalendarza)/[1-9]\d*$"
)
_HOST_RESERVATION_ITEM = re.compile(
    r"^/api/host/rezerwacja/[1-9]\d*/(?P<action>faza|przydziel-stolik|posadz)$"
)

_PROTECTED_PREFIXES = (
    "/api/rezerwacje-stolik",
    "/api/lista-oczekujacych",
    "/api/host",
    "/api/stoliki",
    "/api/kombinacje",
    "/api/sasiedztwo",
    "/api/godziny-otwarcia",
    "/api/wyjatki-kalendarza",
    "/api/rezerwacje/config",
    "/api/plan-sali",
    "/api/analityka/rezerwacje",
    "/api/analityka/oblozenie",
)


def _chroniona_przestrzen(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix + "/") for prefix in _PROTECTED_PREFIXES)


def requirement_for(method: str, path: str) -> Requirement | None:
    """Zwraca wymagania albo ``None``, gdy trasa nie należy do tej polityki."""
    method = method.upper()

    if path == "/api/rezerwacje-stolik":
        if method == "GET":
            return Requirement(all_of=(OPERATIONS,))
        if method == "POST":
            return Requirement(all_of=(OPERATIONS, CONTACT))
        return ADMIN_ONLY

    if path == "/api/rezerwacje-stolik/wyszukaj":
        if method == "POST":
            return Requirement(all_of=(OPERATIONS, CONTACT))
        return ADMIN_ONLY

    match = _RESERVATION_ITEM.fullmatch(path)
    if match:
        action = match.group("action")
        if action is None and method == "GET":
            return Requirement(all_of=(OPERATIONS,))
        if action is None and method == "PUT":
            return Requirement(all_of=(OPERATIONS, CONTACT))
        if action == "auto-przydziel" and method == "POST":
            return Requirement(any_of=(OPERATIONS, HOST))
        if action == "status" and method == "POST":
            return Requirement(all_of=(OPERATIONS,))
        if action == "wyslij-potwierdzenie" and method == "POST":
            return Requirement(all_of=(OPERATIONS, CONTACT))
        # Twarde DELETE pozostaje admin-only. Operator anuluje wpis przez status.
        return ADMIN_ONLY

    if path == "/api/lista-oczekujacych":
        if method == "GET":
            return Requirement(any_of=(OPERATIONS, HOST))
        if method == "POST":
            return Requirement(all_of=(CONTACT,), any_of=(OPERATIONS, HOST))
        return ADMIN_ONLY

    match = _WAITLIST_ITEM.fullmatch(path)
    if match:
        action = match.group("action")
        if action == "odwolaj" and method == "POST":
            return Requirement(any_of=(OPERATIONS, HOST))
        if action in {"hold", "zwolnij-hold"} and method == "POST":
            return Requirement(any_of=(OPERATIONS, HOST))
        if action == "zrealizuj" and method == "POST":
            return Requirement(any_of=(OPERATIONS, HOST))
        if action == "powiadom" and method == "POST":
            return Requirement(all_of=(CONTACT,), any_of=(OPERATIONS, HOST))
        return ADMIN_ONLY

    if method == "GET" and path in {
        "/api/host/sugestia-stolika",
        "/api/host/kolejka",
        "/api/host/os-czasu",
    }:
        return Requirement(all_of=(HOST,))
    if method == "POST" and path == "/api/host/auto-no-show":
        return Requirement(all_of=(HOST,))
    if method == "POST" and _HOST_RESERVATION_ITEM.fullmatch(path):
        return Requirement(all_of=(HOST,))

    if path == "/api/rezerwacje/config":
        return Requirement(any_of=(OPERATIONS, HOST, FLOOR)) if method == "GET" else ADMIN_ONLY

    if path in {"/api/stoliki", "/api/kombinacje", "/api/sasiedztwo"}:
        if method == "GET":
            return Requirement(any_of=(OPERATIONS, HOST, FLOOR))
        if method == "POST":
            return Requirement(all_of=(FLOOR,))
        return ADMIN_ONLY

    if path in {"/api/godziny-otwarcia", "/api/wyjatki-kalendarza"}:
        if method == "GET":
            return Requirement(any_of=(OPERATIONS, HOST, RULES))
        if method == "POST":
            return Requirement(all_of=(RULES,))
        return ADMIN_ONLY

    match = _CONFIG_ITEM.fullmatch(path)
    if match:
        resource = match.group("resource")
        permission = RULES if resource in {"godziny-otwarcia", "wyjatki-kalendarza"} else FLOOR
        if method in {"PUT", "DELETE"}:
            return Requirement(all_of=(permission,))
        return ADMIN_ONLY

    if path == "/api/plan-sali":
        return Requirement(any_of=(HOST, FLOOR)) if method == "GET" else ADMIN_ONLY
    if path == "/api/plan-sali/pozycje":
        return Requirement(all_of=(FLOOR,)) if method == "PUT" else ADMIN_ONLY

    if path in {"/api/analityka/rezerwacje", "/api/analityka/oblozenie"}:
        return Requirement(all_of=(ANALYTICS,)) if method == "GET" else ADMIN_ONLY

    return ADMIN_ONLY if _chroniona_przestrzen(path) else None


def user_satisfies(user, requirement: Requirement) -> bool:
    """Sprawdza wymaganie na bieżących, efektywnych prawach konta."""
    if getattr(user, "rola", None) == "admin":
        return True
    if requirement.admin_only:
        return False
    if any(not uprawnienia.ma_user(user, permission) for permission in requirement.all_of):
        return False
    return not requirement.any_of or any(
        uprawnienia.ma_user(user, permission) for permission in requirement.any_of
    )
