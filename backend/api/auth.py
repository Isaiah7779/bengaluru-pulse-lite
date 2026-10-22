"""Registration, login/logout and the caller's own profile."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import Unauthorized, current_user, settings_dep, token_expiry
from auth.security import (
    LoginRateLimiter,
    burn_time,
    create_access_token,
    hash_password,
    password_problems,
    verify_password,
)
from core.errors import AppError, Conflict
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

    model_config = {"from_attributes": True}


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


def _check_password(password: str) -> None:
    problems = password_problems(password)
    if problems:
        raise AppError("Password must contain " + ", ".join(problems), code="weak_password", status_code=422)


@router.post("/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)):
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
    return TokenOut(access_token=token, expires_at=expires, user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db), settings: Settings = Depends(settings_dep)):
    email = body.email.lower()
    keys = (f"email:{email}", f"ip:{_client_ip(request)}")
    if limiter.blocked(*keys):
        raise AppError("Too many failed sign-in attempts; try again later", code="rate_limited", status_code=429)
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        burn_time()
        limiter.record_failure(*keys)
        raise Unauthorized("Incorrect e-mail or password", code="invalid_credentials")
    if not verify_password(body.password, user.password_hash):
        limiter.record_failure(*keys)
        raise Unauthorized("Incorrect e-mail or password", code="invalid_credentials")
    if not user.is_active:
        raise Unauthorized("Account is disabled", code="account_disabled")
    limiter.reset(f"email:{email}")
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    token, _, expires = create_access_token(settings, user.id, user.role)
    return TokenOut(access_token=token, expires_at=expires, user=UserOut.model_validate(user))


@router.post("/logout", status_code=204)
def logout(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    claims = request.state.token_claims
    if db.get(RevokedToken, claims["jti"]) is None:
        db.add(RevokedToken(jti=claims["jti"], user_id=user.id, expires_at=token_expiry(request)))
        db.commit()
    return Response(status_code=204)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.patch("/me", response_model=UserOut)
def update_me(body: ProfileUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.display_name is not None:
        user.display_name = body.display_name.strip()
    if body.new_password is not None:
        if not body.current_password or not verify_password(body.current_password, user.password_hash):
            raise Unauthorized("Current password is incorrect", code="invalid_credentials")
        _check_password(body.new_password)
        user.password_hash = hash_password(body.new_password)
        db.add(AuditLog(actor_user_id=user.id, action="user.password_change", target=f"user:{user.id}"))
    db.commit()
    return user


class DeleteAccountIn(BaseModel):
    password: str = Field(..., max_length=200)


@router.post("/me/delete", status_code=204)
def delete_me(body: DeleteAccountIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Delete the caller's account and all personal data (favourites, trips, submissions)."""

    if not verify_password(body.password, user.password_hash):
        raise Unauthorized("Password is incorrect", code="invalid_credentials")
    if user.role == "admin":
        admins = db.scalars(select(User).where(User.role == "admin", User.is_active.is_(True))).all()
        if len(admins) <= 1:
            raise AppError("The last administrator cannot delete their account", code="last_admin", status_code=409)
    db.add(AuditLog(actor_user_id=None, action="user.self_delete", target=f"user:{user.id}"))
    db.delete(user)
    db.commit()
    return Response(status_code=204)
