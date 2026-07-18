"""Server-side identity and revocation for the shared Reservations workstation.

The browser receives two HostOnly cookies: a long-lived device proof and a
short-lived opaque operator session. Raw secrets are never persisted; the
database contains SHA-256 hashes only. A PIN is bcrypt-hashed after a separate
HMAC pepper so a leaked database cannot be brute-forced without application
configuration.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
import secrets
import uuid

import bcrypt
from fastapi import Request
from sqlalchemy.orm import Session

import models
import uprawnienia


DEVICE_COOKIE = "lokalo_reservation_workstation_device"
SESSION_COOKIE = "lokalo_reservation_workstation_session"
CSRF_COOKIE = "lokalo_reservation_workstation_csrf"
CSRF_HEADER = "x-lokalo-workstation-csrf"
UNLOCK_INTENT_HEADER = "x-lokalo-workstation-intent"
REAUTH_HEADER = "x-lokalo-workstation-reauth"
REAUTH_SCOPE_RESERVATION_OVERRIDE = "reservation_override"
REAUTH_GRANT_SECONDS = 90

SESSION_ABSOLUTE_SECONDS = max(
    900,
    min(12 * 60 * 60, int(os.environ.get("WORKSTATION_SESSION_SECONDS", "28800"))),
)
PIN_PEPPER = os.environ.get(
    "WORKSTATION_PIN_PEPPER",
    "dev-workstation-pin-pepper-change-me",
)
PIN_SCOPE = frozenset({
    "rezerwacje.operacje",
    "rezerwacje.host",
    "rezerwacje.nadpisuj_limity",
    "rezerwacje.dane_kontaktowe",
})


class WorkstationLocked(Exception):
    def __init__(self, reason: str = "locked"):
        self.reason = reason
        super().__init__(reason)


class WorkstationCsrfRejected(Exception):
    pass


class WorkstationPinRejected(Exception):
    def __init__(self, retry_after: int = 0):
        self.retry_after = max(0, int(retry_after or 0))
        super().__init__("pin_rejected")


class WorkstationReauthRequired(Exception):
    def __init__(self, reason: str = "missing_grant"):
        self.reason = reason
        super().__init__(reason)


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def secret_hash(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def _pin_material(pin: str) -> bytes:
    return hmac.new(
        PIN_PEPPER.encode("utf-8"),
        (pin or "").encode("ascii", errors="ignore"),
        hashlib.sha256,
    ).hexdigest().encode("ascii")


def hash_pin(pin: str) -> str:
    return bcrypt.hashpw(_pin_material(pin), bcrypt.gensalt()).decode("ascii")


def verify_pin(pin: str, pin_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_pin_material(pin), pin_hash.encode("ascii"))
    except (AttributeError, TypeError, ValueError):
        return False


_DUMMY_PIN_HASH: str | None = None


def verify_dummy_pin(pin: str) -> None:
    global _DUMMY_PIN_HASH
    if _DUMMY_PIN_HASH is None:
        _DUMMY_PIN_HASH = hash_pin("000000")
    verify_pin(pin, _DUMMY_PIN_HASH)


def authorization_fingerprint(user: models.User) -> str:
    payload = {
        "active": bool(user.aktywny),
        "role": user.rola,
        "employee_id": user.pracownik_id,
        "employee_active": (
            bool(user.pracownik.aktywny) if user.pracownik is not None else None
        ),
        "permissions": uprawnienia.efektywne(user),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def eligible_operator(user: models.User | None) -> bool:
    """PIN sessions are deliberately narrower than password sessions.

    Only the exact Reception/Host preset is eligible. An administrator or a
    manager with broader privileges must use the ordinary password fallback.
    """
    if user is None or not user.aktywny or user.rola != "szef":
        return False
    if user.pracownik is not None and not user.pracownik.aktywny:
        return False
    return (
        uprawnienia.rozpoznaj_preset(user) == uprawnienia.PRESET_RECEPCJA_HOST
        and set(uprawnienia.efektywne(user)) == PIN_SCOPE
    )


def operator_display_name(user: models.User) -> str:
    if user.pracownik is not None:
        full_name = f"{user.pracownik.imie} {user.pracownik.nazwisko}".strip()
        if full_name:
            return full_name[:128]
    return user.login[:64]


def parse_device_cookie(value: str | None) -> tuple[str, str] | None:
    if not value or "." not in value:
        return None
    workstation_id, secret = value.split(".", 1)
    try:
        if str(uuid.UUID(workstation_id)) != workstation_id or len(secret) < 32:
            return None
    except (ValueError, AttributeError):
        return None
    return workstation_id, secret


def resolve_device(db: Session, request: Request) -> models.ReservationWorkstation | None:
    parsed = parse_device_cookie(request.cookies.get(DEVICE_COOKIE))
    if parsed is None:
        return None
    workstation_id, raw_secret = parsed
    station = db.get(models.ReservationWorkstation, workstation_id)
    if station is None or not station.active:
        return None
    if not hmac.compare_digest(station.secret_hash, secret_hash(raw_secret)):
        return None
    return station


def _request_ip(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    return (request.client.host or "")[:64] or None


def add_audit(
    db: Session,
    *,
    event: str,
    outcome: str,
    request: Request | None = None,
    workstation: models.ReservationWorkstation | None = None,
    session: models.ReservationOperatorSession | None = None,
    user: models.User | None = None,
    details: dict | None = None,
) -> models.ReservationWorkstationAudit:
    row = models.ReservationWorkstationAudit(
        ts=utcnow_naive(),
        workstation_id=getattr(workstation, "id", None),
        session_id=getattr(session, "id", None),
        user_id=getattr(user, "id", None),
        actor_login=getattr(user, "login", None),
        event=event,
        outcome=outcome,
        ip=_request_ip(request),
        details=details or None,
    )
    db.add(row)
    return row


def _lock_seconds(failed_attempts: int) -> int:
    if failed_attempts >= 10:
        return 60 * 60
    if failed_attempts >= 8:
        return 30 * 60
    if failed_attempts >= 5:
        return 5 * 60
    if failed_attempts >= 3:
        return 30
    return 0


def remaining_lock_seconds(locked_until: datetime | None, now: datetime | None = None) -> int:
    if locked_until is None:
        return 0
    seconds = int(((locked_until - (now or utcnow_naive())).total_seconds()) + 0.999)
    return max(0, seconds)


def record_unlock_failure(
    db: Session,
    station: models.ReservationWorkstation,
    credential: models.ReservationOperatorCredential | None,
    user: models.User | None,
    request: Request,
    *,
    event: str = "unlock",
    session: models.ReservationOperatorSession | None = None,
    audit_details: dict | None = None,
) -> int:
    now = utcnow_naive()
    station.failed_attempts = int(station.failed_attempts or 0) + 1
    station_delay = _lock_seconds(station.failed_attempts)
    if station_delay:
        station.locked_until = now + timedelta(seconds=station_delay)

    credential_delay = 0
    if credential is not None:
        credential.failed_attempts = int(credential.failed_attempts or 0) + 1
        credential_delay = _lock_seconds(credential.failed_attempts)
        if credential_delay:
            credential.locked_until = now + timedelta(seconds=credential_delay)
        credential.updated_at = now

    delay = max(
        station_delay,
        credential_delay,
        remaining_lock_seconds(station.locked_until, now),
        remaining_lock_seconds(getattr(credential, "locked_until", None), now),
    )
    details = {"attempts": station.failed_attempts, "lock_seconds": delay}
    if audit_details:
        details.update(audit_details)
    add_audit(
        db,
        event=event,
        outcome="blocked" if delay else "failure",
        request=request,
        workstation=station,
        session=session,
        user=user,
        details=details,
    )
    return delay


def new_secret(prefix: str = "") -> str:
    return f"{prefix}{secrets.token_urlsafe(32)}"


def create_operator_session(
    db: Session,
    *,
    station: models.ReservationWorkstation,
    user: models.User,
    credential: models.ReservationOperatorCredential,
    request: Request,
) -> tuple[models.ReservationOperatorSession, str, str]:
    now = utcnow_naive()
    event = "switch" if station.session_epoch else "unlock"
    station.session_epoch = int(station.session_epoch or 0) + 1
    station.failed_attempts = 0
    station.locked_until = None
    station.updated_at = now
    credential.failed_attempts = 0
    credential.locked_until = None
    credential.updated_at = now

    db.query(models.ReservationOperatorSession).filter(
        models.ReservationOperatorSession.workstation_id == station.id,
        models.ReservationOperatorSession.locked_at.is_(None),
    ).update(
        {
            models.ReservationOperatorSession.locked_at: now,
            models.ReservationOperatorSession.lock_reason: "switch",
            models.ReservationOperatorSession.reauth_grant_hash: None,
            models.ReservationOperatorSession.reauth_scope: None,
            models.ReservationOperatorSession.reauth_expires_at: None,
        },
        synchronize_session=False,
    )

    raw_token = new_secret("wst_")
    raw_csrf = new_secret("wcsrf_")
    session = models.ReservationOperatorSession(
        id=str(uuid.uuid4()),
        token_hash=secret_hash(raw_token),
        csrf_hash=secret_hash(raw_csrf),
        workstation_id=station.id,
        user_id=user.id,
        actor_login=user.login,
        station_epoch=station.session_epoch,
        credential_version=credential.version,
        authorization_fingerprint=authorization_fingerprint(user),
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(seconds=SESSION_ABSOLUTE_SECONDS),
    )
    db.add(session)
    db.flush()
    add_audit(
        db,
        event=event,
        outcome="success",
        request=request,
        workstation=station,
        session=session,
        user=user,
    )
    return session, raw_token, raw_csrf


def issue_reauth_grant(
    db: Session,
    *,
    session: models.ReservationOperatorSession,
    user: models.User,
    pin: str,
    scope: str,
    request: Request,
) -> tuple[str, datetime]:
    """Verify the active operator's own PIN and replace any previous grant.

    The caller commits both the attempt audit/lockout state and successful
    grant issuance. Only the SHA-256 digest of the opaque grant is persisted.
    """
    if scope != REAUTH_SCOPE_RESERVATION_OVERRIDE:
        raise ValueError("unsupported reauthorization scope")

    station = db.query(models.ReservationWorkstation).filter_by(
        id=session.workstation_id,
    ).with_for_update().first()
    credential = db.query(models.ReservationOperatorCredential).filter_by(
        user_id=user.id,
    ).with_for_update().first()
    locked_session = db.query(models.ReservationOperatorSession).filter_by(
        id=session.id,
    ).with_for_update().first()
    if (
        station is None
        or locked_session is None
        or locked_session.locked_at is not None
        or locked_session.user_id != user.id
        or locked_session.workstation_id != station.id
        or not station.active
        or station.session_epoch != locked_session.station_epoch
        or credential is None
        or credential.version != locked_session.credential_version
        or not eligible_operator(user)
        or authorization_fingerprint(user) != locked_session.authorization_fingerprint
    ):
        raise WorkstationLocked("authorization_change")

    now = utcnow_naive()
    blocked_for = max(
        remaining_lock_seconds(station.locked_until, now),
        remaining_lock_seconds(credential.locked_until, now),
    )
    if blocked_for:
        add_audit(
            db,
            event="reauth",
            outcome="blocked",
            request=request,
            workstation=station,
            session=locked_session,
            user=user,
            details={"scope": scope, "lock_seconds": blocked_for},
        )
        raise WorkstationPinRejected(blocked_for)

    if not verify_pin(pin, credential.pin_hash):
        delay = record_unlock_failure(
            db,
            station,
            credential,
            user,
            request,
            event="reauth",
            session=locked_session,
            audit_details={"scope": scope},
        )
        raise WorkstationPinRejected(delay)

    station.failed_attempts = 0
    station.locked_until = None
    station.updated_at = now
    credential.failed_attempts = 0
    credential.locked_until = None
    credential.updated_at = now
    raw_grant = new_secret("wreauth_")
    expires_at = now + timedelta(seconds=REAUTH_GRANT_SECONDS)
    locked_session.reauth_grant_hash = secret_hash(raw_grant)
    locked_session.reauth_scope = scope
    locked_session.reauth_expires_at = expires_at
    add_audit(
        db,
        event="reauth",
        outcome="success",
        request=request,
        workstation=station,
        session=locked_session,
        user=user,
        details={"scope": scope, "ttl_seconds": REAUTH_GRANT_SECONDS},
    )
    return raw_grant, expires_at


def consume_reauth_grant(
    db: Session,
    *,
    request: Request,
    user: models.User,
    scope: str = REAUTH_SCOPE_RESERVATION_OVERRIDE,
) -> None:
    """Atomically consume a one-use grant for a workstation PIN session.

    Ordinary bearer/password requests intentionally bypass this additional
    proof. The mutation that required the proof commits the consumption in the
    same transaction, so a failed business write cannot leave a partial write.
    """
    if getattr(request.state, "auth_strength", None) != "workstation_pin":
        return
    session_id = getattr(request.state, "workstation_session_id", None)
    if not session_id:
        raise WorkstationReauthRequired("missing_session")

    session = db.query(models.ReservationOperatorSession).filter_by(
        id=session_id,
    ).with_for_update().first()
    raw_grant = request.headers.get(REAUTH_HEADER) or ""
    now = utcnow_naive()
    reason = None
    if session is None or session.locked_at is not None or session.user_id != user.id:
        reason = "invalid_session"
    elif not raw_grant.startswith("wreauth_") or len(raw_grant) < 40:
        reason = "missing_grant"
    elif session.reauth_scope != scope:
        reason = "scope_mismatch"
    elif session.reauth_expires_at is None or session.reauth_expires_at <= now:
        reason = "expired_grant"
    elif not session.reauth_grant_hash or not hmac.compare_digest(
        session.reauth_grant_hash,
        secret_hash(raw_grant),
    ):
        reason = "invalid_grant"
    if reason is not None:
        raise WorkstationReauthRequired(reason)

    session.reauth_grant_hash = None
    session.reauth_scope = None
    session.reauth_expires_at = None
    add_audit(
        db,
        event="reauth_use",
        outcome="success",
        request=request,
        workstation=session.workstation,
        session=session,
        user=user,
        details={"scope": scope},
    )


def _lock_session(
    db: Session,
    session: models.ReservationOperatorSession,
    *,
    reason: str,
    request: Request | None = None,
    event: str | None = None,
) -> None:
    if session.locked_at is not None:
        return
    now = utcnow_naive()
    station = session.workstation
    session.locked_at = now
    session.lock_reason = reason[:32]
    session.reauth_grant_hash = None
    session.reauth_scope = None
    session.reauth_expires_at = None
    if station is not None and station.session_epoch == session.station_epoch:
        station.session_epoch += 1
        station.updated_at = now
    user = session.user
    add_audit(
        db,
        event=event or ("timeout" if reason in {"idle", "expired"} else "lock"),
        outcome="success",
        request=request,
        workstation=station,
        session=session,
        user=user,
        details={"reason": reason},
    )


def lock_session(
    db: Session,
    session: models.ReservationOperatorSession,
    *,
    reason: str,
    request: Request | None = None,
) -> None:
    _lock_session(db, session, reason=reason, request=request)


def revoke_user_sessions(
    db: Session,
    user_id: int,
    *,
    reason: str = "authorization_change",
    event: str = "authz_revoke",
) -> int:
    sessions = db.query(models.ReservationOperatorSession).filter(
        models.ReservationOperatorSession.user_id == user_id,
        models.ReservationOperatorSession.locked_at.is_(None),
    ).all()
    for session in sessions:
        _lock_session(db, session, reason=reason, event=event)
    return len(sessions)


def revoke_station_sessions(
    db: Session,
    station: models.ReservationWorkstation,
    *,
    reason: str = "station_revoked",
    request: Request | None = None,
) -> int:
    sessions = db.query(models.ReservationOperatorSession).filter(
        models.ReservationOperatorSession.workstation_id == station.id,
        models.ReservationOperatorSession.locked_at.is_(None),
    ).all()
    for session in sessions:
        _lock_session(
            db,
            session,
            reason=reason,
            request=request,
            event="revoke",
        )
    return len(sessions)


def _valid_csrf(request: Request, session: models.ReservationOperatorSession) -> bool:
    header = request.headers.get(CSRF_HEADER) or ""
    cookie = request.cookies.get(CSRF_COOKIE) or ""
    return bool(
        header
        and cookie
        and hmac.compare_digest(header, cookie)
        and hmac.compare_digest(session.csrf_hash, secret_hash(header))
    )


def resolve_operator_session(
    db: Session,
    request: Request,
    *,
    require_csrf: bool = False,
    touch: bool = False,
) -> models.ReservationOperatorSession:
    raw_token = request.cookies.get(SESSION_COOKIE) or ""
    if not raw_token.startswith("wst_") or len(raw_token) < 40:
        raise WorkstationLocked("missing_session")
    session = db.query(models.ReservationOperatorSession).filter_by(
        token_hash=secret_hash(raw_token)
    ).first()
    if session is None:
        raise WorkstationLocked("unknown_session")
    station = session.workstation
    user = session.user
    now = utcnow_naive()
    device = resolve_device(db, request)

    invalid_reason = None
    if session.locked_at is not None:
        invalid_reason = session.lock_reason or "locked"
    elif station is None or not station.active:
        invalid_reason = "station_revoked"
    elif device is None or device.id != getattr(station, "id", None):
        invalid_reason = "device_mismatch"
    elif station.session_epoch != session.station_epoch:
        invalid_reason = "session_replaced"
    elif user is None or not eligible_operator(user):
        invalid_reason = "authorization_change"
    elif session.expires_at <= now:
        invalid_reason = "expired"
    elif session.last_seen_at + timedelta(seconds=station.idle_timeout_seconds) <= now:
        invalid_reason = "idle"
    elif user.reservation_pin_credential is None:
        invalid_reason = "pin_revoked"
    elif user.reservation_pin_credential.version != session.credential_version:
        invalid_reason = "pin_changed"
    elif authorization_fingerprint(user) != session.authorization_fingerprint:
        invalid_reason = "authorization_change"

    if invalid_reason is not None:
        if session.locked_at is None:
            _lock_session(db, session, reason=invalid_reason, request=request)
            db.commit()
        raise WorkstationLocked(invalid_reason)

    if require_csrf and not _valid_csrf(request, session):
        raise WorkstationCsrfRejected()
    if touch:
        session.last_seen_at = now
        db.commit()
        db.refresh(session)
    return session


def workstation_request(request: Request) -> bool:
    return bool(request.cookies.get(SESSION_COOKIE) or request.cookies.get(DEVICE_COOKIE))
