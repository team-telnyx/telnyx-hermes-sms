"""Telnyx SMS platform plugin entry point for Hermes Agent."""

try:
    from .adapter import register
except ImportError:  # pragma: no cover - supports direct file/plugin loading
    from adapter import register

__all__ = ["register"]
