from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


TRANSITIONS = {
    "draft": {"approved"},
    "approved": {"retired"},
    "retired": set(),
}


def set_editorial_status(manifest_path: Path, status: str) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    current = manifest.get("editorial_status")
    if status not in TRANSITIONS.get(current, set()):
        raise ValueError(f"Transición editorial no permitida: {current} → {status}")
    manifest["editorial_status"] = status
    manifest["editorial_commit"] = os.environ.get("MURDOKU_COMMIT", "local")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest
