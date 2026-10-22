"""Shared FastAPI dependencies: DB session, settings, authentication, roles."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from auth.security import decode_access_token
from core.errors import AppError, Forbidden
from core.settings import Settings, get_settings
from db.models import RevokedToken, User
from db.session import get_db

bearer = HTTPBearer(auto_error=False)


class Unauthorized(AppError):
    status_code = 401
    code = "unauthorized"


def settings_dep() -> Settings:
    return get_settings()


def _resolve_user(
    credentials: Optional[HTTPAuthorizationCredentials],
    db: Session,
    settings: Settings,
    request: Request,
) -> Optional[User]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        return None
    try:
        claims = decode_access_token(settings, credentials.credentials)
    except jwt.ExpiredSignatureError as exc:
        raise Unauthorized("Session expired; please sign in again", code="token_expired") from exc
    except jwt.PyJWTError as exc:
        raise Unauthorized("Invalid authentication token") from exc
    if db.get(RevokedToken, claims["jti"]) is not None:
        raise Unauthorized("Session has been signed out", code="token_revoked")
    try:
        user = db.get(User, int(claims["sub"]))
    except (TypeError, ValueError) as exc:
        raise Unauthorized("Invalid authentication token") from exc
    if user is None or not user.is_active:
        raise Unauthorized("Account is disabled or no longer exists")
    request.state.token_claims = claims
    return user


def optional_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
) -> Optional[User]:
    return _resolve_user(credentials, db, settings, request)


def current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
) -> User:
    user = _resolve_user(credentials, db, settings, request)
    if user is None:
        raise Unauthorized("Authentication required")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    # The role is read from the database row, never from token claims.
    if user.role != "admin":
        raise Forbidden("Administrator role required")
    return user


def token_expiry(request: Request) -> datetime:
    claims = getattr(request.state, "token_claims", {}) or {}
    return datetime.fromtimestamp(int(claims.get("exp", 0)), tz=timezone.utc)
