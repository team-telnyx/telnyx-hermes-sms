"""Telnyx SMS platform plugin entry point for Hermes Agent."""


def register(ctx):
    try:
        from .adapter import register as _register
    except ImportError:  # pragma: no cover - supports direct file/plugin loading
        from adapter import register as _register

    return _register(ctx)


__all__ = ["register"]
