"""Password hashing, JWT access tokens and login rate limiting."""

from __future__ import annotations

import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Dict

import bcrypt
import jwt

from core.settings import Settings

# bcrypt only uses the first 72 bytes; longer passwords are rejected at validation.
MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


# Constant-time dummy check so unknown e-mails take as long as wrong passwords.
_DUMMY_HASH = hash_password(uuid.uuid4().hex)


def burn_time() -> None:
    verify_password("not-the-password", _DUMMY_HASH)


def password_problems(password: str) -> list[str]:
    problems = []
    if len(password) < 10:
        problems.append("at least 10 characters")
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        problems.append(f"at most {MAX_PASSWORD_BYTES} bytes")
    if password.lower() == password or password.upper() == password:
        problems.append("both upper- and lower-case letters")
    if not any(ch.isdigit() for ch in password):
        problems.append("a digit")
    return problems


def create_access_token(settings: Settings, user_id: int, role: str) -> tuple[str, str, datetime]:
    jti = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=settings.access_token_minutes)
    payload = {
        "sub": str(user_id),
        "role": role,  # informational only; authorization re-reads the role from the DB
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "iss": "bengaluru-pulse",
    }
    token = jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm)
    return token, jti, expires


def decode_access_token(settings: Settings, token: str) -> Dict[str, Any]:
    return jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        algorithms=[settings.jwt_algorithm],
        issuer="bengaluru-pulse",
        options={"require": ["sub", "jti", "exp", "iat"]},
    )


class LoginRateLimiter:
    """In-process sliding-window limiter keyed by e-mail and client IP."""

    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window = window_seconds
        self._attempts: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> Deque[float]:
        q = self._attempts[key]
        while q and now - q[0] > self.window:
            q.popleft()
        return q

    def blocked(self, *keys: str) -> bool:
        now = time.monotonic()
        with self._lock:
            return any(len(self._prune(k, now)) >= self.max_attempts for k in keys)

    def record_failure(self, *keys: str) -> None:
        now = time.monotonic()
        with self._lock:
            for k in keys:
                self._prune(k, now).append(now)

    def reset(self, *keys: str) -> None:
        with self._lock:
            for k in keys:
                self._attempts.pop(k, None)
