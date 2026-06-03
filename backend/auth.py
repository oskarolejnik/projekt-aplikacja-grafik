"""Uwierzytelnianie: hashowanie haseł (bcrypt) + tokeny dostępu (JWT)."""

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
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


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Brak tokenu uwierzytelniającego.")
    try:
        payload = jwt.decode(creds.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token nieprawidłowy lub wygasł.")

    user = db.get(models.User, user_id)
    if user is None or not user.aktywny:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Konto nieaktywne lub nie istnieje.")
    return user


def require_admin(user: models.User = Depends(get_current_user)) -> models.User:
    if user.rola != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Wymagane uprawnienia administratora.")
    return user
