from __future__ import annotations
import hmac
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from app.config import settings

_ALGORITHM = "HS256"
_bearer = HTTPBearer(auto_error=False)


def verify_api_key(api_key: str) -> bool:
    expected = settings.api_key
    if not expected:
        return False
    return hmac.compare_digest(api_key.encode(), expected.encode())


def create_access_token() -> str:
    expiry = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expiry_hours)
    return jwt.encode({"exp": expiry, "sub": "muster"}, settings.jwt_secret, algorithm=_ALGORITHM)


def require_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(_bearer),
) -> str:
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=[_ALGORITHM])
        return payload["sub"]
    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
