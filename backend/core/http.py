"""Shared HTTP client construction.

Building an SSL context reads the CA bundle from disk (~1 s on slow volumes), so
one context is created lazily and reused by every client.
"""

from __future__ import annotations

import ssl
from functools import lru_cache

import httpx


@lru_cache(maxsize=1)
def ssl_context() -> ssl.SSLContext:
    return httpx.create_ssl_context()


def async_client(timeout: float | httpx.Timeout) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, verify=ssl_context())
