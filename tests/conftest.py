import os
import sys
from pathlib import Path


def _find_hermes_root() -> Path:
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
    raise RuntimeError(
        "Hermes Agent checkout not found. Set HERMES_AGENT_ROOT to the local "
        "hermes-agent repository before running tests."
    )


HERMES_ROOT = _find_hermes_root()
if str(HERMES_ROOT) not in sys.path:
    sys.path.insert(0, str(HERMES_ROOT))
