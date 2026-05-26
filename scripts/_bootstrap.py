from __future__ import annotations

import sys
from pathlib import Path


def ensure_project_root() -> Path:
    base_dir = Path(__file__).resolve().parents[1]
    if str(base_dir) not in sys.path:
        sys.path.insert(0, str(base_dir))
    return base_dir
