"""Atomowy ledger dostępności rezerwacji stolikowych (R0b).

Routery nadal odpowiadają za politykę kanału i kształt odpowiedzi HTTP. Ten moduł
jest jedynym miejscem, które zajmuje lub zwalnia fizyczne zasoby i pacing.
Każda mutacja musi najpierw wywołać :func:`begin_locked_write`, a następnie wykonać
co najwyżej jeden commit obejmujący ``Termin`` i jego ledger.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import and_, delete, func, insert, or_, select, text, update
from sqlalchemy.exc import IntegrityError, OperationalError

import models


ACTIVE_STATUSES = frozenset({"rezerwacja", "potwierdzona"})
LIVE_HOST_PHASES = frozenset({"posadzony", "rachunek", "oplacony"})
WAITLIST_ACTIVE_STATUSES = frozenset({"oczekuje", "zaoferowano"})
WAITLIST_TERMINAL_STATUSES = frozenset({"zaakceptowano", "wygasla", "anulowano"})
IDEMPOTENCY_TTL_DAYS = 30
PUBLIC_HOLD_SESSION_LIMIT = 2
PUBLIC_HOLD_IP_LIMIT = 10
PUBLIC_MANAGEMENT_TOKEN_TTL_DAYS = 30
PUBLIC_PRIVACY_NOTICE_VERSION = "reservation-privacy-2026-07-v1"


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def lifecycle_now_utc() -> datetime:
    """Current lifecycle instant in the repository's naive-UTC DB convention."""
    return _utcnow_naive()


def _lifecycle_utc_naive(value: datetime, *, field_name: str) -> datetime:
    """Normalise lifecycle instants to the database convention: naive UTC.

    Reservation dates and ``time`` values are local business wall time. Expiries are
    instants, however, and must never be compared as Europe/Warsaw wall time. Aware
    inputs are therefore converted to UTC; naive inputs are accepted as already UTC
    for compatibility with SQLite and the existing ``DateTime(timezone=False)`` schema.
    """
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is not None and value.utcoffset() is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.replace(tzinfo=None)


@dataclass(frozen=True)
class AvailabilityResult:
    available: bool
    code: str | None = None
    rule: str | None = None
    message: str | None = None
    candidates: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    alternatives: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    decision: str | None = None
    service: dict[str, Any] | None = None
    krok_slotu_min: int | None = None
    turn_time_min: int | None = None
    godz_do: str | None = None
    violations: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    checks: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    resource_allocation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "code": self.code,
            "rule": self.rule,
            "candidates": list(self.candidates),
            "alternatives": list(self.alternatives),
            "decision": self.decision,
            "service": self.service,
            "krok_slotu_min": self.krok_slotu_min,
            "turn_time_min": self.turn_time_min,
            "godz_do": self.godz_do,
            "violations": list(self.violations),
            "checks": list(self.checks),
            "resource_allocation": self.resource_allocation,
        }


