"""R6a: registered Reception/Host devices and named PIN operators."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

import models
import schemas
import settings as app_settings
import workstation_auth
from auth import get_current_user, require_admin
from database import get_db
from deps import _user_out


router = APIRouter()


def _cookie_kwargs(*, httponly: bool, max_age: int | None = None) -> dict:
    result = {
        "httponly": httponly,
        "secure": not app_settings.IS_DEV,
        "samesite": "strict",
        "path": "/api",
    }
    if max_age is not None:
        result["max_age"] = max_age
    return result


def _set_device_cookie(response: Response, station_id: str, raw_secret: str) -> None:
    response.set_cookie(
        workstation_auth.DEVICE_COOKIE,
        f"{station_id}.{raw_secret}",
        **_cookie_kwargs(httponly=True, max_age=365 * 24 * 60 * 60),
    )


def _set_operator_cookies(response: Response, raw_token: str, raw_csrf: str) -> None:
    response.set_cookie(
        workstation_auth.SESSION_COOKIE,
        raw_token,
        **_cookie_kwargs(httponly=True),
    )
    response.set_cookie(
        workstation_auth.CSRF_COOKIE,
        raw_csrf,
        **{**_cookie_kwargs(httponly=False), "path": "/"},
    )


def clear_operator_cookies(response: Response) -> None:
    for name in (workstation_auth.SESSION_COOKIE, workstation_auth.CSRF_COOKIE):
        response.delete_cookie(
            name,
            path="/api" if name == workstation_auth.SESSION_COOKIE else "/",
            secure=not app_settings.IS_DEV,
            httponly=name == workstation_auth.SESSION_COOKIE,
            samesite="strict",
        )


def clear_device_cookie(response: Response) -> None:
    response.delete_cookie(
        workstation_auth.DEVICE_COOKIE,
        path="/api",
        secure=not app_settings.IS_DEV,
        httponly=True,
        samesite="strict",
    )


def _station_out(station: models.ReservationWorkstation) -> schemas.ReservationWorkstationOut:
    return schemas.ReservationWorkstationOut.model_validate(station)


def _station_missing() -> HTTPException:
    return HTTPException(
        401,
        detail={
            "code": "WORKSTATION_NOT_REGISTERED",
            "message": "To urządzenie nie jest zarejestrowanym stanowiskiem.",
        },
    )


@router.get(
    "/api/reservation-workstations",
    response_model=list[schemas.ReservationWorkstationOut],
)
def list_workstations(
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
):
    return db.query(models.ReservationWorkstation).order_by(
        models.ReservationWorkstation.active.desc(),
        models.ReservationWorkstation.name,
    ).all()


@router.post(
    "/api/reservation-workstations",
    response_model=schemas.ReservationWorkstationOut,
    status_code=201,
)
def register_workstation(
    data: schemas.ReservationWorkstationCreate,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    now = workstation_auth.utcnow_naive()
    raw_secret = workstation_auth.new_secret("wdev_")
    station = models.ReservationWorkstation(
        id=str(uuid.uuid4()),
        name=data.name,
        secret_hash=workstation_auth.secret_hash(raw_secret),
        active=True,
        idle_timeout_seconds=data.idle_timeout_seconds,
        session_epoch=0,
        failed_attempts=0,
        created_by_user_id=admin.id,
        created_at=now,
        updated_at=now,
    )
    db.add(station)
    workstation_auth.add_audit(
        db,
        event="register",
        outcome="success",
        request=request,
        workstation=station,
        user=admin,
    )
    db.commit()
    db.refresh(station)
    clear_operator_cookies(response)
    _set_device_cookie(response, station.id, raw_secret)
    response.headers["Cache-Control"] = "private, no-store"
    return station


@router.delete("/api/reservation-workstations/{station_id}", status_code=204)
def revoke_workstation(
    station_id: str,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    station = db.get(models.ReservationWorkstation, station_id)
    if station is None:
        raise HTTPException(404, "Nie znaleziono stanowiska.")
    station.active = False
    station.updated_at = workstation_auth.utcnow_naive()
    workstation_auth.revoke_station_sessions(
        db,
        station,
        request=request,
    )
    workstation_auth.add_audit(
        db,
        event="revoke",
        outcome="success",
        request=request,
        workstation=station,
        user=admin,
        details={"reason": "admin"},
    )
    db.commit()
    parsed = workstation_auth.parse_device_cookie(
        request.cookies.get(workstation_auth.DEVICE_COOKIE)
    )
    if parsed and parsed[0] == station.id:
        clear_operator_cookies(response)
        clear_device_cookie(response)
    response.headers["Cache-Control"] = "private, no-store"


@router.put("/api/users/{user_id}/reservation-pin", status_code=204)
def set_reservation_pin(
    user_id: int,
    data: schemas.ReservationPinIn,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(404, "Nie znaleziono konta.")
    if not workstation_auth.eligible_operator(user):
        raise HTTPException(
            400,
            "PIN stanowiska można ustawić wyłącznie aktywnemu kontu z dokładnym presetem Recepcja / Host.",
        )
    now = workstation_auth.utcnow_naive()
    credential = db.get(models.ReservationOperatorCredential, user_id)
    pin_hash = workstation_auth.hash_pin(data.pin)
    if credential is None:
        credential = models.ReservationOperatorCredential(
            user_id=user.id,
            pin_hash=pin_hash,
            failed_attempts=0,
            version=1,
            updated_at=now,
        )
        db.add(credential)
    else:
        credential.pin_hash = pin_hash
        credential.failed_attempts = 0
        credential.locked_until = None
        credential.version += 1
        credential.updated_at = now
    workstation_auth.revoke_user_sessions(
        db,
        user.id,
        reason="pin_changed",
        event="authz_revoke",
    )
    workstation_auth.add_audit(
        db,
        event="pin_set",
        outcome="success",
        request=request,
        user=user,
        details={"admin_user_id": admin.id},
    )
    db.commit()


@router.delete("/api/users/{user_id}/reservation-pin", status_code=204)
def revoke_reservation_pin(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(404, "Nie znaleziono konta.")
    credential = db.get(models.ReservationOperatorCredential, user_id)
    workstation_auth.revoke_user_sessions(
        db,
        user.id,
        reason="pin_revoked",
        event="authz_revoke",
    )
    if credential is not None:
        db.delete(credential)
    workstation_auth.add_audit(
        db,
        event="pin_revoke",
        outcome="success",
        request=request,
        user=user,
        details={"admin_user_id": admin.id},
    )
    db.commit()


@router.get(
    "/api/reservation-workstations/operators",
    response_model=schemas.ReservationWorkstationGateOut,
)
def workstation_operators(request: Request, response: Response, db: Session = Depends(get_db)):
    station = workstation_auth.resolve_device(db, request)
    if station is None:
        raise _station_missing()
    last_session = db.query(models.ReservationOperatorSession).filter_by(
        workstation_id=station.id
    ).order_by(models.ReservationOperatorSession.created_at.desc()).first()
    users = db.query(models.User).join(
        models.ReservationOperatorCredential,
        models.ReservationOperatorCredential.user_id == models.User.id,
    ).order_by(models.User.id).all()
    operators = [
        schemas.ReservationWorkstationOperatorOut(
            id=user.id,
            display_name=workstation_auth.operator_display_name(user),
            last_used=bool(last_session and last_session.user_id == user.id),
        )
        for user in users
        if workstation_auth.eligible_operator(user)
    ]
    operators.sort(key=lambda item: (not item.last_used, item.display_name.casefold(), item.id))
    response.headers["Cache-Control"] = "private, no-store"
    return schemas.ReservationWorkstationGateOut(
        station=_station_out(station),
        operators=operators,
    )


@router.post(
    "/api/reservation-workstations/unlock",
    response_model=schemas.ReservationWorkstationSessionOut,
)
def unlock_workstation(
    data: schemas.ReservationWorkstationUnlockIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    if request.headers.get(workstation_auth.UNLOCK_INTENT_HEADER) != "unlock":
        raise HTTPException(403, "Brak potwierdzenia bezpiecznej akcji stanowiska.")
    station = workstation_auth.resolve_device(db, request)
    if station is None:
        workstation_auth.verify_dummy_pin(data.pin)
        raise _station_missing()

    station = db.query(models.ReservationWorkstation).filter_by(id=station.id).with_for_update().one()
    user = db.query(models.User).filter_by(id=data.operator_id).with_for_update().first()
    credential = db.get(models.ReservationOperatorCredential, data.operator_id)
    valid_operator = workstation_auth.eligible_operator(user) and credential is not None
    pin_ok = (
        workstation_auth.verify_pin(data.pin, credential.pin_hash)
        if valid_operator else False
    )
    if not valid_operator:
        workstation_auth.verify_dummy_pin(data.pin)

    now = workstation_auth.utcnow_naive()
    blocked_for = max(
        workstation_auth.remaining_lock_seconds(station.locked_until, now),
        workstation_auth.remaining_lock_seconds(
            getattr(credential, "locked_until", None), now,
        ),
    )
    if blocked_for:
        workstation_auth.add_audit(
            db,
            event="unlock",
            outcome="blocked",
            request=request,
            workstation=station,
            user=user if valid_operator else None,
            details={"lock_seconds": blocked_for},
        )
        db.commit()
        raise HTTPException(
            429,
            "Za dużo prób PIN. Spróbuj ponownie po zakończeniu blokady.",
            headers={"Retry-After": str(blocked_for)},
        )

    if not valid_operator or not pin_ok:
        delay = workstation_auth.record_unlock_failure(
            db,
            station,
            credential if valid_operator else None,
            user if valid_operator else None,
            request,
        )
        db.commit()
        if delay:
            raise HTTPException(
                429,
                "Za dużo prób PIN. Spróbuj ponownie po zakończeniu blokady.",
                headers={"Retry-After": str(delay)},
            )
        raise HTTPException(401, "Nieprawidłowy operator lub PIN.")

    session, raw_token, raw_csrf = workstation_auth.create_operator_session(
        db,
        station=station,
        user=user,
        credential=credential,
        request=request,
    )
    db.commit()
    db.refresh(session)
    _set_operator_cookies(response, raw_token, raw_csrf)
    response.headers["Cache-Control"] = "private, no-store"
    return schemas.ReservationWorkstationSessionOut(
        active=True,
        station=_station_out(station),
        user=_user_out(user),
        expires_at=session.expires_at,
        idle_timeout_seconds=station.idle_timeout_seconds,
    )


@router.get(
    "/api/me/reservation-workstation",
    response_model=schemas.ReservationWorkstationSessionOut,
)
def current_workstation_session(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    session_id = getattr(request.state, "workstation_session_id", None)
    if session_id is None:
        return schemas.ReservationWorkstationSessionOut(active=False)
    session = db.get(models.ReservationOperatorSession, session_id)
    return schemas.ReservationWorkstationSessionOut(
        active=True,
        station=_station_out(session.workstation),
        user=_user_out(user),
        expires_at=session.expires_at,
        idle_timeout_seconds=session.workstation.idle_timeout_seconds,
    )


@router.post(
    "/api/me/reservation-workstation/reauthorize",
    response_model=schemas.ReservationWorkstationReauthorizeOut,
)
def reauthorize_workstation_session(
    data: schemas.ReservationWorkstationReauthorizeIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if request.headers.get(workstation_auth.UNLOCK_INTENT_HEADER) != "reauthorize":
        raise HTTPException(403, "Brak potwierdzenia bezpiecznej akcji stanowiska.")
    session_id = getattr(request.state, "workstation_session_id", None)
    if session_id is None:
        raise HTTPException(400, "To nie jest sesja stanowiska.")
    session = db.get(models.ReservationOperatorSession, session_id)
    if session is None:
        raise HTTPException(
            423,
            detail={
                "code": "WORKSTATION_LOCKED",
                "message": "Stanowisko jest zablokowane.",
                "reason": "unknown_session",
            },
        )
    try:
        grant, expires_at = workstation_auth.issue_reauth_grant(
            db,
            session=session,
            user=user,
            pin=data.pin,
            scope=data.scope,
            request=request,
        )
    except workstation_auth.WorkstationPinRejected as exc:
        db.commit()
        detail = {
            "code": "WORKSTATION_REAUTH_FAILED",
            "message": "Nieprawidłowy PIN operatora.",
        }
        if exc.retry_after:
            raise HTTPException(
                429,
                detail=detail,
                headers={"Retry-After": str(exc.retry_after)},
            ) from exc
        raise HTTPException(400, detail=detail) from exc
    except workstation_auth.WorkstationLocked as exc:
        db.rollback()
        raise HTTPException(
            423,
            detail={
                "code": "WORKSTATION_LOCKED",
                "message": "Stanowisko jest zablokowane.",
                "reason": exc.reason,
            },
        ) from exc
    db.commit()
    response.headers["Cache-Control"] = "private, no-store"
    return schemas.ReservationWorkstationReauthorizeOut(
        grant=grant,
        scope=data.scope,
        expires_at=expires_at,
    )


@router.post("/api/me/reservation-workstation/touch", status_code=204)
def touch_workstation_session(
    request: Request,
    db: Session = Depends(get_db),
    _user: models.User = Depends(get_current_user),
):
    session_id = getattr(request.state, "workstation_session_id", None)
    if session_id is None:
        raise HTTPException(400, "To nie jest sesja stanowiska.")
    session = db.get(models.ReservationOperatorSession, session_id)
    session.last_seen_at = workstation_auth.utcnow_naive()
    db.commit()


@router.post("/api/me/reservation-workstation/lock", status_code=204)
def lock_workstation_session(
    request: Request,
    response: Response,
    data: Optional[schemas.ReservationWorkstationLockIn] = None,
    db: Session = Depends(get_db),
    _user: models.User = Depends(get_current_user),
):
    session_id = getattr(request.state, "workstation_session_id", None)
    if session_id is None:
        raise HTTPException(400, "To nie jest sesja stanowiska.")
    session = db.get(models.ReservationOperatorSession, session_id)
    workstation_auth.lock_session(
        db,
        session,
        reason=data.reason if data is not None else "manual",
        request=request,
    )
    db.commit()
    clear_operator_cookies(response)
    response.headers["Cache-Control"] = "private, no-store"


@router.post("/api/reservation-workstations/forget-device", status_code=204)
def forget_workstation_device(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    if request.headers.get(workstation_auth.UNLOCK_INTENT_HEADER) != "forget":
        raise HTTPException(403, "Brak potwierdzenia bezpiecznej akcji stanowiska.")
    station = workstation_auth.resolve_device(db, request)
    if station is None:
        raise _station_missing()
    raw_token = request.cookies.get(workstation_auth.SESSION_COOKIE) or ""
    if raw_token:
        session = db.query(models.ReservationOperatorSession).filter_by(
            token_hash=workstation_auth.secret_hash(raw_token),
            workstation_id=station.id,
        ).first()
        if session is not None and session.locked_at is None:
            workstation_auth.lock_session(db, session, reason="device_forgotten", request=request)
            db.commit()
    clear_operator_cookies(response)
    clear_device_cookie(response)
    response.headers["Cache-Control"] = "private, no-store"
