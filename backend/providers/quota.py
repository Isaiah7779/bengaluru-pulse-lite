"""Daily request budget for quota-limited providers (TomTom free tier).

Every call is recorded in `provider_calls`; the count for the current UTC day is
checked before calling. Interactive requests may use the whole budget; background
collection stops early to leave `reserve` calls for users.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, time, timezone
from typing import Optional

from sqlalchemy import func, select

from db.models import ProviderCall
from db.session import session_scope

logger = logging.getLogger(__name__)
_lock = threading.Lock()


class QuotaExceeded(Exception):
    pass


def _day_start(now: Optional[datetime] = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return datetime.combine(now.date(), time.min, tzinfo=timezone.utc)


class QuotaGuard:
    def __init__(self, provider: str, daily_budget: int, background_reserve: int = 500) -> None:
        self.provider = provider
        self.daily_budget = daily_budget
        self.background_reserve = background_reserve

    def used_today(self) -> int:
        with session_scope() as session:
            return int(
                session.scalar(
                    select(func.count(ProviderCall.id)).where(
                        ProviderCall.provider == self.provider,
                        ProviderCall.called_at >= _day_start(),
                    )
                )
                or 0
            )

    def remaining(self, background: bool = False) -> int:
        limit = self.daily_budget - (self.background_reserve if background else 0)
        return max(limit - self.used_today(), 0)

    def acquire(self, endpoint: str, purpose: str, background: bool = False) -> int:
        """Reserve one call; returns the ProviderCall id to finalise later."""

        with _lock:
            if self.remaining(background=background) <= 0:
                raise QuotaExceeded(f"{self.provider} daily budget exhausted")
            with session_scope() as session:
                call = ProviderCall(provider=self.provider, endpoint=endpoint, purpose=purpose)
                session.add(call)
                session.flush()
                return call.id

    @staticmethod
    def finish(call_id: int, status_code: Optional[int], ok: bool, error: Optional[str] = None) -> None:
        try:
            with session_scope() as session:
                call = session.get(ProviderCall, call_id)
                if call is not None:
                    call.status_code = status_code
                    call.ok = ok
                    call.error = (error or "")[:200] or None
        except Exception:  # bookkeeping must never break the request
            logger.exception("Failed to record provider call result")
