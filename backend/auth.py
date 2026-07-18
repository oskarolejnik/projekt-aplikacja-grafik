"""Uwierzytelnianie: hashowanie haseł (bcrypt) + tokeny dostępu (JWT)."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

import models
from database import get_db

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
ALGORITHM = "HS256"
TOKEN_TTL_MINUTES = int(os.environ.get("TOKEN_TTL_MINUTES", "720"))  # 12 h

bearer_scheme = HTTPBearer(auto_error=False)


def _pw_bytes(haslo: str) -> bytes:
    # bcrypt obsługuje maks. 72 bajty — przycinamy bezpiecznie na poziomie bajtów.
    return haslo.encode("utf-8")[:72]


def hash_password(haslo: str) -> str:
    return bcrypt.hashpw(_pw_bytes(haslo), bcrypt.gensalt()).decode("utf-8")


def verify_password(haslo: str, haslo_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_pw_bytes(haslo), haslo_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(user: models.User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "rola": user.rola,
        "pracownik_id": user.pracownik_id,
        "iat": now,
        "exp": now + timedelta(minutes=TOKEN_TTL_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _jwt_user(db: Session, raw_token: str) -> models.User:
    try:
        payload = jwt.decode(raw_token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Token nieprawidłowy lub wygasł.",
        )
    user = db.get(models.User, user_id)
    if user is None or not user.aktywny:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Konto nieaktywne lub nie istnieje.",
        )
    return user


def resolve_request_user(
    request: Request,
    db: Session,
    creds: HTTPAuthorizationCredentials | None = None,
    *,
    require_workstation_csrf: bool = False,
    touch_workstation: bool = False,
) -> models.User:
    """Resolve an ordinary password JWT or a server-side workstation session."""
    if creds is not None:
        user = _jwt_user(db, creds.credentials)
        request.state.auth_strength = "password"
        request.state.workstation_session_id = None
        return user

    import workstation_auth

    if workstation_auth.workstation_request(request):
        try:
            session = workstation_auth.resolve_operator_session(
                db,
                request,
                require_csrf=require_workstation_csrf,
                touch=touch_workstation,
            )
        except workstation_auth.WorkstationLocked as exc:
            raise HTTPException(
                status_code=423,
                detail={
                    "code": "WORKSTATION_LOCKED",
                    "message": "Stanowisko jest zablokowane.",
                    "reason": exc.reason,
                },
            ) from exc
        except workstation_auth.WorkstationCsrfRejected as exc:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "WORKSTATION_CSRF_REJECTED",
                    "message": "Sesja stanowiska wymaga ponowienia bezpiecznej akcji.",
                },
            ) from exc
        request.state.auth_strength = "workstation_pin"
        request.state.workstation_session_id = session.id
        request.state.workstation_id = session.workstation_id
        return session.user

    raise HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Brak tokenu uwierzytelniającego.",
    )


def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    return resolve_request_user(request, db, creds)


def require_admin(user: models.User = Depends(get_current_user)) -> models.User:
    if user.rola != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Wymagane uprawnienia administratora.")
    return user
