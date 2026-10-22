"""Registration, login/logout, Firebase account linking and the caller's own profile.

Firebase Authentication is the primary sign-in; the built-in e-mail/password endpoints
remain while LEGACY_AUTH_ENABLED / LEGACY_REGISTRATION_ENABLED are true.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import Unauthorized, bearer, current_user, firebase_identity, settings_dep, token_expiry
from auth.security import (
    LoginRateLimiter,
    burn_time,
    create_access_token,
    hash_password,
    password_problems,
    verify_password,
)
from core.errors import AppError, Conflict, Forbidden, NotFound
from core.settings import Settings, get_settings
from db.models import AuditLog, RevokedToken, User
from db.session import get_db

router = APIRouter(prefix="/v1/auth", tags=["auth"])

_settings = get_settings()
limiter = LoginRateLimiter(_settings.login_max_attempts, _settings.login_window_seconds)


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=200)
    display_name: str = Field(..., min_length=1, max_length=80)

    # NOTE: there is deliberately no `role` field. Extra fields are ignored, so a
    # client cannot self-assign "admin" at registration.

    @field_validator("display_name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("display name required")
        return v


class LoginIn(BaseModel):
    # Not EmailStr: sign-in must work for any stored address (e.g. bootstrap admins
    # on reserved domains); format is validated at registration.
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., max_length=200)


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str
    role: str
    created_at: datetime
    last_login_at: Optional[datetime] = None
    firebase_linked: bool = False
    has_password: bool = False

    model_config = {"from_attributes": True}

    @classmethod
    def of(cls, user: User) -> "UserOut":
        out = cls.model_validate(user)
        out.firebase_linked = user.firebase_uid is not None
        out.has_password = user.password_hash is not None
        return out


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserOut


class ProfileUpdate(BaseModel):
    display_name: Optional[str] = Field(None, min_length=1, max_length=80)
    current_password: Optional[str] = Field(None, max_length=200)
    new_password: Optional[str] = Field(None, max_length=200)
    # No role / is_active / email fields: users cannot change their privileges.


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _require_legacy(settings: Settings, registration: bool = False) -> None:
    if not settings.legacy_auth_enabled or (registration and not settings.legacy_registration_enabled):
        raise NotFound("This sign-in method is no longer available; use the sign-in screen", code="legacy_auth_disabled")


def _check_password(password: str) -> None:
    problems = password_problems(password)
    if problems:
        raise AppError("Password must contain " + ", ".join(problems), code="weak_password", status_code=422)


@router.post("/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)):
    _require_legacy(settings, registration=True)
    email = body.email.lower()
    _check_password(body.password)
    if db.scalar(select(User.id).where(User.email == email)):
        raise Conflict("An account with this e-mail already exists", code="email_taken")
    user = User(email=email, password_hash=hash_password(body.password), display_name=body.display_name, role="user")
    db.add(user)
    db.flush()
    db.add(AuditLog(actor_user_id=user.id, action="user.register", target=f"user:{user.id}"))
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    token, _, expires = create_access_token(settings, user.id, user.role)
    return TokenOut(access_token=token, expires_at=expires, user=UserOut.of(user))


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)):
    _require_legacy(settings)
    email = body.email.lower()
    keys = (f"email:{email}", f"ip:{_client_ip(request)}")
    if limiter.blocked(*keys):
        raise AppError("Too many failed sign-in attempts; try again later", code="rate_limited", status_code=429)
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        burn_time()
        limiter.record_failure(*keys)
        raise Unauthorized("Incorrect e-mail or password", code="invalid_credentials")
    if user.password_hash is None or not verify_password(body.password, user.password_hash):
        limiter.record_failure(*keys)
        raise Unauthorized("Incorrect e-mail or password", code="invalid_credentials")
    if not user.is_active:
        raise Unauthorized("Account is disabled", code="account_disabled")
    limiter.reset(f"email:{email}")
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    token, _, expires = create_access_token(settings, user.id, user.role)
    return TokenOut(access_token=token, expires_at=expires, user=UserOut.of(user))


class LinkIn(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., max_length=200)


@router.post("/link", response_model=UserOut)
def link_existing_account(
    body: LinkIn,
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    db: Session = Depends(get_db),
    settings: Settings = Depends(settings_dep),
):
    """Attach the caller's verified Firebase identity to an existing pre-Firebase account.

    Requires both a verified Firebase ID token and the old account's password, so an
    e-mail address alone can never transfer an account (or its role). The account keeps
    its ID, role, trips and other records.
    """

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise Unauthorized("Authentication required")
    ident = firebase_identity(settings, credentials.credentials)
    if db.scalar(select(User.id).where(User.firebase_uid == ident.uid)) is not None:
        raise Conflict("This sign-in is already linked to an account", code="already_linked")
    email = body.email.strip().lower()
    keys = (f"email:{email}", f"ip:{_client_ip(request)}")
    if limiter.blocked(*keys):
        raise AppError("Too many failed attempts; try again later", code="rate_limited", status_code=429)
    user = db.scalar(select(User).where(User.email == email))
    if user is None or user.password_hash is None or not verify_password(body.password, user.password_hash):
        if user is None:
            burn_time()
        limiter.record_failure(*keys)
        raise Unauthorized("Incorrect e-mail or password", code="invalid_credentials")
    if not user.is_active:
        raise Unauthorized("Account is disabled", code="account_disabled")
    if user.firebase_uid is not None:
        raise Conflict("That account is already linked to another sign-in", code="already_linked")
    limiter.reset(f"email:{email}")
    user.firebase_uid = ident.uid
    new_email = ident.email.lower()
    if new_email != user.email and db.scalar(select(User.id).where(User.email == new_email)) is None:
        user.email = new_email  # adopt the verified Firebase address
    user.last_login_at = datetime.now(timezone.utc)
    db.add(AuditLog(actor_user_id=user.id, action="user.link_firebase", target=f"user:{user.id}", details={"provider": ident.provider}))
    db.commit()
    return UserOut.of(user)


@router.post("/logout", status_code=204)
def logout(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if request.state.token_kind == "firebase":
        # Firebase sessions end on the client (signOut); ID tokens expire within an hour.
        return Response(status_code=204)
    claims = request.state.token_claims
    if db.get(RevokedToken, claims["jti"]) is None:
        db.add(RevokedToken(jti=claims["jti"], user_id=user.id, expires_at=token_expiry(request)))
        db.commit()
    return Response(status_code=204)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return UserOut.of(user)


@router.patch("/me", response_model=UserOut)
def update_me(body: ProfileUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.display_name is not None:
        user.display_name = body.display_name.strip()
    if body.new_password is not None:
        if user.password_hash is None:
            raise AppError("Change this password from the sign-in screen", code="password_managed_by_firebase", status_code=400)
        if not body.current_password or not verify_password(body.current_password, user.password_hash):
            raise Unauthorized("Current password is incorrect", code="invalid_credentials")
        _check_password(body.new_password)
        user.password_hash = hash_password(body.new_password)
        db.add(AuditLog(actor_user_id=user.id, action="user.password_change", target=f"user:{user.id}"))
    db.commit()
    return UserOut.of(user)


RECENT_SIGN_IN_SECONDS = 300


class DeleteAccountIn(BaseModel):
    password: Optional[str] = Field(None, max_length=200)
    confirm: bool = False


@router.post("/me/delete", status_code=204)
def delete_me(body: DeleteAccountIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Delete the caller's PostgreSQL account and its records (trips, favourites, submissions).

    Explicit only: legacy accounts confirm with their password; Firebase sessions must
    send `confirm: true` with a sign-in from the last five minutes. Firestore documents and
    the Firebase user are removed by the client afterwards (see the account screen).
    """

    if request.state.token_kind == "firebase":
        if not body.confirm:
            raise AppError("Confirm the deletion", code="confirmation_required", status_code=400)
        if time.time() - int(request.state.firebase.auth_time or 0) > RECENT_SIGN_IN_SECONDS:
            raise Forbidden("Sign in again, then delete within five minutes", code="recent_sign_in_required")
    elif user.password_hash is None or not body.password or not verify_password(body.password, user.password_hash):
        raise Unauthorized("Password is incorrect", code="invalid_credentials")
    if user.role == "admin":
        admins = db.scalars(select(User).where(User.role == "admin", User.is_active.is_(True))).all()
        if len(admins) <= 1:
            raise AppError("The last administrator cannot delete their account", code="last_admin", status_code=409)
    db.add(AuditLog(actor_user_id=None, action="user.self_delete", target=f"user:{user.id}"))
    db.delete(user)
    db.commit()
    return Response(status_code=204)
