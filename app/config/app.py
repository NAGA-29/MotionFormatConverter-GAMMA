"""Backwards-compatible import for configuration helpers.

Prefer using :mod:`app.config.settings` and ``get_settings`` directly.
This module remains to avoid breaking existing imports while the
application is being modularized.
"""

from app.config.settings import AppSettings, get_settings  # noqa: F401

