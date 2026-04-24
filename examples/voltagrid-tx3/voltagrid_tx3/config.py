from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parent
EXAMPLE_ROOT = PACKAGE_ROOT.parent
DEFAULT_CONFIG = EXAMPLE_ROOT / "config" / "tx3-core.json"


def load_site_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or DEFAULT_CONFIG
    return json.loads(config_path.read_text())
