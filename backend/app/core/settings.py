"""Backward-compatible re-export — canonical config lives in app.config."""

from app.config import Settings, get_settings, settings

__all__ = ["Settings", "get_settings", "settings"]
