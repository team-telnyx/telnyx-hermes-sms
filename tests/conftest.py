import os
import sys
from pathlib import Path


def _find_hermes_root() -> Path | None:
    """Locate a Hermes Agent checkout for tests that import gateway modules."""
    candidates = []
    env_root = os.getenv("HERMES_AGENT_ROOT")
    if env_root:
        candidates.append(Path(env_root).expanduser())
    candidates.extend([
        Path.cwd().parent / "hermes-agent",
        Path.home() / ".hermes" / "hermes-agent",
        Path("/Users/ifthikar/.hermes/hermes-agent"),
    ])
    for candidate in candidates:
        if (candidate / "gateway" / "platforms" / "base.py").exists():
            return candidate
    return None


HERMES_ROOT = _find_hermes_root()
if HERMES_ROOT is not None and str(HERMES_ROOT) not in sys.path:
    sys.path.insert(0, str(HERMES_ROOT))


def _ensure_telnyx_sms_registered():
    """Pre-register telnyx_sms so Platform('telnyx_sms') works in all tests."""
    try:
        from gateway.platform_registry import PlatformEntry, platform_registry
    except (ImportError, ModuleNotFoundError):
        return

    if not platform_registry.is_registered("telnyx_sms"):
        platform_registry.register(
            PlatformEntry(
                name="telnyx_sms",
                label="Telnyx SMS",
                adapter_factory=lambda cfg: None,
                check_fn=lambda: True,
            )
        )


_ensure_telnyx_sms_registered()
