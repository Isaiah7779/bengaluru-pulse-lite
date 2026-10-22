"""Shared FastAPI dependencies: DB session, settings, authentication, roles.

Two bearer-token kinds are accepted:

* Firebase ID tokens (RS256, verified by the Firebase Admin SDK) — the primary sign-in.
  The account row is found by Firebase UID only; an e-mail address is never enough to
  attach a Firebase identity to an existing account (see POST /v1/auth/link).
* Legacy Bengaluru Pulse access tokens (HS256, issued by /v1/auth/login) while
  LEGACY_AUTH_ENABLED is true.

Roles always come from the PostgreSQL `users` row, never from a token.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from auth import firebase
from auth.security import decode_access_token
from core.errors import AppError, Forbidden
from core.settings import Settings, get_settings
from db.models import AuditLog, RevokedToken, User
from db.session import get_db

bearer = HTTPBearer(auto_error=False)


class Unauthorized(AppError):
    status_code = 401
    code = "unauthorized"


def settings_dep() -> Settings:
    return get_settings()


def _is_legacy_token(token: str) -> bool:
    try:
        return jwt.get_unverified_header(token).get("alg") == "HS256"
    except jwt.PyJWTError:
        return False


def firebase_identity(settings: Settings, token: str) -> firebase.FirebaseIdentity:
    """Verify a Firebase ID token and insist on a verified e-mail address."""

    try:
        ident = firebase.verify_id_token(settings, token)
    except firebase.FirebaseNotConfigured as exc:
        raise Unauthorized("Firebase sign-in is not configured on this server", code="firebase_not_configured") from exc
    except firebase.FirebaseTokenExpired as exc:
        raise Unauthorized("Session expired; please sign in again", code="token_expired") from exc
    except firebase.FirebaseUnavailable as exc:
        raise AppError("Sign-in verification is temporarily unavailable", code="auth_unavailable", status_code=503) from exc
    except firebase.FirebaseTokenInvalid as exc:
        raise Unauthorized("Invalid authentication token") from exc
    if not ident.email or not ident.email_verified:
        raise Forbidden("Verify your e-mail address to continue", code="email_not_verified")
    return ident


def _default_name(ident: firebase.FirebaseIdentity) -> str:
    name = (ident.name or "").strip() or (ident.email or "").split("@")[0] or "Pulse user"
    return name[:80]


def _user_for_firebase(ident: firebase.FirebaseIdentity, db: Session) -> User:
    user = db.scalar(select(User).where(User.firebase_uid == ident.uid))
    if user is not None:
        return user
    email = ident.email.lower()
    if db.scalar(select(User.id).where(func.lower(User.email) == email)) is not None:
        # An older account already uses this address. Matching on e-mail alone would let
        # whoever controls a Firebase identity take that account (and its role) over, so
        # the owner must link it explicitly by proving the old password.
        raise AppError(
            "An existing Bengaluru Pulse account uses this e-mail. Link it with its old password to continue.",
            code="account_link_required",
            status_code=409,
        )
    user = User(email=email, password_hash=None, firebase_uid=ident.uid, display_name=_default_name(ident), role="user")
    db.add(user)
    db.flush()
    db.add(AuditLog(actor_user_id=user.id, action="user.register_firebase", target=f"user:{user.id}", details={"provider": ident.provider}))
    db.commit()
    return user


def _resolve_user(
    credentials: Optional[HTTPAuthorizationCredentials],
    db: Session,
    settings: Settings,
    request: Request,
) -> Optional[User]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        return None
    token = credentials.credentials
    if _is_legacy_token(token):
        if not settings.legacy_auth_enabled:
            raise Unauthorized("This sign-in method has been retired; sign in again", code="legacy_auth_disabled")
        try:
            claims = decode_access_token(settings, token)
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
        request.state.token_kind = "legacy"
    else:
        ident = firebase_identity(settings, token)
        user = _user_for_firebase(ident, db)
        claims = ident.claims
        request.state.token_kind = "firebase"
        request.state.firebase = ident
    if user is None or not user.is_active:
        raise Unauthorized("Account is disabled or no longer exists", code="account_disabled")
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


def app_access(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
) -> Optional[User]:
    """Router-level guard for application endpoints (API_AUTH_REQUIRED)."""

    user = _resolve_user(credentials, db, settings, request)
    if user is None and settings.api_auth_required:
        raise Unauthorized("Sign in to use Bengaluru Pulse")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    # The role is read from the database row, never from token claims.
    if user.role != "admin":
        raise Forbidden("Administrator role required")
    return user


def token_expiry(request: Request) -> datetime:
    claims = getattr(request.state, "token_claims", {}) or {}
    return datetime.fromtimestamp(int(claims.get("exp", 0)), tz=timezone.utc)
