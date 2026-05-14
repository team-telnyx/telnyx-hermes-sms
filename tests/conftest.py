import sys
from pathlib import Path

HERMES_ROOT = Path('/Users/ifthikar/.hermes/hermes-agent')
if str(HERMES_ROOT) not in sys.path:
    sys.path.insert(0, str(HERMES_ROOT))
