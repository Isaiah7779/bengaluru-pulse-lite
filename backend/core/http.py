"""Shared HTTP client construction.

Building an SSL context reads the CA bundle from disk (~1 s on slow volumes), so
one context is created lazily and reused by every client.
"""

from __future__ import annotations

import ssl
from functools import lru_cache

import httpx

# Public OSM services (OSRM demo servers, Photon) ask clients to identify themselves.
USER_AGENT = "BengaluruPulse/3.0 (academic project)"


@lru_cache(maxsize=1)
def ssl_context() -> ssl.SSLContext:
    return httpx.create_ssl_context()


def async_client(timeout: float | httpx.Timeout) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, verify=ssl_context(), headers={"User-Agent": USER_AGENT})