class ReservationError(Exception):
    """Błąd domenowy z kompatybilnym komunikatem i stabilnym kodem maszynowym."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        rule: str | None = None,
        candidates: Sequence[Mapping[str, Any]] = (),
        alternatives: Sequence[Mapping[str, Any]] = (),
        decision: str | None = None,
        service: Mapping[str, Any] | None = None,
        krok_slotu_min: int | None = None,
        turn_time_min: int | None = None,
        godz_do: str | None = None,
        violations: Sequence[Mapping[str, Any]] = (),
        checks: Sequence[Mapping[str, Any]] = (),
        resource_allocation: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.availability = AvailabilityResult(
            available=False,
            code=code,
            rule=rule,
            message=message,
            candidates=tuple(dict(item) for item in candidates),
            alternatives=tuple(dict(item) for item in alternatives),
            decision=decision,
            service=dict(service) if service is not None else None,
            krok_slotu_min=krok_slotu_min,
            turn_time_min=turn_time_min,
            godz_do=godz_do,
            violations=tuple(dict(item) for item in violations),
            checks=tuple(dict(item) for item in checks),
            resource_allocation=resource_allocation,
        )


@dataclass(frozen=True)
class IdempotencyDecision:
    record: models.RezerwacjaIdempotencja | None
    replayed: bool = False
    response: dict[str, Any] | None = None
    http_status: int | None = None


@dataclass(frozen=True)
class IdempotencyIdentity:
    """Hash-only identity for domain-owned replay without a persisted response."""
    key_hash: str
    request_fingerprint: str


@dataclass(frozen=True)
class IssuedManagementToken:
    record: models.RezerwacjaTokenZarzadzania
    raw_token: str
    replayed: bool = False


@dataclass(frozen=True)
class IssuedPublicHold:
    record: models.RezerwacjaPublicznyHold
    raw_token: str
    replayed: bool = False


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    raise TypeError(f"unsupported canonical JSON type: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )


def request_fingerprint(operation: str, payload: Any, secret: str) -> str:
    body = canonical_json({"operation": operation, "payload": payload}).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _normalise_idempotency_key(raw_key: str | None) -> str | None:
    if raw_key is None:
        return None
    key = raw_key.strip()
    if not key:
        return None
    if len(key) > 128 or any(ord(char) < 33 or ord(char) > 126 for char in key):
        raise ReservationError(
            400,
            "INVALID_IDEMPOTENCY_KEY",
            "Klucz idempotencji musi mieć 1–128 drukowalnych znaków ASCII.",
            rule="idempotency",
        )
    return key


def required_idempotency_identity(
    *,
    operation: str,
    raw_key: str | None,
    payload: Any,
    secret: str,
) -> IdempotencyIdentity:
    """Validate a mandatory key and return only non-reversible hashes.

    Used by waitlist offers, whose replay is rebuilt from the current owner row
    under the current operator permissions. No PII response is persisted.
    """
    key = _normalise_idempotency_key(raw_key)
    if key is None:
        raise ReservationError(
            400,
            "IDEMPOTENCY_KEY_REQUIRED",
            "Operacja wymaga naglowka Idempotency-Key.",
            rule="idempotency",
        )
    operation = operation.strip()
    if not operation or len(operation) > 64:
        raise ValueError("idempotency operation must have 1-64 characters")
    return IdempotencyIdentity(
        key_hash=hashlib.sha256(key.encode("utf-8")).hexdigest(),
        request_fingerprint=request_fingerprint(operation, payload, secret),
    )


def begin_idempotency(
    db,
    *,
    operation: str,
    raw_key: str | None,
    payload: Any,
    secret: str,
    now: datetime,
) -> IdempotencyDecision:
    """Rejestruje próbę lub zwraca zaszyfrowany wynik wcześniejszego sukcesu.

    Wywołujący musi już posiadać blokadę dnia. W bazie trafia wyłącznie hash klucza
    i HMAC treści; PII z payloadu nie jest możliwe do odtworzenia z tych pól.
    """

    key = _normalise_idempotency_key(raw_key)
    if key is None:
        return IdempotencyDecision(record=None)
    operation = operation.strip()
    if not operation or len(operation) > 64:
        raise ValueError("idempotency operation must have 1-64 characters")
    key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
    fingerprint = request_fingerprint(operation, payload, secret)
    db.execute(
        delete(models.RezerwacjaIdempotencja).where(
            models.RezerwacjaIdempotencja.expires_at <= now,
        )
    )
    existing = db.execute(
        select(models.RezerwacjaIdempotencja).where(
            models.RezerwacjaIdempotencja.operation == operation,
            models.RezerwacjaIdempotencja.key_hash == key_hash,
        )
    ).scalar_one_or_none()
    if existing is not None:
        if not hmac.compare_digest(existing.request_fingerprint, fingerprint):
            raise ReservationError(
                409,
                "IDEMPOTENCY_KEY_REUSED",
                "Ten klucz idempotencji został już użyty z inną treścią żądania.",
                rule="idempotency",
            )
        if existing.status == "succeeded" and existing.response_enc:
            try:
                response = json.loads(existing.response_enc)
            except (TypeError, ValueError) as exc:
                raise ReservationError(
                    503,
                    "RESERVATION_BUSY",
                    "Zapisany wynik żądania jest chwilowo niedostępny. Spróbuj ponownie.",
                    rule="idempotency",
                ) from exc
            return IdempotencyDecision(
                record=existing,
                replayed=True,
                response=response,
                http_status=existing.http_status,
            )
        raise ReservationError(
            409,
            "IDEMPOTENCY_IN_PROGRESS",
            "Identyczne żądanie jest już przetwarzane. Spróbuj ponownie za chwilę.",
            rule="idempotency",
        )
    record = models.RezerwacjaIdempotencja(
        operation=operation,
        key_hash=key_hash,
        request_fingerprint=fingerprint,
        status="processing",
        created_at=now,
        expires_at=now + timedelta(days=IDEMPOTENCY_TTL_DAYS),
    )
    db.add(record)
    db.flush()
    return IdempotencyDecision(record=record)


def complete_idempotency(
    record: models.RezerwacjaIdempotencja | None,
    *,
    response: Mapping[str, Any],
    http_status: int,
    termin_id: int | None,
    now: datetime,
) -> None:
    if record is None:
        return
    record.status = "succeeded"
    record.http_status = int(http_status)
    record.response_enc = canonical_json(dict(response))
    record.termin_id = termin_id
    record.completed_at = now


def _public_value(value: str, *, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 512:
        raise ReservationError(
            400,
            "INVALID_PUBLIC_CREDENTIAL",
            f"{field_name} ma niepoprawny format.",
            rule="public_security",
        )
    return value


def hash_public_value(
    raw_value: str,
    *,
    secret: str,
    purpose: str,
    field_name: str = "Identyfikator",
) -> str:
    """Domain-separated HMAC for public tokens, sessions and client identifiers."""
    value = _public_value(raw_value, field_name=field_name)
    if not isinstance(secret, str) or not secret:
        raise ValueError("public credential hashing requires a non-empty secret")
    purpose = (purpose or "").strip()
    if not purpose or len(purpose) > 96:
        raise ValueError("public credential purpose must have 1-96 characters")
    message = f"lokalo:r5a:{purpose}\0{value}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def hash_management_token(raw_token: str, *, secret: str) -> str:
    return hash_public_value(
        raw_token,
        secret=secret,
        purpose="management-token",
        field_name="Token zarzadzania",
    )


def hash_public_hold_token(raw_token: str, *, secret: str) -> str:
    return hash_public_value(
        raw_token,
        secret=secret,
        purpose="public-hold-token",
        field_name="Token holdu",
    )


def hash_public_client(raw_client: str, *, secret: str, purpose: str) -> str:
    return hash_public_value(
        raw_client,
        secret=secret,
        purpose=purpose,
        field_name="Identyfikator klienta",
    )


def _normalise_scopes(scopes: Iterable[str]) -> tuple[str, ...]:
    values = []
    for raw_scope in scopes:
        scope = str(raw_scope or "").strip()
        if not scope or len(scope) > 64:
            raise ReservationError(
                400,
                "INVALID_MANAGEMENT_SCOPE",
                "Zakres tokenu zarzadzania ma niepoprawny format.",
                rule="management_token",
            )
        if scope not in values:
            values.append(scope)
    if not values:
        raise ReservationError(
            400,
            "INVALID_MANAGEMENT_SCOPE",
            "Token zarzadzania wymaga co najmniej jednego zakresu.",
            rule="management_token",
        )
    return tuple(sorted(values))


def _token_scopes(record: models.RezerwacjaTokenZarzadzania) -> tuple[str, ...]:
    raw = record.scopes
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            raw = [raw]
    return tuple(str(value) for value in (raw or ()))


def create_management_token(
    db,
    *,
    termin_id: int,
    scopes: Iterable[str],
    secret: str,
    now: datetime,
    expires_at: datetime | None = None,
    ttl_days: int = PUBLIC_MANAGEMENT_TOKEN_TTL_DAYS,
    idempotency_key: str | None = None,
    operation: str = "reservation.create.online:v2",
) -> IssuedManagementToken:
    """Issues a raw token once while persisting only its HMAC."""
    if db.get(models.Termin, int(termin_id)) is None:
        raise ReservationError(
            404,
            "RESERVATION_NOT_FOUND",
            "Nie znaleziono rezerwacji.",
            rule="management_token",
        )
    normalised_scopes = _normalise_scopes(scopes)
    ttl_days = int(ttl_days)
    if ttl_days < 1 or ttl_days > 3650:
        raise ValueError("management token ttl_days must be between 1 and 3650")
    expiry = expires_at or (now + timedelta(days=ttl_days))
    if expiry <= now:
        raise ValueError("management token expiry must be in the future")
    key = _normalise_idempotency_key(idempotency_key)
    operation = (operation or "").strip()
    if not operation or len(operation) > 64:
        raise ValueError("management token operation must have 1-64 characters")
    if key is None:
        raw_token = secrets.token_urlsafe(32)
    else:
        initial_payload = (
            "lokalo:r5a:management-initial\0"
            f"{operation}\0{key}\0{int(termin_id)}\0{','.join(normalised_scopes)}"
        ).encode("utf-8")
        digest = hmac.new(
            secret.encode("utf-8"), initial_payload, hashlib.sha256,
        ).digest()
        raw_token = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    token_hash = hash_management_token(raw_token, secret=secret)
    existing = db.execute(
        select(models.RezerwacjaTokenZarzadzania).where(
            models.RezerwacjaTokenZarzadzania.token_hash == token_hash,
        )
    ).scalar_one_or_none()
    if existing is not None:
        if (
            existing.termin_id != int(termin_id)
            or tuple(sorted(_token_scopes(existing))) != normalised_scopes
        ):
            raise ReservationError(
                409,
                "IDEMPOTENCY_KEY_REUSED",
                "Klucz idempotencji zostal uzyty z innymi parametrami tokenu.",
                rule="idempotency",
            )
        if existing.revoked_at is not None or existing.expires_at <= now:
            raise ReservationError(
                410,
                "MANAGEMENT_TOKEN_EXPIRED",
                "Pierwotny link zarzadzania nie jest juz aktywny.",
                rule="management_token",
            )
        if existing.used_at is not None:
            raise ReservationError(
                409,
                "MANAGEMENT_TOKEN_ALREADY_ADVANCED",
                "Pierwotny link zostal juz zastapiony nowszym.",
                rule="management_token",
            )
        return IssuedManagementToken(
            record=existing, raw_token=raw_token, replayed=True,
        )
    record = models.RezerwacjaTokenZarzadzania(
        termin_id=int(termin_id),
        token_hash=token_hash,
        scopes=list(normalised_scopes),
        expires_at=expiry,
        created_at=now,
    )
    db.add(record)
    db.flush()
    return IssuedManagementToken(record=record, raw_token=raw_token)


def lookup_management_token(
    db, raw_token: str, *, secret: str,
) -> models.RezerwacjaTokenZarzadzania | None:
    if not isinstance(raw_token, str) or not raw_token or raw_token != raw_token.strip():
        return None
    token_hash = hash_management_token(raw_token, secret=secret)
    return db.execute(
        select(models.RezerwacjaTokenZarzadzania).where(
            models.RezerwacjaTokenZarzadzania.token_hash == token_hash,
        )
    ).scalar_one_or_none()


def validate_management_token(
    db,
    raw_token: str,
    *,
    scope: str,
    secret: str,
    now: datetime,
) -> models.RezerwacjaTokenZarzadzania:
    record = lookup_management_token(db, raw_token, secret=secret)
    if record is None:
        raise ReservationError(
            404,
            "MANAGEMENT_TOKEN_INVALID",
            "Link zarzadzania jest nieprawidlowy lub nieaktualny.",
            rule="management_token",
        )
    if record.revoked_at is not None:
        raise ReservationError(
            410,
            "MANAGEMENT_TOKEN_REVOKED",
            "Link zarzadzania zostal uniewazniony.",
            rule="management_token",
        )
    if record.expires_at <= now:
        raise ReservationError(
            410,
            "MANAGEMENT_TOKEN_EXPIRED",
            "Link zarzadzania wygasl.",
            rule="management_token",
        )
    if record.used_at is not None:
        raise ReservationError(
            409,
            "MANAGEMENT_TOKEN_USED",
            "Ten link zarzadzania zostal juz uzyty.",
            rule="management_token",
        )
    scopes = _token_scopes(record)
    if scope not in scopes and "*" not in scopes:
        raise ReservationError(
            403,
            "MANAGEMENT_TOKEN_SCOPE_DENIED",
            "Ten link nie pozwala wykonac tej operacji.",
            rule="management_token",
        )
    return record


def _rotated_management_raw_token(
    *,
    raw_token: str,
    idempotency_key: str,
    operation: str,
    request_fingerprint_value: str,
    secret: str,
) -> str:
    payload = (
        "lokalo:r5a:management-rotation\0"
        f"{operation}\0{idempotency_key}\0{request_fingerprint_value}\0{raw_token}"
    ).encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def consume_and_rotate_management_token(
    db,
    raw_token: str,
    *,
    operation: str,
    idempotency_key: str | None,
    payload: Any,
    secret: str,
    now: datetime,
    allow_revoked_successor_replay: bool = False,
) -> IssuedManagementToken:
    """Consumes once and derives a replayable successor without storing plaintext.

    The same old token, Idempotency-Key and payload deterministically derive the same
    successor. A retry therefore does not need a raw secret in ``response_enc``.
    """
    operation = (operation or "").strip()
    if not operation or len(operation) > 64:
        raise ReservationError(
            400,
            "INVALID_MANAGEMENT_OPERATION",
            "Operacja tokenu zarzadzania ma niepoprawny format.",
            rule="management_token",
        )
    key = _normalise_idempotency_key(idempotency_key)
    if key is None:
        raise ReservationError(
            400,
            "IDEMPOTENCY_KEY_REQUIRED",
            "Ta operacja wymaga naglowka Idempotency-Key.",
            rule="idempotency",
        )
    token_hash = hash_management_token(raw_token, secret=secret)
    statement = select(models.RezerwacjaTokenZarzadzania).where(
        models.RezerwacjaTokenZarzadzania.token_hash == token_hash,
    ).with_for_update()
    record = db.execute(statement).scalar_one_or_none()
    if record is None:
        raise ReservationError(
            404,
            "MANAGEMENT_TOKEN_INVALID",
            "Link zarzadzania jest nieprawidlowy lub nieaktualny.",
            rule="management_token",
        )
    fingerprint = request_fingerprint(
        f"reservation.management.{operation}",
        {"idempotency_key": key, "payload": payload},
        secret,
    )
    next_raw = _rotated_management_raw_token(
        raw_token=raw_token,
        idempotency_key=key,
        operation=operation,
        request_fingerprint_value=fingerprint,
        secret=secret,
    )
    next_hash = hash_management_token(next_raw, secret=secret)

    if record.used_at is not None:
        successor = db.get(models.RezerwacjaTokenZarzadzania, record.rotated_to_id)
        if (
            record.used_operation != operation
            or not record.used_request_fingerprint
            or not hmac.compare_digest(record.used_request_fingerprint, fingerprint)
            or successor is None
            or not hmac.compare_digest(successor.token_hash, next_hash)
        ):
            raise ReservationError(
                409,
                "MANAGEMENT_TOKEN_USED",
                "Ten link zostal juz uzyty do innej operacji.",
                rule="management_token",
            )
        if successor.expires_at <= now:
            raise ReservationError(
                410,
                "MANAGEMENT_TOKEN_EXPIRED",
                "Nastepny link zarzadzania jest juz nieaktywny.",
                rule="management_token",
            )
        if successor.revoked_at is not None and not allow_revoked_successor_replay:
            raise ReservationError(
                410,
                "MANAGEMENT_TOKEN_REVOKED",
                "Nastepny link zarzadzania zostal uniewazniony.",
                rule="management_token",
            )
        if successor.used_at is not None:
            raise ReservationError(
                409,
                "MANAGEMENT_TOKEN_SUCCESSOR_USED",
                "Nastepny link zarzadzania zostal juz uzyty.",
                rule="management_token",
            )
        return IssuedManagementToken(
            record=successor, raw_token=next_raw, replayed=True,
        )

    validate_management_token(db, raw_token, scope=operation, secret=secret, now=now)
    successor = models.RezerwacjaTokenZarzadzania(
        termin_id=record.termin_id,
        token_hash=next_hash,
        scopes=list(_token_scopes(record)),
        expires_at=record.expires_at,
        created_at=now,
    )
    db.add(successor)
    db.flush()
    record.used_at = now
    record.used_operation = operation
    record.used_request_fingerprint = fingerprint
    record.rotated_to_id = successor.id
    db.flush()
    return IssuedManagementToken(record=successor, raw_token=next_raw)


def cleanup_expired_public_quotas(db, now: datetime) -> int:
    result = db.execute(
        delete(models.RezerwacjaPublicznaKwota).where(
            models.RezerwacjaPublicznaKwota.expires_at <= now,
        )
    )
    return int(result.rowcount or 0)


def consume_public_quota(
    db,
    *,
    scope: str,
    raw_client: str,
    secret: str,
    now: datetime,
    limit: int,
    window_seconds: int,
) -> int:
    """Atomically consumes a fixed-window quota shared by SQLite/Postgres workers."""
    scope = (scope or "").strip()
    limit = int(limit)
    window_seconds = int(window_seconds)
    if not scope or len(scope) > 64:
        raise ValueError("public quota scope must have 1-64 characters")
    if limit < 1 or window_seconds < 1:
        raise ValueError("public quota limit and window_seconds must be positive")
    epoch = datetime(1970, 1, 1)
    elapsed = int((now - epoch).total_seconds())
    window_start = epoch + timedelta(
        seconds=(elapsed // window_seconds) * window_seconds,
    )
    window_end = window_start + timedelta(seconds=window_seconds)
    client_hash = hash_public_client(
        raw_client,
        secret=secret,
        purpose=f"public-quota:{scope}",
    )
    cleanup_expired_public_quotas(db, now)
    table = models.RezerwacjaPublicznaKwota.__table__
    values = {
        "scope": scope,
        "client_hash": client_hash,
        "window_start": window_start,
        "expires_at": window_end,
        "count": 1,
        "created_at": now,
        "updated_at": now,
    }
    dialect = db.get_bind().dialect.name
    if dialect in {"sqlite", "postgresql"}:
        if dialect == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as dialect_insert
        else:
            from sqlalchemy.dialects.postgresql import insert as dialect_insert
        statement = dialect_insert(table).values(**values).on_conflict_do_update(
            index_elements=[table.c.scope, table.c.client_hash, table.c.window_start],
            set_={
                "count": table.c.count + 1,
                "expires_at": window_end,
                "updated_at": now,
            },
            where=table.c.count < limit,
        ).returning(table.c.count)
        consumed = db.execute(statement).scalar_one_or_none()
    else:
        row = db.execute(
            select(models.RezerwacjaPublicznaKwota).where(
                models.RezerwacjaPublicznaKwota.scope == scope,
                models.RezerwacjaPublicznaKwota.client_hash == client_hash,
                models.RezerwacjaPublicznaKwota.window_start == window_start,
            ).with_for_update()
        ).scalar_one_or_none()
        if row is None:
            row = models.RezerwacjaPublicznaKwota(**values)
            db.add(row)
            db.flush()
            consumed = row.count
        elif row.count < limit:
            row.count += 1
            row.updated_at = now
            consumed = row.count
        else:
            consumed = None
    if consumed is None:
        raise ReservationError(
            429,
            "PUBLIC_RATE_LIMITED",
            "Przekroczono limit prob. Sprobuj ponownie pozniej.",
            rule="public_rate_limit",
        )
    return int(consumed)


def _dialect_name(db) -> str:
    return db.get_bind().dialect.name


def begin_floor_plan_write(db) -> None:
    """Serializuje publikację planu z zapisami rezerwacji na SQLite.

    PostgreSQL synchronizuje się później na tych samych wierszach ``stoliki``
    co rezerwacje i holdy. SQLite nie ma ``FOR UPDATE``, więc publikacja musi
    zdobyć blokadę zapisu przed pierwszym odczytem walidacyjnym.
    """
    if _dialect_name(db) != "sqlite":
        return
    db.rollback()
    try:
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    except OperationalError as exc:
        db.rollback()
        raise ReservationError(
            503,
            "RESERVATION_BUSY",
            "Inna zmiana rezerwacji jest w toku. Spróbuj ponownie za chwilę.",
            rule="transaction",
        ) from exc


def lock_tables(db, table_ids: Iterable[int]) -> tuple[models.Stolik, ...]:
    """Zwraca stabilnie posortowane stoły i blokuje je na PostgreSQL."""
    ids = tuple(sorted({int(value) for value in table_ids if value is not None}))
    if not ids:
        return ()
    statement = (
        select(models.Stolik)
        .where(models.Stolik.id.in_(ids))
        .order_by(models.Stolik.id)
        .execution_options(populate_existing=True)
    )
    if _dialect_name(db) == "postgresql":
        statement = statement.with_for_update()
    return tuple(db.execute(statement).scalars().all())


def lock_days_in_current_transaction(
    db,
    dates: Iterable[date],
) -> tuple[models.RezerwacjaDzienLedger, ...]:
    """Blokuje dni rosnąco bez restartowania bieżącej transakcji.

    Na SQLite wywołujący musi wcześniej wejść w ``BEGIN IMMEDIATE``. PostgreSQL
    używa tych samych trwałych anchorów ``RezerwacjaDzienLedger`` i tej samej
    globalnej kolejności co zwykli producenci zmian rezerwacji.
    """

    ordered = tuple(sorted(set(dates)))
    if not ordered:
        raise ValueError("at least one reservation date is required")
    dialect = _dialect_name(db)
    try:
        table = models.RezerwacjaDzienLedger.__table__
        locked_at = _utcnow_naive()
        if dialect == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as dialect_insert

            for day in ordered:
                db.execute(
                    dialect_insert(table)
                    .values(data=day, revision=0, updated_at=locked_at)
                    .on_conflict_do_nothing(index_elements=["data"])
                )
        elif dialect == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as dialect_insert

            for day in ordered:
                db.execute(
                    dialect_insert(table)
                    .values(data=day, revision=0, updated_at=locked_at)
                    .on_conflict_do_nothing(index_elements=["data"])
                )
        else:
            for day in ordered:
                if db.get(models.RezerwacjaDzienLedger, day) is None:
                    db.add(models.RezerwacjaDzienLedger(
                        data=day, revision=0, updated_at=locked_at,
                    ))
            db.flush()

        statement = (
            select(models.RezerwacjaDzienLedger)
            .where(models.RezerwacjaDzienLedger.data.in_(ordered))
            .order_by(models.RezerwacjaDzienLedger.data)
        )
        if dialect == "postgresql":
            statement = statement.with_for_update()
        guards = tuple(db.execute(statement).scalars().all())
    except OperationalError as exc:
        db.rollback()
        raise ReservationError(
            503,
            "RESERVATION_BUSY",
            "Inny zapis rezerwacji jest w toku. Spróbuj ponownie za chwilę.",
            rule="transaction",
        ) from exc
    if len(guards) != len(ordered):
        db.rollback()
        raise ReservationError(
            503,
            "RESERVATION_BUSY",
            "Nie udało się zablokować dnia rezerwacyjnego.",
            rule="transaction",
        )
    return guards


def begin_locked_write(db, dates: Iterable[date]) -> tuple[models.RezerwacjaDzienLedger, ...]:
    """Rozpoczyna świeżą transakcję zapisu i blokuje dni w kolejności rosnącej.

    SQLite nie implementuje ``FOR UPDATE``; ``BEGIN IMMEDIATE`` zdobywa jedyną
    blokadę zapisu przed pierwszym odczytem walidacyjnym. PostgreSQL blokuje trwałe
    wiersze-anchor przez ``SELECT FOR UPDATE``. Wywołujący wykonuje commit/rollback.
    """
    ordered = tuple(sorted(set(dates)))
    if not ordered:
        raise ValueError("at least one reservation date is required")
    db.rollback()
    try:
        if _dialect_name(db) == "sqlite":
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    except OperationalError as exc:
        db.rollback()
        raise ReservationError(
            503,
            "RESERVATION_BUSY",
            "Inny zapis rezerwacji jest w toku. Spróbuj ponownie za chwilę.",
            rule="transaction",
        ) from exc
    return lock_days_in_current_transaction(db, ordered)


def touch_days(guards: Iterable[models.RezerwacjaDzienLedger]) -> None:
    now = _utcnow_naive()
    for guard in guards:
        guard.revision = int(guard.revision or 0) + 1
        guard.updated_at = now


def _minute(value: time, *, field_name: str) -> int:
    if value.tzinfo is not None or value.second or value.microsecond:
        raise ReservationError(
            400,
            "INVALID_RESERVATION_INTERVAL",
            f"{field_name} musi wskazywać pełną minutę czasu lokalnego.",
            rule="interval",
        )
    return value.hour * 60 + value.minute


def _interval(start: time, end: time) -> tuple[int, int]:
    start_minute = _minute(start, field_name="Godzina rozpoczęcia")
    end_minute = _minute(end, field_name="Godzina zakończenia")
    if end_minute <= start_minute:
        raise ReservationError(
            400,
            "INVALID_RESERVATION_INTERVAL",
            "Rezerwacja musi kończyć się po rozpoczęciu i nie może przechodzić przez północ.",
            rule="interval",
        )
    return start_minute, end_minute


def claim_minute_window(start: time, end: time, buffer_min: int = 0) -> tuple[int, int]:
    """Return the exact half-open minute window used by table-claim writers."""
    start_minute, end_minute = _interval(start, end)
    return start_minute, min(1440, end_minute + max(0, int(buffer_min or 0)))


def _active_hold_filter(now: datetime):
    claim = models.RezerwacjaStolikClaim
    return or_(claim.expires_at.is_(None), claim.expires_at > now)


def _projected_table_ids(primary: Any, additional: Any) -> set[int]:
    """Best-effort odczyt fizycznych stołów z kompatybilnej projekcji ``Termin``."""
    if isinstance(additional, str):
        try:
            additional = json.loads(additional)
        except (TypeError, ValueError):
            additional = ()
    values = [primary]
    if isinstance(additional, (list, tuple, set)):
        values.extend(additional)
    result = set()
    for value in values:
        if value is None or isinstance(value, bool):
            continue
        try:
            table_id = int(value)
        except (TypeError, ValueError):
            continue
        if table_id > 0:
            result.add(table_id)
    return result


def _configured_post_buffer_min(db, *, include_r3: bool = True) -> int:
    """Konserwatywny fallback dla claimów utworzonych przed materializacją R4.

    Stary ``Termin`` nie przechowuje rozstrzygniętej reguły bufora. W takim
    przypadku bezpieczniej jest użyć największej skonfigurowanej wartości niż
    przedwcześnie sprzedać zasób. ``include_r3=False`` pozostaje wyłącznie
    adapterem odbudowy schematu sprzed migracji 0059, gdzie tabele i kolumny R3
    jeszcze nie istnieją.
    """
    values = [db.query(models.LokalConfig.rez_bufor_min).limit(1).scalar()]
    if include_r3:
        values.extend((
            db.execute(
                select(func.max(models.SalaRezerwacyjna.domyslny_bufor_min))
            ).scalar_one_or_none(),
            db.execute(
                select(func.max(models.RegulaDostepnosciRezerwacji.bufor_min))
            ).scalar_one_or_none(),
        ))
    return max(0, *(int(value or 0) for value in values))


def _public_hold_table_ids(
    primary: Any, additional: Any,
) -> tuple[int, ...]:
    ids = _projected_table_ids(primary, additional)
    if not ids:
        raise ReservationError(
            400,
            "INVALID_HOLD_RESOURCE",
            "Hold wymaga co najmniej jednego stolika.",
            rule="public_hold",
        )
    return tuple(sorted(ids))


def normalise_public_hold_allocation_snapshot(
    table_ids: Iterable[int],
    snapshot: Mapping[str, Any] | None,
) -> dict[str, Any]:
    try:
        ids = tuple(sorted({
            int(value) for value in table_ids
            if value is not None and not isinstance(value, bool) and int(value) > 0
        }))
    except (TypeError, ValueError) as exc:
        raise ReservationError(
            400,
            "INVALID_ALLOCATION_SNAPSHOT",
            "Snapshot przydzialu ma niepoprawna liste stolikow.",
            rule="public_hold",
        ) from exc
    if not ids:
        raise ReservationError(
            400,
            "INVALID_ALLOCATION_SNAPSHOT",
            "Snapshot przydzialu wymaga co najmniej jednego stolika.",
            rule="public_hold",
        )
    raw = dict(snapshot or {})
    snapshot_ids = raw.get("stoliki", raw.get("table_ids"))
    if snapshot_ids is not None:
        try:
            supplied_ids = tuple(sorted({int(value) for value in snapshot_ids}))
        except (TypeError, ValueError) as exc:
            raise ReservationError(
                400,
                "INVALID_ALLOCATION_SNAPSHOT",
                "Snapshot przydzialu ma niepoprawna liste stolikow.",
                rule="public_hold",
            ) from exc
        if supplied_ids != ids:
            raise ReservationError(
                409,
                "ALLOCATION_SNAPSHOT_MISMATCH",
                "Snapshot przydzialu nie odpowiada zasobom holdu.",
                rule="public_hold",
            )
    combination_id = raw.get(
        "combination_id",
        raw.get("plan_combination_id", raw.get(
            "kombinacja_planu_id", raw.get("przydzial_kombinacja_planu_id"),
        )),
    )
    plan_version_id = raw.get(
        "plan_version_id",
        raw.get("wersja_planu_id", raw.get("przydzial_wersja_planu_id")),
    )
    room_id = raw.get("room_id", raw.get("sala_id"))
    room_name = raw.get("room_name", raw.get("sala_nazwa", raw.get("sala")))
    reason = raw.get("reason", raw.get("powod", raw.get("reasons")))
    normalised = {
        "type": raw.get("type", raw.get(
            "kind", "combination" if len(ids) > 1 else "single_table",
        )),
        "stoliki": list(ids),
        "combination_id": combination_id,
        "room": {"id": room_id, "name": room_name},
        "plan_version_id": plan_version_id,
        "reason": reason,
        # Compatibility aliases consumed by the existing Termin provenance adapter.
        "kombinacja_planu_id": combination_id,
        "wersja_planu_id": plan_version_id,
    }
    try:
        return json.loads(canonical_json(normalised))
    except (TypeError, ValueError) as exc:
        raise ReservationError(
            400,
            "INVALID_ALLOCATION_SNAPSHOT",
            "Snapshot przydzialu zawiera nieobslugiwane dane.",
            rule="public_hold",
        ) from exc


def lookup_public_hold(
    db, raw_token: str, *, secret: str,
) -> models.RezerwacjaPublicznyHold | None:
    if not isinstance(raw_token, str) or not raw_token or raw_token != raw_token.strip():
        return None
    token_hash = hash_public_hold_token(raw_token, secret=secret)
    return db.execute(
        select(models.RezerwacjaPublicznyHold).where(
            models.RezerwacjaPublicznyHold.token_hash == token_hash,
        )
    ).scalar_one_or_none()


def expire_public_holds(
    db,
    now: datetime,
    *,
    dates: Iterable[date] | None = None,
) -> int:
    now = _lifecycle_utc_naive(now, field_name="now")
    scope_provided = dates is not None
    scoped_dates = tuple(sorted(set(dates or ())))
    if scope_provided and not scoped_dates:
        return 0
    statement = select(models.RezerwacjaPublicznyHold).where(
        models.RezerwacjaPublicznyHold.state == "active",
        models.RezerwacjaPublicznyHold.expires_at <= now,
    )
    if scoped_dates:
        statement = statement.where(
            models.RezerwacjaPublicznyHold.data.in_(scoped_dates),
        )
    statement = statement.with_for_update()
    holds = tuple(db.execute(statement).scalars().all())
    if not holds:
        return 0
    hold_ids = tuple(hold.id for hold in holds)
    db.execute(
        delete(models.RezerwacjaStolikClaim).where(
            models.RezerwacjaStolikClaim.public_hold_id.in_(hold_ids),
        )
    )
    for hold in holds:
        hold.state = "expired"
        hold.released_at = now
    db.flush()
    return len(holds)


def _public_hold_advisory_key(subject_hash: str) -> int:
    """Mapuje HMAC na deterministyczny signed bigint dla blokady PostgreSQL."""
    unsigned = int(subject_hash[:16], 16)
    return unsigned - (1 << 64) if unsigned >= (1 << 63) else unsigned


def _lock_public_hold_subjects(db, *subject_hashes: str) -> None:
    """Serializuje globalne limity sesji/IP także między różnymi datami.

    SQLite jest już serializowany przez ``BEGIN IMMEDIATE`` w day locku. PostgreSQL
    potrzebuje blokady niezależnej od dnia, inaczej dwa równoległe żądania na różne
    daty mogą jednocześnie przejść przez count-then-insert.
    """
    if db.get_bind().dialect.name != "postgresql":
        return
    for key in sorted({_public_hold_advisory_key(value) for value in subject_hashes}):
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def create_public_hold(
    db,
    *,
    data: date,
    start: time,
    end: time,
    table_ids: Iterable[int],
    party_size: int,
    buffer_min: int,
    expires_at: datetime,
    raw_session: str,
    raw_ip: str,
    secret: str,
    now: datetime,
    allocation_snapshot: Mapping[str, Any] | None = None,
    session_limit: int = PUBLIC_HOLD_SESSION_LIMIT,
    ip_limit: int = PUBLIC_HOLD_IP_LIMIT,
    idempotency_key: str | None = None,
    operation: str = "reservation.hold.create:v1",
) -> IssuedPublicHold:
    """Create an all-table hold; ``now``/``expires_at`` are lifecycle UTC instants."""
    now = _lifecycle_utc_naive(now, field_name="now")
    expires_at = _lifecycle_utc_naive(expires_at, field_name="expires_at")
    if expires_at <= now:
        raise ReservationError(
            400,
            "INVALID_HOLD_EXPIRY",
            "Czas wygasniecia holdu musi byc w przyszlosci.",
            rule="public_hold",
        )
    party_size = int(party_size)
    buffer_min = int(buffer_min or 0)
    if party_size < 1 or buffer_min < 0:
        raise ReservationError(
            400,
            "INVALID_HOLD_PARAMETERS",
            "Parametry holdu sa niepoprawne.",
            rule="public_hold",
        )
    session_limit = int(session_limit)
    ip_limit = int(ip_limit)
    if session_limit < 1 or ip_limit < 1:
        raise ValueError("public hold limits must be positive")
    try:
        ids = tuple(sorted({
            int(value) for value in table_ids
            if value is not None and not isinstance(value, bool) and int(value) > 0
        }))
    except (TypeError, ValueError) as exc:
        raise ReservationError(
            400,
            "INVALID_HOLD_RESOURCE",
            "Lista stolikow holdu ma niepoprawny format.",
            rule="public_hold",
        ) from exc
    if not ids:
        raise ReservationError(
            400,
            "INVALID_HOLD_RESOURCE",
            "Hold wymaga co najmniej jednego stolika.",
            rule="public_hold",
        )
    normalised_snapshot = normalise_public_hold_allocation_snapshot(
        ids, allocation_snapshot,
    )
    existing_ids = set(db.execute(
        select(models.Stolik.id).where(models.Stolik.id.in_(ids))
    ).scalars().all())
    if existing_ids != set(ids):
        raise ReservationError(
            400,
            "INVALID_HOLD_RESOURCE",
            "Co najmniej jeden stolik holdu nie istnieje.",
            rule="public_hold",
        )
    start_minute, end_minute = _interval(start, end)
    blocked_end = min(1440, end_minute + buffer_min)
    # An expired waitlist claim is ignored by availability reads, but still occupies
    # the unique (table, date, minute) key. Remove both kinds of stale hold before the
    # new public claim is inserted, otherwise a harmless expiry becomes a 409/500.
    cleanup_expired_holds(db, now, dates=[data])
    session_hash = hash_public_client(
        raw_session, secret=secret, purpose="public-hold-session",
    )
    ip_hash = hash_public_client(
        raw_ip, secret=secret, purpose="public-hold-ip",
    )
    key = _normalise_idempotency_key(idempotency_key)
    operation = (operation or "").strip()
    if not operation or len(operation) > 64:
        raise ValueError("public hold operation must have 1-64 characters")
    if key is None:
        raw_token = secrets.token_urlsafe(32)
    else:
        initial_payload = (
            "lokalo:r5a:public-hold-initial\0"
            f"{operation}\0{session_hash}\0{key}"
        ).encode("utf-8")
        digest = hmac.new(
            secret.encode("utf-8"), initial_payload, hashlib.sha256,
        ).digest()
        raw_token = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    token_hash = hash_public_hold_token(raw_token, secret=secret)
    existing = db.execute(
        select(models.RezerwacjaPublicznyHold).where(
            models.RezerwacjaPublicznyHold.token_hash == token_hash,
        )
    ).scalar_one_or_none()
    if existing is not None:
        same_request = (
            existing.data == data
            and existing.godz_od == start
            and existing.godz_do == end
            and int(existing.liczba_osob) == party_size
            and int(existing.bufor_min or 0) == buffer_min
            and _projected_table_ids(
                existing.stolik_id, existing.stoliki_dodatkowe,
            ) == set(ids)
            and canonical_json(existing.allocation_snapshot) == canonical_json(
                normalised_snapshot,
            )
            and hmac.compare_digest(existing.session_hash, session_hash)
            and hmac.compare_digest(existing.ip_hash, ip_hash)
        )
        if not same_request:
            raise ReservationError(
                409,
                "IDEMPOTENCY_KEY_REUSED",
                "Klucz idempotencji zostal uzyty z innymi parametrami holdu.",
                rule="idempotency",
            )
        if existing.state == "active" and existing.expires_at > now:
            return IssuedPublicHold(
                record=existing, raw_token=raw_token, replayed=True,
            )
        if existing.state in {"released", "expired"}:
            raise ReservationError(
                410,
                "PUBLIC_HOLD_INACTIVE",
                "Hold tego zadania wygasl albo zostal zwolniony.",
                rule="public_hold",
            )
        raise ReservationError(
            409,
            "PUBLIC_HOLD_CONSUMED",
            "Hold tego zadania zostal juz zamieniony w rezerwacje.",
            rule="public_hold",
        )
    _lock_public_hold_subjects(db, session_hash, ip_hash)
    active_filter = (
        models.RezerwacjaPublicznyHold.state == "active",
        models.RezerwacjaPublicznyHold.expires_at > now,
    )
    session_count = db.execute(
        select(func.count(models.RezerwacjaPublicznyHold.id)).where(
            *active_filter,
            models.RezerwacjaPublicznyHold.session_hash == session_hash,
        )
    ).scalar_one()
    if int(session_count or 0) >= session_limit:
        raise ReservationError(
            429,
            "PUBLIC_HOLD_SESSION_LIMIT",
            "Ta sesja ma juz maksymalna liczbe aktywnych holdow.",
            rule="public_hold_limit",
        )
    ip_count = db.execute(
        select(func.count(models.RezerwacjaPublicznyHold.id)).where(
            *active_filter,
            models.RezerwacjaPublicznyHold.ip_hash == ip_hash,
        )
    ).scalar_one()
    if int(ip_count or 0) >= ip_limit:
        raise ReservationError(
            429,
            "PUBLIC_HOLD_IP_LIMIT",
            "Ten klient ma juz maksymalna liczbe aktywnych holdow.",
            rule="public_hold_limit",
        )
    occupied = occupied_table_ids(
        db,
        data=data,
        start=start,
        end=end,
        buffer_min=buffer_min,
        now=now,
    )
    if set(ids) & occupied:
        raise ReservationError(
            409,
            "TABLE_CONFLICT",
            "Co najmniej jeden stolik zostal wlasnie zajety.",
            rule="public_hold",
        )
    record = models.RezerwacjaPublicznyHold(
        token_hash=token_hash,
        session_hash=session_hash,
        ip_hash=ip_hash,
        state="active",
        data=data,
        godz_od=start,
        godz_do=end,
        liczba_osob=party_size,
        stolik_id=ids[0],
        stoliki_dodatkowe=list(ids[1:]) or None,
        allocation_snapshot=normalised_snapshot,
        bufor_min=buffer_min,
        expires_at=expires_at,
        created_at=now,
    )
    db.add(record)
    db.flush()
    rows = [
        {
            "termin_id": None,
            "waitlist_id": None,
            "public_hold_id": record.id,
            "stolik_id": table_id,
            "data": data,
            "minute": minute,
            "expires_at": expires_at,
            "created_at": now,
        }
        for table_id in ids
        for minute in range(start_minute, blocked_end)
    ]
    db.execute(insert(models.RezerwacjaStolikClaim), rows)
    return IssuedPublicHold(record=record, raw_token=raw_token)


def validate_public_hold(
    db,
    raw_token: str,
    *,
    raw_session: str,
    secret: str,
    now: datetime,
) -> models.RezerwacjaPublicznyHold:
    now = _lifecycle_utc_naive(now, field_name="now")
    record = lookup_public_hold(db, raw_token, secret=secret)
    expected_session = hash_public_client(
        raw_session, secret=secret, purpose="public-hold-session",
    )
    if record is None or not hmac.compare_digest(record.session_hash, expected_session):
        raise ReservationError(
            404,
            "PUBLIC_HOLD_NOT_FOUND",
            "Nie znaleziono aktywnego holdu tej sesji.",
            rule="public_hold",
        )
    if record.state == "active" and record.expires_at <= now:
        db.execute(
            delete(models.RezerwacjaStolikClaim).where(
                models.RezerwacjaStolikClaim.public_hold_id == record.id,
            )
        )
        record.state = "expired"
        record.released_at = now
        db.flush()
    if record.state in {"expired", "released"}:
        raise ReservationError(
            410,
            "PUBLIC_HOLD_INACTIVE",
            "Hold wygasl albo zostal zwolniony.",
            rule="public_hold",
        )
    if record.state == "consumed":
        raise ReservationError(
            409,
            "PUBLIC_HOLD_CONSUMED",
            "Hold zostal juz zamieniony w rezerwacje.",
            rule="public_hold",
        )
    return record


def release_public_hold(
    db,
    raw_token: str,
    *,
    raw_session: str,
    secret: str,
    now: datetime,
) -> models.RezerwacjaPublicznyHold:
    now = _lifecycle_utc_naive(now, field_name="now")
    record = lookup_public_hold(db, raw_token, secret=secret)
    expected_session = hash_public_client(
        raw_session, secret=secret, purpose="public-hold-session",
    )
    if record is None or not hmac.compare_digest(record.session_hash, expected_session):
        raise ReservationError(
            404,
            "PUBLIC_HOLD_NOT_FOUND",
            "Nie znaleziono holdu tej sesji.",
            rule="public_hold",
        )
    if record.state == "consumed":
        raise ReservationError(
            409,
            "PUBLIC_HOLD_CONSUMED",
            "Zrealizowanego holdu nie mozna zwolnic.",
            rule="public_hold",
        )
    if record.state in {"released", "expired"}:
        return record
    db.execute(
        delete(models.RezerwacjaStolikClaim).where(
            models.RezerwacjaStolikClaim.public_hold_id == record.id,
        )
    )
    record.state = "expired" if record.expires_at <= now else "released"
    record.released_at = now
    db.flush()
    return record


def replace_public_hold_claims(
    db,
    *,
    public_hold_id: int,
    table_ids: Iterable[int],
    data: date,
    start: time,
    end: time,
    buffer_min: int,
    expires_at: datetime,
    now: datetime,
    cleanup_holds: bool = True,
) -> None:
    """Rebuild helper for an existing public hold; never creates a second owner."""
    now = _lifecycle_utc_naive(now, field_name="now")
    expires_at = _lifecycle_utc_naive(expires_at, field_name="expires_at")
    if cleanup_holds:
        cleanup_expired_holds(db, now, dates=[data])
    db.execute(
        delete(models.RezerwacjaStolikClaim).where(
            models.RezerwacjaStolikClaim.public_hold_id == int(public_hold_id),
        )
    )
    if expires_at <= now:
        return
    ids = tuple(sorted({int(value) for value in table_ids}))
    if not ids:
        raise ReservationError(
            400,
            "INVALID_HOLD_RESOURCE",
            "Hold wymaga co najmniej jednego stolika.",
            rule="public_hold",
        )
    start_minute, end_minute = _interval(start, end)
    blocked_end = min(1440, end_minute + max(0, int(buffer_min or 0)))
    occupied = occupied_table_ids(
        db,
        data=data,
        start=start,
        end=end,
        buffer_min=buffer_min,
        now=now,
    )
    if set(ids) & occupied:
        raise ReservationError(
            409,
            "TABLE_CONFLICT",
            "Nie mozna odbudowac holdu z powodu kolizji zasobu.",
            rule="public_hold",
        )
    rows = [
        {
            "termin_id": None,
            "waitlist_id": None,
            "public_hold_id": int(public_hold_id),
            "stolik_id": table_id,
            "data": data,
            "minute": minute,
            "expires_at": expires_at,
            "created_at": now,
        }
        for table_id in ids
        for minute in range(start_minute, blocked_end)
    ]
    db.execute(insert(models.RezerwacjaStolikClaim), rows)


def consume_public_hold(
    db,
    raw_token: str,
    *,
    raw_session: str,
    termin_id: int,
    secret: str,
    now: datetime,
) -> models.RezerwacjaPublicznyHold:
    """Transfers every minute claim from a hold to Termin in the same transaction."""
    now = _lifecycle_utc_naive(now, field_name="now")
    record = validate_public_hold(
        db, raw_token, raw_session=raw_session, secret=secret, now=now,
    )
    termin = db.get(models.Termin, int(termin_id))
    if termin is None:
        raise ReservationError(
            404,
            "RESERVATION_NOT_FOUND",
            "Nie znaleziono rezerwacji docelowej.",
            rule="public_hold",
        )
    held_ids = _public_hold_table_ids(record.stolik_id, record.stoliki_dodatkowe)
    termin_ids = _projected_table_ids(termin.stolik_id, termin.stoliki_dodatkowe)
    if (
        termin.data != record.data
        or termin.godz_od != record.godz_od
        or termin.godz_do != record.godz_do
        or termin_ids != set(held_ids)
    ):
        raise ReservationError(
            409,
            "PUBLIC_HOLD_RESERVATION_MISMATCH",
            "Rezerwacja docelowa nie odpowiada parametrom holdu.",
            rule="public_hold",
        )
    start_minute, end_minute = _interval(record.godz_od, record.godz_do)
    expected_claims = len(held_ids) * (
        min(1440, end_minute + int(record.bufor_min or 0)) - start_minute
    )
    actual_claims = db.execute(
        select(func.count(models.RezerwacjaStolikClaim.id)).where(
            models.RezerwacjaStolikClaim.public_hold_id == record.id,
        )
    ).scalar_one()
    if int(actual_claims or 0) != expected_claims:
        raise ReservationError(
            409,
            "PUBLIC_HOLD_CLAIMS_INCOMPLETE",
            "Hold nie ma kompletnego atomowego zajecia zasobow.",
            rule="public_hold",
        )
    db.execute(
        update(models.RezerwacjaStolikClaim)
        .where(models.RezerwacjaStolikClaim.public_hold_id == record.id)
        .values(
            termin_id=termin.id,
            waitlist_id=None,
            public_hold_id=None,
            expires_at=None,
        )
    )
    record.state = "consumed"
    record.consumed_at = now
    record.termin_id = termin.id
    db.flush()
    return record


def cleanup_expired_holds(
    db,
    now: datetime,
    *,
    dates: Iterable[date] | None = None,
) -> int:
    """Release public and waitlist inventory using one naive-UTC clock.

    An offered waitlist owner is moved to ``wygasla`` in the same transaction
    that removes every table claim. ``dates`` lets a caller holding day-ledger
    locks keep the cleanup inside exactly that protected scope.
    """
    now = _lifecycle_utc_naive(now, field_name="now")
    scope_provided = dates is not None
    scoped_dates = tuple(sorted(set(dates or ())))
    if scope_provided and not scoped_dates:
        return 0
    expired_public = expire_public_holds(
        db, now, dates=(scoped_dates if scope_provided else None),
    )
    waitlist_statement = select(models.ListaOczekujacych).where(
        models.ListaOczekujacych.hold_do <= now,
    )
    if scoped_dates:
        waitlist_statement = waitlist_statement.where(
            models.ListaOczekujacych.data.in_(scoped_dates),
        )
    expired_waitlists = tuple(db.execute(
        waitlist_statement.with_for_update()
    ).scalars().all())
    expired_waitlist_ids = tuple(row.id for row in expired_waitlists)
    for row in expired_waitlists:
        if row.status == "zaoferowano":
            previous_version = int(row.offer_version or 0)
            row.status = "wygasla"
            row.wygasla_at = now
            row.offer_version = previous_version + 1
            db.add(models.AuditLog(
                ts=now,
                user_id=None,
                login=None,
                akcja="waitlist_offer_expired",
                zasob=f"waitlist:{row.id}",
                szczegoly=canonical_json({
                    "offer_version": previous_version,
                    "next_offer_version": row.offer_version,
                    "deadline": (
                        row.oferta_wygasa_at.isoformat()
                        if row.oferta_wygasa_at else None
                    ),
                }),
            ))
        row.hold_stolik_id = None
        row.hold_stoliki_dodatkowe = None
        row.hold_godz_od = None
        row.hold_godz_do = None
        row.hold_bufor_min = None
        row.hold_do = None
        row.offer_auto_przydzielony = None
        row.offer_override_authorized = None
        row.offer_override_note = None
        row.offer_sala_id = None
        row.offer_kanal = None
    stale_claim_filter = models.RezerwacjaStolikClaim.expires_at <= now
    if expired_waitlist_ids:
        # The owner expiry is authoritative. Delete all claims of that owner even
        # when legacy/corrupt data carries a later per-claim timestamp.
        stale_claim_filter = or_(
            stale_claim_filter,
            models.RezerwacjaStolikClaim.waitlist_id.in_(expired_waitlist_ids),
        )
    if scoped_dates:
        stale_claim_filter = and_(
            models.RezerwacjaStolikClaim.data.in_(scoped_dates),
            stale_claim_filter,
        )
    result = db.execute(
        delete(models.RezerwacjaStolikClaim).where(
            models.RezerwacjaStolikClaim.waitlist_id.isnot(None),
            stale_claim_filter,
        )
    )
    return expired_public + len(expired_waitlists) + int(result.rowcount or 0)


def occupied_table_ids(
    db,
    *,
    data: date,
    start: time,
    end: time,
    buffer_min: int = 0,
    exclude_termin_id: int | None = None,
    now: datetime | None = None,
    include_r3_buffers: bool = True,
) -> set[int]:
    """Zwraca zasoby kolidujące z proponowanym przedziałem.

    ``buffer_min`` jest buforem *po* wizycie. Trwałe claimy nowych alokacji już
    zawierają własny bufor, a tutaj rozszerzamy wyłącznie koniec propozycji. Dzięki
    temu wynik nie zależy od kolejności utworzenia dwóch rezerwacji i bufor nie jest
    naliczany podwójnie.

    Aktywny obrót hosta jest konserwatywną blokadą live: dopóki gość nie wyjdzie,
    jego wszystkie stoły pozostają zajęte także po planowanym ``godz_do``.
    """
    lifecycle_now = _lifecycle_utc_naive(
        now if now is not None else _utcnow_naive(),
        field_name="now",
    )
    start_minute, end_minute = _interval(start, end)
    buffer_min = max(0, int(buffer_min or 0))
    query_start = start_minute
    query_end = min(1440, end_minute + buffer_min)
    claim = models.RezerwacjaStolikClaim
    statement = select(claim.stolik_id).where(
        claim.data == data,
        claim.minute >= query_start,
        claim.minute < query_end,
        _active_hold_filter(lifecycle_now),
    )
    if exclude_termin_id is not None:
        statement = statement.where(
            or_(claim.termin_id.is_(None), claim.termin_id != exclude_termin_id)
        )
    occupied = set(db.execute(statement).scalars().all())

    termin = models.Termin
    legacy_buffer = _configured_post_buffer_min(
        db, include_r3=include_r3_buffers,
    )
    materialized_termin_ids = set(db.execute(
        select(claim.termin_id).where(
            claim.data == data,
            claim.termin_id.isnot(None),
        ).distinct()
    ).scalars().all())
    scheduled_statement = select(
        termin.id,
        termin.stolik_id,
        termin.stoliki_dodatkowe,
        termin.godz_od,
        termin.godz_do,
    ).where(
        termin.data == data,
        termin.rodzaj == "stolik",
        termin.status.in_(ACTIVE_STATUSES),
        termin.godz_od.isnot(None),
        termin.godz_do.isnot(None),
    )
    if exclude_termin_id is not None:
        scheduled_statement = scheduled_statement.where(termin.id != exclude_termin_id)
    for termin_id, primary, additional, existing_start, existing_end in db.execute(
        scheduled_statement,
    ):
        if termin_id in materialized_termin_ids:
            continue
        existing_start_minute, existing_end_minute = _interval(
            existing_start,
            existing_end,
        )
        existing_blocked_end = min(1440, existing_end_minute + legacy_buffer)
        if existing_start_minute < query_end and query_start < existing_blocked_end:
            occupied.update(_projected_table_ids(primary, additional))

    live_statement = select(
        termin.stolik_id,
        termin.stoliki_dodatkowe,
    ).where(
        termin.data == data,
        termin.rodzaj == "stolik",
        termin.status.in_(ACTIVE_STATUSES),
        termin.faza_hosta.in_(LIVE_HOST_PHASES),
    )
    if exclude_termin_id is not None:
        live_statement = live_statement.where(termin.id != exclude_termin_id)
    for primary, additional in db.execute(live_statement):
        occupied.update(_projected_table_ids(primary, additional))
    return occupied


def pacing_status(
    db,
    *,
    data: date,
    start: time,
    window_min: int,
    party_size: int,
    max_reservations: int | None,
    max_covers: int | None,
    exclude_termin_id: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    effective_now = _lifecycle_utc_naive(
        now if now is not None else _utcnow_naive(),
        field_name="now",
    )
    start_minute = _minute(start, field_name="Godzina rozpoczęcia")
    window_min = max(1, int(window_min or 1))
    ledger = models.RezerwacjaPacingLedger
    bucket_start = (start_minute // window_min) * window_min
    statement = select(ledger).where(
        ledger.data == data,
        ledger.start_minute >= bucket_start,
        ledger.start_minute < min(1440, bucket_start + window_min),
    )
    if exclude_termin_id is not None:
        statement = statement.where(ledger.termin_id != exclude_termin_id)
    rows = db.execute(statement).scalars().all()
    waitlist_rows = [
        row for row in active_waitlist_offer_projections(
            db, data=data, now=effective_now,
        )
        if bucket_start <= row.start_minute < min(1440, bucket_start + window_min)
    ]
    reservations = len(rows) + len(waitlist_rows)
    covers = (
        sum(int(row.covers or 0) for row in rows)
        + sum(row.covers for row in waitlist_rows)
    )
    would_reservations = reservations + 1
    would_covers = covers + max(1, int(party_size or 1))
    reservation_full = bool(max_reservations and would_reservations > max_reservations)
    covers_full = bool(max_covers and would_covers > max_covers)
    return {
        "full": reservation_full or covers_full,
        "reservation_full": reservation_full,
        "covers_full": covers_full,
        "reservations": reservations,
        "covers": covers,
        "would_reservations": would_reservations,
        "would_covers": would_covers,
        "max_reservations": max_reservations,
        "max_covers": max_covers,
        "bucket_start": bucket_start,
        "bucket_end": min(1440, bucket_start + window_min),
    }


@dataclass(frozen=True)
class WaitlistOfferProjection:
    waitlist_id: int
    owner_key: tuple[str, int]
    data: date
    start_minute: int
    end_minute: int
    blocked_end_minute: int
    covers: int
    channel: str
    room_id: int | None


def active_waitlist_offer_projections(
    db,
    *,
    data: date,
    now: datetime | None = None,
) -> tuple[WaitlistOfferProjection, ...]:
    """Materialize complete active offers as synthetic R3 capacity owners.

    Physical table claims remain the source of truth. A waitlist offer enters
    pacing/concurrent calculations only when every frozen claim is present and
    carries the same unexpired lifecycle deadline.
    """
    effective_now = _lifecycle_utc_naive(
        now if now is not None else _utcnow_naive(),
        field_name="now",
    )
    owners = db.query(models.ListaOczekujacych).filter(
        models.ListaOczekujacych.data == data,
        models.ListaOczekujacych.status == "zaoferowano",
        models.ListaOczekujacych.hold_do > effective_now,
        models.ListaOczekujacych.hold_stolik_id.isnot(None),
        models.ListaOczekujacych.hold_godz_od.isnot(None),
        models.ListaOczekujacych.hold_godz_do.isnot(None),
    ).order_by(models.ListaOczekujacych.id).all()
    if not owners:
        return ()
    owner_ids = [row.id for row in owners]
    claims_by_owner: dict[int, list[Any]] = {owner_id: [] for owner_id in owner_ids}
    for claim in db.query(models.RezerwacjaStolikClaim).filter(
        models.RezerwacjaStolikClaim.waitlist_id.in_(owner_ids),
    ).all():
        claims_by_owner.setdefault(claim.waitlist_id, []).append(claim)

    projections = []
    for owner in owners:
        if (
            int(owner.offer_version or 0) <= 0
            or not owner.offer_key_hash
            or not owner.offer_request_fingerprint
            or owner.zaoferowano_at is None
            or owner.oferta_wygasa_at is None
            or owner.oferta_wygasa_at != owner.hold_do
            or owner.offer_auto_przydzielony is None
            or owner.offer_override_authorized is None
            or owner.offer_kanal not in {"online", "wewnetrzna"}
        ):
            continue
        raw_ids = [owner.hold_stolik_id, *(owner.hold_stoliki_dodatkowe or [])]
        try:
            table_ids = tuple(int(value) for value in raw_ids)
        except (TypeError, ValueError):
            continue
        if (
            not table_ids
            or any(value <= 0 for value in table_ids)
            or len(set(table_ids)) != len(table_ids)
        ):
            continue
        try:
            start_minute, blocked_end = claim_minute_window(
                owner.hold_godz_od,
                owner.hold_godz_do,
                int(owner.hold_bufor_min or 0),
            )
            end_minute = _minute(
                owner.hold_godz_do, field_name="Godzina zakończenia",
            )
        except (ReservationError, TypeError, ValueError):
            continue
        expected = {
            (table_id, minute)
            for table_id in table_ids
            for minute in range(start_minute, blocked_end)
        }
        claims = claims_by_owner.get(owner.id, [])
        if (
            len(claims) != len(expected)
            or {(row.stolik_id, row.minute) for row in claims} != expected
            or any(
                row.data != owner.data
                or row.expires_at is None
                or row.expires_at <= effective_now
                or row.expires_at != owner.hold_do
                for row in claims
            )
        ):
            continue
        projections.append(WaitlistOfferProjection(
            waitlist_id=owner.id,
            # Tagged identity cannot collide with a real Termin primary key.
            owner_key=("waitlist", int(owner.id)),
            data=owner.data,
            start_minute=start_minute,
            end_minute=end_minute,
            blocked_end_minute=blocked_end,
            covers=max(1, int(owner.liczba_osob or 1)),
            channel=owner.offer_kanal,
            room_id=owner.offer_sala_id,
        ))
    return tuple(projections)


def release_termin_allocation(
    db, termin_id: int, *, include_capacity: bool = True,
) -> None:
    db.execute(
        delete(models.RezerwacjaStolikClaim).where(
            models.RezerwacjaStolikClaim.termin_id == termin_id
        )
    )
    db.execute(
        delete(models.RezerwacjaPacingLedger).where(
            models.RezerwacjaPacingLedger.termin_id == termin_id
        )
    )
    if include_capacity:
        db.execute(
            delete(models.RezerwacjaOblozenieLedger).where(
                models.RezerwacjaOblozenieLedger.termin_id == termin_id
            )
        )


def normalise_reservation_channel(value: str | None) -> str:
    """Ledger reguł ma dwa kanały; historyczne źródła operatora są wewnętrzne."""
    return "online" if value == "online" else "wewnetrzna"


def replace_termin_allocation(
    db,
    *,
    termin_id: int,
    data: date,
    start: time | None,
    end: time | None,
    table_ids: Iterable[int] = (),
    party_size: int = 1,
    buffer_min: int | None = None,
    enforce_pacing: bool = False,
    max_reservations: int | None = None,
    max_covers: int | None = None,
    pacing_window_min: int = 1,
    override: bool = False,
    room_id: int | None = None,
    channel: str = "wewnetrzna",
    include_capacity: bool = True,
    now: datetime | None = None,
    candidates: Sequence[Mapping[str, Any]] = (),
    alternatives: Sequence[Mapping[str, Any]] = (),
    cleanup_holds: bool = True,
) -> AvailabilityResult:
    """Atomowo zastępuje wszystkie aktywne wpisy ledgera jednego ``Termin``.

    Funkcja nie wykonuje commita. Jeżeli późniejszy zapis się nie powiedzie, rollback
    przywraca stary przydział razem z jego claimami.
    """

    effective_now = _lifecycle_utc_naive(
        now if now is not None else _utcnow_naive(),
        field_name="now",
    )
    if cleanup_holds:
        cleanup_expired_holds(db, effective_now, dates=[data])
    release_termin_allocation(
        db, termin_id, include_capacity=include_capacity,
    )
    if start is None:
        return AvailabilityResult(available=True)
    if buffer_min is None:
        # ``rez_bufor_min`` jest historycznym fizycznym fallbackiem także dla
        # zapisów wewnętrznych. Warstwa R3 przekazuje wartość bardziej szczegółową,
        # gdy ustawi ją serwis/sala/reguła.
        buffer_min = _configured_post_buffer_min(db, include_r3=cleanup_holds)
    buffer_min = max(0, int(buffer_min or 0))
    start_minute = _minute(start, field_name="Godzina rozpoczęcia")
    ids = tuple(sorted({int(value) for value in table_ids if value is not None}))
    interval: tuple[int, int] | None = _interval(start, end) if end is not None else None
    if ids:
        if end is None:
            raise ReservationError(
                400,
                "INVALID_RESERVATION_INTERVAL",
                "Przydział stołu wymaga godziny zakończenia.",
                rule="interval",
            )
        occupied = occupied_table_ids(
            db,
            data=data,
            start=start,
            end=end,
            buffer_min=buffer_min,
            exclude_termin_id=termin_id,
            now=effective_now,
            # ``cleanup_holds=False`` jest używane przez fallback odbudowujący
            # także schematy sprzed 0059; nie wolno wtedy odczytywać kolumn R3.
            include_r3_buffers=cleanup_holds,
        )
        conflicts = sorted(set(ids) & occupied)
        if conflicts:
            raise ReservationError(
                409,
                "TABLE_CONFLICT",
                "Wybrany stolik jest już zajęty w tym czasie.",
                rule="table",
                candidates=candidates,
                alternatives=alternatives,
            )

    pacing = pacing_status(
        db,
        data=data,
        start=start,
        window_min=pacing_window_min,
        party_size=party_size,
        max_reservations=max_reservations,
        max_covers=max_covers,
        exclude_termin_id=termin_id,
        now=effective_now,
    )
    if enforce_pacing and pacing["reservation_full"]:
        raise ReservationError(
            409,
            "PACING_RESERVATION_LIMIT",
            "Brak miejsc w wybranym czasie — osiągnięto limit nowych rezerwacji.",
            rule="pacing_reservations",
            candidates=candidates,
            alternatives=alternatives,
        )
    if enforce_pacing and pacing["covers_full"]:
        raise ReservationError(
            409,
            "PACING_COVERS_LIMIT",
            "Brak miejsc w wybranym czasie — osiągnięto limit nowych gości.",
            rule="pacing_covers",
            candidates=candidates,
            alternatives=alternatives,
        )

    db.add(
        models.RezerwacjaPacingLedger(
            termin_id=termin_id,
            data=data,
            start_minute=start_minute,
            covers=max(0, int(party_size or 0)),
            override=bool(override),
            created_at=_utcnow_naive(),
        )
    )
    if include_capacity and interval is not None:
        start_raw, end_raw = interval
        capacity_created_at = _utcnow_naive()
        capacity_rows = [
            {
                "termin_id": termin_id,
                "data": data,
                "minute": minute,
                "sala_id": room_id,
                "kanal": normalise_reservation_channel(channel),
                "covers": max(0, int(party_size or 0)),
                "override": bool(override),
                "created_at": capacity_created_at,
            }
            for minute in range(start_raw, end_raw)
        ]
        if capacity_rows:
            db.execute(insert(models.RezerwacjaOblozenieLedger), capacity_rows)
    if ids and interval is not None:
        start_raw, end_raw = interval
        blocked_end = min(1440, end_raw + buffer_min)
        created_at = _utcnow_naive()
        rows = [
            {
                "termin_id": termin_id,
                "waitlist_id": None,
                "stolik_id": table_id,
                "data": data,
                "minute": minute,
                "expires_at": None,
                "created_at": created_at,
            }
            for table_id in ids
            for minute in range(start_raw, blocked_end)
        ]
        if rows:
            db.execute(insert(models.RezerwacjaStolikClaim), rows)
    return AvailabilityResult(
        available=True,
        candidates=tuple(dict(item) for item in candidates),
        alternatives=tuple(dict(item) for item in alternatives),
    )


def release_waitlist_hold(db, waitlist_id: int) -> None:
    db.execute(
        delete(models.RezerwacjaStolikClaim).where(
            models.RezerwacjaStolikClaim.waitlist_id == waitlist_id
        )
    )


def replace_waitlist_hold(
    db,
    *,
    waitlist_id: int,
    table_id: int | None = None,
    table_ids: Iterable[int] = (),
    data: date,
    expires_at: datetime,
    now: datetime,
    start: time | None = None,
    end: time | None = None,
    buffer_min: int = 0,
    cleanup_holds: bool = True,
) -> None:
    """Atomowo zastępuje hold jednym stołem lub pełną kombinacją.

    Nowe holdy zajmują wyłącznie okno wizyty wraz z buforem. Brak czasu jest
    zachowany jako kompatybilny, konserwatywny hold całego dnia.
    """
    now = _lifecycle_utc_naive(now, field_name="now")
    expires_at = _lifecycle_utc_naive(expires_at, field_name="expires_at")
    if expires_at <= now:
        raise ReservationError(
            400,
            "INVALID_HOLD_EXPIRY",
            "Czas wygasniecia holdu musi byc w przyszlosci.",
            rule="table_hold",
        )
    if cleanup_holds:
        cleanup_expired_holds(db, now, dates=[data])
    release_waitlist_hold(db, waitlist_id)
    ids = tuple(sorted({
        int(value)
        for value in ((*table_ids, table_id) if table_id is not None else table_ids)
        if value is not None
    }))
    if not ids:
        raise ReservationError(
            400,
            "INVALID_HOLD_RESOURCE",
            "Hold wymaga co najmniej jednego stolika.",
            rule="table_hold",
        )
    if (start is None) != (end is None):
        raise ReservationError(
            400,
            "INVALID_RESERVATION_INTERVAL",
            "Czasowy hold wymaga początku i końca wizyty.",
            rule="interval",
        )
    if start is None:
        start_minute, blocked_end = 0, 1440
    else:
        start_minute, end_minute = _interval(start, end)
        blocked_end = min(1440, end_minute + max(0, int(buffer_min or 0)))

    claim = models.RezerwacjaStolikClaim
    conflicts = set(db.execute(
        select(claim.stolik_id).where(
            claim.stolik_id.in_(ids),
            claim.data == data,
            claim.minute >= start_minute,
            claim.minute < blocked_end,
            _active_hold_filter(now),
            or_(claim.waitlist_id.is_(None), claim.waitlist_id != waitlist_id),
        )
    ).scalars().all())
    if start is not None:
        conflicts |= set(ids) & occupied_table_ids(
            db,
            data=data,
            start=start,
            end=end,
            buffer_min=buffer_min,
            now=now,
        )
    if conflicts:
        raise ReservationError(
            409,
            "TABLE_CONFLICT",
            "Co najmniej jeden stolik zestawu jest już zajęty lub trzymany w tym czasie.",
            rule="table_hold",
        )
    owner_update = db.execute(
        update(models.ListaOczekujacych)
        .where(models.ListaOczekujacych.id == int(waitlist_id))
        .values(hold_do=expires_at)
    )
    if not int(owner_update.rowcount or 0):
        raise ReservationError(
            404,
            "WAITLIST_NOT_FOUND",
            "Nie znaleziono wpisu listy oczekujacych.",
            rule="table_hold",
        )
    # Keep the owner row and its minute claims on the same lifecycle clock. Callers
    # may fill the remaining projection fields, but must not store a local-wall expiry.
    created_at = _utcnow_naive()
    rows = [
        {
            "termin_id": None,
            "waitlist_id": waitlist_id,
            "stolik_id": int(table_id),
            "data": data,
            "minute": minute,
            "expires_at": expires_at,
            "created_at": created_at,
        }
        for table_id in ids
        for minute in range(start_minute, blocked_end)
    ]
    db.execute(insert(models.RezerwacjaStolikClaim), rows)


def translate_integrity_error(exc: IntegrityError) -> ReservationError:
    text = str(getattr(exc, "orig", exc)).lower()
    if "rezerwacje_stolik_claim_slot" in text or (
        "stolik_id" in text and "minute" in text and "unique" in text
    ):
        return ReservationError(
            409,
            "TABLE_CONFLICT",
            "Wybrany stolik został właśnie zajęty. Wybierz inną propozycję.",
            rule="table",
        )
    if "rezerwacje_idempotencja" in text:
        return ReservationError(
            409,
            "IDEMPOTENCY_IN_PROGRESS",
            "Identyczne żądanie jest już przetwarzane. Spróbuj ponownie za chwilę.",
            rule="idempotency",
        )
    return ReservationError(
        503,
        "RESERVATION_BUSY",
        "Nie udało się bezpiecznie zatwierdzić rezerwacji. Spróbuj ponownie.",
        rule="transaction",
    )
