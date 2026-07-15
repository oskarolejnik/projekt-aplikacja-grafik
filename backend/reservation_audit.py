"""Atomowy i pozbawiony PII audyt mutacji rezerwacji.

Moduł nie zarządza transakcją. :func:`add_reservation_audit` wykonuje wyłącznie
``Session.add``; commit albo rollback należy zawsze do operacji rezerwacji, dzięki czemu
projekcja ``Termin``, ledger, idempotencja i audyt mają jeden wynik transakcyjny.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from datetime import date, datetime, time, timezone
from typing import Any

import models


AUDIT_ACTIONS = frozenset({
    "create", "edit", "cancel", "delete", "status", "host", "assign", "override",
})
ACTOR_KINDS = frozenset({"user", "guest", "system", "migration"})
AUDIT_REASONS = frozenset({
    "guest_request",
    "operator_correction",
    "capacity_override",
    "pacing_override",
    "table_override",
    "system_automation",
    "import_reconciliation",
    "other",
})

# Jedyna zawartość rezerwacji, którą wolno utrwalić w diffie. W szczególności nie ma
# tu nazwiska, telefonu, e-maila, notatki, tokenów ani identyfikatora zewnętrznego.
AUDITABLE_FIELDS = (
    "data",
    "godz_od",
    "godz_do",
    "liczba_osob",
    "status",
    "stolik_id",
    "stoliki_dodatkowe",
    "auto_przydzielony",
    "przydzial_wersja_planu_id",
    "przydzial_kombinacja_planu_id",
    "kanal",
    "faza_hosta",
)
PII_FIELDS = frozenset({
    "nazwisko",
    "telefon",
    "email",
    "notatka",
    "token_potwierdzenia",
    "source_external_id",
})

_TOKEN_FIELDS = frozenset({"status", "kanal", "faza_hosta"})
_SAFE_TOKEN = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,31}$")
_PACING_OVERRIDE_RULES = frozenset({"pacing_reservations", "pacing_covers"})
_MISSING = object()


def _value(source: Any, field: str) -> Any:
    if source is None:
        return _MISSING
    if isinstance(source, Mapping):
        return source[field] if field in source else _MISSING
    return getattr(source, field, _MISSING)


def _normalise_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("invalid auditable date") from exc
    if not isinstance(value, date):
        raise ValueError("invalid auditable date")
    return value.isoformat()


def _normalise_time(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = time.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("invalid auditable time") from exc
    if not isinstance(value, time) or value.tzinfo is not None:
        raise ValueError("invalid auditable time")
    return value.isoformat(timespec="seconds")


def _normalise_integer(value: Any, *, positive: bool = False) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("invalid auditable integer")
    if value < (1 if positive else 0):
        raise ValueError("invalid auditable integer")
    return value


def _normalise(field: str, value: Any) -> Any:
    if field == "data":
        return _normalise_date(value)
    if field in {"godz_od", "godz_do"}:
        return _normalise_time(value)
    if field == "liczba_osob":
        return _normalise_integer(value)
    if field in {
        "stolik_id",
        "przydzial_wersja_planu_id",
        "przydzial_kombinacja_planu_id",
    }:
        return _normalise_integer(value, positive=True)
    if field == "stoliki_dodatkowe":
        if value is None:
            return None
        if not isinstance(value, (list, tuple)):
            raise ValueError("invalid auditable table list")
        result = []
        for item in value:
            table_id = _normalise_integer(item, positive=True)
            if table_id is None:
                raise ValueError("invalid auditable table list")
            result.append(table_id)
        return result
    if field == "auto_przydzielony":
        if value is not None and type(value) is not bool:
            raise ValueError("invalid auditable boolean")
        return value
    if field in _TOKEN_FIELDS:
        if value is None:
            return None
        if not isinstance(value, str) or not _SAFE_TOKEN.fullmatch(value):
            raise ValueError(f"invalid auditable token field: {field}")
        return value
    raise ValueError(f"unsupported auditable field: {field}")


def reservation_snapshot(source: Any) -> dict[str, Any]:
    """Zwraca wyłącznie bezpieczny stan operacyjny modelu lub mapy wejściowej."""
    snapshot: dict[str, Any] = {}
    for field in AUDITABLE_FIELDS:
        value = _value(source, field)
        if value is not _MISSING:
            snapshot[field] = _normalise(field, value)
    return snapshot


def build_reservation_diff(
    before: Any = None,
    after: Any = None,
    *,
    pii_changed: Iterable[str] = (),
) -> dict[str, Any]:
    """Buduje deterministyczny diff bez wartości PII.

    Nazwy zmienionych pól PII można odnotować jawnie, ale ich stare ani nowe wartości
    nigdy nie są pobierane z ``before``/``after`` i nie trafiają do wyniku.
    """
    before_state = reservation_snapshot(before)
    after_state = reservation_snapshot(after)
    changes: dict[str, dict[str, Any]] = {}
    for field in AUDITABLE_FIELDS:
        if field not in before_state and field not in after_state:
            continue
        old = before_state.get(field)
        new = after_state.get(field)
        if old != new:
            changes[field] = {"before": old, "after": new}

    pii_names = set(pii_changed)
    unknown = pii_names - PII_FIELDS
    if unknown:
        raise ValueError(f"unsupported PII field names: {', '.join(sorted(unknown))}")
    result: dict[str, Any] = {"changes": changes}
    if pii_names:
        result["pii_changed"] = sorted(pii_names)
    return result


def _normalise_override_details(details: Mapping[str, Any]) -> dict[str, Any]:
    """Waliduje metadane override tak, by nie dało się przemycić dowolnego tekstu/PII."""
    if not isinstance(details, Mapping) or set(details) != {"violations"}:
        raise ValueError("invalid override audit details")
    raw_violations = details["violations"]
    if not isinstance(raw_violations, (list, tuple)) or not raw_violations:
        raise ValueError("invalid override audit details")
    violations: list[dict[str, Any]] = []
    for item in raw_violations:
        if not isinstance(item, Mapping) or set(item) != {
            "rule", "observed", "limit", "projected",
        }:
            raise ValueError("invalid override audit details")
        rule = item["rule"]
        if rule not in _PACING_OVERRIDE_RULES:
            raise ValueError("invalid override audit rule")
        values = {key: item[key] for key in ("observed", "limit", "projected")}
        if any(isinstance(value, bool) or not isinstance(value, int) for value in values.values()):
            raise ValueError("invalid override audit values")
        if values["observed"] < 0 or values["limit"] <= 0:
            raise ValueError("invalid override audit values")
        if values["projected"] <= values["limit"]:
            raise ValueError("override audit must describe a real limit breach")
        violations.append({"rule": rule, **values})
    return {"violations": sorted(violations, key=lambda item: item["rule"])}


def reservation_reference(termin: models.Termin) -> str:
    """Stabilny, nieodwracalny identyfikator historii, także po usunięciu ``Termin``."""
    termin_id = getattr(termin, "id", None)
    if isinstance(termin_id, bool) or not isinstance(termin_id, int) or termin_id <= 0:
        raise ValueError("reservation must be flushed before auditing")
    created_at = getattr(termin, "utworzono_at", None)
    if created_at is None:
        stamp = "legacy"
    elif isinstance(created_at, datetime):
        if created_at.tzinfo is not None:
            created_at = created_at.astimezone(timezone.utc).replace(tzinfo=None)
        stamp = created_at.isoformat(timespec="microseconds")
    else:
        raise ValueError("invalid reservation creation timestamp")
    return hashlib.sha256(f"termin:{termin_id}\0{stamp}".encode("utf-8")).hexdigest()


def _utc_naive(value: datetime | None) -> datetime:
    value = value or datetime.now(timezone.utc)
    if not isinstance(value, datetime):
        raise ValueError("invalid audit timestamp")
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def add_reservation_audit(
    db,
    *,
    termin: models.Termin,
    action: str,
    actor: models.User | None = None,
    actor_kind: str = "user",
    reason: str | None = None,
    before: Any = None,
    after: Any = None,
    pii_changed: Iterable[str] = (),
    override_details: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> models.ReservationAudit | None:
    """Dodaje audyt do bieżącej transakcji; nie wykonuje flush/commit/rollback."""
    if action not in AUDIT_ACTIONS:
        raise ValueError("unsupported reservation audit action")
    if actor_kind not in ACTOR_KINDS:
        raise ValueError("unsupported reservation audit actor kind")
    if reason is not None and reason not in AUDIT_REASONS:
        raise ValueError("unsupported reservation audit reason")
    if action == "override" and reason is None:
        raise ValueError("override audit requires a reason")
    if override_details is not None and action != "override":
        raise ValueError("override details require override action")

    actor_user_id = None
    actor_login = None
    if actor_kind == "user":
        actor_user_id = getattr(actor, "id", None)
        actor_login = getattr(actor, "login", None)
        if (
            isinstance(actor_user_id, bool)
            or not isinstance(actor_user_id, int)
            or actor_user_id <= 0
            or not isinstance(actor_login, str)
            or not actor_login.strip()
            or len(actor_login) > 64
        ):
            raise ValueError("user actor must be a persisted named account")
    elif actor is not None:
        raise ValueError("non-user audit cannot carry a user actor")

    diff = build_reservation_diff(before, after, pii_changed=pii_changed)
    if override_details is not None:
        diff["override"] = _normalise_override_details(override_details)
    if action in {"edit", "status", "host", "assign"} and not (
        diff["changes"] or diff.get("pii_changed")
    ):
        return None

    record = models.ReservationAudit(
        created_at=_utc_naive(now),
        reservation_ref=reservation_reference(termin),
        termin_id=termin.id,
        actor_kind=actor_kind,
        actor_user_id=actor_user_id,
        actor_login=actor_login,
        action=action,
        reason=reason,
        diff=diff,
    )
    db.add(record)
    return record
