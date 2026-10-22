"""Firebase ID-token verification through the official Firebase Admin SDK.

`firebase_admin.auth.verify_id_token` checks the RS256 signature against Google's
published keys, the issuer (`https://securetoken.google.com/<project>`), the audience
(project ID), expiry / issued-at, and that `sub` (the UID) is present. Only the project
ID is configured here; verification needs no service-account key.

When FIREBASE_AUTH_EMULATOR_HOST is set (local testing only; refused in production by
the settings validator) the SDK accepts the emulator's unsigned tokens instead.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Dict, Optional

import firebase_admin
from google.auth.credentials import AnonymousCredentials
from firebase_admin import auth as fb_auth

from core.settings import Settings

_APP_NAME = "bengaluru-pulse"
_lock = threading.Lock()


class FirebaseNotConfigured(RuntimeError):
    pass


class FirebaseTokenExpired(ValueError):
    pass


class FirebaseTokenInvalid(ValueError):
    pass


class FirebaseUnavailable(RuntimeError):
    """Google's signing keys could not be fetched."""


@dataclass(frozen=True)
class FirebaseIdentity:
    uid: str
    email: Optional[str]
    email_verified: bool
    name: Optional[str]
    provider: Optional[str]  # e.g. "password", "google.com"
    auth_time: Optional[int]
    claims: Dict[str, Any]


def _app(settings: Settings) -> firebase_admin.App:
    if not settings.firebase_project_id:
        raise FirebaseNotConfigured("FIREBASE_PROJECT_ID is not set")
    with _lock:
        try:
            app = firebase_admin.get_app(_APP_NAME)
        except ValueError:
            app = None
        if app is not None and app.project_id != settings.firebase_project_id:
            firebase_admin.delete_app(app)
            app = None
        if app is None:
            # No credential: token verification only uses public keys and the project ID.
            app = firebase_admin.initialize_app(
                credential=_NoCredential(), options={"projectId": settings.firebase_project_id}, name=_APP_NAME
            )
        return app


class _NoCredential(firebase_admin.credentials.Base):
    """Anonymous credential: the backend never calls authenticated Firebase APIs.

    The SDK builds its auth client eagerly, but ID-token verification only downloads
    Google's public certificates, which needs no authorization.
    """

    def get_credential(self):
        return AnonymousCredentials()


def verify_id_token(settings: Settings, token: str) -> FirebaseIdentity:
    app = _app(settings)
    try:
        claims = fb_auth.verify_id_token(token, app=app, clock_skew_seconds=5)
    except fb_auth.ExpiredIdTokenError as exc:
        raise FirebaseTokenExpired(str(exc)) from exc
    except fb_auth.CertificateFetchError as exc:
        raise FirebaseUnavailable(str(exc)) from exc
    except (fb_auth.InvalidIdTokenError, ValueError) as exc:
        raise FirebaseTokenInvalid(str(exc)) from exc
    firebase_info = claims.get("firebase") or {}
    return FirebaseIdentity(
        uid=claims["uid"],
        email=(claims.get("email") or None),
        email_verified=bool(claims.get("email_verified")),
        name=claims.get("name"),
        provider=firebase_info.get("sign_in_provider"),
        auth_time=claims.get("auth_time"),
        claims=claims,
    )
