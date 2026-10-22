"""Backward-compatible import location for application settings.

The single source of configuration is core.settings.
"""

from core.settings import BASE_DIR, Settings, get_settings, resolve_backend_path

__all__ = ["BASE_DIR", "Settings", "get_settings", "resolve_backend_path"]
