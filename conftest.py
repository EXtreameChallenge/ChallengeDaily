"""Pytest bootstrap: make the repo root importable and install B34 aliases."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from legacy_aliases import install  # noqa: E402

install()
